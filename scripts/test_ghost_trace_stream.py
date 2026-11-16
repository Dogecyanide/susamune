"""Production pump/native hooks/ARM service, with host address translation only."""
import ctypes as C
import hashlib, json, os, re, struct, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STAGE=ROOT
BUILD=ROOT/'build/pr59-stream-integrated'
sys.path.insert(0,str(ROOT/'scripts'))
import test_ghost_trace_read_storage as storage
import test_ghost_trace_reader as files
import test_ghost_trace_decode as records

ENV=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
BOOT=storage.BOOT

DRIVER=r'''
#include "susamune/ghost_trace_stream.hxx"
#include "susamune/ghost_trace_stream_native.hxx"
#include <cstring>
static GhostTraceIo::Transport transport;
static GhostArena::Arena arena;
static GhostTraceStreamNative::Context context;
static GhostTraceStream::Stream stream;
static GhostTraceDecode::Event event;
static unsigned ticket,publications,violations;
static MsTraceReadMailbox *hostMailboxes[2];
static MsTraceReadGrant *hostGrants[2];
static MsTraceMailbox *hostWriter;
static MoonshineGhostMemoryProof *hostProof;
static unsigned char *hostBanks[3];
static void *hostPointer(unsigned address){
 if(address>=MS_TRACE_BUFFER0_PPC&&address<MS_TRACE_BUFFER0_PPC+0x80000)return hostBanks[0]+address-MS_TRACE_BUFFER0_PPC;
 if(address>=MS_TRACE_BUFFER1_PPC&&address<MS_TRACE_BUFFER1_PPC+0x80000)return hostBanks[1]+address-MS_TRACE_BUFFER1_PPC;
 if(address>=MS_TRACE_UPPER_PPC+MS_TRACE_STREAM_PACKED_OFFSET&&address<MS_TRACE_BUFFER1_PPC)return hostBanks[2]+address-MS_TRACE_UPPER_PPC-MS_TRACE_STREAM_PACKED_OFFSET;
 return nullptr;
}
static GhostArena::Address hostAlias(const void *pointer){
 auto p=reinterpret_cast<GhostArena::Address>(pointer);
 for(unsigned i=0;i<3;++i){auto b=reinterpret_cast<GhostArena::Address>(hostBanks[i]);unsigned n=i==2?MS_TRACE_BUFFER1_OFFSET-MS_TRACE_STREAM_PACKED_OFFSET:0x80000;
  if(p>=b&&p-b<n)return (i==0?MS_TRACE_BUFFER0_PPC:i==1?MS_TRACE_BUFFER1_PPC:MS_TRACE_UPPER_PPC+MS_TRACE_STREAM_PACKED_OFFSET)+(p-b);}
 return 0;
}
namespace GhostMemory { bool ready(){return true;} }
static void DCInvalidateRange(void *,unsigned){}
static void DCFlushRange(void *pointer,unsigned bytes){
 for(unsigned i=0;i<2;++i)if(pointer==hostMailboxes[i]&&bytes==32&&hostMailboxes[i]->request.sequence){
  ++publications;const auto &c=transport.channels[i];const auto*e=GhostArena::find(arena,c.lease,GhostArena::WORKSPACE);
  if(!e||e->pending!=c.sequence||e->direction!=GhostArena::WRITES_MEMORY)++violations;
  if(c.operation==MS_TRACE_READ_DATA&&!MsTraceReadGrantValid(hostGrants[i],&hostMailboxes[i]->request,&hostMailboxes[i]->buffer,context.nonce))++violations;
 }
}
NATIVE_SOURCE
#include "src/state_codec.cpp"
#define API extern "C" __declspec(dllexport)
API int setup(void*m0,void*m1,void*g0,void*g1,void*w,void*p,void*b0,void*b1,void*gap){
 transport={};arena={};context={};stream={};ticket=publications=violations=0;
 hostMailboxes[0]=(MsTraceReadMailbox*)m0;hostMailboxes[1]=(MsTraceReadMailbox*)m1;
 hostGrants[0]=(MsTraceReadGrant*)g0;hostGrants[1]=(MsTraceReadGrant*)g1;
 hostWriter=(MsTraceMailbox*)w;hostProof=(MoonshineGhostMemoryProof*)p;
 hostBanks[0]=(unsigned char*)b0;hostBanks[1]=(unsigned char*)b1;hostBanks[2]=(unsigned char*)gap;
 return GhostTraceStreamNative::configure(context,transport,arena,BOOT_PLACEHOLDER);
}
API int start(unsigned nonce,unsigned run,unsigned region,unsigned required){return GhostTraceStream::open(stream,transport,0,{nonce,run,region},region==1?0x474d534a:region==2?0x474d5345:0x474d5350,required);}
API int pump(unsigned n){return GhostTraceStream::poll(stream,n);}
API int next(){return GhostTraceStream::nextEvent(stream,event,ticket);}
API int release(unsigned t){return GhostTraceStream::releaseEvent(stream,t?t:ticket);}
API int closeStream(){return GhostTraceStream::close(stream);}
API int cancelStream(){return GhostTraceStream::cancel(stream);}
API int closed(){return !stream.transport;}
API unsigned decoderReady(){return stream.decoderReady;}
API unsigned get(unsigned key){auto s=GhostTraceStream::status(stream);
 switch(key){case 0:return s.phase;case 1:return s.error;case 2:return s.detail;case 3:return s.fileBytes;case 4:return s.chunks;case 5:return s.buffered;
 case 6:return s.borrowed;case 7:return s.pending;case 8:return ticket;case 9:return GhostArena::available(arena);case 10:return publications;case 11:return violations;
 case 12:return event.type;case 13:return event.frame;case 14:return event.tick;case 15:return event.offset;case 16:return event.kind;case 17:return transport.channels[0].sequence;
 case 18:return transport.channels[0].lease.serial;case 19:return stream.current;case 20:return stream.fill;case 21:return sizeof(stream);case 22:return sizeof(transport);}
 return 0;
}
API int getCursor(void*p){return GhostTraceStream::cursor(stream,ticket,*static_cast<GhostTraceStream::Cursor*>(p));}
API const void* borrowed(){return stream.current<2?stream.decoder.chunk:nullptr;}
API unsigned borrowedBytes(){return stream.current<2?stream.decoder.bytes:0;}
API unsigned inputButtons(){return event.input.pad.buttons.held;}
API int pack(const char*p,unsigned n,char*out,unsigned cap){return LZ4_compress_default(p,out,n,cap);}
API void badAck(unsigned what){auto&c=transport.channels[0];auto&r=hostMailboxes[0]->response;
 r={MS_TRACE_READ_MAGIC,MS_TRACE_READ_VERSION,context.nonce,c.sequence,0,c.bytes,c.fileBytes,c.lease.serial};
 switch(what){case 0:r.lease++;break;case 1:r.ack--;break;case 2:r.bytes++;break;case 3:r.fileSize++;break;case 4:r.magic++;break;case 5:r.bootNonce++;break;}}
API unsigned pendingPin(){const auto&c=transport.channels[0];const auto*e=GhostArena::find(arena,c.lease,GhostArena::WORKSPACE);return e?e->pending:0;}
API void corruptLease(){arena.entry[stream.slots[0].lease.slot].serial++;}
API int grantValid(unsigned i){return MsTraceReadGrantValid(hostGrants[i],&hostMailboxes[i]->request,&hostMailboxes[i]->buffer,context.nonce);}
API int aliasEvent(){return GhostTraceStream::nextEvent(stream,*reinterpret_cast<GhostTraceDecode::Event*>(hostBanks[0]),ticket);}
API int aliasCursor(){return GhostTraceStream::cursor(stream,ticket,*reinterpret_cast<GhostTraceStream::Cursor*>(hostBanks[0]));}
'''

def compile_run(command):
    p=subprocess.run(command,capture_output=True,text=True,env=ENV)
    if p.returncode:raise RuntimeError(p.stdout+p.stderr)
    return p.stderr

def build_backend(folder):
    fixture=(ROOT/'scripts/ghost_kernel_fixture.h').read_text()
    fixture=fixture.replace('#define FIXTURE_FILES 60000','#define FIXTURE_FILES 20').replace('#define FIXTURE_WRITES 80','#define FIXTURE_WRITES 4')
    for name in ('f_close','f_rename_char','f_read','f_lseek','sync_before_read','sync_after_write'):
        fixture=fixture.replace(name+'(',{'f_close':'fixture_close','f_rename_char':'fixture_rename','f_read':'fixture_read','f_lseek':'fixture_seek','sync_before_read':'fixture_sync_before','sync_after_write':'fixture_sync_after'}[name]+'(')
    adapter=storage.ADAPTER.replace('static int f_close(FIL *f){return','static unsigned closes;\nstatic int f_close(FIL *f){++closes;return')
    adapter=adapter.replace('static unsigned char traceBuffers[2][MS_TRACE_BUFFER_BYTES+64];','static unsigned char traceBuffers[2][MS_TRACE_BUFFER_BYTES+64] __attribute__((aligned(32)));')
    # Include fixed native constants before the fixture remaps the ARM codec pointer.
    adapter=adapter.replace('#undef MS_TRACE_PACK_WORK_PHYS','#include "susamune/ghost_trace_stream_native.h"\nenum { TEST_SCRATCH_PHYS=MOONSHINE_GHOST_UPPER_PHYS_BASE+MS_TRACE_STREAM_PACKED_OFFSET, TEST_SCRATCH_BYTES=MS_TRACE_BUFFER1_OFFSET-MS_TRACE_STREAM_PACKED_OFFSET };\n#undef MS_TRACE_PACK_WORK_PHYS')
    read=storage.READ_ADAPTER.replace('static unsigned closes,publishCount','static unsigned publishCount')
    read=read.replace('#include "GhostTraceReadStorage.h"','#include "'+(ROOT/'launcher/kernel/GhostTraceReadStorage.h').as_posix()+'"\nstatic struct MsTraceReadGrant testGrants[2] __attribute__((aligned(32)));\nstatic unsigned char traceGap[TEST_SCRATCH_BYTES+64] __attribute__((aligned(32)));')
    read=read.replace('static void *transport(unsigned address){','static void *transport(unsigned address){\n if(address>=TEST_SCRATCH_PHYS&&address<TEST_SCRATCH_PHYS+TEST_SCRATCH_BYTES)return traceGap+32+address-TEST_SCRATCH_PHYS;')
    from test_ghost_trace_storage import writer_source
    writer=writer_source(ROOT)
    reader=(ROOT/'launcher/kernel/GhostTraceReadStorage.c').read_text()
    reader=re.sub(r'^#include .*$', '',reader,flags=re.M)
    reader=reader.replace('#define READERS ((struct TraceReaders*)(MS_TRACE_CONTROL_PHYS+MS_TRACE_READ_ARM_OFFSET))','static struct TraceReaders testReaders;\n#define READERS (&testReaders)')
    reader=reader.replace('#define READ_MAILBOX(i) ((volatile struct MsTraceReadMailbox*)MS_TRACE_READ_MAILBOX_PHYS(i))','#define READ_MAILBOX(i) (&readMailbox[i])')
    reader=reader.replace('(const void*)MOONSHINE_GHOST_PROOF_PHYS_BASE','&testProof').replace('(void*)b.physical','transport(b.physical)')
    reader=reader.replace('__attribute__((weak)) int GhostTraceReadStorageWindow','static int defaultReadWindow').replace('publish(','readPublish(')
    reader=reader.replace('MS_TRACE_PACK_WORK_PHYS+MS_TRACE_PACK_WORK_BYTES','((SUSAMUNE_TRACE_MENU_CODE_CONSOLE_PPC_BASE&0x7fffffffu)+SUSAMUNE_TRACE_MENU_CODE_SIZE)+MS_TRACE_PACK_WORK_BYTES')
    strong=(STAGE/'launcher/kernel/GhostTraceReadGrant.c').read_text()
    strong=re.sub(r'^#include .*$', '',strong,flags=re.M)
    strong=strong.replace('(const void*)MOONSHINE_GHOST_PROOF_PHYS_BASE','&testProof').replace('(const void*)MS_TRACE_CONTROL_PHYS','&traceMailbox')
    strong=strong.replace('(const void*)MS_TRACE_READ_MAILBOX_PHYS(channel)','&readMailbox[channel]').replace('(const void*)MS_TRACE_STREAM_GRANT_PHYS(channel)','&testGrants[channel]')
    exports=re.sub(r'int GhostTraceReadStorageWindow\(.*?\n\}',strong,storage.READ_EXPORTS,count=1,flags=re.S)
    exports=exports.replace('reset();','reset();memset(testGrants,0,sizeof(testGrants));memset(traceGap,0xa5,sizeof(traceGap));')
    exports+=r'''
__declspec(dllexport) void nativeInit(){
 unsigned*w=testProof.word;memset(&testProof,0,sizeof(testProof));
 w[MGM_MAGIC]=MOONSHINE_GHOST_MEMORY_MAGIC;w[MGM_ABI]=1;w[MGM_NONCE]=0x12345678;w[MGM_IOS]=0x003a1820;
 w[MGM_PHYSICAL]=w[MGM_SIMULATED]=0x04000000;w[MGM_ARENA_LOW]=0x90000800;w[MGM_ARENA_HIGH]=w[MGM_IPC_LOW]=0x935e0000;
 w[MGM_IPC_HIGH]=w[MGM_IOS_LOW]=0x93600000;w[MGM_LOADER_HIGH]=0x933e0000;w[MGM_LOADER_IPC_HIGH]=0x93400000;
 w[MGM_GAME]=0x474d534a;w[MGM_CHECKSUM]=MoonshineGhostMemoryChecksum(&testProof);
}
__declspec(dllexport) void* nativePointer(unsigned which){switch(which){case 0:return testGrants;case 1:return testGrants+1;case 2:return &traceMailbox;case 3:return &testProof;case 4:return traceGap+32;case 5:return traceBuffers[1]+32;}return 0;}
__declspec(dllexport) int gapGuards(){for(unsigned i=0;i<32;++i)if(traceGap[i]!=0xa5||traceGap[TEST_SCRATCH_BYTES+32+i]!=0xa5)return 0;return 1;}
__declspec(dllexport) int strongGrant(unsigned channel,unsigned nonce,unsigned lease){struct GhostTraceReadWindow w;return GhostTraceReadStorageWindow(channel,nonce,lease,&w);}
'''
    source=folder/'backend.c';source.write_text('#define MOONSHINE_GHOST_TRACE 1\n#define TRACE_READER_INTEGRATION 1\n'+fixture+adapter+read+reader+writer+storage.EXPORTS+exports)
    compile_run(['C:/msys64/mingw64/bin/gcc.exe','-shared','-O2','-std=gnu99','-fno-builtin','-static','-DMOONSHINE_GHOST_TRACE=1','-I',str(STAGE/'include'),'-I',str(ROOT/'include'),str(source),str(ROOT/'launcher/kernel/GhostTraceCompression.c'),'-o',str(folder/'backend.dll')])

def build_driver(folder):
    native=(STAGE/'src/ghost_trace_stream_native.cpp').read_text()
    native=re.sub(r'^#include .*$', '',native,flags=re.M)
    native=native.replace('reinterpret_cast<volatile MsTraceReadMailbox*>(MS_TRACE_READ_MAILBOX_PPC(channel))','hostMailboxes[channel]')
    native=native.replace('reinterpret_cast<volatile MsTraceReadGrant*>(MS_TRACE_STREAM_GRANT_PPC(channel))','hostGrants[channel]')
    native=native.replace('reinterpret_cast<A::Address>(span.data)','hostAlias(span.data)')
    native=native.replace('reinterpret_cast<volatile const MsTraceMailbox*>(MS_TRACE_CONTROL_PPC)','hostWriter')
    native=native.replace('reinterpret_cast<const MoonshineGhostMemoryProof*>(MOONSHINE_GHOST_PROOF_PPC_BASE)','hostProof')
    native=re.sub(r'reinterpret_cast<void\*>\((MS_TRACE_BUFFER[01]_PPC|MS_TRACE_UPPER_PPC\+MS_TRACE_STREAM_PACKED_OFFSET|MS_TRACE_STREAM_IO_PPC\([01]\))\)',r'hostPointer(\1)',native)
    source=folder/'driver.cpp';source.write_text(DRIVER.replace('NATIVE_SOURCE',native).replace('BOOT_PLACEHOLDER',str(BOOT)+'u'))
    compile_run(['C:/msys64/mingw64/bin/g++.exe','-std=c++17','-O2','-Wall','-Wextra','-shared','-static','-I',str(STAGE/'include'),'-I',str(ROOT/'include'),'-I',str(ROOT),str(source),str(STAGE/'src/ghost_trace_stream.cpp'),str(STAGE/'src/ghost_trace_reader.cpp'),str(ROOT/'src/ghost_arena.cpp'),str(ROOT/'src/ghost_trace_io.cpp'),str(ROOT/'src/ghost_trace_decode.cpp'),str(ROOT/'src/ghost_world_witness.cpp'),'-o',str(folder/'driver.dll')])

class StreamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder=BUILD/'test-build';folder.mkdir(parents=True,exist_ok=True);build_backend(folder);build_driver(folder)
        cls.arm=C.CDLL(str(folder/'backend.dll'));cls.ppc=C.CDLL(str(folder/'driver.dll'))
        for lib in (cls.arm,cls.ppc):cls.addClassCleanup(lambda lib=lib:C.windll.kernel32.FreeLibrary(C.c_void_p(lib._handle)))
        p,u=C.c_void_p,C.c_uint
        for n in ('mailboxBytes','received','nativePointer'):getattr(cls.arm,n).argtypes=[u];getattr(cls.arm,n).restype=p
        for n,args in {'install':[u,u,p,u,u],'readFault':[u,u],'readStep':[u],'owned':[u,u],'strongGrant':[u,u,u]}.items():getattr(cls.arm,n).argtypes=args
        cls.ppc.setup.argtypes=[p]*9;cls.ppc.start.argtypes=[u]*4
        for n in ('pump','get','release','badAck'):getattr(cls.ppc,n).argtypes=[u]
        cls.ppc.getCursor.argtypes=[p];cls.ppc.borrowed.restype=p;cls.ppc.pack.argtypes=[p,u,p,u]
        cls.receipts=[]

    def setUp(self):
        self.arm.readReset();self.arm.nativeInit();self.owners=[]
        self.assertTrue(self.ppc.setup(self.arm.mailboxBytes(0),self.arm.mailboxBytes(1),*(self.arm.nativePointer(i) for i in range(4)),self.arm.received(0x13408000),self.arm.nativePointer(5),self.arm.nativePointer(4)))

    def tearDown(self):
        self.assertEqual(self.arm.guards(),1);self.assertEqual(self.arm.gapGuards(),1);self.assertEqual(self.ppc.get(11),0)

    def install(self,data):
        game,nonce,run=struct.unpack_from('>3I',data,12);region={0x474d534a:1,0x474d5345:2,0x474d5350:3}[game]
        owner=C.create_string_buffer(data);self.owners.append(owner);self.arm.install(nonce,run,owner,len(data),0)
        self.assertTrue(self.ppc.start(nonce,run,region,0));return nonce,run

    def tick(self,n=1):
        for _ in range(n):self.arm.readStep(1);self.ppc.pump(4)

    def pack(self,data):
        out=C.create_string_buffer(len(data)+len(data)//255+32);n=self.ppc.pack(data,len(data),out,len(out));self.assertGreater(n,0);return out.raw[:n]

    def drain(self,maxsteps=1000000):
        events=[]
        for _ in range(maxsteps):
            result=self.ppc.next()
            if result==1:
                events.append(tuple(self.ppc.get(i) for i in (16,13,14,15)))
                self.assertTrue(self.ppc.release(0))
            elif result==2:return events
            elif result==3:self.fail(f'stream failed: {self.ppc.get(1)}/{self.ppc.get(2)}')
            else:self.tick()
        self.fail('stream did not finish')

    def finish(self):
        self.ppc.closeStream();self.tick(8);self.assertTrue(self.ppc.closed());self.assertEqual(self.ppc.get(9),0x10c000)

    def synthetic(self,nchunks=4):
        chunks=[]
        for i in range(nchunks):
            frame=i+1;body=records.frame(tick=frame)
            chunks.append(files.record(frame,frame,body,2)+b''.join(files.record(frame,frame,b'x'*60000,99) for _ in range(8)))
        return chunks

    def test_multi_megabyte_raw_and_compressed_roundtrip_with_bounded_work(self):
        chunks=self.synthetic()
        for compressed in (None,self.pack):
            with self.subTest(compressed=bool(compressed)):
                self.setUp();data=files.capture(chunks,game=records.GAME,compressed=compressed);self.install(data)
                events=self.drain();self.assertEqual([e[1] for e in events],[1,2,3,4]);self.assertLessEqual(self.arm.stat(2),0x4000)
                self.assertEqual(self.ppc.get(4),4);self.finish()

    def test_adjacent_compressed_headers_reuse_transport_read_ahead(self):
        chunks=self.synthetic(2)
        data=files.capture(chunks,game=records.GAME,compressed=self.pack)
        self.assertLess(len(data),0x4000)
        self.install(data);events=self.drain()
        self.assertEqual([event[1] for event in events],[1,2])
        self.assertEqual(self.arm.stat(0),3) # ARM header/footer admission plus one shared body window.
        self.finish()

    def test_prefetch_preserves_borrowed_chunk_and_stops_at_two_outputs(self):
        chunks=self.synthetic();self.install(files.capture(chunks,game=records.GAME))
        while self.ppc.next()!=1:self.tick()
        pointer=self.ppc.borrowed();size=self.ppc.borrowedBytes();before=C.string_at(pointer,size);ticket=self.ppc.get(8)
        self.tick(200);self.assertEqual(self.ppc.get(4),2);self.assertEqual(self.ppc.get(5),2)
        self.assertEqual(C.string_at(pointer,size),before);self.assertEqual(self.ppc.next(),4)
        self.assertFalse(self.ppc.release(ticket+1));self.assertEqual(C.string_at(pointer,size),before)
        cursor=(C.c_uint*13)();self.assertTrue(self.ppc.getCursor(cursor));self.assertEqual(list(cursor)[3:6],[1,len(chunks[0]),files.fnv(chunks[0])])
        self.assertTrue(self.ppc.release(ticket));self.assertEqual(len(self.drain()),3);self.finish()

    def test_cancel_pending_waits_for_exact_ack_and_close_and_borrow(self):
        self.install(files.capture(self.synthetic(),game=records.GAME));available=self.ppc.get(9);seq=self.ppc.get(17)
        self.assertFalse(self.ppc.cancelStream())
        for _ in range(1000):self.ppc.pump(16)
        self.assertFalse(self.ppc.closed());self.assertEqual(self.ppc.get(9),available);self.assertEqual(self.ppc.pendingPin(),seq)
        self.tick(1);self.assertFalse(self.ppc.closed());self.tick(1);self.assertTrue(self.ppc.closed())
        self.setUp();self.install(files.capture(self.synthetic(),game=records.GAME))
        while self.ppc.next()!=1:self.tick()
        pointer=self.ppc.borrowed();before=C.string_at(pointer,self.ppc.borrowedBytes());self.ppc.cancelStream();self.tick(10)
        self.assertFalse(self.ppc.closed());self.assertEqual(C.string_at(pointer,len(before)),before)
        self.assertTrue(self.ppc.release(0));self.assertTrue(self.ppc.closed())

    def test_bad_ack_is_pinned_until_correct_receipt(self):
        self.install(files.capture(self.synthetic(),game=records.GAME));self.tick(1)
        seq=self.ppc.get(17);self.assertTrue(self.ppc.pendingPin())
        for which in range(5):
            self.ppc.badAck(which);self.ppc.pump(1);self.assertEqual(self.ppc.pendingPin(),seq);self.assertEqual(self.ppc.next(),0)
        self.tick(1);self.assertGreater(self.ppc.get(17),seq);self.assertEqual(len(self.drain()),4);self.finish()

    def test_close_failure_and_epoch_change_never_free_storage(self):
        for epoch in (False,True):
            with self.subTest(epoch=epoch):
                self.setUp();self.install(files.capture(self.synthetic(),game=records.GAME));self.tick(1)
                if epoch:self.arm.readFault(6,BOOT+1)
                else:self.arm.readFault(1,1);self.arm.readFault(3,1)
                self.tick(12);self.assertFalse(self.ppc.closed());self.assertEqual(self.ppc.get(0),5)
                if epoch:
                    self.assertTrue(self.ppc.pendingPin());self.ppc.cancelStream();self.tick(10);self.assertFalse(self.ppc.closed())
                else:
                    self.arm.readFault(1,0);self.arm.readFault(3,0);self.ppc.closeStream();self.tick(3);self.assertTrue(self.ppc.closed())

    def test_corrupt_chunk_never_publishes_events(self):
        data=bytearray(files.capture(self.synthetic(1),game=records.GAME));data[100]^=1;self.install(bytes(data))
        for _ in range(80):self.tick();self.assertNotEqual(self.ppc.next(),1)
        self.assertEqual(self.ppc.get(1),4);self.assertEqual(self.ppc.get(2),6);self.assertTrue(self.ppc.closed())

    def test_exact_footer_and_empty_stream(self):
        for data in (files.capture([],game=records.GAME),):
            self.install(data);self.assertEqual(self.drain(),[]);self.finish()
        self.setUp();data=bytearray(files.capture(self.synthetic(1),game=records.GAME));struct.pack_into('>I',data,len(data)-24,2)
        self.install(bytes(data))
        for _ in range(120):self.tick();self.ppc.next();self.ppc.release(0)
        self.assertEqual(self.ppc.get(1),4);self.assertTrue(self.ppc.closed())

    def test_native_grant_rejects_every_other_destination_and_recorder(self):
        self.install(files.capture(self.synthetic(),game=records.GAME));self.tick(1)
        grant=C.cast(self.arm.nativePointer(0),C.POINTER(C.c_uint));box=C.cast(self.arm.mailboxBytes(0),C.POINTER(C.c_uint));lease=self.ppc.get(18)
        self.assertTrue(self.arm.strongGrant(0,BOOT,lease));original=list(grant[:8]);oldb=list(box[8:16])
        for address in (0,0x80000000,0x13400000,0x13408000,0x13488000,0x13498000,0x134c8000,0x134d8000,0x134fc000,0x13508000,0x13588000,0x135e0000):
            grant[4]=box[8]=address;self.assertFalse(self.arm.strongGrant(0,BOOT,lease),hex(address))
        for i,v in enumerate(original):grant[i]=v
        for i,v in enumerate(oldb):box[i+8]=v
        for index in (0,1,2,3,5,6,7):
            old=grant[index];grant[index]^=1;self.assertFalse(self.arm.strongGrant(0,BOOT,lease));grant[index]=old
        writer=C.cast(self.arm.nativePointer(2),C.POINTER(C.c_uint));writer[28]=2
        self.assertFalse(self.arm.strongGrant(0,BOOT,lease));writer[28]=0
        self.assertTrue(self.arm.strongGrant(0,BOOT,lease));self.ppc.cancelStream();self.tick(4)

    def test_reopen_retains_monotonic_operation_and_event_tickets(self):
        data=files.capture([files.record(1,1,records.frame(tick=1),2)],game=records.GAME)
        self.install(data);self.assertEqual(len(self.drain()),1);oldticket=self.ppc.get(8);self.finish();oldseq=self.ppc.get(17)
        self.install(data);self.assertGreater(self.ppc.get(17),oldseq)
        while self.ppc.next()!=1:self.tick()
        self.assertGreater(self.ppc.get(8),oldticket);self.assertFalse(self.ppc.release(oldticket));self.ppc.release(0);self.drain();self.finish()

    def test_closed_tas_decoder_cannot_admit_the_next_clean_watch(self):
        chunks=[files.record(1,1,records.frame(tick=1),2)]
        clean=files.capture(chunks,game=records.GAME)
        tas=bytearray(clean)
        struct.pack_into('>2I',tas,36,0x21,0x50525631)
        struct.pack_into('>I',tas,60,files.fnv(tas[:60]))
        self.install(bytes(tas))
        self.assertEqual(len(self.drain()),1)
        self.assertTrue(self.ppc.decoderReady())
        self.finish()
        self.assertFalse(self.ppc.decoderReady())
        self.install(clean)
        self.assertFalse(self.ppc.decoderReady())
        self.assertEqual(len(self.drain()),1)
        self.assertTrue(self.ppc.decoderReady())
        self.finish()

    def test_delta_baselines_survive_prefetch_and_chunk_rotation(self):
        old=records.input_body(buttons=0x100);new=records.input_body(buttons=0x200)
        chunks=[files.record(1,1,records.frame(tick=1),2)+files.record(1,1,old,14),
                files.record(2,2,records.frame(tick=2),2)+files.record(2,2,records.delta(old,new),20)]
        data=bytearray(files.capture(chunks,game=records.GAME,compressed=self.pack))
        self.install(bytes(data));buttons=[]
        for _ in range(100):
            result=self.ppc.next()
            if result==1:
                if self.ppc.get(12)==1:buttons.append(self.ppc.inputButtons())
                self.assertFalse(self.ppc.aliasCursor());self.ppc.release(0)
            elif result==2:break
            elif result==3:self.fail(f'{self.ppc.get(1)}/{self.ppc.get(2)}')
            else:
                self.assertEqual(self.ppc.aliasEvent(),3);self.tick()
        self.assertEqual(buttons,[0x100,0x200]);self.finish()

    def test_lost_output_lease_is_quarantined_before_reader_copy(self):
        self.install(files.capture(self.synthetic(1),game=records.GAME));self.tick(1)
        before=C.string_at(self.arm.received(0x13408000),0x80000)
        self.ppc.corruptLease();self.tick(4)
        self.assertEqual(self.ppc.get(1),2);self.assertFalse(self.ppc.closed())
        self.assertEqual(C.string_at(self.arm.received(0x13408000),0x80000),before)
        self.ppc.closeStream();self.tick(8);self.assertFalse(self.ppc.closed())

    def test_real_wii_files(self):
        paths=sorted((ROOT/'build/pr48-sd-trace/wii-r9-captures').glob('*.msgt'))
        self.assertTrue(paths,'actual Wii captures are required for this receipt')
        # One large capture plus the existing reference capture; every read uses actual ARM code.
        chosen={max(paths,key=lambda p:p.stat().st_size),ROOT/'build/pr48-sd-trace/wii-r9-captures/trace_A4362729_8C9D5ED7.msgt'}
        for p in sorted(chosen):
            with self.subTest(file=p.name):
                self.setUp();data=p.read_bytes();self.install(data);events=self.drain();self.assertTrue(events);self.finish()
                self.receipts.append({'file':str(p),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'events':len(events),'reads':self.arm.stat(0),'max_read':self.arm.stat(2)})

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(StreamTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    (BUILD/'test-results.json').write_text(json.dumps({'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'real_files':getattr(StreamTests,'receipts',[])},indent=2))
    sys.exit(not result.wasSuccessful())

