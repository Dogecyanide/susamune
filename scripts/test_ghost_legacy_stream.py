"""Bounded legacy SGHF -> compact pose/input cache, using production validators."""
import bisect
import ctypes as C
import os
from pathlib import Path
import random
import struct
import subprocess
import tempfile
import unittest
import zlib

import validate_ghost as canonical
from test_ghost_format import build_ghost
from test_ghost_teaching import teaching_file
from test_ghost_camera_storage import camera_file
from test_ghost_initial_rng import rng_file
from test_ghost_context import context_file, changed_input, complete_camera
from test_ghost_storage import rechecksum_ghost

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = r'''
#include "susamune/ghost_legacy_index.hxx"
#include "susamune/ghost_trace_race_stream.hxx"
#include <cstring>
using namespace GhostLegacyStream;
static Reader reader;
static GhostLegacyIndex::Adapter adapter;
static Read read;
alignas(32) static unsigned char source[16384+64],poseScratch[8192+64],inputScratch[8192+64];
static GhostTraceIndex::Page directories[2][512];
alignas(32) static unsigned char stored[2][512][8192];
static unsigned events[4],flushes[2],largestRead;
static GhostTraceIndex::Sample result;
static GhostLegacyIndex::Observation observation;
static GhostArena::Arena arena;
alignas(32) static unsigned char memory[131072];
static GhostTraceRaceStream::Stream streams[4];
#define API extern "C" __declspec(dllexport)
API int start(unsigned bytes,unsigned target,unsigned block) {
    reader={};adapter={};memset(events,0,sizeof(events));memset(flushes,0,sizeof(flushes));largestRead=0;
    memset(source,0xa5,sizeof(source));memset(poseScratch,0xa5,sizeof(poseScratch));memset(inputScratch,0xa5,sizeof(inputScratch));
    if(!begin(reader,bytes,target,source+32,block))return 0;
    return GhostLegacyIndex::begin(adapter,reader.metadata,directories[0],512,poseScratch+32,8192,directories[1],512,inputScratch+32,8192);
}
API unsigned state(){return status(reader);}
API unsigned error(){return reader.error;}
API int next_read(){int ok=nextRead(reader,read);if(ok&&read.bytes>largestRead)largestRead=read.bytes;return ok;}
API unsigned offset(){return read.offset;}
API unsigned bytes(){return read.bytes;}
API void* destination(){return read.destination;}
API int accept(unsigned n){return acceptRead(reader,n);}
static bool flush() {
    const auto *page=GhostLegacyIndex::pendingPage(adapter);if(!page||page->ordinal>=512)return false;
    memcpy(stored[adapter.target][page->ordinal],GhostLegacyIndex::pendingData(adapter),8192);
    ++flushes[adapter.target];return GhostLegacyIndex::commitPage(adapter);
}
API int drain() {
    Event event;
    while(next(reader,event)) {
        ++events[event.type];
        for(;;) {
            auto result=GhostLegacyIndex::feed(adapter,event);
            if(result==GhostTraceIndex::ACCEPTED)break;
            if(result!=GhostTraceIndex::PAGE_READY||!flush())return 0;
        }
    }
    return status(reader)!=FAILED;
}
API int finish() {
    for(;;) {
        auto result=GhostLegacyIndex::finish(adapter,reader);
        if(result==GhostTraceIndex::FINISHED)return 1;
        if(result!=GhostTraceIndex::PAGE_READY||!flush())return 0;
    }
}
API unsigned version(){return reader.metadata.version;}
API unsigned poses(){return events[0];}
API unsigned inputs(){return events[1];}
API unsigned cameras(){return events[2];}
API unsigned contexts(){return events[3];}
API unsigned segments(){return reader.metadata.segmentCount;}
API unsigned splits(){return reader.metadata.splitCount;}
API unsigned split_qf(unsigned n){return reader.metadata.splits[n].qf;}
API unsigned pages(unsigned kind){return kind?adapter.observations.count:adapter.poses.count;}
API unsigned largest_read(){return largestRead;}
API unsigned control_bytes(){return sizeof(Reader)+sizeof(GhostLegacyIndex::Adapter);}
API int validate_pages() {
    for(unsigned kind=0;kind<2;++kind) {
        unsigned n=pages(kind);if(n&&!GhostTraceIndex::validDirectory(directories[kind],n))return 0;
        for(unsigned p=0;p<n;++p)if(!GhostTraceIndex::validPage(directories[kind][p],stored[kind][p],directories[kind][p].count*64))return 0;
    }
    return 1;
}
static bool bracket(unsigned kind,unsigned segment,int qf,GhostTraceIndex::Bracket &out) {
    unsigned indexSegment;
    if(!GhostLegacyIndex::indexSegment(directories[kind],pages(kind),segment,indexSegment))return false;
    const auto query=GhostTraceIndex::byQf(indexSegment,qf);GhostTraceIndex::Needed needed;
    if(!GhostTraceIndex::locate(directories[kind],pages(kind),query,needed))return false;
    return GhostTraceIndex::bracket(query,directories[kind][needed.first],reinterpret_cast<GhostTraceIndex::Sample*>(stored[kind][needed.first]),
        directories[kind][needed.second],reinterpret_cast<GhostTraceIndex::Sample*>(stored[kind][needed.second]),out);
}
API int sample(unsigned segment,int qf) {
    GhostTraceIndex::Bracket pose,input;
    if(!bracket(0,segment,qf,pose))return 0;
    const auto *observation=bracket(1,segment,qf,input)?&input:nullptr;
    return GhostLegacyIndex::sample(reader.metadata,segment,qf,pose,observation,result,&::observation);
}
API float x(){return result.x;}
API float y(){return result.y;}
API float z(){return result.z;}
API int yaw(){return result.yaw;}
API unsigned animation(){return result.animationId;}
API unsigned phase(){return result.animationPhase;}
API unsigned yoshi(){return result.yoshi;}
API unsigned held(){return result.heldObjectId;}
API unsigned name_key(){return result.heldNameKey;}
API unsigned buttons(){return result.raw.buttons;}
API int stick(){return result.raw.stickX;}
API int input_error(){return result.raw.error;}
API unsigned input_qf(){return observation.qf;}
API unsigned input_index(){return observation.sourceIndex;}
API int input_present(){return observation.present;}
API int steering(){return observation.steering;}
API int camera_yaw(){return observation.cameraYaw;}
API unsigned camera_mode(){return observation.cameraMode;}
API void* fludd(){return &result.fludd;}
API int watch2() {
    if(!pages(0)||!pages(1))return 0;
    arena={};const GhostArena::Span span={memory,sizeof(memory)};
    if(!GhostArena::configure(arena,&span,1))return 0;
    const auto recording=GhostArena::acquire(arena,GhostArena::RECORDING,65536);
    if(!GhostArena::write(arena,recording,GhostArena::RECORDING).data)return 0;
    for(unsigned i=0;i<4;++i) {
        const unsigned kind=i&1;streams[i]={};
        if(!GhostTraceRaceStream::begin(streams[i],arena,directories[kind],pages(kind)))return 0;
        const int qf=int(reader.metadata.endQf);
        unsigned segment;
        if(!GhostLegacyIndex::indexSegment(directories[kind],pages(kind),reader.metadata.segmentCount-1,segment))return 0;
        if(!GhostTraceRaceStream::request(streams[i],GhostTraceIndex::byQf(segment,qf)))return 0;
        GhostTraceRaceStream::Read request;
        while(GhostTraceRaceStream::nextRead(streams[i],request)) {
            memcpy(request.destination,reinterpret_cast<unsigned char*>(stored[kind])+request.offset,request.bytes);
            if(!GhostTraceRaceStream::acceptRead(streams[i],request.sequence,request.bytes,true))return 0;
        }
        GhostTraceIndex::Bracket sample;if(!GhostTraceRaceStream::sample(streams[i],sample))return 0;
    }
    if(GhostArena::available(arena))return 0;
    for(unsigned i=0;i<4;++i)if(!GhostTraceRaceStream::close(streams[i]))return 0;
    return GhostArena::available(arena)==65536&&GhostArena::write(arena,recording,GhostArena::RECORDING).data;
}
API int guards(){for(unsigned i=0;i<32;++i)if(source[i]!=0xa5||source[16416+i]!=0xa5||poseScratch[i]!=0xa5||poseScratch[8224+i]!=0xa5||inputScratch[i]!=0xa5||inputScratch[8224+i]!=0xa5)return 0;return 1;}
'''


def versions():
    return [build_ghost(version=3), build_ghost(version=4), teaching_file(),
            teaching_file(fludd=[bytes(8)] * 3), teaching_file(fludd=[bytes(8)] * 3, extended=True),
            camera_file(), rng_file(), context_file()]


class LegacyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='moonshine-legacy-stream-')
        cls.addClassCleanup(cls.temp.cleanup)
        out = Path(cls.temp.name)
        (out / 'fixture.cpp').write_text(FIXTURE, encoding='utf-8')
        env = dict(os.environ, PATH='C:/msys64/mingw64/bin;' + os.environ['PATH'])
        args = ['C:/msys64/mingw64/bin/g++.exe', '-std=c++11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-Wno-unused-function', '-shared', '-static', '-I', str(ROOT / 'include'), str(out / 'fixture.cpp')]
        args += [str(ROOT / 'src' / f'{name}.cpp') for name in ('ghost_arena', 'ghost_legacy_stream', 'ghost_legacy_index', 'ghost_trace_index', 'ghost_trace_race_stream')]
        run = subprocess.run(args + ['-o', str(out / 'legacy.dll')], env=env, capture_output=True, text=True, encoding='utf-8')
        if run.returncode:
            raise RuntimeError(run.stderr)
        cls.lib = C.CDLL(str(out / 'legacy.dll'))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.destination.restype = cls.lib.fludd.restype = C.c_void_p
        for axis in ('x', 'y', 'z'):
            getattr(cls.lib, axis).restype = C.c_float

    def feed(self, data, target=0x474d534a, block=16384, finish=True):
        self.assertEqual(self.lib.start(len(data), target, block), 1)
        while self.lib.state() not in (2, 3):
            self.assertEqual(self.lib.next_read(), 1, f'state={self.lib.state()} error={self.lib.error()}')
            at, count = self.lib.offset(), self.lib.bytes()
            self.assertLessEqual(count, block)
            chunk = data[at:at + count]
            C.memmove(self.lib.destination(), chunk, len(chunk))
            if not self.lib.accept(len(chunk)) or not self.lib.drain():
                break
        self.assertEqual(self.lib.guards(), 1)
        if self.lib.state() == 2 and finish:
            self.assertEqual(self.lib.finish(), 1)
            self.assertEqual(self.lib.validate_pages(), 1)
        return self.lib.state()

    def test_all_supported_public_versions_match_canonical_admission(self):
        for version, data in enumerate(versions(), 3):
            with self.subTest(version=version):
                expected = canonical.validate_ghost(data)
                self.assertEqual(self.feed(data), 2)
                self.assertEqual(self.lib.version(), version)
                self.assertEqual(self.lib.poses(), expected['sample_count'])
                self.assertEqual(self.lib.inputs(), expected['teaching']['input_count'])
                self.assertEqual(self.lib.splits(), len(expected['teaching']['splits']))
                for index, split in enumerate(expected['teaching']['splits']):
                    self.assertEqual(self.lib.split_qf(index), split['qf'])
                self.assertEqual(self.lib.sample(0, 102), 1)
                self.assertAlmostEqual(self.lib.x(), 21 if version < 8 else 0)
                self.assertEqual(self.lib.input_present(), bool(expected['teaching']['input_count']))

    def test_experimental_and_future_versions_are_refused(self):
        for version in (1, 2, 11, 65535):
            data = bytearray(build_ghost(version=3))
            struct.pack_into('>H', data, 4, version)
            self.assertEqual(self.feed(rechecksum_ghost(data)), 3)
            self.assertEqual(self.lib.error(), 4)
            self.assertEqual(self.lib.poses(), 0)

    def test_input_changes_between_poses_remain_at_exact_qf(self):
        data = teaching_file()
        self.assertEqual(self.feed(data), 2)
        for qf, buttons, iqf in ((100, 0x100, 100), (101, 0x100, 100), (102, 0, 102), (103, 0, 102), (104, 0x200, 104)):
            self.assertEqual(self.lib.sample(0, qf), 1)
            self.assertEqual(self.lib.buttons(), buttons)
            self.assertEqual(self.lib.input_qf(), iqf)
            self.assertAlmostEqual(self.lib.x(), 20 + (qf - 100) / 2)

    def test_raw_signed_inputs_and_v10_steering_provenance(self):
        base = rng_file(base=complete_camera(teaching_file(fludd=[bytes(8)] * 3, extended=True), 3))
        data = changed_input(context_file(base=base), 1, yaw=-12345, mode=73)
        self.assertEqual(self.feed(data), 2)
        self.assertEqual(self.lib.sample(0, 102), 1)
        self.assertEqual(self.lib.input_index(), 1)
        self.assertEqual(self.lib.input_qf(), 102)
        self.assertEqual(self.lib.steering(), 1)
        self.assertEqual(self.lib.camera_yaw(), -12345)
        self.assertEqual(self.lib.camera_mode(), 73)
        self.assertEqual(self.lib.sample(0, 100), 1)
        self.assertEqual(self.lib.steering(), 0)
        self.assertEqual(self.lib.stick(), -40)

    def test_yoshi_fludd_and_held_attachments_are_not_conflated(self):
        base = build_ghost(version=4, samples=[(0,0,0,32760,0,7,4000,3,1),(80,0,0,-32760,4,7,64,3,0)], attachments=[(0x40000016, 0x1234)])
        visuals = [bytes([0x80,15,1,128,127,3,120,255]), bytes([0xb0,17,0,255,0,4,100,64]), bytes(8)]
        data = teaching_file(base=base, fludd=visuals, extended=True)
        self.assertEqual(self.feed(data), 2)
        self.assertEqual(self.lib.sample(0, 101), 1)
        self.assertEqual(self.lib.yoshi(), 3)
        self.assertEqual(self.lib.held(), 0x40000016)
        self.assertEqual(self.lib.name_key(), 0x1234)
        self.assertEqual(C.string_at(self.lib.fludd(), 8), visuals[0])
        self.assertEqual(self.lib.sample(0, 103), 1)
        self.assertEqual(C.string_at(self.lib.fludd(), 8), visuals[1])

    def test_missing_and_truncated_input_is_not_extrapolated(self):
        row = (102, 0x100, -40, 30, 0, 0, 70, 0, 0, 0, -1, 0)
        for flags in (0, 1):
            self.assertEqual(self.feed(teaching_file(inputs=[row], splits=[], flags=flags)), 2)
            for qf, present in ((100, False), (102, True), (103, not flags)):
                self.assertEqual(self.lib.sample(0, qf), 1)
                self.assertEqual(self.lib.input_present(), present)
                if present:
                    self.assertEqual(self.lib.input_error(), -1)

    def test_equal_boundary_segments_and_duplicate_observation(self):
        segments = [{'first_sample': 0, 'sample_count': 2, 'start_qf': 100, 'end_qf': 104,
                     'route': {'area': 2, 'episode': 0, 'parent_area': 255, 'flags': 0, 'variant': 0}},
                    {'first_sample': 2, 'sample_count': 2, 'start_qf': 104, 'end_qf': 108,
                     'route': {'area': 2, 'episode': 0, 'parent_area': 255, 'flags': 0, 'variant': 0}}]
        base = build_ghost(version=4, samples=[(0,0,0,0,0,7,0),(32,0,0,0,4,7,0),(800,0,0,0,0,7,0),(832,0,0,0,4,7,0)], segments=segments)
        data = teaching_file(base=base)
        self.assertEqual(self.feed(data), 2)
        self.assertEqual(self.lib.sample(0, 104), 1)
        self.assertEqual(self.lib.x(), 4)
        self.assertEqual(self.lib.buttons(), 0x200)
        self.assertEqual(self.lib.sample(1, 104), 1)
        self.assertEqual(self.lib.x(), 100)
        self.assertEqual(self.lib.buttons(), 0x200)
        self.assertEqual(self.lib.sample(1, 103), 0)

    def test_pose_interpolation_rounding_does_not_follow_input_keys(self):
        base = build_ghost(version=4, samples=[(0,0,0,30000,0,7,3980),(80,0,0,-30000,11,7,30)])
        rows = [(qf,0,0,0,0,0,0,0,0,0,0,0) for qf in (100,102,105,108,111)]
        data = teaching_file(base=base, inputs=rows, splits=[])
        self.assertEqual(self.feed(data), 2)
        before = canonical._unpack_pose_sample_v4(data, 0x900)
        after = canonical._unpack_pose_sample_v4(data, 0x910)
        phase_a, phase_b = before[6] * 4095 // 255, after[6] * 4095 // 255
        delta = ((phase_b - phase_a + 2048) & 4095) - 2048
        yaw_delta = ((-30000 - 30000 + 32768) & 65535) - 32768
        for qf in range(100, 112):
            self.assertEqual(self.lib.sample(0, qf), 1)
            self.assertEqual(self.lib.yaw(), C.c_short(30000 + int(yaw_delta * (qf - 100) / 11)).value)
            self.assertEqual(self.lib.phase(), (phase_a + int(delta * (qf - 100) / 11)) & 4095)

    def test_bad_checksums_semantics_trailing_data_and_short_reads(self):
        good = context_file()
        for offset in (16, 20, 256, 0x904, len(good) - 1):
            bad = bytearray(good);bad[offset] ^= 1
            self.assertEqual(self.feed(bytes(bad)), 3)
        bad = bytearray(teaching_file());bad[0x900 + 32 + 32 + 15] = 1
        self.assertEqual(self.feed(rechecksum_ghost(bad)), 3)
        self.assertEqual(self.feed(good + b'x'), 3)
        self.assertEqual(self.lib.start(len(good), 0x474d534a, 16384), 1)
        self.assertEqual(self.lib.next_read(), 1)
        self.assertEqual(self.lib.accept(255), 0)
        self.assertEqual(self.lib.error(), 2)

    def test_cross_region_uses_existing_portable_route_policy(self):
        good = build_ghost(version=4, region=0)
        self.assertEqual(self.feed(good, target=0x474d5350), 2)
        private = build_ghost(version=4, region=0, route_area=0x0a)
        self.assertEqual(self.feed(private, target=0x474d534a), 2)
        self.assertEqual(self.feed(private, target=0x474d5350), 3)

    def test_no_successful_publication_before_complete_validation(self):
        data = teaching_file()
        self.assertEqual(self.lib.start(len(data), 0x474d534a, 16384), 1)
        self.assertEqual(self.lib.finish(), 0)
        self.assertEqual(self.feed(data), 2)

    def test_bounded_blocks_page_flush_and_watch_two_shared_leases(self):
        samples = [(i * 8, 0, 0, i, 0 if not i else 4, 7, 0) for i in range(700)]
        base = build_ghost(version=4, samples=samples, start_qf=0)
        rows = [(i * 2,0x100,0,0,0,0,0,0,0,0,0,0) for i in range(1399)]
        data = teaching_file(base=base, inputs=rows, splits=[], fludd=[bytes(8)] * len(rows))
        self.assertEqual(self.feed(data, block=2048), 2)
        self.assertEqual(self.lib.pages(0), 6)
        self.assertEqual(self.lib.pages(1), 11)
        self.assertLessEqual(self.lib.largest_read(), 2048)
        self.assertEqual(self.lib.watch2(), 1)
        for qf in (0, 255, 511, 1025, 2796):
            self.assertEqual(self.lib.sample(0, qf), 1)
            self.assertAlmostEqual(self.lib.x(), qf / 4)

    def test_actual_existing_public_legacy_recordings(self):
        files = sorted((ROOT / 'build').glob('**/*.smsghost'))
        if not files:
            self.skipTest('Private .smsghost fixtures unavailable')
        checked = 0
        for path in files:
            data = path.read_bytes()
            if data[:4] != b'SGHF':
                continue
            expected = canonical.validate_ghost(data)
            with self.subTest(file=str(path.relative_to(ROOT))):
                self.assertEqual(self.feed(data, target=int(expected['game_id'], 16)), 2)
                self.assertEqual(self.lib.poses(), expected['sample_count'])
                self.assertEqual(self.lib.inputs(), expected['teaching']['input_count'])
                self.assertEqual(self.lib.segments(), expected['segment_count'])
                for index, segment in enumerate(expected['segments']):
                    first, count = segment['first_sample'], segment['sample_count']
                    unpack = canonical._unpack_pose_sample if expected['version'] == 3 else canonical._unpack_pose_sample_v4
                    poses = [unpack(data, 0x900 + (first + i) * 16) for i in range(count)]
                    times = [segment['start_qf']]
                    for row in poses[1:]:
                        times.append(times[-1] + row[4])
                    queries = {times[0], times[-1], (times[0] + times[-1]) // 2}
                    rng = random.Random(0x5a17 + index)
                    queries.update(rng.randint(times[0], times[-1]) for _ in range(12))
                    for qf in sorted(queries):
                        self.assertEqual(self.lib.sample(index, qf), 1)
                        at = bisect.bisect_right(times, qf) - 1
                        a, b = poses[at], poses[min(at + 1, len(poses) - 1)]
                        span = times[at + 1] - times[at] if at + 1 < len(times) else 0
                        elapsed = qf - times[at]
                        t = elapsed / span if span else 0
                        for axis, fn in enumerate(('x', 'y', 'z')):
                            self.assertAlmostEqual(getattr(self.lib, fn)(), (a[axis] + (b[axis] - a[axis]) * t) / 8, delta=.02)
                        delta = ((b[3] - a[3] + 32768) & 65535) - 32768
                        yaw = C.c_short(a[3] + (int(delta * elapsed / span) if span else 0)).value
                        self.assertEqual(self.lib.yaw(), yaw)
                        phase_a = a[6] if expected['version'] == 3 else a[6] * 4095 // 255
                        phase_b = b[6] if expected['version'] == 3 else b[6] * 4095 // 255
                        delta = ((phase_b - phase_a + 2048) & 4095) - 2048
                        phase = (phase_a + (int(delta * elapsed / span) if span and a[5] == b[5] else 0)) & 4095
                        self.assertEqual(self.lib.animation(), a[5])
                        self.assertEqual(self.lib.phase(), phase)
                        self.assertEqual(self.lib.yoshi(), a[7] if expected['version'] >= 4 else 0)
                checked += 1
        self.assertGreater(checked, 0)


if __name__ == '__main__':
    unittest.main()
