"""Execute both production trace services against guarded memory and in-memory FatFS."""
import ctypes as C
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import unittest

from test_ghost_trace_storage import ADAPTER, EXPORTS

ROOT = Path(__file__).resolve().parents[1]
BOOT = 0x12345678
FILE_NONCE = 0x87654321
BASE = 0x13408000
BASE1 = 0x13508000

READ_ADAPTER = r'''
#include "GhostTraceReadStorage.h"
int GhostTraceChildDependencyValid(const unsigned char*,unsigned,unsigned,unsigned);
int GhostTraceBranchLookup(unsigned,unsigned,unsigned,struct MsTraceLookup*);
static struct MsTraceReadMailbox readMailbox[2] __attribute__((aligned(32)));
static int (*externalWindow)(unsigned,unsigned,unsigned,unsigned*,unsigned*);
static unsigned grant,grantBase,grantBytes,recorderOwns,leaseValue;
static unsigned readFailure,shortFailure,seekFailure,epochAfterRead,revokeAfterRead;
static unsigned closes,publishCount,orderTick,dataPublication,responsePublication;
static void *transport(unsigned address){
 if(address>=MS_TRACE_BUFFER0_PPC-0x80000000u && address<MS_TRACE_BUFFER0_PPC-0x80000000u+MS_TRACE_BUFFER_BYTES)
  return traceBuffers[0]+32+address-(MS_TRACE_BUFFER0_PPC-0x80000000u);
 if(address>=MS_TRACE_BUFFER1_PPC-0x80000000u && address<MS_TRACE_BUFFER1_PPC-0x80000000u+MS_TRACE_BUFFER_BYTES)
  return traceBuffers[1]+32+address-(MS_TRACE_BUFFER1_PPC-0x80000000u);
 return NULL;
}
static int f_read(FIL*f,void*p,UINT bytes,UINT*done){
 if(readFailure){*done=0;++readCalls;return FR_DISK_ERR;}
 int result=fixture_read(f,p,shortFailure&&bytes>1?bytes-1:bytes,done);
 if(epochAfterRead)testProof.word[MGM_NONCE]++;
 if(revokeAfterRead)grant=0;
 return result;
}
static int f_lseek(FIL*f,u32 offset){return seekFailure?FR_DISK_ERR:fixture_seek(f,offset);}
static void sync_before_read(void*p,u32 n){(void)p;(void)n;}
static void sync_after_write(void*p,u32 n){
 ++orderTick;
 for(unsigned i=0;i<2;++i){
  if(p==&readMailbox[i].response){responsePublication=orderTick;++publishCount;}
  if((unsigned char*)p>=traceBuffers[i]+32 && (unsigned char*)p<traceBuffers[i]+32+MS_TRACE_BUFFER_BYTES)dataPublication=orderTick;
 }
 (void)n;
}
'''

READ_EXPORTS = r'''
int GhostTraceReadStorageWindow(unsigned channel,unsigned nonce,unsigned lease,struct GhostTraceReadWindow*w){
 if(externalWindow)return externalWindow(channel,nonce,lease,&w->physical,&w->bytes);
 if(!grant)return defaultReadWindow(channel,nonce,lease,w);
 if(nonce!=testProof.word[MGM_NONCE]||lease!=leaseValue||recorderOwns)return 0;
 w->physical=grantBase;w->bytes=grantBytes;return 1;
}
__declspec(dllexport) void bindWindow(void*p){externalWindow=(int(*)(unsigned,unsigned,unsigned,unsigned*,unsigned*))p;}
__declspec(dllexport) void readReset(void){
 externalWindow=0;grant=recorderOwns=readFailure=shortFailure=seekFailure=epochAfterRead=revokeAfterRead=0;
 grantBase=MS_TRACE_BUFFER0_PPC-0x80000000u;grantBytes=MS_TRACE_BUFFER_BYTES;leaseValue=37;
 closes=publishCount=orderTick=dataPublication=responsePublication=0;
 initialized=0;memset(&testReaders,0,sizeof(testReaders));memset(readMailbox,0,sizeof(readMailbox));
 reset();
}
__declspec(dllexport) void install(unsigned nonce,unsigned run,const void*p,unsigned n,unsigned partial){
 char path[128];_sprintf(path,"/Moonshine data/ghosts/recordings/trace_%08X_%08X.%s",nonce,run,partial?"part":"msgt");
 int i=lookup(path);if(i<0)i=testCount++;
 strcpy(testFiles[i].path,path);testFiles[i].bytes=p;testFiles[i].size=n;testFiles[i].live=1;testFiles[i].writable=0;
}
__declspec(dllexport) void installAdmissionFile(const char*path,const void*p,unsigned n){
 int i=lookup(path);if(i<0)i=testCount++;strcpy(testFiles[i].path,path);testFiles[i].bytes=p;testFiles[i].size=n;testFiles[i].live=1;testFiles[i].writable=0;
}
__declspec(dllexport) void request(unsigned channel,const void*q,const void*b){
 memcpy(&readMailbox[channel].request,q,32);memcpy(&readMailbox[channel].buffer,b,32);
}
__declspec(dllexport) const void* readResponse(unsigned channel){return &readMailbox[channel].response;}
__declspec(dllexport) unsigned readStep(unsigned count){
 for(unsigned i=0;i<count&&GhostTraceStoragePending();++i)GhostTraceStorageService();
 return GhostTraceStoragePending();
}
__declspec(dllexport) unsigned readerPending(void){return GhostTraceReadStoragePending();}
__declspec(dllexport) unsigned readerScheduled(unsigned writer){return GhostTraceReadStorageService(writer);}
__declspec(dllexport) void window(unsigned enabled,unsigned base,unsigned bytes,unsigned lease,unsigned recording){
 grant=enabled;grantBase=base;grantBytes=bytes;leaseValue=lease;recorderOwns=recording;
}
__declspec(dllexport) void readFault(unsigned key,unsigned value){
 switch(key){case 0:readFailure=value;break;case 1:shortFailure=value;break;case 2:seekFailure=value;break;
 case 3:closeFailure=value;break;case 4:epochAfterRead=value;break;case 5:revokeAfterRead=value;break;
 case 6:testProof.word[MGM_NONCE]=value;break;}
}
__declspec(dllexport) unsigned owned(unsigned nonce,unsigned run){return GhostTraceReadStorageOwns(nonce,run);}
__declspec(dllexport) unsigned stat(unsigned key){switch(key){case 0:return readCalls;case 1:return openCalls;
 case 2:return maxRead;case 3:return closes;case 4:return dataPublication;case 5:return responsePublication;
 case 6:return publishCount;case 7:return sizeof(struct TraceReaders);case 8:return writeBytes;}return 0;}
__declspec(dllexport) unsigned layout(unsigned key){
 const unsigned values[]={MS_TRACE_BUFFER0_PPC-0x80000000u,MS_TRACE_BUFFER1_PPC-0x80000000u,
 MS_TRACE_CONTROL_PHYS,SUSAMUNE_TRACE_MENU_CODE_CONSOLE_PPC_BASE&0x7fffffffu,
 (SUSAMUNE_TRACE_MENU_CODE_CONSOLE_PPC_BASE&0x7fffffffu)+SUSAMUNE_TRACE_MENU_CODE_SIZE,
 (SUSAMUNE_TRACE_MENU_CODE_CONSOLE_PPC_BASE&0x7fffffffu)+SUSAMUNE_TRACE_MENU_CODE_SIZE+MS_TRACE_PACK_WORK_BYTES,
 MOONSHINE_GHOST_UPPER_PHYS_BASE,MOONSHINE_GHOST_UPPER_PHYS_BASE+MOONSHINE_GHOST_UPPER_SIZE,
 SUSAMUNE_MEM2_SNAPSHOT_PHYS_BASE,SUSAMUNE_CONSOLE_GHOST_RECORD_PHYS_BASE};
 return key<sizeof(values)/sizeof(values[0])?values[key]:0;
}
__declspec(dllexport) const void* mailboxBytes(unsigned channel){return &readMailbox[channel];}
__declspec(dllexport) void sizeChange(unsigned size){int i=lookup("/Moonshine data/ghosts/recordings/trace_87654321_00000007.msgt");testFiles[i].size=size;}
__declspec(dllexport) const void* received(unsigned address){return transport(address);}
'''


def hash_bytes(data):
    value=2166136261
    for b in data:value=((value^b)*16777619)&0xffffffff
    return value


def completed(nonce=FILE_NONCE,run=7,region=1,payload=bytes(range(256))*3):
    words=[0x4d535452,3,64,(0x474d534a,0x474d5345,0x474d5350)[region-1],nonce,run,0,0x4ff,0x80000]+[0]*6
    header=struct.pack('>15I',*words)
    header+=struct.pack('>I',hash_bytes(header))
    return header+payload+struct.pack('>8I',0x444f4e45,run,1,64+len(payload),0x4ff,0,0,0)


class TraceReadStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='trace-read-')
        cls.addClassCleanup(cls.temp.cleanup);folder=Path(cls.temp.name)
        fixture=(ROOT/'scripts/ghost_kernel_fixture.h').read_text(encoding='utf-8')
        fixture=fixture.replace('#define FIXTURE_FILES 60000','#define FIXTURE_FILES 20').replace('#define FIXTURE_WRITES 80','#define FIXTURE_WRITES 4').replace('#define FIXTURE_FILE_BYTES 1400000','#define FIXTURE_FILE_BYTES 2000000')
        for a,b in (('f_close(','fixture_close('),('f_rename_char(','fixture_rename('),('f_read(','fixture_read('),('f_lseek(','fixture_seek('),('sync_before_read(','fixture_sync_before('),('sync_after_write(','fixture_sync_after(')):
            fixture=fixture.replace(a,b)
        adapter=ADAPTER.replace('static int f_close(FIL *f){return','static unsigned closes;\nstatic int f_close(FIL *f){++closes;return')
        read_adapter=READ_ADAPTER.replace('static unsigned closes,publishCount','static unsigned publishCount')
        read_adapter=read_adapter.replace('#include \"GhostTraceReadStorage.h\"','#include \"'+(ROOT/'launcher/kernel/GhostTraceReadStorage.h').as_posix()+'\"')
        from test_ghost_trace_storage import writer_source
        writer=writer_source(ROOT)
        reader=(ROOT/'launcher/kernel/GhostTraceReadStorage.c').read_text(encoding='utf-8')
        reader=re.sub(r'^#include .*$', '',reader,flags=re.M)
        reader=reader.replace('#define READERS ((struct TraceReaders*)(MS_TRACE_CONTROL_PHYS+MS_TRACE_READ_ARM_OFFSET))','static struct TraceReaders testReaders;\n#define READERS (&testReaders)')
        reader=reader.replace('#define READ_MAILBOX(i) ((volatile struct MsTraceReadMailbox*)MS_TRACE_READ_MAILBOX_PHYS(i))','#define READ_MAILBOX(i) (&readMailbox[i])')
        reader=reader.replace('(const void*)MOONSHINE_GHOST_PROOF_PHYS_BASE','&testProof').replace('(void*)b.physical','transport(b.physical)')
        reader=reader.replace('__attribute__((weak)) int GhostTraceReadStorageWindow','static int defaultReadWindow').replace('publish(','readPublish(')
        # Keep native physical constants while redirecting only actual memory accesses.
        reader=reader.replace('MS_TRACE_PACK_WORK_PHYS+MS_TRACE_PACK_WORK_BYTES','((SUSAMUNE_TRACE_MENU_CODE_CONSOLE_PPC_BASE&0x7fffffffu)+SUSAMUNE_TRACE_MENU_CODE_SIZE)+MS_TRACE_PACK_WORK_BYTES')
        source=folder/'test.c'
        source.write_text('#define MOONSHINE_GHOST_TRACE 1\n#define TRACE_READER_INTEGRATION 1\n'+fixture+adapter+read_adapter+reader+writer+EXPORTS+READ_EXPORTS,encoding='utf-8')
        library=folder/'test.dll';env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
        result=subprocess.run(['C:/msys64/mingw64/bin/gcc.exe','-shared','-O2','-std=gnu99','-fno-builtin','-static','-I',str(ROOT/'include'),'-DMOONSHINE_GHOST_TRACE=1',str(source),str(ROOT/'launcher/kernel/GhostTraceCompression.c'),'-o',str(library)],capture_output=True,text=True,encoding='utf-8',env=env)
        if result.returncode:raise RuntimeError(result.stdout+result.stderr)
        cls.lib=C.CDLL(str(library));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        for name,args in {'bindWindow':[C.c_void_p],'install':[C.c_uint,C.c_uint,C.c_void_p,C.c_uint,C.c_uint],'installAdmissionFile':[C.c_char_p,C.c_void_p,C.c_uint],'request':[C.c_uint,C.c_void_p,C.c_void_p],'window':[C.c_uint]*5,'readFault':[C.c_uint]*2,'owned':[C.c_uint]*2,'received':[C.c_uint],'readResponse':[C.c_uint],'file':[C.c_uint,C.POINTER(C.c_uint)],'stat':[C.c_uint],'sizeChange':[C.c_uint],'mailboxBytes':[C.c_uint],'layout':[C.c_uint],'readStep':[C.c_uint],'readerScheduled':[C.c_uint],'submit':[C.c_uint]*4,'chunk':[C.c_uint]*3+[C.c_void_p,C.c_uint,C.c_uint]}.items():
            getattr(cls.lib,name).argtypes=args
        cls.lib.readResponse.restype=C.POINTER(C.c_uint);cls.lib.received.restype=C.c_void_p
        cls.lib.response.restype=C.POINTER(C.c_uint);cls.lib.mailboxBytes.restype=cls.lib.file.restype=C.c_void_p

    def setUp(self):
        self.lib.readReset();self.seq=[0,0];self.buffers=[]
        self.data=completed();self.install(self.data)

    def install(self,data,nonce=FILE_NONCE,run=7,partial=0):
        owner=C.create_string_buffer(data);self.buffers.append(owner)
        self.lib.install(nonce,run,owner,len(data),partial)

    def send(self,op,channel=0,nonce=FILE_NONCE,run=7,region=1,boot=BOOT,offset=0,size=0,address=0,capacity=None,lease=37,sequence=None,reserved=0):
        self.seq[channel]=self.seq[channel]+1 if sequence is None else sequence
        q=(C.c_uint*8)(0x4d535244,1,boot,self.seq[channel],op,nonce,run,region)
        b=(C.c_uint*8)(address,((size+31)&~31) if capacity is None else capacity,size,lease,offset,reserved,0,0)
        self.lib.request(channel,q,b)

    def result(self,channel=0):return list(self.lib.readResponse(channel)[:8])
    def step(self,n=20):return self.lib.readStep(n)
    def open(self,channel=0,**kwargs):
        self.send(1,channel=channel,**kwargs);self.step()
        self.assertEqual(self.result(channel)[4],0)
    def grant(self,base=BASE,size=0x80000,lease=37,recording=0):self.lib.window(1,base,size,lease,recording)

    def test_open_read_close_and_publication_order(self):
        self.open();self.assertEqual(self.result()[6],len(self.data));self.assertTrue(self.lib.owned(FILE_NONCE,7))
        self.grant();self.send(2,offset=73,size=37,address=BASE);self.step()
        self.assertEqual(self.result()[4:8],[0,37,len(self.data),37])
        self.assertEqual(C.string_at(self.lib.received(BASE),37),self.data[73:110])
        self.assertLess(self.lib.stat(4),self.lib.stat(5));self.assertEqual(self.lib.guards(),1)
        self.send(3);self.step();self.assertEqual(self.result()[4],0);self.assertFalse(self.lib.owned(FILE_NONCE,7))
        self.assertEqual(self.lib.stat(8),0)

    def install_named(self,path,data):
        owner=C.create_string_buffer(data);self.buffers.append(owner);self.lib.installAdmissionFile(path.encode(),owner,len(data))

    def test_branched_child_requires_committed_exact_map_and_completed_parent(self):
        from ghost_trace_branch_admission_fixture import branch_graph,map_path,fnv
        for condition in ('missing','pending','wrong_child','wrong_parent','wrong_chunk','bad_crc','bad_parent_header_crc','changed_parent_header','parent_part','bad_parent_footer','valid'):
            self.lib.readReset();self.seq=[0,0];child,parent,edge=branch_graph()
            self.install(child);self.install(parent,run=6,partial=condition=='parent_part')
            if condition in ('bad_parent_header_crc','changed_parent_header'):
                bad=bytearray(parent)
                if condition=='bad_parent_header_crc':bad[60]^=1
                else:struct.pack_into('>I',bad,24,0x604);struct.pack_into('>I',bad,60,fnv(bad[:60]))
                self.install(bytes(bad),run=6)
            if condition=='bad_parent_footer':
                bad=bytearray(parent);struct.pack_into('>I',bad,len(bad)-20,len(bad));self.install(bytes(bad),run=6)
            if condition not in ('missing',):
                bad=bytearray(edge)
                if condition=='wrong_child':struct.pack_into('>I',bad,20,8)
                elif condition=='wrong_parent':struct.pack_into('>I',bad,36,5)
                elif condition=='wrong_chunk':struct.pack_into('>I',bad,52,2)
                if condition in ('wrong_child','wrong_parent','wrong_chunk'):struct.pack_into('>I',bad,124,fnv(bad[:124]))
                if condition=='bad_crc':bad[124]^=1
                self.install_named(map_path(FILE_NONCE,7,condition=='pending'),bytes(bad))
            self.send(1);self.step()
            self.assertEqual(self.result()[4],0 if condition=='valid' else 4,condition)
            self.assertEqual(bool(self.lib.owned(FILE_NONCE,7)),condition=='valid',condition)
            self.assertEqual(self.lib.stat(8),0)
            if condition=='valid':
                self.grant();self.send(2,offset=0,size=64,address=BASE);self.step()
                self.assertEqual(self.result()[4],0);self.assertEqual(C.string_at(self.lib.received(BASE),64),child[:64])

    def test_unknown_partial_or_unclassified_parent_headers_are_refused(self):
        from ghost_trace_branch_admission_fixture import branch_graph,fnv
        child,_,_=branch_graph()
        for offset,value in ((44,0),(44,0x12345678),(48,0),(52,0),(56,0),(36,0),(40,0),(28,0x1fffff)):
            self.lib.readReset();self.seq=[0,0];bad=bytearray(child);struct.pack_into('>I',bad,offset,value)
            struct.pack_into('>I',bad,60,fnv(bad[:60]));self.install(bytes(bad));self.send(1);self.step()
            self.assertEqual(self.result()[4],4,(offset,value));self.assertFalse(self.lib.owned(FILE_NONCE,7))
        self.lib.readReset();self.seq=[0,0];bad=bytearray(child);struct.pack_into('>II',bad,48,FILE_NONCE,7);struct.pack_into('>I',bad,60,fnv(bad[:60]));self.install(bytes(bad));self.send(1);self.step()
        self.assertEqual(self.result()[4],4)

    def test_failed_dependency_admission_close_keeps_exact_reader_owner(self):
        from ghost_trace_branch_admission_fixture import branch_graph
        child,_,_=branch_graph();self.install(child);self.lib.readFault(3,1);self.send(1);self.step()
        self.assertEqual(self.result()[4],3);self.assertTrue(self.lib.owned(FILE_NONCE,7))
        self.lib.readFault(3,0);self.send(3);self.step();self.assertEqual(self.result()[4],0);self.assertFalse(self.lib.owned(FILE_NONCE,7))

    def test_default_hook_denies_all_destinations_without_data_io(self):
        self.open();before=self.lib.stat(0)
        self.send(2,size=64,address=BASE);self.step()
        self.assertEqual(self.result()[4],5);self.assertEqual(self.lib.stat(0),before)
        self.assertFalse(self.lib.owned(FILE_NONCE,7));self.assertEqual(self.lib.guards(),1)

    def test_two_handles_are_independent_and_round_robin(self):
        other=completed(run=8,region=2);self.install(other,run=8)
        self.send(1,channel=0);self.send(1,channel=1,run=8,region=2)
        self.step(1);self.assertEqual(self.result(0)[3],1);self.assertEqual(self.result(1)[3],0)
        self.step(1);self.assertEqual(self.result(1)[4],0)
        self.assertTrue(self.lib.owned(FILE_NONCE,7));self.assertTrue(self.lib.owned(FILE_NONCE,8))
        self.send(3,channel=0);self.step();self.assertFalse(self.lib.owned(FILE_NONCE,7));self.assertTrue(self.lib.owned(FILE_NONCE,8))

    def test_writer_receives_three_slices_then_reader_progresses(self):
        self.lib.submit(1,1,0,BOOT);self.step(1)
        data=b'writer'*20000;self.lib.chunk(0,1,1,data,len(data),0)
        self.send(1)
        before=self.lib.stat(8)
        for _ in range(3):self.step(1);self.assertEqual(self.result()[3],0)
        self.assertGreater(self.lib.stat(8),before)
        self.step(1);self.assertEqual(self.result()[4],0);self.assertEqual(self.result()[3],1)
        self.lib.submit(2,1,1,BOOT);self.step(100)
        self.assertEqual(self.lib.response()[4],4);self.assertEqual(self.lib.guards(),1)

    def test_partial_file_and_malformed_completion_are_refused(self):
        for raw in (self.data[:-1],self.data[:64],self.data[:-32]+b'NOPE'+self.data[-28:],self.data[:-16]+struct.pack('>I',0x10004ff)+self.data[-12:]):
            self.lib.readReset();self.seq=[0,0];self.install(raw)
            self.send(1);self.step();self.assertEqual(self.result()[4],4);self.assertFalse(self.lib.owned(FILE_NONCE,7))
        self.lib.readReset();self.seq=[0,0];self.install(self.data,partial=1)
        self.send(1);self.step();self.assertEqual(self.result()[4],3)

    def test_header_identity_and_region_are_verified(self):
        for off,value in ((0,0),(4,0),(4,4),(8,32),(12,0x474d5345),(16,123),(20,8),(32,32)):
            raw=bytearray(self.data);struct.pack_into('>I',raw,off,value);struct.pack_into('>I',raw,60,hash_bytes(raw[:60]))
            self.lib.readReset();self.seq=[0,0];self.install(bytes(raw));self.send(1);self.step()
            self.assertEqual(self.result()[4],4)
        self.lib.readReset();self.seq=[0,0];self.install(self.data)
        before=self.lib.stat(1);self.send(1,region=4);self.step();self.assertEqual(self.result()[4],1);self.assertEqual(self.lib.stat(1),before)

    def test_wrong_boot_reordered_sequence_and_stale_file_identity(self):
        for kwargs in ({'boot':99},{'sequence':1},{'run':8},{'nonce':1},{'reserved':1}):
            self.lib.readReset();self.seq=[0,0];self.install(self.data);self.open();self.grant()
            self.send(2,size=32,address=BASE,**kwargs)
            if kwargs=={'sequence':1}:
                # Exact duplicate is ignored; a later acknowledgement makes the older sequence invalid.
                self.assertFalse(self.lib.readerPending());self.send(2,size=32,address=BASE,sequence=3);self.step();self.send(2,size=32,address=BASE,sequence=2)
            before=self.lib.stat(0);self.step();self.assertNotEqual(self.result()[4],0);self.assertEqual(self.lib.stat(0),before)

    def test_destination_ranges_alignment_lengths_and_full_line_lease(self):
        control,code,codec,codec_end,core,end,snapshot,legacy=[self.lib.layout(i) for i in range(2,10)]
        cases=[(BASE+1,32,32,BASE,0x80000),(BASE,0,0,BASE,0x80000),(BASE,0x4001,0x4020,BASE,0x80000),
               (BASE,33,33,BASE,0x80000),(BASE,33,64,BASE,63),(BASE,32,32,snapshot,0x1000000),
               (control,32,32,control,32),(code,32,32,code,32),(codec,32,32,codec,32),
               (codec_end-32,32,32,codec_end-32,64),(core,32,32,core,32),(end,32,32,end,32),
               (0xffffffe0,32,32,0xffffffe0,64),(BASE,32,32,legacy,0x100000)]
        for address,n,cap,base,size in cases:
            self.lib.readReset();self.seq=[0,0];self.install(self.data);self.open();self.grant(base,size)
            before=self.lib.stat(0);self.send(2,size=n,address=address,capacity=cap);self.step()
            self.assertNotEqual(self.result()[4],0);self.assertEqual(self.lib.stat(0),before);self.assertEqual(self.lib.guards(),1)

    def test_recorder_ownership_and_lease_token_gate_the_whole_read(self):
        for lease,recording in ((38,0),(37,1)):
            self.lib.readReset();self.seq=[0,0];self.install(self.data);self.open();self.grant(lease=lease,recording=recording)
            before=self.lib.stat(0);self.send(2,size=32,address=BASE);self.step()
            self.assertEqual(self.result()[4],5);self.assertEqual(self.lib.stat(0),before)

    def test_short_read_seek_failure_and_io_failure_close_without_success_bytes(self):
        for fault in (0,1,2):
            self.lib.readReset();self.seq=[0,0];self.install(self.data);self.open();self.grant();self.lib.readFault(fault,1)
            self.send(2,size=64,address=BASE);self.step()
            self.assertEqual(self.result()[4:6],[3,0]);self.assertFalse(self.lib.owned(FILE_NONCE,7));self.assertEqual(self.lib.guards(),1)

    def test_epoch_change_and_lease_loss_during_io_never_publish_success(self):
        for fault in (4,5):
            self.lib.readReset();self.seq=[0,0];self.install(self.data);self.open();self.grant();self.lib.readFault(fault,1)
            self.send(2,size=64,address=BASE);self.step(1)
            self.assertIn(self.result()[4],(2,5));self.assertEqual(self.result()[5],0)
            self.assertFalse(self.lib.owned(FILE_NONCE,7))
        self.lib.readReset();self.seq=[0,0];self.install(self.data);self.open()
        self.lib.readFault(6,BOOT+1);self.step(1)
        self.assertEqual(self.result()[2],BOOT+1);self.assertEqual(self.result()[4],2);self.assertFalse(self.lib.owned(FILE_NONCE,7))

    def test_failed_close_keeps_handle_owned_until_safe_retry(self):
        self.open();self.lib.readFault(3,1);self.send(3);self.step()
        self.assertEqual(self.result()[4],3);self.assertTrue(self.lib.owned(FILE_NONCE,7))
        self.lib.readFault(3,0);self.send(3);self.step()
        self.assertEqual(self.result()[4],0);self.assertFalse(self.lib.owned(FILE_NONCE,7))

    def test_out_of_file_read_is_refused_without_any_storage_read(self):
        for offset,n in ((len(self.data),1),(len(self.data)-1,2),(0xffffffff,32)):
            self.lib.readReset();self.seq=[0,0];self.install(self.data);self.open();self.grant()
            before=self.lib.stat(0);self.send(2,size=n,address=BASE,offset=offset);self.step()
            self.assertEqual(self.result()[4],4);self.assertEqual(self.lib.stat(0),before)

    def test_epoch_acknowledges_original_lease_and_allows_new_boot_sequence(self):
        self.open();self.send(2,size=64,address=BASE)
        self.lib.readFault(6,BOOT+1);self.step(1)
        self.assertEqual(self.result()[2:6],[BOOT+1,2,2,0]);self.assertEqual(self.result()[7],37)
        self.assertFalse(self.lib.readerPending())
        self.send(1,boot=BOOT+1,sequence=1);self.step()
        self.assertEqual(self.result()[2:5],[BOOT+1,1,0]);self.assertTrue(self.lib.owned(FILE_NONCE,7))

    def test_response_publication_preserves_ppc_request_and_descriptor_lines(self):
        self.open();self.grant();self.send(2,size=37,address=BASE)
        pointer=self.lib.mailboxBytes(0);before=C.string_at(pointer,64)
        reserved=C.string_at(pointer+96,32);self.step()
        self.assertEqual(C.string_at(pointer,64),before)
        self.assertEqual(C.string_at(pointer+96,32),reserved)
        self.assertEqual(self.result()[7],37)

    def test_changed_file_size_and_oversized_open_fail_before_data_read(self):
        self.open();self.grant();self.lib.sizeChange(len(self.data)-1)
        before=self.lib.stat(0);self.send(2,size=32,address=BASE);self.step()
        self.assertEqual(self.result()[4],4);self.assertEqual(self.lib.stat(0),before)
        self.lib.sizeChange(0xffffffff);before=self.lib.stat(0);self.send(1);self.step()
        self.assertEqual(self.result()[4],4);self.assertEqual(self.lib.stat(0),before)

    def test_identical_file_remains_owned_until_both_readers_close(self):
        self.open(0);self.open(1);self.send(3);self.step()
        self.assertTrue(self.lib.owned(FILE_NONCE,7))
        self.send(3,channel=1);self.step();self.assertFalse(self.lib.owned(FILE_NONCE,7))

    def stream_through_production_reader(self,raw,nonce,run,region,expected=None):
        from test_ghost_trace_reader import ReaderTests
        ReaderTests.setUpClass()
        try:
            decoder=ReaderTests.lib
            self.open(nonce=nonce,run=run,region=region);self.grant()
            self.assertEqual(decoder.start(len(raw)),1);chunks=[]
            while decoder.state()==0:
                self.assertEqual(decoder.next(),1)
                offset,count=decoder.offset(),decoder.size()
                self.send(2,nonce=nonce,run=run,region=region,offset=offset,size=count,address=BASE)
                self.step();self.assertEqual(self.result()[4:6],[0,count])
                self.assertLess(self.lib.stat(4),self.lib.stat(5))
                C.memmove(decoder.target(),self.lib.received(BASE),count)
                self.assertEqual(decoder.accept(count),1)
                if decoder.state()==1:
                    chunks.append(C.string_at(decoder.chunk(),decoder.chunkSize()))
                    self.assertEqual(decoder.release(),1)
            self.assertEqual(decoder.state(),2);self.assertEqual(decoder.guards(),1)
            self.assertEqual(self.lib.guards(),1)
            if expected is not None:self.assertEqual(chunks,expected)
            self.send(3,nonce=nonce,run=run,region=region);self.step()
            self.assertFalse(self.lib.owned(nonce,run))
            return len(chunks)
        finally:ReaderTests.doClassCleanups()

    def test_writer_completed_file_roundtrips_through_storage_and_ppc_reader(self):
        self.lib.submit(1,1,0,BOOT);self.step(1)
        record=struct.pack('>HHII',99,60000,1,0)+b'abcd'*15000
        record+=struct.pack('>HHII',99,60000,8,4)+b'efgh'*15000
        self.lib.chunk(0,1,1,record,len(record),0);self.lib.submit(2,1,1,BOOT);self.step(100)
        self.assertEqual(self.lib.response()[4],4)
        count=C.c_uint();pointer=self.lib.file(1,C.byref(count));self.assertTrue(pointer)
        raw=C.string_at(pointer,count.value)
        self.assertEqual(self.stream_through_production_reader(raw,BOOT,1,1,[record]),1)

    def test_private_wii_completed_file_streams_through_storage_and_ppc_reader(self):
        files=sorted((ROOT/'build/pr48-sd-trace/wii-r9-captures').glob('*.msgt'))
        if not files:self.skipTest('Private Wii capture unavailable')
        raw=files[0].read_bytes();game,nonce,run=struct.unpack_from('>3I',raw,12)
        region=(0x474d534a,0x474d5345,0x474d5350).index(game)+1
        self.install(raw,nonce,run)
        self.assertGreater(self.stream_through_production_reader(raw,nonce,run,region),0)

    def test_second_trace_buffer_and_maximum_slice(self):
        raw=completed(payload=bytes(range(256))*100);self.install(raw);self.open();self.grant(BASE1)
        self.send(2,size=0x4000,address=BASE1,offset=64);self.step()
        self.assertEqual(self.result()[4:6],[0,0x4000]);self.assertEqual(self.lib.stat(2),0x4000)
        self.assertEqual(C.string_at(self.lib.received(BASE1),0x4000),raw[64:64+0x4000]);self.assertEqual(self.lib.guards(),1)


if __name__=='__main__':unittest.main()
