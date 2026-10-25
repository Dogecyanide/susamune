"""Adversarial word-visible cache transfers through the native publication API."""
import ctypes as C
import itertools
import unittest

import test_timewarp_transfer_lease as lease
from test_timewarp_transfer_lease import Arm, Control, Line, Ppc, Publication, clone

LOAD = C.CFUNCTYPE(C.c_uint, C.c_void_p)
STORE = C.CFUNCTYPE(None, C.c_void_p, C.c_uint)
CACHE = C.CFUNCTYPE(None, C.c_void_p, C.c_uint)
BARRIER = C.CFUNCTYPE(None)


class Io(C.Structure):
    _fields_ = [('load', LOAD), ('store', STORE), ('flush', CACHE),
                ('invalidate', CACHE), ('barrier', BARRIER)]


class Writer(C.Structure):
    _fields_ = [('issued', C.c_uint)]


class Memory:
    def __init__(self, line, generation=1, direction='request', order=range(8)):
        self.control = Control()
        setattr(self.control, direction, clone(line))
        self.body = getattr(self.control, direction)
        self.publication = getattr(self.control, direction+'Publication')
        self.publication.generation = self.publication.issued = generation
        self.writer = Writer(generation)
        self.base = C.addressof(self.control)
        self.body_address, self.publication_address = C.addressof(self.body), C.addressof(self.publication)
        self.order = list(order)
        self.cache, self.events = {}, []
        self.trace = [bytes(self.control)]
        self.io = Io(LOAD(self.load), STORE(self.store), CACHE(self.flush),
                     CACHE(self.invalidate), BARRIER(self.barrier))
        self.read_schedule = {}
        self.loads = 0

    def load(self, address):
        if self.loads in self.read_schedule:
            C.memmove(self.base, self.read_schedule[self.loads], C.sizeof(Control))
        self.loads += 1
        self.events.append(('load', address-self.base))
        return C.c_uint.from_address(address).value

    def store(self, address, value):
        self.cache[address] = value
        self.events.append(('store', address-self.base, value))

    def flush(self, address, size):
        self.events.append(('flush', address-self.base, size))
        for i in self.order:
            word = address+4*i
            if word in self.cache:
                C.c_uint.from_address(word).value = self.cache[word]
            self.trace.append(bytes(self.control))

    def invalidate(self, address, size):
        self.events.append(('invalidate', address-self.base, size))

    def barrier(self):
        self.events.append(('barrier',))

    def restore(self, data):
        C.memmove(self.base, data, C.sizeof(Control))
        self.loads = 0


class PublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lease.TransferLeaseTests.setUpClass.__func__(cls)
        cls.api.TWLeasePublicationWrite.argtypes = [C.POINTER(Writer), C.POINTER(Line),
            C.POINTER(Publication), C.POINTER(Line), C.POINTER(Io)]
        cls.api.TWLeasePublicationRead.argtypes = [C.POINTER(Line), C.POINTER(Line),
            C.POINTER(Publication), C.POINTER(Io)]
        cls.api.TWLeasePublicationResume.argtypes = [C.POINTER(Writer), C.POINTER(Publication), C.POINTER(Io)]

    def publish(self, memory, line):
        return self.api.TWLeasePublicationWrite(C.byref(memory.writer), C.byref(memory.body),
            C.byref(memory.publication), C.byref(line), C.byref(memory.io))

    def read(self, memory):
        result = Line(1, 2, 3, 4, 5, 6, 7, 8)
        ok = self.api.TWLeasePublicationRead(C.byref(result), C.byref(memory.body),
            C.byref(memory.publication), C.byref(memory.io))
        if not ok:
            self.assertEqual(result.epoch, 0)
            self.assertEqual(result.ticket, 0)
            self.assertEqual(result.phase, 0)
        return ok, result

    def test_flush_and_invalidation_barriers_are_in_the_required_order(self):
        old = Line(0x534c5331, 1, 2, 1, 5, 7, 8, 9)
        new = Line(0x534c5331, 1, 3, 2, 4, 0, 0, 0)
        m = Memory(old)
        self.assertTrue(self.publish(m, new))
        pub, body = m.publication_address-m.base, m.body_address-m.base
        self.assertEqual([e for e in m.events if e[0] in ('flush', 'barrier')],
            [('flush', pub, 32), ('barrier',), ('flush', body, 32), ('barrier',),
             ('flush', pub, 32), ('barrier',)])
        self.assertEqual(m.events[:2], [('store', pub, 0), ('store', pub+4, 2)])
        m.events.clear()
        self.assertTrue(self.read(m)[0])
        self.assertEqual([e for e in m.events if e[0] in ('invalidate', 'barrier')],
            [('invalidate', pub, 32), ('barrier',), ('invalidate', body, 32),
             ('barrier',), ('invalidate', pub, 32), ('barrier',)])

    def test_every_word_cut_of_both_directions_never_accepts_a_mixed_body(self):
        old = Line(0x534c5331, 7, 12, 1, 5, 1, 2, 3)
        new = Line(0x534c5331, 8, 13, 2, 4, 10, 11, 12)
        attempts = 0
        for direction, order in itertools.product(('request', 'response'),
                (tuple(range(8)), tuple(reversed(range(8))), (2, 4, 3, 0, 7, 5, 6, 1))):
            m = Memory(old, direction=direction, order=order)
            self.assertTrue(self.publish(m, new))
            trace = list(dict.fromkeys(m.trace))
            # Pause the writer at every visible word and let it advance at
            # each possible reader load. No indivisible cache-line assumption.
            for begin in range(len(trace)):
                for end in range(begin, len(trace)):
                    for cut in range(11):
                        m.restore(trace[begin]); m.read_schedule = {cut: trace[end]}
                        ok, result = self.read(m); attempts += 1
                        if ok:
                            self.assertIn(bytes(result), (bytes(old), bytes(new)))
            m.read_schedule = {}
            m.restore(trace[-1])
            self.assertEqual(bytes(self.read(m)[1]), bytes(new))
        self.assertGreater(attempts, 4000)

    def test_all_torn_body_subsets_are_invisible_while_commit_is_withdrawn(self):
        old = Line(0x534c5331, 7, 12, 1, 5, 1, 2, 3)
        new = Line(0x534c5331, 8, 13, 2, 4, 10, 11, 12)
        a, b = list((C.c_uint*8).from_buffer_copy(old)), list((C.c_uint*8).from_buffer_copy(new))
        for direction in ('request', 'response'):
            m = Memory(old, direction=direction)
            m.publication.generation = 0
            for mask in range(256):
                C.memmove(C.addressof(m.body), (C.c_uint*8)(*(b[i] if mask>>i&1 else a[i] for i in range(8))), 32)
                self.assertFalse(self.read(m)[0])

    def test_torn_local_claim_cannot_reanimate_old_ghost_request(self):
        old = Line(0x534c5331, 7, 12, 1, 5, 1, 2, 3)
        new = Line(0x534c5331, 7, 13, 2, 4, 0, 0, 0)
        arm = Arm(); arm.epoch = 7; arm.lastTicket = 12; arm.enabled = 1
        control = Control(); control.request = clone(old); control.request.ticket = 13
        # This is the concrete counterexample to an unguarded line read.
        trial = clone(arm)
        self.assertTrue(self.api.TWLeaseStart(C.byref(trial), C.byref(control), 1, 1, 2, 3))
        m = Memory(old, order=(2, 0, 1, 3, 4, 5, 6, 7))
        self.assertTrue(self.publish(m, new))
        for sample in m.trace:
            m.restore(sample); ok, control.request = self.read(m)
            trial = clone(arm)
            self.assertFalse(self.api.TWLeaseStart(C.byref(trial), C.byref(control), 1, 1, 2, 3))

    def test_a_new_response_cannot_validate_an_old_receipt_body(self):
        old = Line(0x534c5331, 7, 12, 1, 7, 1, 2, 3)
        new = Line(0x534c5331, 7, 14, 2, 7, 2, 4, 6)
        ppc = Ppc(); ppc.key = clone(new); ppc.phase = 4
        ppc.key.phase = 5
        m = Memory(old, direction='response', order=(2, 0, 1, 3, 4, 5, 6, 7))
        self.assertTrue(self.publish(m, new))
        for sample in m.trace:
            m.restore(sample); ok, result = self.read(m)
            control = Control(); control.response = result; trial = clone(ppc)
            accepted = self.api.TWLeasePoll(C.byref(trial), C.byref(control))
            self.assertEqual(bool(accepted), bool(ok and bytes(result) == bytes(new)))

    def test_high_water_survives_reset_after_withdrawal_and_generations_never_wrap(self):
        old = Line(0x534c5331, 7, 12, 1, 5, 1, 2, 3)
        new = Line(0x534c5331, 7, 13, 2, 4, 0, 0, 0)
        m = Memory(old)
        self.assertTrue(self.publish(m, new))
        # Reset can park the old writer after its withdrawal has completed.
        withdrawn = next(s for s in m.trace if
            Control.from_buffer_copy(s).requestPublication.generation == 0 and
            Control.from_buffer_copy(s).requestPublication.issued == 2)
        m.restore(withdrawn); m.writer = Writer()
        self.assertTrue(self.api.TWLeasePublicationResume(C.byref(m.writer),
            C.byref(m.publication), C.byref(m.io)))
        self.assertEqual(m.writer.issued, 2)
        self.assertTrue(self.publish(m, new))
        self.assertEqual(m.publication.generation, 3)
        m.writer.issued = 0xffffffff
        before = bytes(m.control)
        self.assertFalse(self.publish(m, old))
        self.assertEqual(bytes(m.control), before)

    def test_same_ticket_phase_changes_cannot_reuse_a_publication_generation(self):
        old = Line(0x534c5331, 7, 12, 1, 5, 1, 2, 3)
        cancelled = clone(old); cancelled.phase = 6
        m = Memory(old)
        initial = bytes(m.control)
        self.assertTrue(self.publish(m, cancelled))
        self.assertTrue(self.publish(m, old))
        final = bytes(m.control)
        self.assertEqual(m.publication.generation, 3)
        m.restore(initial)
        m.read_schedule = {9: final}
        self.assertFalse(self.read(m)[0])


if __name__ == '__main__':
    unittest.main()
