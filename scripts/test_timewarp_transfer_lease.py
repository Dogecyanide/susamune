"""Executable ownership proof with independent PPC/ARM cache-line snapshots."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GHOST, STATE = 1, 2


class Line(C.Structure):
    _fields_ = [(n, C.c_uint) for n in ("magic", "epoch", "ticket", "owner", "phase", "seq", "session", "command")]


class Publication(C.Structure):
    _fields_ = [("generation", C.c_uint), ("issued", C.c_uint), ("reserved", C.c_uint * 6)]


class Control(C.Structure):
    _fields_ = [("request", Line), ("response", Line),
                ("requestPublication", Publication), ("responsePublication", Publication)]


class Token(C.Structure):
    _fields_ = [("epoch", C.c_uint), ("ticket", C.c_uint)]


class Ppc(C.Structure):
    _fields_ = [("key", Line)] + [(n, C.c_uint) for n in ("nextTicket", "leaseTicket", "quiescentTicket", "phase")]


class Arm(C.Structure):
    _fields_ = [("key", Line)] + [(n, C.c_uint) for n in ("epoch", "lastTicket", "busy", "resetMask", "enabled")]


def clone(value):
    return type(value).from_buffer_copy(value)


class World:
    def __init__(self, api):
        self.api, self.p, self.a = api, Ppc(), Arm()
        self.memory, self.ppc, self.arm = Control(), Control(), Control()
        self.payload = bytearray([0xA7] * 256)
        self.reset()
        self.attach()

    def flush_ppc(self):
        self.memory.request = self.ppc.request

    def flush_arm(self):
        self.memory.response = self.arm.response

    def read_ppc(self):
        self.ppc.response = self.memory.response

    def read_arm(self):
        self.arm.request = self.memory.request

    def reset(self):
        self.api.TWLeaseResetBegin(C.byref(self.a), C.byref(self.arm))
        assert self.api.TWLeaseRetired(C.byref(self.a), GHOST, 1)
        assert self.api.TWLeaseRetired(C.byref(self.a), STATE, 1)
        assert self.api.TWLeaseResetPublish(C.byref(self.a), C.byref(self.arm))
        self.flush_arm()

    def attach(self):
        self.p = Ppc()
        self.read_ppc()
        assert self.api.TWLeaseAttach(C.byref(self.p), C.byref(self.ppc))
        self.flush_ppc(); self.read_arm()
        assert self.api.TWLeaseActivate(C.byref(self.a), C.byref(self.arm), 1, 1)
        self.flush_arm(); self.read_ppc()
        assert self.api.TWLeaseAttached(C.byref(self.p), C.byref(self.ppc))

    def claim(self, owner):
        token = Token()
        ok = self.api.TWLeaseClaim(C.byref(self.p), C.byref(self.ppc), owner, C.byref(token))
        if ok:
            self.flush_ppc()
        return token if ok else None

    def submit(self, token, seq=1, session=9, command=2):
        ok = self.api.TWLeaseSubmit(C.byref(self.p), C.byref(self.ppc), token, seq, session, command)
        if ok:
            self.flush_ppc()
        return ok

    def start(self, owner=None, seq=None, session=None, command=None):
        self.read_arm()
        q = self.arm.request
        return self.api.TWLeaseStart(C.byref(self.a), C.byref(self.arm),
            q.owner if owner is None else owner, q.seq if seq is None else seq,
            q.session if session is None else session, q.command if command is None else command)

    def finish(self, ghost=1, state=1, receipt=1, token=None):
        if token is None:
            token = Token(self.a.key.epoch, self.a.key.ticket)
        ok = self.api.TWLeaseFinish(C.byref(self.a), C.byref(self.arm), token, ghost, state, receipt)
        if ok:
            self.flush_arm()
        return ok

    def poll(self):
        self.read_ppc()
        return self.api.TWLeasePoll(C.byref(self.p), C.byref(self.ppc))

    def take(self):
        token = Token()
        return token if self.api.TWLeaseTake(C.byref(self.p), C.byref(token)) else None

    def consumed(self, token):
        ok = self.api.TWLeaseConsumed(C.byref(self.p), C.byref(self.ppc), token)
        if ok:
            self.flush_ppc()
        return ok

    def release(self, token):
        ok = self.api.TWLeaseRelease(C.byref(self.p), C.byref(self.ppc), token)
        if ok:
            self.flush_ppc()
        return ok


class TransferLeaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="transfer-lease-")
        cls.addClassCleanup(cls.temp.cleanup)
        path = Path(cls.temp.name)
        source = path / "lease.c"
        source.write_text('#define TW_LEASE_INLINE __declspec(dllexport)\n#include "timewarp/transfer_publication.h"\n')
        compiler = str(ROOT / "toolchain/clang.exe")
        common = ["-O2", "-nostdlib", "-ffreestanding", "-fno-builtin", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "scripts")]
        dll = path / "lease.dll"
        subprocess.run([compiler, "--target=x86_64-pc-windows-msvc", *common, "-shared", "-fuse-ld=lld",
                        "-Wl,/noentry", str(source), "-o", str(dll)], check=True)
        # Actual ARM's language mode and the PPC frontend both compile the same transitions.
        source.write_text('#define TW_LEASE_INLINE\n#include "timewarp/transfer_publication.h"\n')
        for target in ("powerpc-gecko-ibm-kuribo-eabi", "armeb-none-eabi"):
            subprocess.run([compiler, "--target=" + target, "-std=gnu89", *common, "-c", str(source),
                            "-o", str(path / (target + ".o"))], check=True)
        cls.api = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.api._handle)))
        signatures = {
            "ResetBegin": [C.POINTER(Arm), C.POINTER(Control)],
            "Retired": [C.POINTER(Arm), C.c_uint, C.c_int],
            "ResetPublish": [C.POINTER(Arm), C.POINTER(Control)],
            "Attach": [C.POINTER(Ppc), C.POINTER(Control)],
            "Activate": [C.POINTER(Arm), C.POINTER(Control), C.c_int, C.c_int],
            "Attached": [C.POINTER(Ppc), C.POINTER(Control)],
            "Claim": [C.POINTER(Ppc), C.POINTER(Control), C.c_uint, C.POINTER(Token)],
            "Submit": [C.POINTER(Ppc), C.POINTER(Control), Token, C.c_uint, C.c_uint, C.c_uint],
            "Cancel": [C.POINTER(Ppc), C.POINTER(Control), Token, C.c_int],
            "Start": [C.POINTER(Arm), C.POINTER(Control), C.c_uint, C.c_uint, C.c_uint, C.c_uint],
            "CancelRequested": [C.POINTER(Arm), C.POINTER(Control)],
            "Finish": [C.POINTER(Arm), C.POINTER(Control), Token, C.c_int, C.c_int, C.c_int],
            "Poll": [C.POINTER(Ppc), C.POINTER(Control)],
            "Take": [C.POINTER(Ppc), C.POINTER(Token)],
            "Consumed": [C.POINTER(Ppc), C.POINTER(Control), Token],
            "Release": [C.POINTER(Ppc), C.POINTER(Control), Token],
        }
        for name, arguments in signatures.items():
            getattr(cls.api, "TWLease" + name).argtypes = arguments

    def test_budget_and_immediate_local_ram_save_repack(self):
        self.assertEqual((C.sizeof(Control), C.sizeof(Ppc), C.sizeof(Arm), C.sizeof(Token)), (128, 48, 52, 8))
        w = World(self.api)
        for _ in range(8):
            token = w.claim(STATE)
            self.assertIsNotNone(token)
            before = clone(w.memory.response)
            w.payload[:] = bytes([0x38]) * 256
            self.assertIsNone(w.claim(GHOST))
            self.assertFalse(w.start(GHOST, 900, 0, 4))
            self.assertEqual(bytes(w.memory.response), bytes(before))
            self.assertTrue(w.release(token))
        self.assertEqual(w.a.lastTicket, 0)

    def test_ghost_preparation_ack_then_local_import_consumption(self):
        w = World(self.api)
        token = w.claim(GHOST)
        w.payload[:] = bytes(range(256))
        self.assertIsNone(w.claim(STATE))
        self.assertTrue(w.submit(token, command=2))
        self.assertTrue(w.start())
        self.assertFalse(w.release(token))
        self.assertTrue(w.finish())
        self.assertIsNone(w.claim(STATE))
        self.assertTrue(w.poll())
        self.assertFalse(w.release(token))
        borrow = w.take()
        self.assertIsNotNone(borrow)
        self.assertFalse(w.release(token))
        self.assertEqual(w.payload, bytes(range(256)))
        self.assertTrue(w.consumed(borrow))
        self.assertTrue(w.release(token))
        self.assertIsNotNone(w.claim(STATE))

    def test_state_result_keeps_lease_across_afterdraw_card_wait_and_tas_copy(self):
        w = World(self.api)
        token = w.claim(STATE)
        self.assertTrue(w.submit(token))
        self.assertTrue(w.start()); self.assertTrue(w.finish()); self.assertTrue(w.poll())
        borrow = w.take()
        for _ in range(120):
            self.assertIsNone(w.claim(GHOST))
            self.assertFalse(w.start(GHOST, 1, 0, 4))
            self.assertFalse(w.release(token))
        self.assertTrue(w.consumed(borrow))
        # A streaming decoder consumes one window, then submits another under the same owner.
        self.assertTrue(w.submit(token, seq=2))
        self.assertTrue(w.start()); self.assertTrue(w.finish()); self.assertTrue(w.poll())
        next_borrow = w.take()
        self.assertFalse(w.consumed(borrow))
        self.assertTrue(w.consumed(next_borrow)); self.assertTrue(w.release(token))

    def test_cancellation_and_timeouts_never_release_a_worker(self):
        for start_first in (False, True):
            w = World(self.api)
            token = w.claim(STATE)
            self.assertTrue(w.submit(token))
            if start_first:
                self.assertTrue(w.start())
            for _ in range(120):
                self.assertFalse(w.poll())
            self.assertFalse(w.release(token))
            self.assertTrue(self.api.TWLeaseCancel(C.byref(w.p), C.byref(w.ppc), token, 1))
            w.flush_ppc(); w.read_arm()
            if not start_first:
                self.assertTrue(w.start())
            self.assertTrue(self.api.TWLeaseCancelRequested(C.byref(w.a), C.byref(w.arm)))
            self.assertFalse(w.finish(state=0))
            self.assertFalse(w.finish(ghost=0))
            self.assertFalse(w.finish(receipt=0))
            self.assertIsNone(w.claim(GHOST))
            self.assertTrue(w.finish()); self.assertTrue(w.poll())
            self.assertTrue(w.consumed(w.take())); self.assertTrue(w.release(token))

    def test_mutation_cancellation_does_not_claim_to_undo_commit(self):
        w = World(self.api)
        token = w.claim(STATE)
        self.assertTrue(w.submit(token, command=8)); self.assertTrue(w.start())
        self.assertFalse(self.api.TWLeaseCancel(C.byref(w.p), C.byref(w.ppc), token, 0))
        self.assertFalse(w.release(token))
        self.assertTrue(w.finish()); self.assertTrue(w.poll())
        self.assertTrue(w.consumed(w.take())); self.assertTrue(w.release(token))

    def test_boot_activation_requires_both_workers_and_never_assumes_v4(self):
        w = World(self.api)
        w.reset(); w.p = Ppc(); w.read_ppc()
        self.assertIsNone(w.claim(STATE))
        self.assertTrue(self.api.TWLeaseAttach(C.byref(w.p), C.byref(w.ppc)))
        w.flush_ppc(); w.read_arm()
        for ghost, state in ((0, 0), (1, 0), (0, 1)):
            self.assertFalse(self.api.TWLeaseActivate(C.byref(w.a), C.byref(w.arm), ghost, state))
        self.assertIsNone(w.claim(GHOST))
        self.assertTrue(self.api.TWLeaseActivate(C.byref(w.a), C.byref(w.arm), 1, 1))
        w.flush_arm(); w.read_ppc()
        self.assertTrue(self.api.TWLeaseAttached(C.byref(w.p), C.byref(w.ppc)))

    def test_reset_retires_both_workers_and_rejects_old_finish_and_borrow(self):
        w = World(self.api)
        token = w.claim(GHOST); self.assertTrue(w.submit(token)); self.assertTrue(w.start())
        old = Token(w.a.key.epoch, w.a.key.ticket)
        self.api.TWLeaseResetBegin(C.byref(w.a), C.byref(w.arm))
        w.flush_arm(); w.read_ppc()
        self.assertFalse(w.finish(token=old))
        self.assertFalse(self.api.TWLeaseResetPublish(C.byref(w.a), C.byref(w.arm)))
        self.assertFalse(self.api.TWLeaseRetired(C.byref(w.a), GHOST, 0))
        self.assertTrue(self.api.TWLeaseRetired(C.byref(w.a), STATE, 1))
        self.assertFalse(self.api.TWLeaseResetPublish(C.byref(w.a), C.byref(w.arm)))
        self.assertTrue(self.api.TWLeaseRetired(C.byref(w.a), GHOST, 1))
        self.assertTrue(self.api.TWLeaseResetPublish(C.byref(w.a), C.byref(w.arm)))
        w.flush_arm(); w.attach()
        fresh = w.claim(STATE)
        self.assertFalse(w.release(token))
        self.assertTrue(w.submit(fresh)); self.assertTrue(w.start())
        self.assertFalse(w.finish(token=old))
        self.assertTrue(w.finish()); self.assertTrue(w.poll())
        self.assertFalse(w.consumed(old))
        self.assertTrue(w.consumed(w.take())); self.assertTrue(w.release(fresh))

    def test_stale_ack_worker_identity_and_sequence_wrap(self):
        w = World(self.api)
        token = w.claim(STATE)
        self.assertTrue(w.submit(token, seq=0xFFFFFFFF))
        self.assertFalse(w.start(GHOST)); self.assertFalse(w.start(session=10))
        self.assertFalse(w.start(seq=1)); self.assertFalse(w.start(command=4))
        self.assertTrue(w.start()); self.assertTrue(w.finish()); self.assertTrue(w.poll())
        old_receipt = clone(w.memory.response)
        self.assertTrue(w.consumed(w.take()))
        self.assertTrue(w.submit(token, seq=1)); self.assertTrue(w.start())
        w.memory.response = old_receipt
        self.assertFalse(w.poll())
        self.assertFalse(w.finish(token=Token(old_receipt.epoch, old_receipt.ticket)))
        self.assertTrue(w.finish()); self.assertTrue(w.poll())
        self.assertTrue(w.consumed(w.take())); self.assertTrue(w.release(token))

    def test_reinjection_abandons_each_local_and_remote_phase_only_after_retirement(self):
        for owner in (GHOST, STATE):
            for phase in ("prepare", "worker", "result", "borrowed"):
                with self.subTest(owner=owner, phase=phase):
                    w = World(self.api)
                    old_owner = w.claim(owner)
                    old_borrow = None
                    if phase != "prepare":
                        self.assertTrue(w.submit(old_owner)); self.assertTrue(w.start())
                        if phase != "worker":
                            self.assertTrue(w.finish()); self.assertTrue(w.poll())
                            if phase == "borrowed":
                                old_borrow = w.take()
                    w.reset(); w.attach()
                    new_owner = w.claim(STATE)
                    self.assertIsNotNone(new_owner)
                    self.assertFalse(w.release(old_owner))
                    if old_borrow:
                        self.assertFalse(w.consumed(old_borrow))
                    self.assertTrue(w.release(new_owner))

    def test_completed_ghost_doorbell_cannot_revive_during_local_state_save(self):
        w = World(self.api)
        ghost = w.claim(GHOST)
        self.assertTrue(w.submit(ghost, seq=91, session=0, command=4))
        old_request = clone(w.memory.request)
        self.assertTrue(w.start()); self.assertTrue(w.finish()); self.assertTrue(w.poll())
        self.assertTrue(w.consumed(w.take())); self.assertTrue(w.release(ghost))
        state = w.claim(STATE)
        w.arm.request = old_request
        self.assertFalse(self.api.TWLeaseStart(C.byref(w.a), C.byref(w.arm), GHOST, 91, 0, 4))
        self.assertTrue(w.release(state))

    def test_lost_cache_publication_cannot_start_or_ack_a_new_operation(self):
        w = World(self.api)
        token = w.claim(GHOST)
        self.assertTrue(self.api.TWLeaseSubmit(C.byref(w.p), C.byref(w.ppc), token, 9, 0, 2))
        self.assertFalse(w.start())  # PPC request line was not flushed.
        w.flush_ppc(); self.assertTrue(w.start())
        old = clone(w.memory.response)
        self.assertTrue(self.api.TWLeaseFinish(C.byref(w.a), C.byref(w.arm),
                                             Token(w.a.key.epoch, w.a.key.ticket), 1, 1, 1))
        self.assertEqual(bytes(w.memory.response), bytes(old))
        self.assertFalse(w.poll())  # ARM completion line was not flushed.
        w.flush_arm(); self.assertTrue(w.poll())

    def test_ticket_and_epoch_exhaustion_fail_closed(self):
        w = World(self.api)
        w.p.nextTicket = 0xFFFFFFFF
        self.assertIsNone(w.claim(STATE))
        w.a.epoch = 0xFFFFFFFF
        self.api.TWLeaseResetBegin(C.byref(w.a), C.byref(w.arm))
        self.assertTrue(self.api.TWLeaseRetired(C.byref(w.a), GHOST, 1))
        self.assertTrue(self.api.TWLeaseRetired(C.byref(w.a), STATE, 1))
        self.assertFalse(self.api.TWLeaseResetPublish(C.byref(w.a), C.byref(w.arm)))


if __name__ == "__main__":
    unittest.main()
