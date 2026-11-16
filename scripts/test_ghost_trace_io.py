"""Production PPC transport plus real ARM backend, using arena-owned guarded RAM."""
import ctypes as C
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import test_ghost_trace_read_storage as storage
completed,BOOT,FILE_NONCE=storage.completed,storage.BOOT,storage.FILE_NONCE

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=r'''
#include "susamune/ghost_trace_io.hxx"
#include <cstring>
using namespace GhostTraceIo;
alignas(32) static Transport transport;
static GhostArena::Arena arena;
struct Context {
 volatile MsTraceReadMailbox *mailbox[2];
 GhostArena::Span banks[2];unsigned physical[2];
 unsigned quiet,mapFailure,flushes,invalidations,publications,violations,sequenceZero,fullPayload;
} context;
static GhostArena::Handle recording;
static volatile MsTraceReadMailbox *mailbox(void*p,unsigned n){return static_cast<Context*>(p)->mailbox[n];}
static bool physical(void*p,GhostArena::Handle h,GhostArena::Span s,unsigned&out){
 Context&c=*static_cast<Context*>(p);
 const auto*e=GhostArena::find(arena,h,GhostArena::WORKSPACE);
 if(c.mapFailure||!e||s.data!=e->span.data||s.bytes>e->span.bytes)return false;
 for(unsigned i=0;i<2;++i){auto a=reinterpret_cast<GhostArena::Address>(s.data),b=reinterpret_cast<GhostArena::Address>(c.banks[i].data);
  if(a>=b&&a-b<=c.banks[i].bytes&&s.bytes<=c.banks[i].bytes-(a-b)){out=c.physical[i]+unsigned(a-b);return true;}}
 return false;
}
static void flush(void*p,const void*address,unsigned bytes){
 Context&c=*static_cast<Context*>(p);++c.flushes;
 for(unsigned i=0;i<2;++i)if(address==c.mailbox[i]){
  if(!c.mailbox[i]->request.sequence){if(bytes==32)++c.sequenceZero;if(bytes==64)++c.fullPayload;}
  else {++c.publications;const auto&channel=transport.channels[i];const auto*e=GhostArena::find(arena,channel.lease,GhostArena::WORKSPACE);
   if(bytes!=32||!e||e->pending!=channel.sequence||e->direction!=GhostArena::WRITES_MEMORY||c.mailbox[i]->request.sequence!=channel.sequence)++c.violations;}
 }
}
static void invalidate(void*p,void*address,unsigned bytes){(void)address;(void)bytes;++static_cast<Context*>(p)->invalidations;}
static bool quiet(void*p,unsigned channel,unsigned nonce,unsigned lease,unsigned seq){
 const Channel&c=transport.channels[channel];return static_cast<Context*>(p)->quiet&&nonce==transport.bootNonce&&lease==c.lease.serial&&seq==c.sequence;
}
static Hooks hooks(){return {&context,sizeof(context),mailbox,flush,invalidate,physical,quiet};}
#define API extern "C" __declspec(dllexport)
API int setup(void*m0,void*m1,void*b0,void*b1,unsigned p0,unsigned p1,unsigned nonce){
 transport={};arena={};context={};recording=GhostArena::invalid();
 context.mailbox[0]=static_cast<MsTraceReadMailbox*>(m0);context.mailbox[1]=static_cast<MsTraceReadMailbox*>(m1);
 context.banks[0]={b0,0x80000};context.banks[1]={b1,0x80000};context.physical[0]=p0;context.physical[1]=p1;
 return GhostArena::configure(arena,context.banks,2)&&configure(transport,arena,hooks(),nonce);
}
API int configureAgain(unsigned nonce){return configure(transport,arena,hooks(),nonce);}
API int takeRecording(){recording=GhostArena::acquire(arena,GhostArena::RECORDING,0x80000);return recording.serial!=0;}
API int openFile(unsigned n,unsigned nonce,unsigned run,unsigned region){return open(transport,n,{nonce,run,region});}
API int readFile(unsigned n,unsigned offset,unsigned bytes){return read(transport,n,offset,bytes);}
API int pollFile(unsigned n){return poll(transport,n);}
API int closeFile(unsigned n){return close(transport,n);}
API int abandonFile(unsigned n){return abandon(transport,n);}
API int consumeFile(unsigned n){return consume(transport,n);}
API const void* data(unsigned n){return view(transport,n).data;}
API unsigned dataBytes(unsigned n){return view(transport,n).bytes;}
API unsigned get(unsigned n,unsigned key){const auto s=status(transport,n);const auto&c=transport.channels[n];const auto*e=GhostArena::find(arena,c.lease,GhostArena::WORKSPACE);
 switch(key){case 0:return s.phase;case 1:return s.error;case 2:return s.remoteStatus;case 3:return s.fileBytes;case 4:return s.sequence;case 5:return s.pending;
 case 6:return c.lease.serial;case 7:return GhostArena::read(arena,c.lease,GhostArena::WORKSPACE).data!=nullptr;case 8:return e?e->pending:0;case 9:return c.physical;}
 return 0;
}
API unsigned metrics(unsigned key){switch(key){case 0:return context.flushes;case 1:return context.invalidations;case 2:return context.publications;case 3:return context.violations;
 case 4:return context.sequenceZero;case 5:return context.fullPayload;case 6:return GhostArena::available(arena);case 7:return sizeof(Transport);case 8:return sizeof(Channel);}return 0;}
API void options(unsigned proof,unsigned failure){context.quiet=proof;context.mapFailure=failure;}
API int drop(unsigned n){return GhostArena::release(arena,transport.channels[n].lease,GhostArena::WORKSPACE);}
API void leaseFault(unsigned n){arena.entry[transport.channels[n].lease.slot].serial^=0x10000;}
API void exhaust(unsigned n){transport.channels[n].sequence=~0u;}
API void ack(unsigned n,unsigned which){
 const Channel&c=transport.channels[n];volatile MsTraceReadResponse&r=context.mailbox[n]->response;
 r.magic=MS_TRACE_READ_MAGIC;r.version=MS_TRACE_READ_VERSION;r.bootNonce=transport.bootNonce;r.ack=c.sequence;
 r.lease=c.lease.serial;r.status=0;r.bytes=c.bytes;r.fileSize=c.fileBytes;
 switch(which){case 0:r.lease++;break;case 1:r.bootNonce++;break;case 2:r.ack--;break;case 3:r.bytes--;break;case 4:r.magic++;break;case 5:r.fileSize++;break;case 6:r.status=99;break;}
}
API int granted(unsigned n,unsigned nonce,unsigned lease,unsigned*base,unsigned*bytes){
 if(n>=2||nonce!=transport.bootNonce)return 0;
 const Channel&c=transport.channels[n];
 const auto*e=GhostArena::find(arena,c.lease,GhostArena::WORKSPACE);
 if(!e||c.lease.serial!=lease||c.operation!=MS_TRACE_READ_DATA||e->pending!=c.sequence||e->direction!=GhostArena::WRITES_MEMORY)return 0;
 unsigned address;if(!physical(&context,c.lease,e->span,address))return 0;*base=address;*bytes=e->span.bytes;return 1;
}
API int badConfigure(unsigned which){
 Transport t={};Hooks h=hooks();auto*m=context.mailbox[1];auto saved=arena.bank[0];
 if(which==0)h.flush=nullptr;
 if(which==1)context.mailbox[1]=context.mailbox[0];
 if(which==2)context.mailbox[1]=reinterpret_cast<MsTraceReadMailbox*>(reinterpret_cast<GhostArena::Address>(m)+4);
 if(which==3)arena.bank[0]={&transport,32};
 if(which==4)arena.bank[0]={const_cast<MsTraceReadMailbox*>(context.mailbox[0]),128};
 if(which==5)h.contextBytes=0;
 bool ok=configure(which==3?transport:t,arena,h,BOOT_PLACEHOLDER,which==6?33:0x4000);
 context.mailbox[1]=m;arena.bank[0]=saved;return ok;
}
API int untouched(){Transport t={};unsigned before=context.flushes+context.invalidations;
 bool safe=!open(t,0,{1,1,1})&&!read(t,0,0,32)&&poll(t,0)==UNCONFIGURED&&!close(t,0)&&!abandon(t,0)&&!view(t,0).data;
 return safe&&context.flushes+context.invalidations==before;}
'''.replace('BOOT_PLACEHOLDER',str(BOOT)+'u')


class TraceIoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        storage.TraceReadStorageTests.setUpClass();cls.addClassCleanup(storage.TraceReadStorageTests.doClassCleanups)
        cls.backend=storage.TraceReadStorageTests.lib
        cls.temp=tempfile.TemporaryDirectory(prefix='trace-io-');cls.addClassCleanup(cls.temp.cleanup)
        out=Path(cls.temp.name);source=out/'io.cpp';source.write_text(FIXTURE,encoding='utf-8')
        env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
        result=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-std=c++11','-O2','-Wall','-Wextra','-Werror','-shared','-static','-I',str(ROOT/'include'),str(source),str(ROOT/'src/ghost_arena.cpp'),str(ROOT/'src/ghost_trace_io.cpp'),'-o',str(out/'io.dll')],capture_output=True,text=True,encoding='utf-8',env=env)
        if result.returncode:raise RuntimeError(result.stderr)
        cls.io=C.CDLL(str(out/'io.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.io._handle)))
        u,p=C.c_uint,C.c_void_p
        for name,args in {'setup':[p,p,p,p,u,u,u],'configureAgain':[u],'openFile':[u,u,u,u],'readFile':[u,u,u],'pollFile':[u],'closeFile':[u],'abandonFile':[u],'consumeFile':[u],'data':[u],'dataBytes':[u],'get':[u,u],'metrics':[u],'options':[u,u],'drop':[u],'leaseFault':[u],'exhaust':[u],'ack':[u,u],'badConfigure':[u]}.items():getattr(cls.io,name).argtypes=args
        cls.io.data.restype=p

    def setUp(self):
        self.backend.readReset();self.raw=completed();self.owner=C.create_string_buffer(self.raw)
        self.backend.install(FILE_NONCE,7,self.owner,len(self.raw),0)
        self.base=[self.backend.layout(i) for i in range(2)]
        self.assertTrue(self.io.setup(self.backend.mailboxBytes(0),self.backend.mailboxBytes(1),self.backend.received(self.base[0]),self.backend.received(self.base[1]),*self.base,BOOT))
        self.backend.bindWindow(C.cast(self.io.granted,C.c_void_p))

    def tearDown(self):self.assertEqual(self.backend.guards(),1);self.assertEqual(self.io.metrics(3),0)
    def pump(self,n=1):
        for _ in range(n):self.backend.readStep(1);self.io.pollFile(0);self.io.pollFile(1)
    def opened(self,n=0):
        self.assertTrue(self.io.openFile(n,FILE_NONCE,7,1));self.pump(8);self.assertEqual(self.io.get(n,0),3)

    def test_no_global_or_hardware_access_before_configuration_and_alias_refusals(self):
        self.assertEqual(self.io.untouched(),1)
        for case in range(7):self.assertEqual(self.io.badConfigure(case),0)

    def test_open_read_checked_view_consume_close_and_reopen_sequences(self):
        self.opened();self.assertTrue(self.io.readFile(0,73,37))
        self.assertFalse(self.io.data(0));self.assertEqual(self.io.get(0,7),0);self.assertFalse(self.io.drop(0))
        self.backend.readStep(1);self.assertFalse(self.io.data(0));self.assertEqual(self.io.get(0,7),0)
        before=self.io.metrics(1);self.assertEqual(self.io.pollFile(0),5);self.assertGreater(self.io.metrics(1),before)
        self.assertEqual(C.string_at(self.io.data(0),self.io.dataBytes(0)),self.raw[73:110])
        logical=C.create_string_buffer(b'X'*39);C.memmove(C.addressof(logical)+1,self.io.data(0),37)
        self.assertEqual(logical.raw[:39],b'X'+self.raw[73:110]+b'X')
        self.assertTrue(self.io.consumeFile(0));self.assertFalse(self.io.data(0));self.assertTrue(self.io.closeFile(0));self.pump()
        self.assertEqual(self.io.get(0,0),1);sequence=self.io.get(0,4);self.assertEqual(self.io.metrics(6),0x100000)
        self.opened();self.assertGreater(self.io.get(0,4),sequence)
        self.assertEqual(self.io.metrics(2),self.io.metrics(4));self.assertEqual(self.io.metrics(2),self.io.metrics(5))

    def test_close_during_open_and_read_waits_for_both_exact_acks(self):
        for read_first in (False,True):
            self.setUp()
            if read_first:self.opened();self.assertTrue(self.io.readFile(0,0,64))
            else:self.assertTrue(self.io.openFile(0,FILE_NONCE,7,1))
            old=self.io.get(0,4);self.assertTrue(self.io.closeFile(0));self.assertFalse(self.io.drop(0))
            self.assertFalse(self.io.configureAgain(BOOT));self.assertEqual(self.io.get(0,4),old)
            self.pump();self.assertEqual(self.io.get(0,0),6);self.assertTrue(self.io.get(0,5));self.assertFalse(self.io.data(0))
            self.assertGreater(self.io.get(0,4),old);self.assertFalse(self.io.drop(0))
            self.pump();self.assertEqual(self.io.get(0,0),1);self.assertFalse(self.backend.owned(FILE_NONCE,7))

    def test_wrong_or_stale_ack_never_completes_or_releases_the_lease(self):
        for fault in range(7):
            self.setUp();self.opened();self.assertTrue(self.io.readFile(0,0,64));seq=self.io.get(0,4)
            self.io.ack(0,fault);self.io.pollFile(0)
            self.assertEqual(self.io.get(0,8),seq);self.assertTrue(self.io.get(0,5));self.assertFalse(self.io.data(0));self.assertFalse(self.io.drop(0))
            self.pump();self.assertEqual(self.io.get(0,0),5)
            self.assertEqual(C.string_at(self.io.data(0),64),self.raw[:64])

    def test_epoch_change_requires_explicit_quiescence_proof(self):
        self.opened();self.io.readFile(0,0,64);self.backend.readFault(6,BOOT+1);self.pump()
        self.assertEqual(self.io.get(0,1),7);self.assertTrue(self.io.get(0,5));self.assertFalse(self.io.abandonFile(0));self.assertFalse(self.io.drop(0))
        self.assertFalse(self.backend.owned(FILE_NONCE,7));self.io.options(1,0);self.assertTrue(self.io.abandonFile(0))
        seq=self.io.get(0,4);self.assertTrue(self.io.configureAgain(BOOT+1));self.assertEqual(self.io.get(0,4),seq)
        self.opened();self.assertGreater(self.io.get(0,4),seq)

    def test_short_io_and_failed_close_keep_ownership_until_confirmed(self):
        self.opened();self.backend.readFault(1,1);self.backend.readFault(3,1);self.io.readFile(0,0,64)
        self.pump();self.assertEqual(self.io.get(0,0),6);self.assertFalse(self.io.data(0))
        self.pump();self.assertEqual(self.io.get(0,0),7);self.assertTrue(self.backend.owned(FILE_NONCE,7));self.assertTrue(self.io.get(0,6))
        self.backend.readFault(1,0);self.backend.readFault(3,0);self.assertTrue(self.io.closeFile(0));self.pump()
        self.assertEqual(self.io.get(0,0),1);self.assertEqual(self.io.get(0,1),8);self.assertEqual(self.io.get(0,2),3)
        self.assertFalse(self.backend.owned(FILE_NONCE,7));self.assertEqual(self.io.metrics(6),0x100000)

    def test_failed_open_with_unknown_size_does_not_assume_remote_handle_closed(self):
        self.backend.sizeChange(0xffffffff);self.backend.readFault(3,1)
        self.assertTrue(self.io.openFile(0,FILE_NONCE,7,1));self.pump()
        self.assertEqual(self.io.get(0,0),6);self.assertTrue(self.backend.owned(FILE_NONCE,7));self.assertFalse(self.io.drop(0))
        self.pump();self.assertEqual(self.io.get(0,0),7);self.assertTrue(self.io.get(0,6))
        self.backend.readFault(3,0);self.assertTrue(self.io.closeFile(0));self.pump()
        self.assertEqual(self.io.get(0,0),1);self.assertFalse(self.backend.owned(FILE_NONCE,7))
        self.assertEqual(self.io.get(0,3),0);self.assertEqual(self.io.metrics(6),0x100000)

    def test_short_read_after_successful_remote_close_still_gets_close_confirmation(self):
        self.opened();self.backend.readFault(1,1);self.io.readFile(0,0,64);self.pump()
        self.assertEqual(self.io.get(0,0),6);self.assertFalse(self.backend.owned(FILE_NONCE,7));self.assertFalse(self.io.data(0))
        self.pump();self.assertEqual(self.io.get(0,0),1);self.assertEqual(self.io.get(0,2),3)

    def test_lost_lease_cannot_complete_or_abandon_a_replacement_owner(self):
        self.opened();self.io.readFile(0,0,64);self.io.leaseFault(0)
        self.io.pollFile(0);self.assertEqual(self.io.get(0,1),3);self.assertFalse(self.io.closeFile(0))
        self.io.options(1,0);self.assertFalse(self.io.abandonFile(0));self.assertFalse(self.io.data(0))
        self.io.leaseFault(0);self.pump();self.assertEqual(self.io.get(0,0),5)

    def test_map_failure_bounds_and_sequence_exhaustion_do_not_publish(self):
        self.opened();before=self.io.metrics(2);seq=self.io.get(0,4)
        for offset,n in ((0,0),(0,0x4001),(len(self.raw),1),(0xffffffff,32)):
            self.assertFalse(self.io.readFile(0,offset,n))
        self.io.options(0,1);self.assertFalse(self.io.readFile(0,0,64));self.assertEqual(self.io.get(0,1),4)
        self.assertEqual(self.io.metrics(2),before);self.assertEqual(self.io.get(0,4),seq);self.assertEqual(self.io.get(0,7),1)
        self.assertTrue(self.io.closeFile(0));self.pump();self.io.exhaust(0)
        self.assertFalse(self.io.openFile(0,FILE_NONCE,7,1));self.assertEqual(self.io.get(0,1),5);self.assertEqual(self.io.get(0,6),0)

    def test_two_streams_progress_while_real_writer_owns_the_other_bank(self):
        self.assertTrue(self.io.takeRecording());self.backend.submit(1,1,0,BOOT);self.backend.readStep(1)
        payload=b'writer data'*8000;self.backend.chunk(0,1,1,payload,len(payload),0);self.backend.submit(2,1,1,BOOT)
        for channel in (0,1):self.assertTrue(self.io.openFile(channel,FILE_NONCE,7,1))
        self.pump(40)
        for channel in (0,1):self.assertEqual(self.io.get(channel,0),3);self.assertTrue(self.io.readFile(channel,channel*64,64))
        self.pump(20)
        for channel in (0,1):
            self.assertEqual(self.io.get(channel,0),5);self.assertGreaterEqual(self.io.get(channel,9),self.base[1])
            self.assertEqual(C.string_at(self.io.data(channel),64),self.raw[channel*64:channel*64+64])
        self.assertNotEqual(self.io.get(0,6),self.io.get(1,6));self.assertEqual(self.backend.response()[4],4)
        for channel in (0,1):self.assertTrue(self.io.closeFile(channel))
        self.pump(8);self.assertEqual(self.io.metrics(6),0x80000)


if __name__=='__main__':unittest.main()
