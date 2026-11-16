"""Exercise the compact production index and arena-backed race streams on the host."""
import ctypes as C
import os
from pathlib import Path
import subprocess
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = r'''
#include "susamune/ghost_trace_index.hxx"
#include "susamune/ghost_trace_race_stream.hxx"
#include <cstring>
#include <limits>
using namespace GhostTraceIndex;
static Capture capture;
static GhostTraceDecode::Decoder decoder;
static Page pages[64];
alignas(32) static unsigned char scratch[kPageBytes+64];
alignas(32) static Sample stored[64][kSamplesPerPage];
static Bracket result;
static Needed needed;
static GhostArena::Arena arena;
static GhostArena::Handle recording;
alignas(32) static unsigned char memory[131072+64];
static GhostTraceRaceStream::Stream streams[2];
static GhostTraceRaceStream::Read reads[2];
#define API extern "C" __declspec(dllexport)
API int reset(unsigned capacity) {
    capture={};memset(pages,0,sizeof(pages));memset(stored,0,sizeof(stored));
    memset(scratch,0xa5,sizeof(scratch));result={};arena={};streams[0]={};streams[1]={};
    const GhostArena::Span span={memory+32,131072};
    if(!GhostArena::configure(arena,&span,1))return 0;
    recording=GhostArena::acquire(arena,GhostArena::RECORDING,65536);
    return begin(capture,pages,capacity,scratch+32,kPageBytes);
}
API int visual(unsigned frame,int qf,unsigned flags,unsigned scene,unsigned attempt,unsigned generation) {
    GhostTraceDecode::Event e={};e.type=GhostTraceDecode::VISUAL;e.frame=frame;
    e.visual.flags=flags;e.visual.qf=qf;e.visual.scene=scene;e.visual.attempt=attempt;e.visual.generation=generation;
    e.visual.directorTick=frame*4;
    if(flags&POSE){e.visual.x=float(qf);e.visual.y=2;e.visual.z=3;e.visual.yaw=short(frame);e.visual.animationId=7;e.visual.visible=1;}
    return feed(capture,e);
}
API int input(unsigned frame,unsigned buttons,unsigned flags) {
    GhostTraceDecode::Event e={};e.type=GhostTraceDecode::INPUT;e.frame=frame;e.input.flags=flags;
    e.input.raw.buttons=static_cast<unsigned short>(buttons);e.input.raw.stickX=-50;e.input.raw.error=-1;
    return feed(capture,e);
}
API int end(){return finish(capture);}
API int flush() {
    const Page *page=pendingPage(capture.builder);if(!page)return 0;
    memcpy(stored[page->ordinal],capture.builder.samples,page->count*sizeof(Sample));
    return commitPage(capture.builder);
}
API int decode_begin(unsigned version,unsigned game,unsigned caps){return GhostTraceDecode::begin(decoder,version,game,caps,0x20000);}
API int decode_chunk(const void *data,unsigned bytes) {
    if(!GhostTraceDecode::pushChunk(decoder,data,bytes))return 100+decoder.error;
    GhostTraceDecode::Event event;
    for(;;) {
        const auto state=GhostTraceDecode::next(decoder,event);
        if(state==GhostTraceDecode::CHUNK_DONE)return 0;
        if(state==GhostTraceDecode::FAILED)return 100+decoder.error;
        for(;;) {
            const auto result=feed(capture,event);
            if(result==ACCEPTED)break;
            if(result!=PAGE_READY||!flush())return 200+capture.builder.error;
        }
    }
}
API unsigned error(){return capture.builder.error;}
API unsigned count(){return capture.builder.count;}
API unsigned segment(unsigned page){return pages[page].segment;}
API unsigned page_count(unsigned page){return pages[page].count;}
API unsigned page_bytes(){return sizeof(Sample)*kSamplesPerPage;}
API unsigned control_bytes(){return sizeof(Capture)+sizeof(GhostTraceRaceStream::Stream);}
API int directory(){return validDirectory(pages,capture.builder.count);}
API int validate(unsigned page){return validPage(pages[page],stored[page],pages[page].count*sizeof(Sample));}
API void corrupt(unsigned page,unsigned offset){reinterpret_cast<unsigned char*>(stored[page])[offset]^=1;}
API void corrupt_directory(unsigned page,unsigned field,unsigned value){reinterpret_cast<unsigned*>(pages+page)[field]=value;}
API int query(unsigned segment,int qf) {
    const Query q=byQf(segment,qf);if(!locate(pages,capture.builder.count,q,needed))return 0;
    return bracket(q,pages[needed.first],stored[needed.first],pages[needed.second],stored[needed.second],result);
}
API int frame_query(unsigned segment,unsigned frame) {
    const Query q=byFrame(segment,frame);if(!locate(pages,capture.builder.count,q,needed))return 0;
    return bracket(q,pages[needed.first],stored[needed.first],pages[needed.second],stored[needed.second],result);
}
API unsigned needed_first(){return needed.first;}
API unsigned needed_second(){return needed.second;}
API unsigned before_frame(){return result.before->frame;}
API unsigned after_frame(){return result.after->frame;}
API int before_qf(){return result.before->qf;}
API int after_qf(){return result.after->qf;}
API unsigned before_flags(){return result.before->flags;}
API unsigned before_buttons(){return result.before->raw.buttons;}
API int before_stick(){return result.before->raw.stickX;}
API float alpha(){return result.alpha;}
API int clamped(){return result.clamped;}
API int invalid_sample(unsigned kind) {
    Sample sample={};sample.frame=1;sample.flags=POSE|QFT;sample.visible=1;Identity id={0xd00,1,1};
    if(kind==0)sample.x=std::numeric_limits<float>::infinity();
    if(kind==1)sample.flags|=32;
    if(kind==2)sample.raw.buttons=1;
    if(kind==3)sample.fludd.mode=255;
    if(kind==4)sample.flags=QFT;
    if(kind==5)sample.reserved[0]=1;
    if(kind==6)sample.flags=POSE,sample.qf=1;
    if(kind==7)id.scene=0x10000;
    if(kind==8)sample.animationId=336;
    if(kind==9)sample.animationPhase=4096;
    if(kind==10)sample.yoshi=6;
    if(kind==11)sample.fludd.mode=0x80;
    if(kind==12)sample.raw.buttons=0x80,sample.flags|=INPUT;
    return append(capture.builder,id,sample);
}
API int alias_begin(unsigned kind) {
    Builder b={};
    if(kind==0)return begin(b,reinterpret_cast<Page*>(scratch+32),1,scratch+32,kPageBytes);
    if(kind==1)return begin(b,pages,1,&b,kPageBytes);
    if(kind==2)return begin(b,pages,1,scratch+33,kPageBytes);
    return begin(b,pages,1,scratch+32,kPageBytes-1);
}
API int open_stream(unsigned n){return GhostTraceRaceStream::begin(streams[n],arena,pages,capture.builder.count);}
API int request(unsigned n,unsigned segment,int qf){return GhostTraceRaceStream::request(streams[n],byQf(segment,qf));}
API int next(unsigned n){return GhostTraceRaceStream::nextRead(streams[n],reads[n]);}
API unsigned sequence(unsigned n){return reads[n].sequence;}
API unsigned offset(unsigned n){return reads[n].offset;}
API unsigned read_bytes(unsigned n){return reads[n].bytes;}
API int complete(unsigned n,unsigned sequence,int corruption,int success) {
    auto &r=reads[n];memcpy(r.destination,reinterpret_cast<unsigned char*>(stored)+r.offset,r.bytes);
    if(corruption)static_cast<unsigned char*>(r.destination)[7]^=1;
    return GhostTraceRaceStream::acceptRead(streams[n],sequence,r.bytes,success!=0);
}
API int stale(unsigned n,unsigned seq){return GhostTraceRaceStream::acceptRead(streams[n],seq,0,true);}
API int stream_sample(unsigned n){return GhostTraceRaceStream::sample(streams[n],result);}
API int stream_error(unsigned n){return streams[n].error;}
API int close_stream(unsigned n){return GhostTraceRaceStream::close(streams[n]);}
API unsigned available(){return GhostArena::available(arena);}
API int record_writable(){return GhostArena::write(arena,recording,GhostArena::RECORDING).bytes==65536;}
API int guards(){for(unsigned i=0;i<32;++i)if(scratch[i]!=0xa5||scratch[32+kPageBytes+i]!=0xa5)return 0;return 1;}
'''


class IndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='moonshine-trace-index-')
        cls.addClassCleanup(cls.temp.cleanup)
        out = Path(cls.temp.name)
        (out / 'fixture.cpp').write_text(FIXTURE, encoding='utf-8')
        env = dict(os.environ, PATH='C:/msys64/mingw64/bin;' + os.environ['PATH'])
        run = subprocess.run(['C:/msys64/mingw64/bin/g++.exe', '-std=c++11', '-O2',
                              '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-shared', '-static', '-I', str(ROOT / 'include'),
                              str(out / 'fixture.cpp'), str(ROOT / 'src/ghost_trace_index.cpp'),
                              str(ROOT / 'src/ghost_arena.cpp'), str(ROOT / 'src/ghost_world_witness.cpp'), str(ROOT / 'src/ghost_trace_race_stream.cpp'), str(ROOT / 'src/ghost_trace_decode.cpp'), '-o', str(out / 'index.dll')],
                             env=env, capture_output=True, text=True, encoding='utf-8')
        if run.returncode:
            raise RuntimeError(run.stderr)
        cls.lib = C.CDLL(str(out / 'index.dll'))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.alpha.restype = C.c_float
        cls.lib.decode_chunk.argtypes = [C.c_void_p, C.c_uint]

    def setUp(self):
        self.assertEqual(self.lib.reset(64), 1)

    def tearDown(self):
        self.assertEqual(self.lib.guards(), 1)

    def visual(self, frame, qf, flags=3, scene=0xd00, attempt=1, generation=1):
        while True:
            result = self.lib.visual(frame, qf, flags, scene, attempt, generation)
            if result != 1:
                self.assertEqual(result, 0, f'index error {self.lib.error()}')
                return
            self.assertEqual(self.lib.flush(), 1)

    def finish(self):
        while True:
            result = self.lib.end()
            if result != 1:
                self.assertEqual(result, 2, f'index error {self.lib.error()}')
                break
            self.assertEqual(self.lib.flush(), 1)
        self.assertEqual(self.lib.directory(), 1)
        for page in range(self.lib.count()):
            self.assertEqual(self.lib.validate(page), 1)

    def frames(self, count=260):
        for i in range(count):
            self.visual(i + 1, i * 4)
        self.finish()

    def load_stream(self, stream=0):
        reads = 0
        while self.lib.next(stream):
            self.assertEqual(self.lib.stream_sample(stream), 0)
            self.assertEqual(self.lib.complete(stream, self.lib.sequence(stream), 0, 1), 1)
            reads += 1
        self.assertEqual(self.lib.stream_sample(stream), 1)
        return reads

    def test_sample_sizes_page_boundaries_and_exact_qf(self):
        self.frames()
        self.assertEqual(self.lib.page_bytes(), 8192)
        self.assertEqual(self.lib.count(), 3)
        self.assertEqual([self.lib.page_count(i) for i in range(3)], [128, 128, 4])
        self.assertEqual(self.lib.query(0, 510), 1)
        self.assertEqual((self.lib.before_qf(), self.lib.after_qf()), (508, 512))
        self.assertAlmostEqual(self.lib.alpha(), .5)
        self.assertEqual((self.lib.needed_first(), self.lib.needed_second()), (0, 1))

    def test_input_pairs_only_matching_boundary_and_keeps_signed_raw(self):
        self.visual(1, -8)
        self.assertEqual(self.lib.input(1, 1, 0), 0)
        self.assertEqual(self.lib.input(1, 0x400, 0x80000003), 0)
        self.visual(2, -4)
        self.assertEqual(self.lib.input(2, 0x100, 0), 0)
        self.finish()
        self.assertEqual(self.lib.query(0, -8), 1)
        self.assertEqual(self.lib.before_buttons(), 0x400)
        self.assertEqual(self.lib.before_stick(), -50)
        self.assertEqual(self.lib.before_flags(), 31)
        self.assertEqual(self.lib.query(0, -4), 1)
        self.assertEqual(self.lib.before_flags(), 3)
        self.assertEqual(self.lib.before_buttons(), 0)

    def test_missing_poses_and_frame_gaps_do_not_interpolate(self):
        self.visual(1, 0)
        self.visual(2, 4, flags=2)
        self.visual(3, 8)
        self.visual(6, 12)
        self.finish()
        for qf, expected in ((2, 1), (6, 2), (10, 3)):
            self.assertEqual(self.lib.query(0, qf), 1)
            self.assertEqual(self.lib.before_frame(), expected)
            self.assertEqual(self.lib.after_frame(), expected)
            self.assertEqual(self.lib.alpha(), 0)

    def test_identity_clock_and_regression_start_new_segments(self):
        self.visual(1, 20)
        self.visual(2, 4)
        self.visual(3, 8, attempt=2)
        self.visual(4, 12, attempt=2, generation=2)
        self.visual(5, 16, scene=0x700, attempt=2, generation=2)
        self.visual(6, 99, flags=1, scene=0x700, attempt=2, generation=2)
        self.finish()
        self.assertEqual(self.lib.count(), 6)
        self.assertEqual([self.lib.segment(i) for i in range(6)], list(range(6)))
        self.assertEqual(self.lib.query(5, 0), 0)
        self.assertEqual(self.lib.frame_query(5, 6), 1)
        self.assertEqual(self.lib.before_qf(), 0)

    def test_duplicate_qf_uses_latest_observed_frame_across_pages(self):
        for i in range(260):
            self.visual(i + 1, 0 if i < 258 else 4)
        self.finish()
        self.assertEqual(self.lib.query(0, 0), 1)
        self.assertEqual(self.lib.before_frame(), 258)
        self.assertEqual(self.lib.after_frame(), 259)
        self.assertEqual(self.lib.query(0, 4), 1)
        self.assertEqual(self.lib.before_frame(), 260)

    def test_outside_range_clamps_without_inventing_input(self):
        self.frames(3)
        self.assertEqual(self.lib.query(0, -10), 1)
        self.assertEqual(self.lib.before_frame(), 1)
        self.assertEqual(self.lib.clamped(), 1)
        self.assertEqual(self.lib.query(0, 100), 1)
        self.assertEqual(self.lib.before_frame(), 3)
        self.assertEqual(self.lib.clamped(), 1)
        self.assertEqual(self.lib.query(9, 0), 0)

    def test_unconsumed_event_can_retry_after_page_publication(self):
        for i in range(129):
            self.assertEqual(self.lib.visual(i + 1, i * 4, 3, 0xd00, 1, 1), 0)
        self.assertEqual(self.lib.visual(130, 516, 3, 0xd00, 1, 1), 1)
        self.assertEqual(self.lib.count(), 0)
        self.assertEqual(self.lib.flush(), 1)
        self.assertEqual(self.lib.visual(130, 516, 3, 0xd00, 1, 1), 0)
        self.finish()
        self.assertEqual(self.lib.query(0, 512), 1)
        self.assertEqual(self.lib.before_frame(), 129)

    def test_capacity_is_explicit_failure_without_silent_truncation(self):
        self.assertEqual(self.lib.reset(1), 1)
        for i in range(129):
            self.visual(i + 1, i * 4)
        self.assertEqual(self.lib.end(), 1)
        self.assertEqual(self.lib.flush(), 1)
        self.assertEqual(self.lib.end(), 3)
        self.assertEqual(self.lib.error(), 4)
        self.assertEqual(self.lib.validate(0), 1)

    def test_bad_samples_aliases_and_order_are_refused(self):
        for case in range(13):
            self.assertEqual(self.lib.reset(64), 1)
            self.assertEqual(self.lib.invalid_sample(case), 3)
        for case in range(4):
            self.assertEqual(self.lib.alias_begin(case), 0)
        self.assertEqual(self.lib.reset(64), 1)
        self.visual(2, 0)
        self.assertEqual(self.lib.visual(1, 4, 3, 0xd00, 1, 1), 3)

    def test_cache_corruption_and_bad_directory_are_refused(self):
        self.frames()
        self.lib.corrupt(0, 20)
        self.assertEqual(self.lib.validate(0), 0)
        self.lib.corrupt_directory(1, 1, 9)
        self.assertEqual(self.lib.directory(), 0)
        self.assertEqual(self.lib.open_stream(0), 0)
        self.assertEqual(self.lib.available(), 65536)

    def test_racing_and_watch_two_coexist_with_recording(self):
        self.frames()
        for stream, qf in ((0, 510), (1, 1030)):
            self.assertEqual(self.lib.open_stream(stream), 1)
            self.assertEqual(self.lib.request(stream, 0, qf), 1)
            self.assertGreater(self.load_stream(stream), 0)
        self.assertEqual(self.lib.available(), 32768)
        self.assertEqual(self.lib.record_writable(), 1)
        self.assertEqual(self.lib.stream_sample(0), 1)
        self.assertAlmostEqual(self.lib.alpha(), .5)
        self.assertEqual(self.lib.request(0, 0, 514), 1)
        self.assertEqual(self.load_stream(0), 1)
        for stream in (0, 1):
            self.assertEqual(self.lib.close_stream(stream), 1)
        self.assertEqual(self.lib.available(), 65536)

    def test_pending_io_blocks_close_and_stale_ack_does_not_unpin(self):
        self.frames()
        self.assertEqual(self.lib.open_stream(0), 1)
        self.assertEqual(self.lib.request(0, 0, 510), 1)
        self.assertEqual(self.lib.next(0), 1)
        seq = self.lib.sequence(0)
        self.assertEqual(self.lib.close_stream(0), 0)
        self.assertEqual(self.lib.request(0, 0, 100), 0)
        self.assertEqual(self.lib.stale(0, seq + 9), 0)
        self.assertEqual(self.lib.close_stream(0), 0)
        self.assertEqual(self.lib.complete(0, seq, 0, 1), 1)
        self.assertEqual(self.lib.close_stream(0), 1)
        self.assertEqual(self.lib.stale(0, seq), 0)

    def test_real_capture_reader_decoder_index_pipeline(self):
        path = ROOT / 'build/pr48-sd-trace/runtime-r12-capture.msgt'
        if not path.exists():
            self.skipTest('Private normalized-visual capture unavailable')
        from test_ghost_trace_reader import ReaderTests
        ReaderTests.setUpClass()
        try:
            reader = ReaderTests.lib
            with path.open('rb') as stream:
                header = stream.read(64)
                version, game, caps = (struct.unpack_from('>I', header, off)[0] for off in (4, 12, 28))
                self.assertEqual(self.lib.decode_begin(version, game, caps), 1)
                self.assertEqual(reader.start(path.stat().st_size), 1)
                while reader.state() == 0:
                    self.assertEqual(reader.next(), 1)
                    stream.seek(reader.offset())
                    data = stream.read(reader.size())
                    C.memmove(reader.target(), data, len(data))
                    self.assertEqual(reader.accept(len(data)), 1)
                    if reader.state() == 1:
                        self.assertEqual(self.lib.decode_chunk(reader.chunk(), reader.chunkSize()), 0)
                        self.assertEqual(reader.release(), 1)
                self.assertEqual(reader.state(), 2)
                self.assertEqual(reader.guards(), 1)
            self.finish()
            self.assertEqual(self.lib.count(), 2)
            self.assertEqual(sum(self.lib.page_count(i) for i in range(2)), 151)
            for qf, frame in ((1140, 1), (1740, 151)):
                self.assertEqual(self.lib.query(0, qf), 1)
                self.assertEqual(self.lib.before_frame(), frame)
                self.assertEqual(self.lib.before_qf(), qf)
                self.assertEqual(self.lib.before_flags(), 3)
            self.assertEqual(self.lib.open_stream(0), 1)
            self.assertEqual(self.lib.request(0, 0, 1650), 1)
            self.assertEqual(self.load_stream(), 2)
            self.assertAlmostEqual(self.lib.alpha(), .5)
            self.assertEqual(self.lib.close_stream(0), 1)
        finally:
            ReaderTests.doClassCleanups()

    def test_close_reopen_rejects_old_completion_sequence(self):
        self.frames()
        self.assertEqual(self.lib.open_stream(0), 1)
        self.assertEqual(self.lib.request(0, 0, 510), 1)
        self.assertEqual(self.lib.next(0), 1)
        old = self.lib.sequence(0)
        self.assertEqual(self.lib.complete(0, old, 0, 1), 1)
        self.assertEqual(self.lib.close_stream(0), 1)
        self.assertEqual(self.lib.open_stream(0), 1)
        self.assertEqual(self.lib.request(0, 0, 510), 1)
        self.assertEqual(self.lib.next(0), 1)
        new = self.lib.sequence(0)
        self.assertGreater(new, old)
        self.assertEqual(self.lib.stale(0, old), 0)
        self.assertEqual(self.lib.close_stream(0), 0)
        self.assertEqual(self.lib.complete(0, new, 0, 1), 1)
        self.assertEqual(self.lib.close_stream(0), 1)

    def test_corrupt_io_fails_but_returns_completed_lease_on_close(self):
        self.frames()
        self.assertEqual(self.lib.open_stream(0), 1)
        self.assertEqual(self.lib.request(0, 0, 510), 1)
        self.assertEqual(self.lib.next(0), 1)
        self.assertEqual(self.lib.complete(0, self.lib.sequence(0), 1, 1), 0)
        self.assertEqual(self.lib.stream_error(0), 2)
        self.assertEqual(self.lib.stream_sample(0), 0)
        self.assertEqual(self.lib.close_stream(0), 1)
        self.assertEqual(self.lib.available(), 65536)


if __name__ == '__main__':
    unittest.main()
