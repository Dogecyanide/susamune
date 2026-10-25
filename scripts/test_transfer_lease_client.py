"""Compile the production PPC adapter; exercise ownership and reinjection in memory."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import subprocess
import unittest

from test_timewarp_transfer_lease import Arm, Control, Line, Token as WireToken, clone

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/timewarp-lease-client"


class Token(C.Structure):
    _fields_ = [(name, C.c_uint) for name in ("epoch", "ticket", "owner")]


SHIM = r'''
#include "susamune/transfer_layout.h"
alignas(32) TWLeaseControl TestWire;
#define SUSAMUNE_TRANSFER_CLIENT_WIRE (&TestWire)
#include "src/transfer_lease.cpp"
static unsigned int InterruptDepth, Errors, Flushes, Invalidates, Tear, TailInvalidates;
static unsigned int Trace[1024], TraceCount;
extern "C" {
void *memset(void *p, int c, size_t n) { unsigned char *q=(unsigned char *)p; while(n--) *q++=(unsigned char)c; return p; }
void *memcpy(void *p, const void *s, size_t n) { unsigned char *q=(unsigned char *)p; const unsigned char *r=(const unsigned char *)s; while(n--) *q++=*r++; return p; }
bool OSDisableInterrupts() { bool old = !InterruptDepth; ++InterruptDepth; return old; }
void OSRestoreInterrupts(bool old) { if (!InterruptDepth || old != (InterruptDepth == 1)) ++Errors; --InterruptDepth; }
void DCFlushRange(void *p, size_t n) {
    if (!InterruptDepth || ((size_t)p & 31) || n != 32) ++Errors;
    ++Flushes;
    if (TraceCount + 3 <= 1024) {
        Trace[TraceCount++] = (unsigned int)((unsigned char *)p - (unsigned char *)&TestWire);
        Trace[TraceCount++] = TestWire.requestPublication.generation;
        Trace[TraceCount++] = TestWire.requestPublication.issued;
    }
}
void DCInvalidateRange(void *p, size_t n) {
    if (p == (void *)SUSAMUNE_TRANSFER_POOL_THIRD_PPC_BASE ||
        p == (void *)SUSAMUNE_TRANSFER_POOL_FOURTH_PPC_BASE) {
        const size_t expected = p == (void *)SUSAMUNE_TRANSFER_POOL_THIRD_PPC_BASE
            ? SUSAMUNE_TRANSFER_POOL_THIRD_SIZE : SUSAMUNE_TRANSFER_POOL_FOURTH_SIZE;
        if (!InterruptDepth || n != expected) ++Errors;
        return;
    }
    if (p == (void *)SUSAMUNE_TRANSFER_POOL_FIFTH_PPC_BASE) {
        if (!InterruptDepth || n != SUSAMUNE_TRANSFER_POOL_FIFTH_SIZE) ++Errors;
        ++TailInvalidates;
        return;
    }
    if (!InterruptDepth || ((size_t)p & 31) || n != 32) ++Errors;
    ++Invalidates;
    if (Tear && p == &TestWire.response) { ++TestWire.responsePublication.generation; --Tear; }
}
__declspec(dllexport) void reset(int clearWire) {
    using namespace TransferLease;
    sPpc = {}; sControl = {}; sPublisher = {}; sMode = UNINITIALIZED; sOwner = 0; sShared = false;
    if (clearWire) TestWire = {};
    InterruptDepth = Errors = Flushes = Invalidates = TraceCount = Tear = TailInvalidates = 0;
}
__declspec(dllexport) void *wire() { return &TestWire; }
__declspec(dllexport) unsigned int init() { return TransferLease::init(); }
__declspec(dllexport) unsigned int mode() { return TransferLease::mode(); }
__declspec(dllexport) int legacy() { return TransferLease::legacyAllowed(); }
__declspec(dllexport) int shared() { return TransferLease::sharedMap(); }
__declspec(dllexport) int activate(int a,int b,int c) { return TransferLease::activate(a,b,c); }
__declspec(dllexport) void poll() { TransferLease::poll(); }
__declspec(dllexport) int claim(unsigned int owner, TransferLease::Token *t) { return TransferLease::claim((TransferLease::Owner)owner,*t); }
__declspec(dllexport) int owns(TransferLease::Token *t) { return TransferLease::owns(*t); }
__declspec(dllexport) int submit(TransferLease::Token *t,unsigned int seq,unsigned int session,unsigned int cmd) { return TransferLease::submit(*t,seq,session,cmd); }
__declspec(dllexport) int cancel(TransferLease::Token *t) { return TransferLease::cancel(*t); }
__declspec(dllexport) int take(TransferLease::Token *t,TransferLease::Borrow *b) { return TransferLease::take(*t,*b); }
__declspec(dllexport) int consumed(TransferLease::Token *t,TransferLease::Borrow *b) { return TransferLease::consumed(*t,*b); }
__declspec(dllexport) int release(TransferLease::Token *t) { return TransferLease::release(*t); }
__declspec(dllexport) unsigned int errors() { return Errors + InterruptDepth; }
__declspec(dllexport) unsigned int flushes() { return Flushes; }
__declspec(dllexport) unsigned int invalidates() { return Invalidates; }
__declspec(dllexport) unsigned int tailInvalidates() { return TailInvalidates; }
__declspec(dllexport) unsigned int traceSize() { return TraceCount; }
__declspec(dllexport) void *trace() { return Trace; }
__declspec(dllexport) void tear() { Tear = 1; }
__declspec(dllexport) void ticket(unsigned int n) { TransferLease::sPpc.nextTicket = n; }
__declspec(dllexport) void pub(unsigned int n) { TransferLease::sPublisher.issued = n; }
}
'''


class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OUT.mkdir(parents=True, exist_ok=True)
        source = OUT / "client.cpp"
        source.write_text(SHIM)
        cls.libs = []
        compiler = ROOT / "toolchain/clang++.exe"
        for emulator in (0, 1):
            dll = OUT / f"client-{emulator}.dll"
            command = [str(compiler), "--target=x86_64-pc-windows-msvc", "-std=c++17", "-O2",
                       "-ffreestanding", "-fno-builtin", "-fno-exceptions", "-fno-rtti", "-nostdlib",
                       "-Wall", "-Wextra", "-Werror", "-I", str(ROOT), "-I", str(ROOT / "include"),
                       f"-DIS_EMULATOR={emulator}", "-shared", "-fuse-ld=lld", "-Wl,/noentry",
                       str(source), "-o", str(dll)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            api = C.CDLL(str(dll))
            cls.addClassCleanup(lambda api=api: C.windll.kernel32.FreeLibrary(C.c_void_p(api._handle)))
            for name in ("wire", "trace"):
                getattr(api, name).restype = C.c_void_p
            pointer = C.POINTER(Token)
            signatures = {"reset": [C.c_int], "activate": [C.c_int] * 3,
                          "claim": [C.c_uint, pointer], "owns": [pointer], "cancel": [pointer],
                          "submit": [pointer] + [C.c_uint] * 3, "take": [pointer, pointer],
                          "consumed": [pointer, pointer], "release": [pointer],
                          "ticket": [C.c_uint], "pub": [C.c_uint]}
            for name, args in signatures.items():
                getattr(api, name).argtypes = args
            cls.libs.append(api)
        for emulator in (0, 1):
            subprocess.run([str(compiler), "--target=powerpc-gecko-ibm-kuribo-eabi", "-std=c++17",
                "-Oz", "-ffreestanding", "-fno-builtin", "-fno-exceptions", "-fno-rtti", "-Wall", "-Wextra",
                "-Werror", "-I", str(ROOT / "include"), f"-DIS_EMULATOR={emulator}", "-c",
                str(ROOT / "src/transfer_lease.cpp"), "-o", str(OUT / f"client-{emulator}.o")],
                check=True, capture_output=True, text=True)

    def setUp(self):
        self.api = self.libs[0]
        self.api.reset(1)
        self.wire = Control.from_address(self.api.wire())

    def tearDown(self):
        self.assertEqual(self.api.errors(), 0)

    def response(self, phase=1, epoch=1, command=0x10002):
        self.wire.response = Line(0x534C5331, epoch, 0, 0, phase, 0, 0, command)
        self.publish_response()

    def publish_response(self):
        p = self.wire.responsePublication
        p.issued += 1
        p.generation = p.issued

    def start(self):
        self.response()
        self.assertEqual(self.api.init(), 3)
        self.assertTrue(self.api.legacy())
        self.assertTrue(self.api.activate(1, 1, 1))
        self.assertEqual(self.api.mode(), 4)
        self.assertFalse(self.api.legacy())
        self.response(3)
        self.api.poll()
        self.assertEqual(self.api.mode(), 5)
        self.assertTrue(self.api.shared())

    def claim(self, owner=2):
        token = Token()
        self.assertTrue(self.api.claim(owner, C.byref(token)))
        return token

    def done(self):
        self.wire.response = clone(self.wire.request)
        self.wire.response.phase = 7
        self.publish_response()
        self.api.poll()

    def test_unavailable_emulator_never_accesses_wire_and_legacy_does_not_publish(self):
        self.assertEqual(self.api.init(), 2)
        self.assertTrue(self.api.legacy())
        self.assertFalse(self.api.activate(1, 1, 1))
        self.assertEqual(self.api.flushes(), 0)
        emulator = self.libs[1]
        emulator.reset(1)
        self.assertEqual(emulator.init(), 1)
        self.assertFalse(emulator.legacy())
        self.assertFalse(emulator.activate(1, 1, 1))
        self.assertFalse(emulator.claim(3, C.byref(Token())))
        self.assertEqual(emulator.invalidates() + emulator.flushes() + emulator.errors(), 0)

    def test_activation_requires_quiet_and_persists_across_missing_receipt(self):
        self.response()
        self.assertEqual(self.api.init(), 3)
        before = bytes(self.wire)
        for quiet in ((0, 1, 1), (1, 0, 1), (1, 1, 0)):
            self.assertFalse(self.api.activate(*quiet))
            self.assertEqual(bytes(self.wire), before)
        self.assertTrue(self.api.activate(1, 1, 1))
        self.assertEqual(self.api.tailInvalidates(), 0)
        self.wire.responsePublication.generation = 0
        for _ in range(5):
            self.api.poll()
            self.assertEqual(self.api.mode(), 4)
            self.assertFalse(self.api.legacy())
        self.response(3)
        self.api.poll()
        self.assertEqual(self.api.mode(), 5)
        self.assertEqual(self.api.tailInvalidates(), 1)
        for _ in range(5):
            self.api.poll()
        self.assertEqual(self.api.tailInvalidates(), 1)

    def test_older_shared_layout_cannot_donate_the_live_di_tail(self):
        self.response(command=0x10001)
        self.assertEqual(self.api.init(), 6)
        self.assertFalse(self.api.activate(1, 1, 1))
        self.assertFalse(self.api.shared())
        self.assertEqual(self.api.tailInvalidates(), 0)

    def test_local_codec_excludes_every_other_owner_and_cannot_submit(self):
        self.start()
        token = self.claim(3)
        for owner in (1, 2, 3):
            self.assertFalse(self.api.claim(owner, C.byref(Token())))
        self.assertFalse(self.api.submit(C.byref(token), 1, 2, 1))
        wrong = clone(token); wrong.owner = 2
        self.assertFalse(self.api.release(C.byref(wrong)))
        self.assertTrue(self.api.release(C.byref(token)))
        self.assertFalse(self.api.owns(C.byref(token)))
        self.assertFalse(self.api.release(C.byref(token)))
        newer = self.claim(1)
        self.assertGreater(newer.ticket, token.ticket)

    def test_terminal_and_explicit_consumption_required_before_reuse(self):
        self.start(); token = self.claim()
        self.assertTrue(self.api.submit(C.byref(token), 7, 13, 2))
        self.assertFalse(self.api.release(C.byref(token)))
        self.assertFalse(self.api.take(C.byref(token), C.byref(Token())))
        self.done()
        self.assertFalse(self.api.release(C.byref(token)))
        borrow = Token()
        self.assertTrue(self.api.take(C.byref(token), C.byref(borrow)))
        self.assertFalse(self.api.release(C.byref(token)))
        self.assertFalse(self.api.claim(1, C.byref(Token())))
        bad = clone(borrow); bad.ticket += 1
        self.assertFalse(self.api.consumed(C.byref(token), C.byref(bad)))
        self.assertTrue(self.api.consumed(C.byref(token), C.byref(borrow)))
        self.assertFalse(self.api.consumed(C.byref(token), C.byref(borrow)))
        self.assertTrue(self.api.release(C.byref(token)))

    def test_cancel_keeps_same_key_and_drains_even_late_terminal(self):
        self.start(); token = self.claim()
        self.assertTrue(self.api.submit(C.byref(token), 9, 27, 7))
        original = clone(self.wire.request)
        self.assertTrue(self.api.cancel(C.byref(token)))
        original.phase = 6
        self.assertEqual(bytes(original), bytes(self.wire.request))
        for _ in range(10):
            self.api.poll()
            self.assertTrue(self.api.owns(C.byref(token)))
            self.assertFalse(self.api.release(C.byref(token)))
        self.done(); borrow = Token()
        self.assertTrue(self.api.take(C.byref(token), C.byref(borrow)))
        self.assertTrue(self.api.consumed(C.byref(token), C.byref(borrow)))
        self.assertTrue(self.api.release(C.byref(token)))

    def test_mutation_and_ghost_cancel_refused_and_ghost_session_must_be_zero(self):
        for owner, command in ((2, 5), (2, 6), (2, 10), (1, 2)):
            self.setUp(); self.start(); token = self.claim(owner)
            if owner == 1:
                self.assertFalse(self.api.submit(C.byref(token), 8, 1, command))
            self.assertTrue(self.api.submit(C.byref(token), 8, 0, command))
            before = bytes(self.wire.request)
            self.assertFalse(self.api.cancel(C.byref(token)))
            self.assertEqual(bytes(self.wire.request), before)

    def test_stale_done_and_torn_publication_never_admitted(self):
        self.start(); token = self.claim()
        self.assertTrue(self.api.submit(C.byref(token), 9, 3, 2))
        self.wire.response = clone(self.wire.request)
        self.wire.response.phase = 7
        self.wire.response.seq -= 1
        self.publish_response(); self.api.poll()
        self.assertFalse(self.api.take(C.byref(token), C.byref(Token())))
        self.wire.response.seq += 1; self.publish_response()
        self.api.tear(); self.api.poll()
        self.assertFalse(self.api.take(C.byref(token), C.byref(Token())))
        self.publish_response(); self.api.poll()
        self.assertTrue(self.api.take(C.byref(token), C.byref(Token())))

    def test_reinjection_resumes_withdrawn_publication_highwater(self):
        self.response(epoch=4)
        self.wire.requestPublication.issued = 87
        self.wire.requestPublication.generation = 0
        self.api.reset(0)
        self.assertEqual(self.api.init(), 3)
        self.assertTrue(self.api.activate(1, 1, 1))
        self.assertEqual(self.wire.requestPublication.generation, 88)
        self.assertEqual(self.wire.requestPublication.issued, 88)
        self.assertEqual(self.wire.request.epoch, 4)
        trace = list((C.c_uint * self.api.traceSize()).from_address(self.api.trace()))
        self.assertEqual(trace, [64, 0, 88, 0, 0, 88, 64, 88, 88])

    def test_reinjection_cannot_adopt_ready_done_or_corrupt_highwater(self):
        for phase in (3, 7, 8):
            self.setUp(); self.response(phase)
            self.assertEqual(self.api.init(), 6)
            self.assertFalse(self.api.legacy())
            self.assertFalse(self.api.activate(1, 1, 1))
            self.assertEqual(self.api.flushes(), 0)
        self.setUp(); self.response()
        self.wire.requestPublication.generation = 3
        self.wire.requestPublication.issued = 4
        self.assertEqual(self.api.init(), 6)

    def test_epoch_retirement_blocks_reuse_without_reverting_shared_map(self):
        self.start(); token = self.claim()
        self.response(8)
        self.api.poll()
        self.assertEqual(self.api.mode(), 6)
        self.assertTrue(self.api.shared())
        self.assertFalse(self.api.legacy())
        self.assertFalse(self.api.release(C.byref(token)))
        self.assertFalse(self.api.claim(1, C.byref(Token())))
        self.response(epoch=2)
        self.assertEqual(self.api.init(), 6)
        self.api.reset(0)
        self.assertEqual(self.api.init(), 3)

    def test_ticket_and_publication_exhaustion_never_wrap(self):
        self.start(); self.api.ticket(0xffffffff)
        before = bytes(self.wire)
        self.assertFalse(self.api.claim(2, C.byref(Token())))
        self.assertEqual(bytes(self.wire), before)
        self.setUp(); self.start(); token = self.claim()
        self.api.pub(0xffffffff)
        before = bytes(self.wire)
        self.assertFalse(self.api.submit(C.byref(token), 1, 0, 2))
        self.assertEqual(bytes(self.wire), before)
        self.assertEqual(self.api.mode(), 6)
        self.assertFalse(self.api.legacy())

    def test_activation_rechecks_abi_and_exact_capability_shape(self):
        for field, value in (("command", 2), ("seq", 3), ("session", 4), ("owner", 2), ("phase", 3)):
            self.setUp(); self.response()
            self.assertEqual(self.api.init(), 3)
            setattr(self.wire.response, field, value)
            self.publish_response()
            self.assertFalse(self.api.activate(1, 1, 1))
            self.assertEqual(self.api.mode(), 6)
            self.assertFalse(self.api.legacy())
            self.assertEqual(self.api.flushes(), 0)

    def test_multiple_windows_keep_lease_but_reject_prior_borrow(self):
        self.start(); token = self.claim()
        previous = None
        for sequence in (4, 5, 6):
            self.assertTrue(self.api.submit(C.byref(token), sequence, 8, 7))
            self.done(); borrow = Token()
            self.assertTrue(self.api.take(C.byref(token), C.byref(borrow)))
            self.assertTrue(self.api.owns(C.byref(token)))
            if previous:
                self.assertFalse(self.api.consumed(C.byref(token), C.byref(previous)))
            self.assertTrue(self.api.consumed(C.byref(token), C.byref(borrow)))
            previous = borrow
        self.assertTrue(self.api.release(C.byref(token)))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ClientTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    receipt = {"tests": result.testsRun, "passed": result.wasSuccessful(),
        "scope": "Production adapter with simulated aligned wire/cache calls; actual PPC compilation, no Wii runtime proof",
        "sources": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [ROOT / "src/transfer_lease.cpp", ROOT / "include/susamune/transfer_lease.hxx",
             ROOT / "include/susamune/transfer_lease.h", ROOT / "include/susamune/transfer_publication.h"]}}
    (OUT / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    raise SystemExit(not result.wasSuccessful())
