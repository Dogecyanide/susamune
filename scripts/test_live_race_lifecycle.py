"""Exercise production frame servicing around unavailable ARM status snapshots."""
import ctypes as C
import _ctypes
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]


class LiveRaceLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="live-race-lifecycle-", dir=ROOT / "build")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        (work / "Dolphin").mkdir()
        (work / "Dolphin/types.h").write_text(
            "using u8=unsigned char;using u16=unsigned short;using u32=unsigned;"
            "using s32=int;using u64=unsigned long long;")
        source = (ROOT / "src/live_race.cpp").read_text()
        code = r'''
#define TIMEWARP_LIVE_RACING 1
#include "susamune/live_race.hxx"
#include "susamune/live_race_session.hxx"
#include "susamune/live_relay.hxx"
#include "susamune/live_transport.hxx"
#include "susamune/ghost_format.h"
extern "C" void* memcpy(void*d,const void*s,__SIZE_TYPE__ n){auto*a=(u8*)d;auto*b=(const u8*)s;while(n--)*a++=*b++;return d;}
extern "C" void* memset(void*d,int c,__SIZE_TYPE__ n){auto*a=(u8*)d;while(n--)*a++=(u8)c;return d;}
static unsigned clockMs,polled,received,relayTicks,sessionTicks,transportStops,ghostResets;
static unsigned sessionStops,relayStops,relayBegins,poses,raceServices,localFrames;
static bool endlessPackets, relayAccepts, submitAccepts;
static LiveTransport::Status network;
static TWLiveMailbox mailbox;
static u64 OSGetTime(){return clockMs;}
enum{VI_PAL=1};static unsigned VIGetTvFormat(){return 0;}
namespace LiveTransport {
static volatile TWLiveMailbox *sWire=&mailbox;
static void flush(volatile void*,unsigned){}
static void invalidate(const volatile void*,unsigned){}
static void barrier(){}
static const TWLiveIo kIo={flush,invalidate,barrier};
bool begin(unsigned short){return true;}
Status poll(){++polled;return network;}
bool localEndpoint(Endpoint*){return false;}
bool sendControl(const Endpoint&,const void*,unsigned){return submitAccepts;}
bool publishPose(const Endpoint&,const void*,unsigned){return submitAccepts;}
bool receive(Packet& packet){++received;packet={};return endlessPackets;}
void stop(){++transportStops;}
}
namespace LiveStun { void update(){} }
namespace LiveRelay {
bool init(Client&c,const Callbacks&){c.info.state=WAITING;return true;}
bool begin(Client&,bool,unsigned,unsigned,unsigned,const Endpoint&,unsigned){++relayBegins;return true;}
bool receive(Client&,const Endpoint&,const void*,unsigned,unsigned){return relayAccepts;}
void tick(Client&,unsigned){++relayTicks;}
Status status(const Client&c){return c.info;}
void stop(Client&c){++relayStops;c.info.state=STOPPED;c.info.peerReady=false;}
}
namespace LiveRaceSession {
void tick(Session&,unsigned){++sessionTicks;}
Status status(const Session&s){return s.info;}
void stop(Session&s){++sessionStops;s.info.connected=false;s.info.state=STOPPED;}
}
namespace LiveGhost {void reset(){++ghostResets;}}
'''
        transport = (ROOT / "src/live_transport.cpp").read_text()
        code += "namespace LiveTransport {\n" + function(transport, "diagnostics") + "\n}\n"
        code += source[source.index("namespace LiveRace {"):source.index("u32 nowMs()")]
        code += r'''
u32 nowMs(){return clockMs;}
bool validOptions(const Options&){return true;}
Session::Endpoint serverEndpoint(){Session::Endpoint e={{192,0,2,1},38400,0};return e;}
bool startSession(u32){s.started=true;return true;}
void acceptConnection(){}
void updatePose(u32){++poses;}
void serviceRace(){++raceServices;}
const Relay::Callbacks kRelayCallbacks={};
const char* relayFailure(Relay::Error){return Text::serverLost;}
'''
        code += function(source, "relayControl") + "\n" + function(source, "relayPose") + "\n"
        code += function(source, "canConfigureRace") + "\n"
        code += function(source, "begin") + "\n}\n"
        code += function(source, "disconnect") + "\n" + function(source, "update") + "\n"
        code += function(source, "status") + "\n}\n"
        code += r'''
using namespace LiveRace;
static void reset(bool running=true){
 s={};sOptions={};network={};mailbox={};clockMs=1000;network.epoch=7;
 polled=received=relayTicks=sessionTicks=transportStops=ghostResets=sessionStops=relayStops=relayBegins=poses=raceServices=localFrames=0;
 endlessPackets=false;relayAccepts=submitAccepts=true;sOptions.serverIp[0]=192;sOptions.serverIp[3]=1;sOptions.port=38400;
 s.active=s.connected=s.relayStarted=s.started=running;s.openedMs=s.networkSeenMs=clockMs;
 s.relay.info.state=LiveRelay::READY;s.relay.info.peerReady=true;s.relay.info.roomCode=123456;
 s.session.info.state=LiveRaceSession::CONNECTED;s.session.info.connected=true;
}
static void frame(unsigned now,unsigned state){clockMs=now;network.state=state;update();++localFrames;}
static void publishDiagnostics(){
 auto& info=mailbox.networkInfo;info.generation=info.issued=1;info.epoch=network.epoch;
 info.reserved[0]=0xabcd1234u;info.reserved[1]=0x01efcdabu;info.reserved[2]=(unsigned)-77;
}
#define CHECK(x) do{if(!(x))return __LINE__;}while(0)
#define API extern "C" __declspec(dllexport)
API unsigned scenario(unsigned test){
 reset();
 if(test==0){
  s.networkError=-77;frame(1001,TW_LIVE_UNAVAILABLE);
  CHECK(s.active&&s.connected&&s.networkError==-77&&polled==1&&localFrames==1);
  CHECK(!transportStops&&!received&&!relayTicks&&!sessionTicks&&!poses&&!raceServices);
  frame(1010,TW_LIVE_READY);
  CHECK(s.active&&s.networkSeenMs==1010&&polled==2&&relayTicks==1&&sessionTicks==1&&poses==1&&raceServices==1&&localFrames==2);
 }else if(test==1){
  frame(15999,TW_LIVE_UNAVAILABLE);CHECK(s.active&&!transportStops);
  frame(16000,TW_LIVE_UNAVAILABLE);
  CHECK(!s.active&&!s.connected&&transportStops==1&&sessionStops==1&&relayStops==1&&ghostResets==1);
  CHECK(s.message==Text::networkLost&&localFrames==2);
 }else if(test==2){
  const unsigned states[]={TW_LIVE_FAILED,TW_LIVE_RETIRING,TW_LIVE_IDLE};
  for(unsigned state:states){reset();frame(1001,state);CHECK(!s.active&&transportStops==1&&s.message==Text::networkLost&&polled==1);}
 }else if(test==3){
  reset(false);frame(1001,TW_LIVE_UNAVAILABLE);CHECK(!polled&&!transportStops&&localFrames==1);
 }else if(test==4){
  reset(false);clockMs=60000;CHECK(begin(true));CHECK(s.networkSeenMs==60000&&s.openedMs==60000);
  frame(60001,TW_LIVE_UNAVAILABLE);CHECK(s.active&&!transportStops&&!relayBegins);
  frame(60002,TW_LIVE_READY);CHECK(s.active&&s.relayStarted&&relayBegins==1&&s.networkSeenMs==60002);
 }else if(test==5){
  frame(14000,TW_LIVE_READY);frame(16001,TW_LIVE_UNAVAILABLE);CHECK(s.active&&!transportStops);
  frame(28999,TW_LIVE_UNAVAILABLE);CHECK(s.active&&!transportStops);
  frame(29000,TW_LIVE_UNAVAILABLE);CHECK(!s.active&&transportStops==1);
 }else if(test==6){
  endlessPackets=true;frame(1001,TW_LIVE_READY);
  CHECK(s.active&&received==4&&relayTicks==1&&sessionTicks==1&&poses==1&&raceServices==1&&localFrames==1);
 }else if(test==7){
  s.networkSeenMs=0xfffffff0u;frame(0x20,TW_LIVE_UNAVAILABLE);CHECK(s.active);
  frame(0xfffffff0u+15000u,TW_LIVE_UNAVAILABLE);CHECK(!s.active&&transportStops==1);
 }else if(test==8){
  publishDiagnostics();network.state=TW_LIVE_READY;
  LiveTransport::Diagnostics value={};
  CHECK(LiveTransport::diagnostics(network,&value));
  CHECK(value.sent==0xabcd&&value.received==0x1234&&value.dropped==0xef);
  CHECK(value.sendErrors==0xcd&&value.receiveErrors==0xab&&value.lastError==-77);
  for(unsigned invalid=0;invalid<5;++invalid){
   publishDiagnostics();network.state=TW_LIVE_READY;value.sent=17;value.lastError=91;
   if(invalid==0)mailbox.networkInfo.epoch++;
   if(invalid==1)mailbox.networkInfo.generation=0;
   if(invalid==2)mailbox.networkInfo.issued++;
   if(invalid==3)mailbox.networkInfo.reserved[1]=0;
   if(invalid==4)network.state=TW_LIVE_RETIRING;
   CHECK(!LiveTransport::diagnostics(network,&value));CHECK(value.sent==17&&value.lastError==91);
  }
 }else if(test==9){
  publishDiagnostics();frame(1001,TW_LIVE_READY);
  CHECK(s.diagnostics.socketAvailable&&s.diagnostics.socketSent==0xabcd&&s.diagnostics.socketError==-77);
  mailbox.networkInfo.generation=0;s.relay.info.state=LiveRelay::FAILED;s.relay.info.error=(LiveRelay::Error)2;
  frame(1002,TW_LIVE_READY);
  CHECK(!s.active&&s.networkError==-1002&&s.diagnostics.socketSent==0xabcd&&s.diagnostics.socketError==-77);
  frame(1003,TW_LIVE_IDLE);auto out=LiveRace::status();
  CHECK(out.networkError==-1002&&out.diagnostics.socketAvailable&&out.diagnostics.socketReceived==0x1234);
  CHECK(begin(true));CHECK(!s.diagnostics.socketAvailable&&!s.diagnostics.socketSent&&!s.networkError);
 }else if(test==10){
  auto endpoint=serverEndpoint();submitAccepts=false;
  CHECK(!relayControl(nullptr,endpoint,nullptr,1)&&!s.diagnostics.submitted);
  CHECK(!relayPose(nullptr,endpoint,nullptr,1)&&!s.diagnostics.submitted);
  submitAccepts=true;CHECK(relayControl(nullptr,endpoint,nullptr,1));CHECK(relayPose(nullptr,endpoint,nullptr,1));
  CHECK(s.diagnostics.submitted==2);
  endlessPackets=true;relayAccepts=false;frame(1001,TW_LIVE_READY);
  CHECK(s.diagnostics.received==4&&!s.diagnostics.accepted&&!s.diagnostics.socketAvailable);
  relayAccepts=true;frame(1002,TW_LIVE_READY);CHECK(s.diagnostics.received==8&&s.diagnostics.accepted==4);
  disconnect();CHECK(begin(true));CHECK(!s.diagnostics.submitted&&!s.diagnostics.received&&!s.diagnostics.accepted);
 }
 return 0;
}
'''
        cls.generated = code
        cpp, dll = work / "test.cpp", work / "test.dll"
        cpp.write_text(code)
        result = subprocess.run([str(ROOT / "toolchain/clang++.exe"),
            "--target=x86_64-pc-windows-msvc", "-std=c++17", "-shared", "-nostdlib", "-fno-builtin",
            "-fno-exceptions", "-fno-rtti", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
            "-I", str(work), "-I", str(ROOT / "include"), str(cpp), "-o", str(dll)],
            capture_output=True, text=True, env={**os.environ, "TEMP": str(work), "TMP": str(work)})
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: _ctypes.FreeLibrary(cls.lib._handle))

    def test_status_publication_lifecycle(self):
        names = ("transient snapshot", "sustained loss", "explicit terminal state", "offline no work",
                 "begin timestamp", "last ready refresh", "bounded receive budget", "clock wrap",
                 "diagnostic decoding and validity", "timeout retention and retry", "packet acceptance counters")
        for number, name in enumerate(names):
            with self.subTest(name=name):
                line = self.lib.scenario(number)
                self.assertEqual(line, 0, self.generated.splitlines()[line - 1] if line else "")


if __name__ == "__main__":
    unittest.main()
