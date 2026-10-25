"""Exercise actual local RAM scopes against the production transfer client."""
import ctypes as C
from pathlib import Path
import subprocess
import unittest

from test_transfer_lease_client import ClientTests, SHIM, Token

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/timewarp-state-work-lease'
CALLBACK = C.CFUNCTYPE(C.c_int)


class StateWorkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OUT.mkdir(parents=True, exist_ok=True)
        source = SHIM.replace('#include "src/transfer_lease.cpp"',
            '#include "src/transfer_lease.cpp"\n#include "src/state_work_lease.cpp"')
        source = source.replace('if (clearWire) TestWire = {};',
            'StateWorkLease::sPhase = StateWorkLease::IDLE; StateWorkLease::sToken = {};\n'
            '    if (clearWire) TestWire = {};')
        source += r'''
extern "C" {
__declspec(dllexport) int withWork(int (*body)()) {
    StateWorkLease::Guard guard;
    return guard ? body() : -1;
}
__declspec(dllexport) int workQuiet() { return StateWorkLease::quiet(); }
__declspec(dllexport) unsigned int workEpoch() { return StateWorkLease::epoch(); }
__declspec(dllexport) int withBorrowedWork(int (*body)()) {
    StateWorkLease::Guard guard(false);
    return guard ? body() : -1;
}
__declspec(dllexport) void workUpdate() { StateWorkLease::update(); }
}
'''
        path = OUT / 'work.cpp'
        path.write_text(source)
        cls.libs = []
        compiler = ROOT / 'toolchain/clang++.exe'
        for emulator in (0, 1):
            dll = OUT / f'work-{emulator}.dll'
            command = [str(compiler), '--target=x86_64-pc-windows-msvc', '-std=c++17', '-O2',
                '-ffreestanding', '-fno-builtin', '-fno-exceptions', '-fno-rtti', '-nostdlib',
                '-Wall', '-Wextra', '-Werror', '-I', str(ROOT), '-I', str(ROOT / 'include'),
                f'-DIS_EMULATOR={emulator}', '-shared', '-fuse-ld=lld', '-Wl,/noentry',
                str(path), '-o', str(dll)]
            compiled = subprocess.run(command, capture_output=True, text=True)
            if compiled.returncode:
                raise RuntimeError(compiled.stdout + compiled.stderr)
            api = C.CDLL(str(dll))
            cls.addClassCleanup(lambda handle=api._handle: C.windll.kernel32.FreeLibrary(C.c_void_p(handle)))
            api.wire.restype = C.c_void_p
            api.withWork.argtypes = [CALLBACK]
            api.withBorrowedWork.argtypes = [CALLBACK]
            api.claim.argtypes = [C.c_uint, C.POINTER(Token)]
            api.release.argtypes = [C.POINTER(Token)]
            api.activate.argtypes = [C.c_int] * 3
            cls.libs.append(api)
            compiled = subprocess.run([str(compiler), '--target=powerpc-gecko-ibm-kuribo-eabi',
                '-std=c++17', '-Oz', '-ffreestanding', '-fno-builtin', '-fno-exceptions',
                '-fno-rtti', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'include'),
                f'-DIS_EMULATOR={emulator}', '-c', str(ROOT / 'src/state_work_lease.cpp'),
                '-o', str(OUT / f'work-{emulator}.o')], capture_output=True, text=True)
            if compiled.returncode:
                raise RuntimeError(compiled.stdout + compiled.stderr)

    setUp = ClientTests.setUp
    tearDown = ClientTests.tearDown
    response = ClientTests.response
    publish_response = ClientTests.publish_response
    start = ClientTests.start

    def test_legacy_scope_blocks_reentry_and_activation_without_wire_writes(self):
        self.response()
        observed = []
        @CALLBACK
        def body():
            observed.append(self.api.workQuiet())
            observed.append(self.api.activate(1, 1, self.api.workQuiet()))
            observed.append(self.api.withWork(CALLBACK(lambda: 23)))
            return 7
        self.assertEqual(self.api.withWork(body), 7)
        self.assertEqual(observed, [0, 0, -1])
        self.assertTrue(self.api.workQuiet())
        self.assertEqual(self.api.flushes(), 0)

    def test_shared_scope_excludes_remote_owners_and_releases_on_failure_return(self):
        self.start()
        observed = []
        @CALLBACK
        def body():
            observed.append(self.api.workQuiet())
            for owner in (1, 2, 3):
                observed.append(self.api.claim(owner, C.byref(Token())))
            return 0
        self.assertEqual(self.api.withWork(body), 0)
        self.assertEqual(observed, [0, 0, 0, 0])
        self.assertTrue(self.api.workQuiet())
        token = Token()
        self.assertTrue(self.api.claim(1, C.byref(token)))
        self.assertTrue(self.api.release(C.byref(token)))

    def test_remote_owner_refuses_before_local_work_runs(self):
        self.start()
        token = Token()
        self.assertTrue(self.api.claim(2, C.byref(token)))
        ran = []
        self.assertEqual(self.api.withWork(CALLBACK(lambda: ran.append(1) or 1)), -1)
        self.assertEqual(ran, [])
        self.assertTrue(self.api.workQuiet())
        self.assertTrue(self.api.release(C.byref(token)))

    def test_sd_restore_scope_does_not_release_its_existing_state_owner(self):
        self.start()
        token = Token()
        self.assertTrue(self.api.claim(2, C.byref(token)))
        self.assertEqual(self.api.withBorrowedWork(CALLBACK(lambda: 17)), 17)
        self.assertEqual(self.api.withWork(CALLBACK(lambda: 99)), -1)
        self.assertFalse(self.api.claim(1, C.byref(Token())))
        self.assertTrue(self.api.release(C.byref(token)))
        self.assertEqual(self.api.withWork(CALLBACK(lambda: 23)), 23)

    def test_epoch_is_available_only_inside_shared_ram_scope(self):
        self.response()
        self.assertEqual(self.api.workEpoch(), 0)
        self.assertEqual(self.api.withWork(CALLBACK(lambda: self.api.workEpoch())), 0)
        self.start()
        self.assertEqual(self.api.workEpoch(), 0)
        self.assertEqual(self.api.withWork(CALLBACK(lambda: self.api.workEpoch())),
                         self.wire.response.epoch)
        self.assertEqual(self.api.workEpoch(), 0)

    def test_withdrawn_receipt_retains_release_token_until_update(self):
        self.start()
        @CALLBACK
        def body():
            self.wire.responsePublication.generation = 0
            return 1
        self.assertEqual(self.api.withWork(body), 1)
        self.assertFalse(self.api.workQuiet())
        for _ in range(3):
            self.api.workUpdate()
            self.assertFalse(self.api.workQuiet())
            self.assertEqual(self.api.withWork(CALLBACK(lambda: 1)), -1)
        self.publish_response()
        self.api.workUpdate()
        self.assertTrue(self.api.workQuiet())
        self.assertEqual(self.api.withWork(CALLBACK(lambda: 8)), 8)

    def test_retired_epoch_never_falls_back_to_legacy_or_loses_pending_owner(self):
        self.start()
        @CALLBACK
        def body():
            self.response(8)
            return 1
        self.assertEqual(self.api.withWork(body), 1)
        self.assertEqual(self.api.mode(), 6)
        self.assertFalse(self.api.workQuiet())
        self.response(epoch=2)
        self.api.workUpdate()
        self.assertFalse(self.api.workQuiet())
        self.assertEqual(self.api.withWork(CALLBACK(lambda: 1)), -1)

    def test_emulator_scope_never_reads_arm_memory(self):
        emulator = self.libs[1]
        emulator.reset(1)
        self.assertEqual(emulator.withWork(CALLBACK(lambda: 5)), 5)
        self.assertTrue(emulator.workQuiet())
        self.assertEqual(emulator.flushes() + emulator.invalidates() + emulator.errors(), 0)


if __name__ == '__main__':
    unittest.main()
