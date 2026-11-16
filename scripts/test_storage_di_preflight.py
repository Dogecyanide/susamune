"""Run the production foreground-storage gate and completion path in a hardware fixture."""
import ctypes as C
from pathlib import Path
import subprocess,tempfile,unittest
from test_practice_tape import function_source
ROOT=Path(__file__).resolve().parents[1]
FIXTURE=r"""
typedef unsigned int u32;typedef _Bool bool;
#define true 1
#define false 0
#define TIMEWARP_LIVE_RACING 1
#define DI_BASE 0
#define DI_CONTROL 1
#define DI_STATUS 2
#define DI_DMA_ADR 3
#define DI_DMA_LEN 4
#define DI_INV_ADR 5
#define DI_INV_LEN 6
#define DI_INT 7
#define HW_IPC_ARMCTRL 8
#define HW_TIMER 9
#define TRI_NONE 0
static u32 reg[16],ticks,flushes,polls,serial,lastFlush,lastPoll,bad,requests,completions,delays,unknowns,storageCalls,storageAcks;
static u32 TITLE_ID=0x474d53,TRIGame,RealDiscError,DILastReadTick;
static bool DI_IRQ,throttled,completeOnDelay;static u32 RealDiscCMD,callbackFlushes;
static void RealDI_Update(void){}
struct Msg{int result;} ;static struct Msg DI_CallbackMsg;
static int DI_Handle=7,DI_MessageQueue=9;
static void IOS_IoctlAsync(int,u32,void*,u32,void*,u32,int,struct Msg*);
static u32 pendingStorage,lastStorage;
static void sync_before_read(void*p,u32 n){}
static void sync_after_write(void*p,u32 n){if(p==&DI_CallbackMsg){++callbackFlushes;if(n!=32)++bad;}}
static void _ahbMemFlush(u32 mask){if(mask!=1)++bad;++flushes;lastFlush=++serial;}
static u32 read32(u32 address){return address==HW_TIMER?++ticks:reg[address];}
static void write32(u32 address,u32 value){reg[address]=value;if(address==HW_IPC_ARMCTRL&&value==8)++completions;}
static void udelay(u32 us){++delays;if(completeOnDelay){completeOnDelay=false;DI_CallbackMsg.result=0;}}
static void CheckOSReport(void){}static void BTUpdateRegisters(void){}
static u32 ReadSpeed_End(void){return !throttled;}
"""
DISPATCH=r"""
static void IOS_IoctlAsync(int handle,u32 mode,void*offset,u32 unused,void*buffer,u32 bytes,int queue,struct Msg*message){
 if(handle!=7||mode!=0||(__UINTPTR_TYPE__)offset!=0x2000||unused||(__UINTPTR_TYPE__)buffer!=0x8000||bytes!=4096||queue!=9||message!=&DI_CallbackMsg||message->result!=-1)++bad;
 if(callbackFlushes!=requests+1)++bad;
 ++requests;
}
static void DIUpdateRegisters(void){
 ++polls;if(lastFlush<=lastPoll)++bad;lastPoll=++serial;
 if(DI_IRQ||!(reg[DI_CONTROL]&1))return;
 if(reg[10]!=0xa8){++unknowns;reg[DI_CONTROL]&=~1u;return;}
 DI_IRQ=true;DiscReadAsync(0x8000,0x2000,4096,0);
}
static bool storagePending(unsigned n){return (pendingStorage&(1u<<n))!=0;}
static void storageService(unsigned n){
 if(DI_IRQ||DI_CallbackMsg.result!=0)++bad;
 ++storageCalls;lastStorage=n;pendingStorage&=~(1u<<n);++storageAcks;
}
#define SERVICE(name,index) static bool name##Pending(void){return storagePending(index);}static void name##Service(void){storageService(index);}
SERVICE(SusamuneCrash,0)
SERVICE(SusamunePb,1)
SERVICE(SusamuneCfg,2)
SERVICE(SusamuneTransfer,3)
SERVICE(GhostReplayReport,4)
SERVICE(GhostTraceStorage,5)
SERVICE(SusamuneGhost,6)
SERVICE(SusamuneStateStorage,7)
SERVICE(MoonshineLayout,8)
SERVICE(MoonshineNetLog,9)
"""
EXPORTS=r"""
#define API __declspec(dllexport)
API void reset(void){
 for(unsigned i=0;i<16;++i)reg[i]=0;
 ticks=flushes=polls=serial=lastFlush=lastPoll=bad=requests=completions=delays=unknowns=storageCalls=storageAcks=pendingStorage=0;
 lastStorage=99;callbackFlushes=RealDiscCMD=0;DI_IRQ=throttled=completeOnDelay=false;DI_CallbackMsg.result=0;RealDiscError=0;
}
API void queue(unsigned command){reg[DI_CONTROL]=3;reg[DI_STATUS]=8;reg[DI_DMA_ADR]=0x8000;reg[DI_DMA_LEN]=4096;reg[10]=command;}
API void diskComplete(void){DI_CallbackMsg.result=0;}
API void oldCallback(unsigned ready){DI_IRQ=false;DI_CallbackMsg.result=ready?0:-1;}
API void yieldCompletes(void){completeOnDelay=true;}
API void delayCompletion(unsigned yes){throttled=yes!=0;}
API void storage(unsigned n){pendingStorage|=1u<<n;}
API unsigned gate(void){return StorageReadPending();}
API unsigned stat(unsigned key){switch(key){case 0:return requests;case 1:return completions;case 2:return storageCalls;case 3:return bad;case 4:return DI_IRQ;case 5:return DI_CallbackMsg.result==0;
 case 6:return polls;case 7:return flushes;case 8:return unknowns;case 9:return lastStorage;case 10:return storageAcks;case 11:return reg[DI_DMA_ADR];case 12:return reg[DI_DMA_LEN];case 14:return callbackFlushes;default:return pendingStorage;}}
"""
class StoragePreflightTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='moonshine-storage-preflight-');cls.addClassCleanup(cls.temp.cleanup)
  main=ROOT/'launcher/kernel/main.c';di=ROOT/'launcher/kernel/DI.c';text=main.read_text()
  start=text.index('\t\tif(StorageReadPending())');end=text.index('\n\t\telse if(SaveCard == true)',start)
  dispatch=text[start:end]
  # This is the production else-if chain, including every foreground owner.
  expected=['SusamuneCrashService','SusamunePbService','SusamuneCfgService','SusamuneTransferService','GhostReplayReportService','GhostTraceStorageService','SusamuneGhostService','SusamuneStateStorageService','MoonshineLayoutService','MoonshineNetLogService']
  if any(name not in dispatch for name in expected):raise AssertionError('Foreground storage dispatch fixture incomplete')
  bottom='\t\t_ahbMemFlush(1);\n\t\tDIUpdateRegisters();'
  if text.count(bottom)!=1 or text.index(bottom)<end:raise AssertionError('Expected retained bottom DI poll')
  source=FIXTURE+function_source(di,'bool DiscCheckAsync(')+function_source(di,'void DIFinishAsync(')+function_source(di,'static void DiscReadAsync(')+DISPATCH+function_source(di,'void DIInterrupt(')+function_source(main,'static bool StorageReadPending(')
  source+='\n__declspec(dllexport) void tick(void){\n'+dispatch+'\n'+bottom+'\n}\n'+EXPORTS
  path=Path(cls.temp.name)/'preflight.c';path.write_text(source);dll=path.with_suffix('.dll')
  result=subprocess.run([str(ROOT/'toolchain/clang.exe'),'--target=x86_64-pc-windows-msvc','-std=c11','-shared','-nostdlib','-fno-builtin','-O2','-fuse-ld=lld','-Wl,/noentry',str(path),'-o',str(dll)],capture_output=True,text=True)
  if result.returncode:raise AssertionError(result.stderr)
  cls.lib=C.CDLL(str(dll));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
 def setUp(self):self.lib.reset()
 def check(self):self.assertEqual(self.lib.stat(3),0)
 def test_queued_read_is_dispatched_before_every_foreground_storage_owner(self):
  for owner in range(10):
   with self.subTest(owner=owner):
    self.lib.reset();self.lib.storage(owner);self.lib.queue(0xa8);self.lib.tick()
    self.assertEqual((self.lib.stat(0),self.lib.stat(2),self.lib.stat(4)),(1,0,1));self.check()
 def test_storage_stays_held_until_real_completion_and_next_service_pass(self):
  self.lib.storage(5);self.lib.queue(0xa8);self.lib.tick();self.lib.tick()
  self.assertEqual(self.lib.stat(2),0);self.assertEqual(self.lib.stat(1),0)
  self.lib.diskComplete();self.lib.tick()
  self.assertEqual((self.lib.stat(1),self.lib.stat(2),self.lib.stat(11),self.lib.stat(12)),(1,0,0x9000,0))
  self.lib.tick();self.lib.tick()
  self.assertEqual((self.lib.stat(1),self.lib.stat(2),self.lib.stat(10)),(1,1,1));self.check()
 def test_previous_callback_without_di_irq_cannot_admit_fat(self):
  self.lib.oldCallback(0);self.lib.storage(1);self.lib.queue(0xa8)
  self.assertEqual(self.lib.gate(),1)
  self.assertEqual((self.lib.stat(0),self.lib.stat(2),self.lib.stat(6)),(0,0,0))
  self.lib.yieldCompletes();self.lib.tick()
  self.assertEqual((self.lib.stat(0),self.lib.stat(2)),(1,0));self.check()
 def test_no_queue_preserves_foreground_priority_and_ordinary_writes(self):
  for owner in (9,6,3,1,0):self.lib.storage(owner)
  for expected in (0,1,3,6,9):
   self.lib.tick();self.assertEqual(self.lib.stat(9),expected);self.check()
  self.assertEqual(self.lib.stat(10),5)
 def test_unknown_command_is_still_delegated_to_di_before_storage(self):
  self.lib.storage(2);self.lib.queue(0xee);self.lib.tick()
  self.assertEqual((self.lib.stat(8),self.lib.stat(0),self.lib.stat(2)),(1,0,1));self.check()
 def test_retirement_handler_cannot_acknowledge_while_a_read_owns_storage(self):
  self.lib.storage(3);self.lib.queue(0xa8);self.lib.tick();self.lib.tick()
  self.assertEqual(self.lib.stat(10),0)
  self.lib.diskComplete();self.lib.tick();self.assertEqual(self.lib.stat(10),0)
  self.lib.tick();self.assertEqual((self.lib.stat(10),self.lib.stat(9)),(1,3));self.check()
 def test_read_speed_delayed_completion_retains_storage_hold(self):
  self.lib.storage(7);self.lib.queue(0xa8);self.lib.tick();self.lib.diskComplete();self.lib.delayCompletion(1)
  for _ in range(3):self.lib.tick()
  self.assertEqual((self.lib.stat(1),self.lib.stat(2)),(0,0))
  self.lib.delayCompletion(0);self.lib.tick();self.lib.tick()
  self.assertEqual((self.lib.stat(1),self.lib.stat(2)),(1,1));self.check()
 def test_poll_reads_have_fresh_bus_flush_and_published_callback_state(self):
  self.lib.queue(0xa8);self.lib.tick();self.lib.diskComplete();self.lib.tick();self.lib.tick()
  self.assertGreater(self.lib.stat(7),0);self.assertGreater(self.lib.stat(14),0);self.assertEqual(self.lib.stat(6),self.lib.stat(7));self.check()

if __name__=='__main__':unittest.main()
