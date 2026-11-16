"""Feed optional spin literals through the real decoder and world replay coordinator."""
import ctypes as C
import struct
import unittest

import test_ghost_trace_decode as trace
import test_ghost_world_replay as world
from test_ghost_trace_reader import record

CAPS = world.CAPS | (1 << 21) | (1 << 23)


def stage(observations=8, frame=0, tick=0, scene=0xd00, generation=3, flag_byte=0):
    body = bytearray(trace.stage(scene=scene, generation=generation))
    struct.pack_into('>I', body, 0, 3)
    body[64] = flag_byte
    return record(frame, tick, body + struct.pack('>2I', 0, observations), 22)


def first(observations=8, moves=0):
    return stage(observations) + world.first_frame(moves=moves)[len(world.prefix()):]


def spin(sequence=1, caller=1, result=1, direction=2, frame=1, tick=0):
    return record(frame, tick, struct.pack('>7I', 1, 4, sequence, caller, result, direction, 1), 29)


def passive(subtype, frame=0, tick=0):
    lengths = {1: 44, 2: 16, 3: 104, 5: 28}
    body = bytearray(lengths[subtype])
    struct.pack_into('>2I', body, 0, 1, subtype)
    return record(frame, tick, body, 29)


FIXTURE = world.FIXTURE + r'''
static GhostSpinObservation::Queue spinQueue;
API int spinAttach(){return W::attachSpinQueue(replay,spinQueue);}
API unsigned stageField(unsigned field){
    return field==0 ? replay.stage.scene : field==1 ? replay.stage.generation
        : replay.stage.flagBytes ? replay.stage.flagBytes[0] : 0xffffffff;
}
API unsigned spinValue(unsigned field){switch(field){case 0:return spinQueue.count;case 1:return spinQueue.read;case 2:return spinQueue.frame;case 3:return spinQueue.tick;case 4:return spinQueue.sequence;case 5:return replay.spinLastSequence;case 6:return spinQueue.error;default:return spinQueue.mode;}}
API unsigned spinEntry(unsigned index,unsigned field){if(index>=16)return 0xffffffff;switch(field){case 0:return spinQueue.events[index].sequence;case 1:return spinQueue.events[index].caller;case 2:return spinQueue.events[index].result;case 3:return spinQueue.events[index].outDir;case 4:return spinQueue.frames[index];default:return spinQueue.ticks[index];}}
// The separate compiled-PPC tests exercise the native hook's validation/override.
API int acknowledgeSpin(){if(spinQueue.read>=spinQueue.count)return 0;spinQueue.sequence=spinQueue.events[spinQueue.read++].sequence;return 1;}
API void spinFault(unsigned error){spinQueue.error=error;}
API int spinAliased(){return W::attachSpinQueue(replay,*reinterpret_cast<GhostSpinObservation::Queue*>(&replay));}
API int spinContinuation(){MsTraceContinuation c={};c.runFlags=MS_TRACE_CONTINUATION_RUN_FLAGS;c.actions=1;c.parentNonce=7;c.parentRun=8;c.parentChunk=1;c.parentHash=9;c.rngSeed=123;c.qf=120;c.attempt=44;c.generation=3;c.contextFlags=1;return W::continueSource(replay,c);}
'''


class SpinReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        previous = trace.FIXTURE
        trace.FIXTURE = FIXTURE
        try:
            trace.DecodeTests.setUpClass.__func__(cls)
        finally:
            trace.FIXTURE = previous
        cls.lib.worldBoundary.restype = C.c_uint

    reset = world.ReplayTests.reset
    push = world.ReplayTests.push
    drain = world.ReplayTests.drain
    initialize = world.ReplayTests.initialize
    start = world.ReplayTests.start

    def setUp(self):
        self.reset(caps=CAPS)
        self.assertEqual(self.lib.spinAttach(), 1)

    def ready(self, data):
        self.assertEqual(self.push(data), 0)
        self.assertEqual(self.lib.worldFinish(), 1)
        self.initialize()
        self.assertEqual(self.start(), 0)
        self.assertEqual(self.lib.worldApplied(1), 1)

    def test_spin_literal_has_own_order_and_does_not_modify_rng_queue_or_seed(self):
        literal = record(1, 0, struct.pack('>3I', 0x80012340, 12345, 0x87654321), 15)
        self.ready(first() + literal + spin())
        self.assertEqual([self.lib.spinValue(i) for i in range(4)], [1, 0, 1, 0])
        # The spin executed before this RNG call, although deferred recording
        # placed its separate observation after the already-emitted RNG packet.
        self.assertEqual(self.lib.acknowledgeSpin(), 1)
        self.assertEqual(self.lib.worldQueued(), 1)
        self.assertEqual(self.lib.worldRandom(0x80012340, 12345, 0x87654321), 1)
        self.assertEqual(self.lib.worldStats(3), 1)
        self.assertEqual(self.lib.worldEnd(1, 1), 1)
        self.assertEqual([self.lib.spinValue(i) for i in (0, 1, 4, 5)], [0, 0, 1, 1])

    def test_borrowed_chunk_bytes_are_copied_before_release(self):
        self.assertEqual(self.push(first() + spin(result=1, direction=3)), 0)
        C.memset(self.buffer, 0xcd, len(self.buffer))
        self.assertEqual([self.lib.spinEntry(0, i) for i in range(6)], [1, 1, 1, 3, 1, 0])
        self.assertEqual(self.lib.worldFinish(), 1)
        self.initialize()
        self.assertEqual(self.start(), 0)
        self.assertEqual(self.lib.worldApplied(1), 1)
        self.assertEqual(self.lib.acknowledgeSpin(), 1)
        self.assertEqual(self.lib.worldEnd(1, 1), 1)

    def test_literal_timing_tracks_each_movement_and_rejects_leftover_prior_tick(self):
        data = first(moves=1) + spin(tick=1) + record(1, 2, trace.input_body(False, valid=3), 14)
        for consume in (True, False):
            self.reset(caps=CAPS)
            self.assertEqual(self.lib.spinAttach(), 1)
            self.ready(data)
            self.assertEqual(self.lib.worldMove(1, 0), 1)
            self.assertEqual(self.lib.spinValue(3), 1)
            self.assertEqual(self.lib.worldApplied(1), 1)
            if consume:
                self.assertEqual(self.lib.acknowledgeSpin(), 1)
                self.assertEqual(self.lib.worldMove(1, 1), 1)
                self.assertEqual(self.lib.spinValue(3), 2)
                self.assertEqual(self.lib.worldApplied(1), 1)
                self.assertEqual(self.lib.worldEnd(1, 1), 1)
            else:
                self.assertEqual(self.lib.worldMove(1, 1), 0)
                self.assertEqual(self.lib.worldError(), 27)

    def test_frame_end_rejects_unconsumed_literals_or_native_hook_error(self):
        for error, expected in ((0, 27), (8, 26), (32, 26), (64, 26)):
            self.reset(caps=CAPS)
            self.assertEqual(self.lib.spinAttach(), 1)
            self.ready(first() + spin())
            if error:
                self.lib.spinFault(error)
            self.assertEqual(self.lib.worldEnd(1, 1), 0)
            self.assertEqual(self.lib.worldError(), expected)

    def test_sequence_gaps_and_spin_without_declaration_are_refused(self):
        for data, error in ((first() + spin(sequence=2), 25),
                            (first(observations=0) + spin(), 2)):
            self.reset(caps=CAPS)
            self.assertEqual(self.lib.spinAttach(), 1)
            self.assertEqual(self.push(data), 2)
            self.assertEqual(self.lib.worldError(), error)

    def test_exact_capacity_and_next_frame_backpressure_preserve_source_order(self):
        data = first() + b''.join(spin(sequence=i) for i in range(1, 17))
        data += record(2, 0, world.frame(), 2) + record(2, 0, trace.visual(), 23)
        data += record(2, 0, world.boundary(), 14) + spin(sequence=17, frame=2)
        self.assertEqual(self.push(data), 1)
        self.assertEqual(self.lib.spinValue(0), 16)
        self.initialize()
        self.assertEqual(self.start(), 0)
        self.assertEqual(self.lib.worldApplied(1), 1)
        for _ in range(16):
            self.assertEqual(self.lib.acknowledgeSpin(), 1)
        self.assertEqual(self.lib.worldEnd(1, 1), 1)
        self.assertEqual(self.drain(), 0)
        self.assertEqual(self.lib.worldFinish(), 1)
        self.assertEqual(self.start(), 0)
        self.assertEqual(self.lib.worldApplied(1), 1)
        self.assertEqual(self.lib.spinValue(2), 2)
        self.assertEqual(self.lib.spinEntry(0, 0), 17)
        self.assertEqual(self.lib.acknowledgeSpin(), 1)
        self.assertEqual(self.lib.worldEnd(1, 1), 1)

    def test_seventeenth_literal_in_same_frame_stops_cleanly(self):
        self.assertEqual(self.push(first() + b''.join(spin(sequence=i) for i in range(1, 18))), 2)
        self.assertEqual((self.lib.worldError(), self.lib.worldDetail(), self.lib.spinValue(0)), (7, 17, 16))

    def test_valid_passive_metadata_works_before_stage_and_at_movement_ticks(self):
        data = passive(1) + stage() + world.first_frame(moves=1)[len(world.prefix()):]
        data += passive(2, 1, 1) + passive(3, 1, 1) + passive(5, 1, 1)
        self.ready(data)
        self.assertEqual(self.lib.worldMove(1, 0), 1)
        self.assertEqual(self.lib.worldApplied(1), 1)
        self.assertEqual(self.lib.worldEnd(1, 1), 1)

    def test_old_traces_need_no_queue_or_new_literal_hook(self):
        self.reset(caps=world.CAPS)
        self.ready(world.first_frame())
        self.assertEqual(self.lib.worldEnd(1, 1), 1)

    def test_spin_literal_cannot_be_silently_placed_in_an_unplayed_loading_frame(self):
        data = stage() + record(1, 0, world.frame(ready=False, flags=0), 2)
        data += record(1, 0, world.settings(), 1) + record(1, 0, world.boundary(), 14) + spin()
        self.assertEqual(self.push(data), 2)
        self.assertEqual(self.lib.worldError(), 2)

    def test_new_literal_source_requires_separate_queue(self):
        self.reset(caps=CAPS)
        self.assertEqual(self.push(stage()), 2)
        self.assertEqual(self.lib.worldError(), 7)
        self.reset(caps=CAPS)
        self.assertEqual(self.lib.spinAliased(), 0)
        self.assertEqual(self.lib.worldError(), 1)

    def test_departure_consumes_late_spin_across_chunks_before_setup_rng(self):
        for late in (False, True):
            with self.subTest(late=late):
                self.setUp()
                self.assertEqual(self.push(first(moves=1)), 0)
                self.initialize()
                outgoing_spin = spin(caller=9, result=0, direction=4, tick=1)
                if not late:
                    self.assertEqual(self.push(outgoing_spin), 0)
                self.assertEqual(self.push(stage(frame=1, tick=1, scene=0xe00,
                                                 generation=4, flag_byte=0x62)), 0)
                C.memset(self.buffer, 0xcd, len(self.buffer))
                self.assertEqual(self.lib.stageField(0), 0xd00)
                self.assertEqual(self.lib.worldInitial(), 0)
                if late:
                    self.assertEqual(self.push(outgoing_spin), 0)
                setup = record(1, 1, struct.pack('>3I', 0x80012340, 10, 11), 15)
                next_frame = record(2, 1, world.frame(tick=1, scene=0xe00), 2)
                next_frame += record(2, 1, world.boundary(), 14)
                self.assertEqual(self.push(setup + next_frame), 1)
                self.assertEqual(self.lib.worldQueued(), 0)
                self.assertEqual(self.lib.spinEntry(0, 1), 9)
                self.assertEqual(self.start(), 0)
                self.assertEqual(self.lib.worldApplied(1), 1)
                self.assertEqual(self.lib.worldMove(1, 0), 1)
                self.assertEqual(self.lib.worldApplied(1), 1)
                self.assertEqual(self.lib.spinValue(3), 1)
                self.assertEqual(self.lib.acknowledgeSpin(), 1)
                self.assertEqual(self.lib.worldEnd(1, 1), 1)
                self.assertEqual([self.lib.stageField(i) for i in range(3)], [0xe00, 4, 0x62])
                self.assertEqual(self.drain(), 0)
                self.initialize()
                self.assertEqual(self.lib.worldConsumeSetup(), 1)
                self.assertEqual(self.lib.worldFinish(), 1)
                self.assertEqual(self.lib.worldRunRecordedFrame(), 1)
                self.assertEqual(self.lib.worldStats(4), 1)

    def test_departure_does_not_accept_a_different_stamp_or_skip_a_spin(self):
        marker = stage(frame=1, tick=1, scene=0xe00, generation=4)
        for event, error in ((spin(tick=2), 6), (spin(frame=2, tick=1), 6),
                             (spin(sequence=2, tick=1), 25)):
            with self.subTest(error=error):
                self.setUp()
                self.assertEqual(self.push(first(moves=1)), 0)
                self.initialize()
                self.assertEqual(self.push(marker + event), 2)
                self.assertEqual(self.lib.worldError(), error)
        for consume in (False, True):
            self.setUp()
            self.assertEqual(self.push(first(moves=1)), 0)
            self.initialize()
            self.assertEqual(self.push(marker + spin(tick=1)), 0)
            self.assertEqual(self.lib.worldFinish(), 1)
            self.assertEqual(self.start(), 0)
            self.assertEqual(self.lib.worldApplied(1), 1)
            self.assertEqual(self.lib.worldMove(1, 0), 1)
            self.assertEqual(self.lib.worldApplied(1), 1)
            if consume:
                self.assertEqual(self.lib.acknowledgeSpin(), 1)
            self.assertEqual(self.lib.worldEnd(1, 1), int(consume))
            self.assertEqual(self.lib.worldError(), 0 if consume else 27)
            self.assertEqual(self.lib.worldStats(4), int(consume))

    def test_continuation_starts_a_new_literal_sequence_without_stale_entries(self):
        self.assertEqual(self.push(first() + spin()), 0)
        self.initialize()
        self.assertEqual(self.lib.worldSeal(1, 0), 1)
        self.assertEqual(self.start(), 0)
        self.assertEqual(self.lib.worldApplied(1), 1)
        self.assertEqual(self.lib.acknowledgeSpin(), 1)
        self.assertEqual(self.lib.worldEnd(1, 1), 1)
        self.assertEqual(self.lib.spinContinuation(), 1)
        self.assertEqual([self.lib.spinValue(i) for i in (0, 1, 4, 5)], [0, 0, 0, 0])
        data = record(2, 0, world.frame(), 2) + record(2, 0, trace.visual(), 23)
        data += record(2, 0, world.boundary(), 14) + spin(sequence=1, frame=2)
        self.assertEqual(self.push(data), 0)
        self.assertEqual(self.lib.worldFinish(), 1)
        self.assertEqual(self.start(), 0)
        self.assertEqual(self.lib.worldApplied(1), 1)
        self.assertEqual(self.lib.acknowledgeSpin(), 1)
        self.assertEqual(self.lib.worldEnd(1, 1), 1)


if __name__ == '__main__':
    unittest.main()

