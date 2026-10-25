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
#include "susamune/live_group.hxx"
#include "susamune/live_invites.hxx"
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
static u64 rtcTicks;
static u64 OSGetTime(){return rtcTicks?rtcTicks:clockMs;}
#define OS_TIMER_CLOCK 1ull
#define ONLINE_EXTRAS 1
extern "C" int memcmp(const void*p,const void*q,__SIZE_TYPE__ n){auto*a=(const u8*)p;auto*b=(const u8*)q;for(;n--;++a,++b)if(*a!=*b)return *a<*b?-1:1;return 0;}
struct SusamuneOnlineNameCfg {unsigned magic;char name[28];unsigned short secret,secretDay;unsigned char last[6],model,flags,friendCode[8];
 unsigned short scoreX,scoreY;unsigned char scoreScale,reserved[39];};
static SusamuneOnlineNameCfg savedBlock;static bool savedAvailable;static unsigned dirtyMarks;
static void DCStoreRange(void*,unsigned){}static void DCInvalidateRange(void*,unsigned){}
enum{SETTING_DISABLE_WARPS};struct Settings{bool getBool(int){return false;}void markDirty(){++dirtyMarks;}}gSettings;
struct QFTStub{unsigned serial;unsigned attemptSerial()const{return serial;}};static QFTStub gQFTTimer;
class Menu{public:bool shown(){return true;}bool openOnline(){return true;}};static Menu*gMenu;
namespace StageLoader{bool active(){return false;}bool onlinePlaylistActive(){return false;}void cancel(){}}
namespace LevelWarp{bool readyForOnlineRace(){return true;}}
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
}
static bool haveLocal;static TWLiveEndpoint localAddr;
namespace LiveTransport {
bool localEndpoint(Endpoint*e){if(!haveLocal)return false;*e=localAddr;return true;}
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
namespace LiveGhost {void resetAll(){++ghostResets;}}
namespace LiveGroup {
bool host(Room&,LiveRaceSession::Session&,const Config&,const LivePlaylist::Plan*,const Hooks&,unsigned){return true;}
void replacePeer(Room&,const TWLiveEndpoint&,const TWLiveEndpoint&,unsigned){}
void stop(Room&){}unsigned connectedCount(const Room&){return 0;}
bool receive(Room&,const TWLiveEndpoint&,const void*,unsigned,unsigned){return false;}
}
namespace LiveGroupRules{unsigned actor(const State&){return Nobody;}}
namespace LiveDraft{u8 currentActor(const State&){return 255;}}

'''
        code += session[session.index("// P2P codec begin"):session.index("// P2P codec end")]
        transport = (ROOT / "src/live_transport.cpp").read_text()
        code += "namespace LiveTransport {\n" + function(transport, "diagnostics") + "\n}\n"
        code += source[source.index("namespace LiveRace {"):source.index("u32 nowMs()")]
        code += r'''
u32 nowMs(){return clockMs;}
SusamuneOnlineNameCfg*savedName(){return savedAvailable?&savedBlock:nullptr;}
bool validOptions(const Options&){return true;}
const Session::Callbacks kCallbacks={};
void acceptConnection(){if(s.session.info.connected)s.connected=true;}
void updatePose(u32){++poses;}
void serviceRace(){++raceServices;}
void serviceGroup(u32){}
const LiveGroup::Hooks kGroupHooks={};
LiveGroup::Config groupConfig(){return {};}
'''
        for name in ("sendControl", "sendPose", "canConfigureRace", "begin", "startSession", "usePeer", "sampleAttempt",
                     "freshSecret", "today", "roomSecret"):
            code += function(source, name) + "\n"
        code += "}\n"
        for name in ("guestName", "enterGuestCode", "enterCode", "disconnect", "serviceAutoOpen", "update", "status"):
            code += function(source, name) + "\n"
        code += "}\n"
        code += r'''
using namespace LiveRace;
static const TWLiveEndpoint kHost={{203,0,113,7},48222,0},kJoiner={{198,51,100,9},50123,0};
static void reset(bool running=true){
 s={};sOptions={};sOptions.players=2;x={};network={};mailbox={};nextPacket={};stunResult={};clockMs=1000;network.epoch=7;
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
static void codeOf(const TWLiveEndpoint&e,unsigned secret,unsigned,char*out){
 LiveP2P::Code c={e,secret};LiveP2P::encode(c,out);
}
#define CHECK(x) do{if(!(x))return __LINE__;}while(0)
#define API extern "C" __declspec(dllexport)
API unsigned scenario(unsigned test){
 rtcTicks=0;savedAvailable=false;savedBlock={};dirtyMarks=0;
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
  CHECK(s.active&&!s.connected&&x.networkRetry&&transportStops==1&&!sessionStops&&stunCancels==1&&!ghostResets);
  CHECK(s.message==Text2::reconnecting&&localFrames==2);
 }else if(test==2){
  const unsigned states[]={TW_LIVE_FAILED,TW_LIVE_RETIRING,TW_LIVE_IDLE};
  for(unsigned state:states){reset();frame(1001,state);CHECK(s.active&&x.networkRetry&&transportStops==1&&s.message==Text2::reconnecting&&polled==1);}
 }else if(test==3){
  reset(false);frame(1001,TW_LIVE_UNAVAILABLE);CHECK(!polled&&!transportStops&&localFrames==1);
 }else if(test==4){
  reset(false);clockMs=60000;CHECK(begin(true));CHECK(s.networkSeenMs==60000&&s.openedMs==60000);
  frame(60001,TW_LIVE_UNAVAILABLE);CHECK(s.active&&!transportStops&&!stunStarts);
  frame(60002,TW_LIVE_READY);CHECK(s.active&&s.stunStarted&&stunStarts==1&&s.networkSeenMs==60002);
 }else if(test==5){
  frame(14000,TW_LIVE_READY);frame(16001,TW_LIVE_UNAVAILABLE);CHECK(s.active&&!transportStops);
  frame(28999,TW_LIVE_UNAVAILABLE);CHECK(s.active&&!transportStops);
  frame(29000,TW_LIVE_UNAVAILABLE);CHECK(s.active&&x.networkRetry&&transportStops==1);
 }else if(test==6){
  endlessPackets=true;frame(1001,TW_LIVE_READY);
  CHECK(s.active&&received==4&&sessionTicks==1&&poses==1&&raceServices==1&&localFrames==1);
 }else if(test==7){
  s.networkSeenMs=0xfffffff0u;frame(0x20,TW_LIVE_UNAVAILABLE);CHECK(s.active);
  frame(0xfffffff0u+15000u,TW_LIVE_UNAVAILABLE);CHECK(s.active&&x.networkRetry&&transportStops==1);
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
  // No STUN answer: retain the room and diagnostics, then retry without user input.
  reset(false);CHECK(begin(true));publishDiagnostics();frame(1001,TW_LIVE_READY);
  CHECK(s.diagnostics.socketAvailable&&s.diagnostics.socketSent==0xabcd&&s.diagnostics.socketError==-77);
  mailbox.networkInfo.generation=0;stunResult.state=LiveStun::DONE;stunResult.answered=0;stunResult.attempts=6;
  frame(1002,TW_LIVE_READY);
  CHECK(s.active&&s.message==Text::noAddress&&s.diagnostics.socketSent==0xabcd&&s.diagnostics.socketError==-77);
  CHECK(s.diagnostics.trouble&&LiveRace::status().diagnostics.net==NET_UP);
  frame(3003,TW_LIVE_READY);CHECK(stunStarts==2);auto out=LiveRace::status();
  CHECK(out.active&&out.diagnostics.socketAvailable&&out.diagnostics.socketReceived==0x1234&&!out.code[0]);
  disconnect();CHECK(begin(true));CHECK(!s.diagnostics.socketAvailable&&!s.diagnostics.socketSent&&!s.networkError);
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
  CHECK(s.own.secret>=1&&s.own.secret<=LiveP2P::SECRET_MAX);
  CHECK(s.started&&hostStarts==1&&!sessionPeer.port&&sessionPin==s.own.secret&&s.message==Text::shareCode);
  auto out=LiveRace::status();
  CHECK(out.code[4]=='-'&&out.code[9]=='-'&&out.code[14]=='-'&&out.code[16]&&out.code[17]==0&&!out.friendCode[0]&&out.hint==Text::hintHost&&out.connection==Text::waitingFriend);
  LiveP2P::Code back;CHECK(LiveP2P::decode(out.code,&back)&&back.secret==s.own.secret&&back.endpoint.ip[3]==7&&back.endpoint.port==48222);
  frame(1500,TW_LIVE_READY);CHECK(!punchesSent);
 }else if(test==12){
  // Joiner: waits for the host's code, then joins with its PIN and punches every 200 ms.
  CHECK(open(false,kJoiner));CHECK(!s.started&&s.message==Text::enterCode);
  char code[20];codeOf(kHost,4242,LiveP2P::HOST,code);
  CHECK(enterCode(code)==nullptr);
  CHECK(s.started&&guestStarts==1&&sessionPeer.port==kHost.port&&sessionPeer.ip[0]==203&&sessionPin==4242);
  CHECK(s.message==Text::connecting&&LiveRace::status().connection==Text::connecting);
  frame(1010,TW_LIVE_READY);CHECK(punchesSent==1&&lastSent.port==kHost.port);
  frame(1100,TW_LIVE_READY);CHECK(punchesSent==1);
  frame(1210,TW_LIVE_READY);CHECK(punchesSent==2);
  s.session.info.connected=true;frame(1300,TW_LIVE_READY);CHECK(s.connected&&punchesSent==2);
  frame(1600,TW_LIVE_READY);CHECK(punchesSent==2);
  CHECK(!LiveRace::status().code[0]&&LiveRace::status().hint==Text::empty);
 }else if(test==13){
  // Code checks: own code, typos and an inactive tab. Codes carry no role.
  CHECK(open(true,kHost));char code[20];
  LiveP2P::Code own=s.own;LiveP2P::encode(own,code);CHECK(enterCode(code)==Text::ownCode);
  codeOf(kJoiner,77,LiveP2P::JOINER,code);code[3]=code[3]=='2'?'3':'2';CHECK(enterCode(code)==Text::badCode);
  CHECK(enterCode("")==Text::badCode&&!s.friendKnown);
  codeOf(kJoiner,77,LiveP2P::JOINER,code);CHECK(enterCode(code)==nullptr&&s.friendKnown);
  CHECK(sInvites.slots[0].punch.peers[0].state==LiveP2P::PUNCHING&&sInvites.pin==s.own.secret);
  CHECK(hostStarts==1&&!guestStarts);
  frame(1010,TW_LIVE_READY);CHECK(punchesSent==1&&lastSent.port==kJoiner.port);
  CHECK(LiveRace::status().friendCode[0]);
  disconnect();CHECK(enterCode(code)==Text::roomFirst);
  CHECK(open(false,kJoiner));codeOf(kHost,5,LiveP2P::JOINER,code);CHECK(enterCode(code)==nullptr&&guestStarts==1);
 }else if(test==14){
  // A joiner whose handshake times out never gives up: it restarts at once and,
  // after 30 s, says it is still trying; a symmetric NAT gets its own explanation.
  CHECK(open(false,kJoiner,LiveStun::DIFFERENT_MAPPING));
  CHECK(LiveRace::status().hint==Text::hintSymmetric);
  char code[20];codeOf(kHost,9,LiveP2P::HOST,code);CHECK(enterCode(code)==nullptr);
  s.session.info.state=LiveRaceSession::FAILED;frame(1100,TW_LIVE_READY);
  CHECK(s.active&&s.started&&guestStarts==2&&!s.unreachable&&s.message==Text::connecting);
  frame(31003,TW_LIVE_READY);CHECK(s.active&&s.unreachable&&s.message==Text2::stillTrying);
  CHECK(LiveRace::status().connection==Text2::stillTrying&&LiveRace::status().hint==Text::hintSymmetric);
  stunResult.verdict=LiveStun::SAME_MAPPING;CHECK(LiveRace::status().hint==Text::hintBlocked);
  CHECK(enterCode(code)==nullptr&&s.started&&!s.unreachable);
 }else if(test==15){
  // The host restarts its listener when a handshake times out, and flags 30 s without a path.
  CHECK(open(true,kHost));char code[20];codeOf(kJoiner,9,LiveP2P::JOINER,code);
  CHECK(enterCode(code)==nullptr);
  s.session.info.state=LiveRaceSession::FAILED;frame(2000,TW_LIVE_READY);
  CHECK(s.active&&s.started&&hostStarts==2&&!s.unreachable);
  frame(31002,TW_LIVE_READY);CHECK(!s.unreachable);
  frame(31003,TW_LIVE_READY);CHECK(s.unreachable&&s.message==Text2::stillTrying&&s.active&&LiveRace::status().hint==Text::hintBlocked);
  s.session.info.connected=true;frame(31100,TW_LIVE_READY);CHECK(s.connected&&LiveRace::status().connection==Text::connected);
 }else if(test==17){
  // The Wii network may need many seconds for DHCP; the tab says it is waiting, then why it stopped.
  reset(false);CHECK(begin(true));CHECK(s.diagnostics.net==NET_WAITING);
  frame(1001,TW_LIVE_OPENING);CHECK(s.active&&!s.diagnostics.waitedS&&LiveRace::status().diagnostics.net==NET_WAITING);
  frame(25000,TW_LIVE_OPENING);CHECK(s.active&&!transportStops&&s.diagnostics.waitedS==24);
  frame(31001,TW_LIVE_OPENING);CHECK(s.active&&x.networkRetry&&s.diagnostics.trouble);
  CHECK(LiveRace::status().diagnostics.net==NET_FAILED&&!LiveRace::status().localIp[0]);
  // Sends that never leave the Wii are reported as such, not as an internet problem.
  reset(false);CHECK(begin(true));haveLocal=true;localAddr=TWLiveEndpoint{{192,168,1,20},48222,0};
  clockMs=4000;network.txRead=3;frame(4000,TW_LIVE_READY);
  CHECK(s.diagnostics.net==NET_UP&&s.diagnostics.waitedS==3&&s.diagnostics.forwarded==3&&s.diagnostics.ip[3]==20);
  stunResult.state=LiveStun::DONE;stunResult.answered=0;stunResult.attempts=4;frame(4100,TW_LIVE_READY);
  CHECK(s.active&&s.message==Text::noSend);
  auto out=LiveRace::status();CHECK(out.localIp[0]==192&&out.localPort==48222&&out.diagnostics.net==NET_UP&&out.diagnostics.trouble);
  // A clean disconnect keeps the address and shows the network as off.
  reset(false);CHECK(begin(true));frame(1001,TW_LIVE_READY);disconnect();
  out=LiveRace::status();CHECK(out.diagnostics.net==NET_OFF&&!out.diagnostics.trouble&&out.localIp[3]==20);
  haveLocal=false;
 }else if(test==16){
  // A saved room code cannot admit a guest without an explicit invitation.
  CHECK(open(true,kHost));
  u8 punch[LiveP2P::PUNCH_BYTES];LiveP2P::Punch other;LiveP2P::reset(other,s.own.secret,LiveP2P::JOINER);
  LiveP2P::add(other,kHost,LiveP2P::HOST);CHECK(LiveP2P::due(other,0,0,punch)==LiveP2P::PUNCH_BYTES);
  nextPacket.endpoint=kJoiner;nextPacket.bytes=sizeof(punch);memcpy(nextPacket.data,punch,sizeof(punch));
  endlessPackets=true;frame(1100,TW_LIVE_READY);
  CHECK(!sInvites.slots[0].punch.peers[0].state&&s.diagnostics.accepted==4);
  endlessPackets=false;frame(1400,TW_LIVE_READY);CHECK(!punchesSent);
  // A wrong PIN is consumed but opens nothing.
  CHECK(open(true,kHost));LiveP2P::reset(other,s.own.secret+1,LiveP2P::JOINER);LiveP2P::add(other,kHost,LiveP2P::HOST);
  LiveP2P::due(other,0,0,punch);nextPacket.endpoint=kJoiner;nextPacket.bytes=sizeof(punch);
  memcpy(nextPacket.data,punch,sizeof(punch));endlessPackets=true;
  frame(1100,TW_LIVE_READY);CHECK(!s.punch.peers[0].state&&s.diagnostics.accepted==4);
 }else if(test==18){
  // Waiting never stops: 200 ms punches for 30 s, then one a second.
  CHECK(open(false,kJoiner));char code[20];codeOf(kHost,9,LiveP2P::HOST,code);CHECK(enterCode(code)==nullptr);
  for(unsigned now=1010;now<31000;now+=10)frame(now,TW_LIVE_READY);
  CHECK(punchesSent>=145&&punchesSent<=151&&s.active);const unsigned early=punchesSent;
  for(unsigned now=31010;now<91010;now+=10)frame(now,TW_LIVE_READY);
  CHECK(punchesSent-early>=59&&punchesSent-early<=61&&s.active&&s.message==Text2::stillTrying);
  // Typing the code again keeps the room and STUN address.
  CHECK(enterCode(code)==nullptr&&s.active&&s.addressed&&!transportStops&&!stunCancels);
 }else if(test==19){
  // STUN every 15 s while waiting keeps the mapping; a new address is reported.
  CHECK(open(true,kHost));frame(16002,TW_LIVE_READY);CHECK(stunStarts==1);
  frame(16003,TW_LIVE_READY);CHECK(stunStarts==2&&x.stunKeepalive);
  stunResult.state=LiveStun::RUNNING;frame(16100,TW_LIVE_READY);CHECK(x.stunKeepalive&&!x.codeChanged);
  stunDone(kHost);frame(16200,TW_LIVE_READY);CHECK(!x.stunKeepalive&&!x.codeChanged);
  TWLiveEndpoint moved=kHost;moved.port=40000;frame(31203,TW_LIVE_READY);CHECK(stunStarts==3);
  stunDone(moved);frame(31300,TW_LIVE_READY);CHECK(x.codeChanged&&s.own.endpoint.port==40000);
  CHECK(LiveRace::status().codeChanged);
 }else if(test==20){
  // Neither long outages nor the other player leaving destroys the local room.
  CHECK(open(true,kHost));s.session.info.connected=true;frame(2000,TW_LIVE_READY);CHECK(s.connected);
  s.session.info.connected=false;s.session.info.state=LiveRaceSession::FAILED;s.session.info.error=LiveRaceSession::PEER_TIMEOUT;
  const unsigned resets=ghostResets;
  frame(3000,TW_LIVE_READY);CHECK(s.active&&!s.connected&&x.reconnecting&&hostStarts==2&&s.message==Text2::reconnecting);
  CHECK(LiveRace::status().reconnecting&&LiveRace::status().connection==Text2::reconnecting&&ghostResets==resets);
  s.session.info.state=LiveRaceSession::LISTENING;frame(122999,TW_LIVE_READY);CHECK(s.active&&x.reconnecting);
  frame(123000,TW_LIVE_READY);CHECK(s.active&&x.reconnecting&&!transportStops);
  CHECK(open(false,kJoiner));char code[20];codeOf(kHost,9,LiveP2P::HOST,code);CHECK(enterCode(code)==nullptr);
  s.session.info.connected=true;frame(2000,TW_LIVE_READY);CHECK(s.connected);
  s.session.info.connected=false;s.session.info.state=LiveRaceSession::FAILED;s.session.info.error=LiveRaceSession::PEER_TIMEOUT;
  frame(3000,TW_LIVE_READY);CHECK(x.reconnecting&&guestStarts==2&&sessionPeer.port==kHost.port);
  s.session.info.state=LiveRaceSession::FAILED;s.session.info.error=LiveRaceSession::PEER_LEFT;frame(3100,TW_LIVE_READY);CHECK(s.active&&x.reconnecting&&!transportStops);
 }else if(test==23){
  CHECK(open(true,kHost));char code[20];codeOf(kJoiner,9,0,code);CHECK(enterCode(code)==nullptr);
  s.session.info.connected=true;frame(2000,TW_LIVE_READY);s.round=17;s.localWins=2;const unsigned resets=ghostResets,stops=sessionStops;
  frame(2100,TW_LIVE_RETIRING);CHECK(s.active&&x.networkRetry&&s.friendKnown&&s.round==17&&s.localWins==2);
  frame(3000,TW_LIVE_IDLE);CHECK(x.networkRetry);
  frame(4100,TW_LIVE_IDLE);CHECK(!x.networkRetry&&s.active&&s.openedMs==4100);
  frame(4200,TW_LIVE_READY);CHECK(s.connected&&s.active&&s.round==17&&s.localWins==2&&s.friendKnown);
  stunDone(kHost);frame(4300,TW_LIVE_READY);CHECK(s.own.endpoint.port==kHost.port);
  CHECK(sessionStops==stops&&ghostResets==resets&&transportStops==1);
  disconnect();CHECK(!s.active&&!x.networkRetry&&sessionStops==stops+1&&ghostResets==resets+1);
 }else if(test==21){
  // The room secret is kept per console and rotated after 90 days of a valid clock.
  savedAvailable=true;savedBlock.secret=1234;
  CHECK(open(true,kHost));CHECK(s.own.secret==1234&&!savedBlock.secretDay&&!x.codeChanged);  // clock unset
  CHECK(savedBlock.last[0]==203&&savedBlock.last[4]==(48222>>8)&&dirtyMarks==1);
  rtcTicks=9100ull*86400;CHECK(open(true,kHost));
  CHECK(s.own.secret==1234&&savedBlock.secretDay==9100&&!x.codeChanged&&dirtyMarks==2);  // old ini gets today
  rtcTicks=9189ull*86400;CHECK(open(true,kHost));
  CHECK(s.own.secret==1234&&savedBlock.secretDay==9100&&!x.codeChanged&&dirtyMarks==2);
  rtcTicks=9190ull*86400;CHECK(open(true,kHost));
  CHECK(s.own.secret!=1234&&s.own.secret>=1&&s.own.secret<=LiveP2P::SECRET_MAX&&savedBlock.secret==s.own.secret);
  CHECK(savedBlock.secretDay==9190&&x.codeChanged&&sessionPin==s.own.secret);
  const unsigned rotated=s.own.secret;
  rtcTicks=100ull*86400;CHECK(open(true,kHost));CHECK(s.own.secret==rotated&&!x.codeChanged);  // clock set back
  TWLiveEndpoint moved=kHost;moved.ip[3]=8;CHECK(open(true,moved));
  CHECK(s.own.secret==rotated&&x.codeChanged&&savedBlock.last[3]==8&&LiveRace::status().codeChanged);
  char code[20];codeOf(kJoiner,77,0,code);CHECK(enterCode(code)==nullptr);
  CHECK(sInvites.slots[0].code.endpoint.ip[0]==198&&sInvites.slots[0].code.secret==77);
 }else if(test==22){
  // Read-only round clock: a retry 1001 ms after the first attempt adds 120 qf.
  s.phase=RUNNING;gQFTTimer.serial=5;sampleAttempt(100);CHECK(x.attemptSeen&&x.firstAttemptMs==100);
  sampleAttempt(500);CHECK(x.lastAttemptMs==100);gQFTTimer.serial=6;sampleAttempt(1101);CHECK(x.lastAttemptMs==1101&&x.firstAttemptMs==100);
  s.phase=WAIT_READY;gQFTTimer.serial=7;sampleAttempt(2000);CHECK(x.lastAttemptMs==1101);
 }
 return 0;
}
'''
        code = code.replace("void update() {", "__attribute__((noinline)) void update() {")
        cls.generated = code
        cpp, dll = work / "test.cpp", work / "test.dll"
        cpp.write_text(code)
        result = subprocess.run([str(ROOT / "toolchain/clang++.exe"),
            "--target=x86_64-pc-windows-msvc", "-std=c++17", "-shared", "-nostdlib", "-fno-builtin",
            "-fno-exceptions", "-fno-rtti", "-fno-inline-functions", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
            "-I", str(work), "-I", str(ROOT / "include"), str(cpp), str(ROOT / "src/live_invites.cpp"), "-DTIMEWARP_LIVE_RACING=1", "-o", str(dll)],
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
                 "host restart and timeout", "one-code adoption", "network wait and send diagnostics",
                 "waiting never gives up", "STUN keepalive", "reconnect and leave", "per-console secret rotation",
                 "round clock sampling", "transport recovery preserves room")
        for number, name in enumerate(names):
            with self.subTest(name=name):
                line = self.lib.scenario(number)
                self.assertEqual(line, 0, self.generated.splitlines()[line - 1] if line else "")


if __name__ == "__main__":
    unittest.main()
