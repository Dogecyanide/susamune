"""Run the production HTTP coordinator through reconnect, timeout and cancellation."""
from pathlib import Path
import ctypes as C
import os,subprocess,unittest
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/test-dolphin-http'
class Info(C.Structure):
 _fields_=[(n,C.c_uint) for n in ('used','status','tls','reusable','complete')]
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  OUT.mkdir(parents=True,exist_ok=True)
  os.environ['PATH']='C:/msys64/mingw64/bin'+os.pathsep+os.environ.get('PATH','')
  code=(ROOT/'native/dolphin_https/http.cpp').read_text()
  code=code[code.index('namespace DolphinHttp {'):]
  code=code.replace('Work &s=*reinterpret_cast<Work *>(DOLPHIN_HTTPS_CONTROL_BASE);','Work s;')
  code=code.replace('reinterpret_cast<void *>(DOLPHIN_HTTPS_WORK_BASE)','tlsWork')
  shim=r"""
#define IS_EMULATOR 1
#define TIMEWARP_LIVE_RACING 1
#include <cstring>
#include "Dolphin/types.h"
#include "susamune/dolphin_http.hxx"
#include "susamune/dolphin_storage_api.hxx"
#include "susamune/dolphin_entropy.hxx"
#include "susamune/dolphin_dns.hxx"
#include "susamune/dolphin_tcp.hxx"
#include "susamune/live_transport.hxx"
#include "susamune/live_race.hxx"
#include "susamune/ghost_service.h"
#define IS_EMULATOR 1
#define TIMEWARP_LIVE_RACING 1
#define OS_BUS_CLOCK 162000000ull
#define OS_TIMER_CLOCK OS_BUS_CLOCK / 4
static u32 milliseconds;
static u64 OSGetTime(){return u64(milliseconds)*40500ull;}
static unsigned char tlsWork[DOLPHIN_HTTPS_WORK_CAPACITY];
static DolphinHttpsInfo tlsInfo;
static LiveTransport::Status net;
static LiveRace::Status room;
static DolphinNetwork::DnsResult dns;
static DolphinTcp::State tcp;
static int seedResult,stepResult,initCalls,beginCalls,stopCalls,resolveCalls,seedCalls,starts;
static int entropyPending,sendBytes,recvBytes;
static bool missingApi;
static int tlsInit(void*,unsigned,const unsigned char*){++initCalls;tlsInfo={};return 0;}
static int tlsStart(void*,const char*,const DolphinHttpsRequest*,void*,unsigned){++starts;tlsInfo={};return 0;}
static int tlsStep(void*,const DolphinHttpsIo *io){
 unsigned char b=0;io->send(nullptr,&b,1);io->recv(nullptr,&b,1);
 if(stepResult==0)tlsInfo={12,200,0,1,1};return stepResult;
}
static void tlsStatus(const void*,DolphinHttpsInfo *out){*out=tlsInfo;}
static const DolphinHttpsApi api={DOLPHIN_HTTPS_MAGIC,2,sizeof(DolphinHttpsApi),sizeof(tlsWork),tlsInit,tlsStart,tlsStep,tlsStatus,nullptr,nullptr};
namespace DolphinHttps{const DolphinHttpsApi *api(){return missingApi?nullptr:&::api;}}
namespace DolphinEntropy{
 bool begin(){++seedCalls;return true;}
 void update(){}
 int take(void *out){if(entropyPending)return 1;memset(out,1,32);return seedResult;}
}
namespace LiveTransport{
 Status poll(){return net;}
 bool begin(unsigned short){++beginCalls;net.state=TW_LIVE_READY;return true;}
 void stop(){++stopCalls;net.state=TW_LIVE_IDLE;}
}
namespace LiveRace{Status status(){return room;}}
namespace DolphinNetwork{
 bool resolve(const char*,unsigned){++resolveCalls;dns.state=DNS_WAITING;return true;}
 DnsResult dnsResult(){return dns;}
 void cancelResolve(){dns={};}
}
namespace DolphinTcp{
 bool connect(unsigned,unsigned short){tcp=CONNECTING;return true;}
 int send(const void*,unsigned){return sendBytes;}
 int read(void*,unsigned){return recvBytes;}
 State state(){return tcp;}
 void close(){tcp=CLOSED;}
}
namespace NativeStorage {
static unsigned nowMs(){return milliseconds;}
static unsigned seconds(){return milliseconds/1000;}
static unsigned state(){return LiveTransport::poll().state;}
static bool begin(){return LiveTransport::begin(0);}
static void stop(){if(!LiveRace::status().active)LiveTransport::stop();}
static DolphinStorageHost callbacks;
static const DolphinStorageHost *host=[](){callbacks.milliseconds=nowMs;callbacks.seconds=seconds;callbacks.networkState=state;callbacks.networkBegin=begin;callbacks.networkStopIfIdle=stop;return &callbacks;}();
}
"""+code+r"""
extern "C" {
__declspec(dllexport) void reset(){DolphinHttp::initialized=false;DolphinHttp::s={};tlsInfo={};net={};net.state=TW_LIVE_IDLE;room={};dns={};tcp=DolphinTcp::CLOSED;milliseconds=0;seedResult=0;stepResult=1;initCalls=beginCalls=stopCalls=resolveCalls=seedCalls=starts=entropyPending=sendBytes=recvBytes=0;missingApi=false;}
__declspec(dllexport) int begin(){static unsigned char out[256];return DolphinHttp::begin("/test",nullptr,out,sizeof(out));}
__declspec(dllexport) void step(){DolphinHttp::update();}
__declspec(dllexport) int take(DolphinHttpsInfo *p){return DolphinHttp::take(p);}
__declspec(dllexport) void cancel(){DolphinHttp::cancel();}
__declspec(dllexport) int close(){return DolphinHttp::close();}
__declspec(dllexport) void set(int key,int value){switch(key){case 0:milliseconds=value;break;case 1:entropyPending=value;break;case 2:seedResult=value;break;case 3:net.state=value;break;case 4:dns.state=value;dns.address=0x7f000001;break;case 5:tcp=(DolphinTcp::State)value;break;case 6:stepResult=value;break;case 7:room.active=value;break;case 8:missingApi=value;break;case 9:sendBytes=value;break;case 10:recvBytes=value;break;}}
__declspec(dllexport) int count(int key){switch(key){case 0:return seedCalls;case 1:return initCalls;case 2:return beginCalls;case 3:return stopCalls;case 4:return resolveCalls;default:return starts;}}
}
"""
  (OUT/'fixture.cpp').write_text(shim)
  r=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-std=c++17','-O2','-shared','-static-libgcc','-static-libstdc++','-I'+str(ROOT/'include'),str(OUT/'fixture.cpp'),'-o',str(OUT/'http.dll')],capture_output=True,text=True)
  if r.returncode:raise RuntimeError(r.stderr)
  cls.lib=C.CDLL(str(OUT/'http.dll'))
 def setUp(self):self.lib.reset()
 def connect(self):
  self.assertTrue(self.lib.begin());self.lib.step();self.lib.step()
  self.lib.set(4,2);self.lib.step();self.lib.set(5,2);self.lib.step()
 def finish(self):
  self.lib.set(6,0);self.lib.step();i=Info();self.assertEqual(self.lib.take(C.byref(i)),0);self.assertEqual(i.status,200)
 def test_reuse_and_reopen(self):
  self.connect();self.finish();self.assertEqual(self.lib.count(0),1)
  self.assertTrue(self.lib.begin());self.finish();self.assertEqual(self.lib.count(0),1)
  self.assertTrue(self.lib.close());self.connect();self.finish();self.assertEqual(self.lib.count(0),2)
 def test_cancel_waits_for_seed_write_completion(self):
  self.lib.set(1,1);self.assertTrue(self.lib.begin());self.lib.step();self.lib.cancel();self.lib.step()
  i=Info();self.assertEqual(self.lib.take(C.byref(i)),1);self.assertFalse(self.lib.begin())
  self.lib.set(1,0);self.lib.step();self.assertEqual(self.lib.take(C.byref(i)),-26)
  self.assertEqual(self.lib.count(1),0);self.assertTrue(self.lib.close())
 def test_missing_or_corrupt_seed_never_opens_network(self):
  self.lib.set(2,-23);self.assertTrue(self.lib.begin());self.lib.step();i=Info()
  self.assertEqual(self.lib.take(C.byref(i)),-23);self.assertEqual(self.lib.count(1),0);self.assertEqual(self.lib.count(2),0)
 def test_timeout_uses_retail_clock_macro(self):
  self.connect();self.lib.set(0,44000);self.lib.step();i=Info();self.assertEqual(self.lib.take(C.byref(i)),1)
  self.lib.set(0,46000);self.lib.step();self.assertEqual(self.lib.take(C.byref(i)),-27)
 def test_transfer_activity_extends_idle_deadline(self):
  self.connect();self.lib.set(9,1);self.lib.set(0,44000);self.lib.step();self.lib.set(9,0)
  self.lib.set(0,80000);self.lib.step();i=Info();self.assertEqual(self.lib.take(C.byref(i)),1)
  self.lib.set(0,90000);self.lib.step();self.assertEqual(self.lib.take(C.byref(i)),-27)
 def test_existing_online_transport_is_never_stopped(self):
  self.lib.set(3,3);self.connect();self.finish();self.lib.close();self.assertEqual(self.lib.count(3),0)
 def test_transport_adopted_by_room_is_kept(self):
  self.connect();self.finish();self.lib.set(7,1);self.lib.close();self.assertEqual(self.lib.count(3),0)
 def test_busy_request_does_not_overwrite_active_request(self):
  self.connect();self.assertFalse(self.lib.begin());self.finish()
 def test_tls_failure_can_retry(self):
  self.connect();self.lib.set(6,-8);self.lib.step();i=Info();self.assertEqual(self.lib.take(C.byref(i)),-8)
  self.connect();self.finish();self.assertEqual(self.lib.count(0),2)
 def test_missing_native_image_is_rejected(self):
  self.lib.set(8,1);self.assertFalse(self.lib.begin());self.assertEqual(self.lib.count(0),0)
if __name__=='__main__':unittest.main()
