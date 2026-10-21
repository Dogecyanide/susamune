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
        session = (ROOT / "src/live_race_session.cpp").read_text()
        code = r'''
#define TIMEWARP_LIVE_RACING 1
#define IS_EMULATOR 0
#define SUSAMUNE_GAME_VERSION 1
#include "susamune/live_race.hxx"
#include "susamune/live_race_session.hxx"
#include "susamune/live_p2p.hxx"
#include "susamune/live_transport.hxx"
#include "susamune/ghost_format.h"
extern "C" void* memcpy(void*d,const void*s,__SIZE_TYPE__ n){auto*a=(u8*)d;auto*b=(const u8*)s;while(n--)*a++=*b++;return d;}
extern "C" void* memset(void*d,int c,__SIZE_TYPE__ n){auto*a=(u8*)d;while(n--)*a++=(u8)c;return d;}
static unsigned clockMs,polled,received,sessionTicks,transportStops,ghostResets;
static unsigned sessionStops,stunStarts,stunCancels,hostStarts,guestStarts,poses,raceServices,localFrames;
static unsigned punchesSent,sessionPin;
static bool endlessPackets, sessionAccepts, submitAccepts, sessionInitOk;
static TWLiveEndpoint lastSent, sessionPeer;
static LiveTransport::Status network;
static LiveTransport::Packet nextPacket;
static LiveStun::Result stunResult;
static TWLiveMailbox mailbox;
static u64 OSGetTime(){return clockMs;}
static unsigned OSGetTick(){return 0x1234567u;}
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
bool sendControl(const Endpoint&e,const void*,unsigned bytes){lastSent=e;if(bytes==LiveP2P::PUNCH_BYTES)++punchesSent;return submitAccepts;}
bool publishPose(const Endpoint&,const void*,unsigned){return submitAccepts;}
bool receive(Packet& packet){++received;packet=nextPacket;return endlessPackets;}
void stop(){++transportStops;}
}
namespace LiveStun {
void update(){}
bool startShared(){++stunStarts;stunResult.state=RUNNING;return true;}
bool accept(const LiveTransport::Packet&){return false;}
const Result &result(){return stunResult;}
void cancel(){++stunCancels;}
}
namespace LiveRaceSession {
bool init(Session&s,const Config&c,const Callbacks&){s=Session{};sessionPin=c.pin;return sessionInitOk;}
bool startHost(Session&s,const Endpoint&e,unsigned){++hostStarts;sessionPeer=e;s.info.state=LISTENING;return true;}
bool startGuest(Session&s,const Endpoint&e,unsigned){++guestStarts;sessionPeer=e;s.info.state=JOINING;return true;}
bool receivePacket(Session&,const Endpoint&,const void*,unsigned,unsigned){return sessionAccepts;}
void tick(Session&,unsigned){++sessionTicks;}
Status status(const Session&s){return s.info;}
void stop(Session&s){++sessionStops;s.info.connected=false;s.info.state=STOPPED;}
}
namespace LiveGhost {void reset(){++ghostResets;}}
'''
        code += session[session.index("// P2P codec begin"):session.index("// P2P codec end")]
        transport = (ROOT / "src/live_transport.cpp").read_text()
        code += "namespace LiveTransport {\n" + function(transport, "diagnostics") + "\n}\n"
        code += source[source.index("namespace LiveRace {"):source.index("u32 nowMs()")]
        code += r'''
u32 nowMs(){return clockMs;}
bool validOptions(const Options&){return true;}
const Session::Callbacks kCallbacks={};
void acceptConnection(){if(s.session.info.connected)s.connected=true;}
void updatePose(u32){++poses;}
void serviceRace(){++raceServices;}
'''
        for name in ("sendControl", "sendPose", "canConfigureRace", "begin", "startSession", "usePeer", "freshSecret"):
            code += function(source, name) + "\n"
        code += "}\n"
        for name in ("enterCode", "disconnect", "update", "status"):
            code += function(source, name) + "\n"
        code += "}\n"
        code += r'''
using namespace LiveRace;
static const TWLiveEndpoint kHost={{203,0,113,7},48222,0},kJoiner={{198,51,100,9},50123,0};
static void reset(bool running=true){
 s={};sOptions={};network={};mailbox={};nextPacket={};stunResult={};clockMs=1000;network.epoch=7;
 polled=received=sessionTicks=transportStops=ghostResets=sessionStops=stunStarts=stunCancels=0;
 hostStarts=guestStarts=poses=raceServices=localFrames=punchesSent=sessionPin=0;
 lastSent=sessionPeer=TWLiveEndpoint{};
 endlessPackets=false;sessionAccepts=submitAccepts=sessionInitOk=true;
 s.active=s.connected=s.stunStarted=s.addressed=s.started=running;s.openedMs=s.networkSeenMs=clockMs;
 s.session.info.state=LiveRaceSession::CONNECTED;s.session.info.connected=true;
}
static void frame(unsigned now,unsigned state){clockMs=now;network.state=state;update();++localFrames;}
static void publishDiagnostics(){
 auto& info=mailbox.networkInfo;info.generation=info.issued=1;info.epoch=network.epoch;
 info.reserved[0]=0xabcd1234u;info.reserved[1]=0x01efcdabu;info.reserved[2]=(unsigned)-77;
}
static void stunDone(const TWLiveEndpoint&mapped,unsigned verdict=LiveStun::SAME_MAPPING){
 stunResult.state=LiveStun::DONE;stunResult.answered=3;stunResult.verdict=(u8)verdict;
 stunResult.mapped[0]=stunResult.mapped[1]=mapped;
}
// Opens a fresh room as host or joiner and finishes its STUN lookup.
static bool open(bool hosting,const TWLiveEndpoint&mapped,unsigned verdict=LiveStun::SAME_MAPPING){
 reset(false);if(!begin(hosting))return false;
 frame(1001,TW_LIVE_READY);if(!s.stunStarted||stunStarts!=1||s.message!=Text::gettingAddress)return false;
 frame(1002,TW_LIVE_READY);if(s.addressed)return false;
 stunDone(mapped,verdict);frame(1003,TW_LIVE_READY);return s.addressed;
}
static void codeOf(const TWLiveEndpoint&e,unsigned secret,unsigned role,char*out){
 LiveP2P::Code c={e,secret,(u8)role};LiveP2P::encode(c,out);
}
#define CHECK(x) do{if(!(x))return __LINE__;}while(0)
#define API extern "C" __declspec(dllexport)
API unsigned scenario(unsigned test){
 reset();
 if(test==0){
  s.networkError=-77;frame(1001,TW_LIVE_UNAVAILABLE);
  CHECK(s.active&&s.connected&&s.networkError==-77&&polled==1&&localFrames==1);
  CHECK(!transportStops&&!received&&!sessionTicks&&!poses&&!raceServices);
  frame(1010,TW_LIVE_READY);
  CHECK(s.active&&s.networkSeenMs==1010&&polled==2&&sessionTicks==1&&poses==1&&raceServices==1&&localFrames==2);
 }else if(test==1){
  frame(15999,TW_LIVE_UNAVAILABLE);CHECK(s.active&&!transportStops);
  frame(16000,TW_LIVE_UNAVAILABLE);
  CHECK(!s.active&&!s.connected&&transportStops==1&&sessionStops==1&&stunCancels==1&&ghostResets==1);
  CHECK(s.message==Text::networkLost&&localFrames==2);
 }else if(test==2){
  const unsigned states[]={TW_LIVE_FAILED,TW_LIVE_RETIRING,TW_LIVE_IDLE};
  for(unsigned state:states){reset();frame(1001,state);CHECK(!s.active&&transportStops==1&&s.message==Text::networkLost&&polled==1);}
 }else if(test==3){
  reset(false);frame(1001,TW_LIVE_UNAVAILABLE);CHECK(!polled&&!transportStops&&localFrames==1);
 }else if(test==4){
  reset(false);clockMs=60000;CHECK(begin(true));CHECK(s.networkSeenMs==60000&&s.openedMs==60000);
  frame(60001,TW_LIVE_UNAVAILABLE);CHECK(s.active&&!transportStops&&!stunStarts);
  frame(60002,TW_LIVE_READY);CHECK(s.active&&s.stunStarted&&stunStarts==1&&s.networkSeenMs==60002);
 }else if(test==5){
  frame(14000,TW_LIVE_READY);frame(16001,TW_LIVE_UNAVAILABLE);CHECK(s.active&&!transportStops);
  frame(28999,TW_LIVE_UNAVAILABLE);CHECK(s.active&&!transportStops);
  frame(29000,TW_LIVE_UNAVAILABLE);CHECK(!s.active&&transportStops==1);
 }else if(test==6){
  endlessPackets=true;frame(1001,TW_LIVE_READY);
  CHECK(s.active&&received==4&&sessionTicks==1&&poses==1&&raceServices==1&&localFrames==1);
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
  // No STUN answer: no address to share, so the room closes and keeps its diagnostics.
  reset(false);CHECK(begin(true));publishDiagnostics();frame(1001,TW_LIVE_READY);
  CHECK(s.diagnostics.socketAvailable&&s.diagnostics.socketSent==0xabcd&&s.diagnostics.socketError==-77);
  mailbox.networkInfo.generation=0;stunResult.state=LiveStun::DONE;stunResult.answered=0;
  frame(1002,TW_LIVE_READY);
  CHECK(!s.active&&s.message==Text::noAddress&&s.diagnostics.socketSent==0xabcd&&s.diagnostics.socketError==-77);
  frame(1003,TW_LIVE_IDLE);auto out=LiveRace::status();
  CHECK(!out.active&&out.diagnostics.socketAvailable&&out.diagnostics.socketReceived==0x1234&&!out.code[0]);
  CHECK(begin(true));CHECK(!s.diagnostics.socketAvailable&&!s.diagnostics.socketSent&&!s.networkError);
 }else if(test==10){
  submitAccepts=false;
  CHECK(!sendControl(nullptr,kHost,nullptr,1)&&!s.diagnostics.submitted);
  CHECK(!sendPose(nullptr,kHost,nullptr,1)&&!s.diagnostics.submitted);
  submitAccepts=true;CHECK(sendControl(nullptr,kHost,nullptr,1));CHECK(sendPose(nullptr,kHost,nullptr,1));
  CHECK(s.diagnostics.submitted==2&&lastSent.port==kHost.port);
  endlessPackets=true;sessionAccepts=false;frame(1001,TW_LIVE_READY);
  CHECK(s.diagnostics.received==4&&!s.diagnostics.accepted&&!s.diagnostics.socketAvailable);
  sessionAccepts=true;frame(1002,TW_LIVE_READY);CHECK(s.diagnostics.received==8&&s.diagnostics.accepted==4);
  disconnect();CHECK(begin(true));CHECK(!s.diagnostics.submitted&&!s.diagnostics.received&&!s.diagnostics.accepted);
 }else if(test==11){
  // Host: STUN address becomes the code, and the session listens for anyone with the PIN.
  CHECK(open(true,kHost));
  CHECK(s.own.role==LiveP2P::HOST&&s.own.secret>=1&&s.own.secret<=LiveP2P::SECRET_MAX);
  CHECK(s.started&&hostStarts==1&&!sessionPeer.port&&sessionPin==s.own.secret&&s.message==Text::shareCode);
  auto out=LiveRace::status();
  CHECK(out.code[4]=='-'&&out.code[19]==0&&!out.friendCode[0]&&out.hint==Text::hintHost&&out.connection==Text::waitingFriend);
  LiveP2P::Code back;CHECK(LiveP2P::decode(out.code,&back)&&back.secret==s.own.secret&&back.endpoint.ip[3]==7&&back.endpoint.port==48222);
  frame(1500,TW_LIVE_READY);CHECK(!punchesSent);
 }else if(test==12){
  // Joiner: waits for the host's code, then joins with its PIN and punches every 200 ms.
  CHECK(open(false,kJoiner));CHECK(!s.started&&s.message==Text::enterCode&&s.own.role==LiveP2P::JOINER);
  char code[20];codeOf(kHost,424242,LiveP2P::HOST,code);
  CHECK(enterCode(code)==nullptr);
  CHECK(s.started&&guestStarts==1&&sessionPeer.port==kHost.port&&sessionPeer.ip[0]==203&&sessionPin==424242);
  CHECK(s.message==Text::connecting&&LiveRace::status().connection==Text::connecting);
  frame(1010,TW_LIVE_READY);CHECK(punchesSent==1&&lastSent.port==kHost.port);
  frame(1100,TW_LIVE_READY);CHECK(punchesSent==1);
  frame(1210,TW_LIVE_READY);CHECK(punchesSent==2);
  s.session.info.connected=true;frame(1300,TW_LIVE_READY);CHECK(s.connected&&punchesSent==2);
  frame(1600,TW_LIVE_READY);CHECK(punchesSent==2);
  CHECK(!LiveRace::status().code[0]&&LiveRace::status().hint==Text::empty);
 }else if(test==13){
  // Code checks: role, own code, typos and an inactive tab.
  CHECK(open(true,kHost));char code[20];
  codeOf(kJoiner,77,LiveP2P::HOST,code);CHECK(enterCode(code)==Text::needJoinerCode);
  LiveP2P::Code own=s.own;LiveP2P::encode(own,code);CHECK(enterCode(code)==Text::ownCode);
  codeOf(kJoiner,77,LiveP2P::JOINER,code);code[3]=code[3]=='2'?'3':'2';CHECK(enterCode(code)==Text::badCode);
  CHECK(enterCode("")==Text::badCode&&!s.friendKnown);
  codeOf(kJoiner,77,LiveP2P::JOINER,code);CHECK(enterCode(code)==nullptr&&s.friendKnown);
  CHECK(s.punch.peers[0].state==LiveP2P::PUNCHING&&s.punch.peers[0].participant==1&&s.punch.pin==s.own.secret);
  CHECK(hostStarts==1&&!guestStarts);
  frame(1010,TW_LIVE_READY);CHECK(punchesSent==1&&lastSent.port==kJoiner.port);
  CHECK(LiveRace::status().friendCode[0]);
  disconnect();CHECK(enterCode(code)==Text::roomFirst);
  CHECK(open(false,kJoiner));codeOf(kHost,5,LiveP2P::JOINER,code);CHECK(enterCode(code)==Text::needHostCode);
 }else if(test==14){
  // A joiner that never hears back reports it; a symmetric NAT gets its own explanation.
  CHECK(open(false,kJoiner,LiveStun::DIFFERENT_MAPPING));
  CHECK(LiveRace::status().hint==Text::hintSymmetric);
  char code[20];codeOf(kHost,9,LiveP2P::HOST,code);CHECK(enterCode(code)==nullptr);
  s.session.info.state=LiveRaceSession::FAILED;frame(1100,TW_LIVE_READY);
  CHECK(s.active&&!s.started&&s.unreachable&&s.message==Text::cantConnect);
  CHECK(LiveRace::status().connection==Text::cantConnect&&LiveRace::status().hint==Text::hintSymmetric);
  stunResult.verdict=LiveStun::SAME_MAPPING;CHECK(LiveRace::status().hint==Text::hintBlocked);
  CHECK(enterCode(code)==nullptr&&s.started&&guestStarts==2&&!s.unreachable);
 }else if(test==15){
  // The host restarts its listener when a handshake times out, and flags 30 s without a path.
  CHECK(open(true,kHost));char code[20];codeOf(kJoiner,9,LiveP2P::JOINER,code);
  CHECK(enterCode(code)==nullptr);
  s.session.info.state=LiveRaceSession::FAILED;frame(2000,TW_LIVE_READY);
  CHECK(s.active&&s.started&&hostStarts==2&&!s.unreachable);
  frame(31002,TW_LIVE_READY);CHECK(!s.unreachable);
  frame(31003,TW_LIVE_READY);CHECK(s.unreachable&&s.message==Text::cantConnect&&s.active&&LiveRace::status().hint==Text::hintBlocked);
  s.session.info.connected=true;frame(31100,TW_LIVE_READY);CHECK(s.connected&&LiveRace::status().connection==Text::connected);
 }else if(test==16){
  // One-code join: the host adopts a punch carrying its PIN from an unknown address.
  CHECK(open(true,kHost));
  u8 punch[LiveP2P::PUNCH_BYTES];LiveP2P::Punch other;LiveP2P::reset(other,s.own.secret,LiveP2P::JOINER);
  LiveP2P::add(other,kHost,LiveP2P::HOST);CHECK(LiveP2P::due(other,0,0,punch)==LiveP2P::PUNCH_BYTES);
  nextPacket.endpoint=kJoiner;nextPacket.bytes=sizeof(punch);memcpy(nextPacket.data,punch,sizeof(punch));
  endlessPackets=true;frame(1100,TW_LIVE_READY);
  CHECK(s.punch.peers[0].state==LiveP2P::OPEN&&s.punch.peers[0].endpoint.port==kJoiner.port&&s.diagnostics.accepted==4);
  endlessPackets=false;frame(1400,TW_LIVE_READY);CHECK(punchesSent>=1&&lastSent.port==kJoiner.port);
  // A wrong PIN is consumed but opens nothing.
  CHECK(open(true,kHost));LiveP2P::reset(other,s.own.secret+1,LiveP2P::JOINER);LiveP2P::add(other,kHost,LiveP2P::HOST);
  LiveP2P::due(other,0,0,punch);nextPacket.endpoint=kJoiner;nextPacket.bytes=sizeof(punch);
  memcpy(nextPacket.data,punch,sizeof(punch));endlessPackets=true;
  frame(1100,TW_LIVE_READY);CHECK(!s.punch.peers[0].state&&s.diagnostics.accepted==4);
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
                 "diagnostic decoding and validity", "no address retention and retry", "packet acceptance counters",
                 "host code and listener", "joiner punching", "code checks", "joiner failure hints",
                 "host restart and timeout", "one-code adoption")
        for number, name in enumerate(names):
            with self.subTest(name=name):
                line = self.lib.scenario(number)
                self.assertEqual(line, 0, self.generated.splitlines()[line - 1] if line else "")


if __name__ == "__main__":
    unittest.main()
