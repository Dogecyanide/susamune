"""Drive the production match and reliable session through two queued peers."""
import ctypes as C
import _ctypes
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]


class LiveRaceMatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="live-race-match-", dir=ROOT / "build")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        (work / "Dolphin").mkdir()
        (work / "Dolphin/types.h").write_text(
            "using u8=unsigned char;using u16=unsigned short;using u32=unsigned;using s32=int;")
        match = (ROOT / "src/live_race.cpp").read_text()
        session = (ROOT / "src/live_race_session.cpp").read_text()
        code = r'''
#define TIMEWARP_LIVE_RACING 1
#include "susamune/live_race.hxx"
#include "susamune/live_race_session.hxx"
#include "susamune/live_p2p.hxx"
#include "susamune/ghost_format.h"
extern "C" void* memset(void*p,int c,unsigned long long n){auto*b=(u8*)p;while(n--)*b++=(u8)c;return p;}
extern "C" void* memcpy(void*p,const void*q,unsigned long long n){auto*b=(u8*)p;auto*a=(const u8*)q;while(n--)*b++=*a++;return p;}
static unsigned current,starts[2],blocked[2];
namespace Ghost {bool observerPreparing(){return blocked[current];}bool observerStatsSuppressed(){return false;}}
namespace StageLoader {bool active(){return false;}}
namespace PracticeSession {bool ownsGameplayInput(){return false;}}
namespace SavestateManager {bool diskBusy(){return false;}}
namespace TasProject {bool busy(){return false;}}
namespace WarpWheel {bool shown(){return false;}bool promptPending(){return false;}}
enum {SETTING_DISABLE_WARPS};
static unsigned dirtyMarks,stores;
struct Settings {bool getBool(int){return false;}void markDirty(){++dirtyMarks;}}gSettings;
struct SusamuneOnlineNameCfg {unsigned magic;char name[28];};
#define SUSAMUNE_ONLINE_NAME_MAGIC 0x534F4E4Du
static SusamuneOnlineNameCfg savedBlock;static bool savedAvailable;
static void DCStoreRange(void*,unsigned){++stores;}
extern "C" int memcmp(const void*p,const void*q,unsigned long long n){auto*a=(const u8*)p;auto*b=(const u8*)q;for(;n--;++a,++b)if(*a!=*b)return *a<*b?-1:1;return 0;}
class Menu {public:void hide(){}};static Menu*gMenu;
struct QFTStub {unsigned serial;unsigned attemptSerial()const{return serial;}};static QFTStub gQFTTimer;
#define ONLINE_EXTRAS 1
namespace ILing {
int count(){return 16;}
int persistentSlot(int entry){return 100+entry;}
bool onlinePoolContains(int entry,unsigned pool){return entry>=0&&entry<15&&pool<3&&(pool==1||(pool==0?entry<8:entry>=8));}
int onlineDefaultEpisode(int entry){return entry>=0&&entry<count()?(entry+3)%8:-1;}
bool copyWarpDiscardName(int,char*,unsigned,unsigned*){return false;}
bool startOnline(int entry,int episode){if(entry<0||entry>=count()||episode<0||episode>7)return false;++starts[current];return true;}
}
namespace LiveGhost {void setName(const char*,unsigned){}}
struct Datagram {unsigned from,to,bytes;bool used;u8 data[256];};
static Datagram queue[2048];static unsigned queueEnd,clockMs;static bool congested[2];
static TWLiveEndpoint endpoints[2]={{{192,168,1,1},38400,0},{{192,168,1,2},38400,0}};
static bool transmit(void*,const TWLiveEndpoint&to,const void*p,unsigned n){
 if(congested[current]||queueEnd==2048||n>256)return false;
 auto&q=queue[queueEnd++];q={};q.from=current;q.to=to.ip[3]-1;q.bytes=n;q.used=true;memcpy(q.data,p,n);return true;
}
'''
        code += session[session.index("namespace LiveRaceSession {"):session.rindex("#endif")]
        code += match[match.index("namespace LiveRace {"):match.index("u32 nowMs()")]
        code += r'''
bool sendControl(void*,const Session::Endpoint&to,const void*p,unsigned n){return transmit(nullptr,to,p,n);}
u32 nowMs(){return clockMs;}
SusamuneOnlineNameCfg*savedName(){return savedAvailable?&savedBlock:nullptr;}
bool sendPose(void*,const Session::Endpoint&,const void*,unsigned){return true;}
void receivedPose(void*,const MSRHeader&,const MSRPose&,unsigned){}
'''
        code += match[match.index("bool validOptions("):match.index("bool begin(")]
        code += function(match, "acceptConnection") + "\n}\n"
        code += "\n".join(function(match, name) for name in ("configure", "ready", "newMatch", "chooseDraft", "onILResult"))
        code += "\n}\n"
        code += r'''
using namespace LiveRace;
static Runtime peers[2];static Options opts[2];static Extra extras[2];
static void select(unsigned p){current=p;s=peers[p];sOptions=opts[p];x=extras[p];}
static void keep(){peers[current]=s;opts[current]=sOptions;extras[current]=x;}
static void service(unsigned p){select(p);LiveRaceSession::tick(s.session,clockMs);acceptConnection();serviceRace();keep();}
static int find(unsigned to,unsigned kind=0){for(unsigned i=0;i<queueEnd;++i)if(queue[i].used&&queue[i].to==to){MSRHeader h;if(MSRDecodeHeader(queue[i].data,queue[i].bytes,&h)&&(!kind||h.kind==kind))return i;}return -1;}
static bool deliver(unsigned to,unsigned kind=0){
 const int index=find(to,kind);if(index<0)return false;
 Datagram q=queue[index];queue[index].used=false;select(to);
 const bool ok=LiveRaceSession::receivePacket(s.session,endpoints[q.from],q.data,q.bytes,clockMs);
 acceptConnection();keep();return ok;
}
static void pump(unsigned rounds=12){for(unsigned i=0;i<rounds;++i){clockMs+=10;for(unsigned p=0;p<2;++p){for(unsigned n=0;n<4&&find(p)>=0;++n)deliver(p);service(p);}}}
static bool connect(unsigned best=3,bool freeRoam=false,bool draft=false,bool setBo5=false,unsigned pool=0){
 memset(peers,0,sizeof(peers));memset(opts,0,sizeof(opts));memset(extras,0,sizeof(extras));memset(queue,0,sizeof(queue));queueEnd=0;clockMs=1;
 starts[0]=starts[1]=blocked[0]=blocked[1]=0;congested[0]=congested[1]=false;
 for(unsigned p=0;p<2;++p){select(p);sOptions={};memcpy(sOptions.name,p?"Guest":"Host",p?6:5);sOptions.bestOf=best;sOptions.entry=2;sOptions.episode=4;sOptions.freeRoam=!p&&freeRoam;
  if(!p){sOptions.draft=draft;sOptions.setBo5=setBo5;sOptions.pool=pool;}
  LiveRaceSession::Config c={};memcpy(c.name,sOptions.name,16);c.pin=123456;c.nonceLow=p+1;c.region=p;c.timing=MSR_TIMING_60HZ;
  if(!LiveRaceSession::init(s.session,c,kCallbacks))return false;s.hosting=p==0;s.active=s.started=true;
  TWLiveEndpoint any={};if(p?!LiveRaceSession::startGuest(s.session,endpoints[0],clockMs):!LiveRaceSession::startHost(s.session,any,clockMs))return false;keep();}
 pump();const auto expected=freeRoam?ROAMING:draft?DRAFTING:WAIT_READY;return peers[0].connected&&peers[1].connected&&peers[0].phase==expected&&peers[1].phase==expected&&!peers[0].session.info.pending&&!peers[1].session.info.pending;
}
// The link drops and both sides restart their sessions with the same room, as
// update() does after PEER_TIMEOUT: the match state must come back intact.
static unsigned generation;
static bool reconnect(){
 ++generation;
 for(unsigned p=0;p<2;++p){select(p);s.connected=false;x.reconnecting=true;
  LiveRaceSession::Config c={};memcpy(c.name,sOptions.name,16);c.pin=123456;c.nonceLow=p+1+2*generation;c.region=p;c.timing=MSR_TIMING_60HZ;
  if(!LiveRaceSession::init(s.session,c,kCallbacks))return false;
  TWLiveEndpoint any={};if(p?!LiveRaceSession::startGuest(s.session,endpoints[0],clockMs):!LiveRaceSession::startHost(s.session,any,clockMs))return false;keep();}
 pump();return peers[0].connected&&peers[1].connected&&!extras[0].reconnecting&&!extras[1].reconnecting;
}
static bool setReady(unsigned p){select(p);bool ok=ready();keep();return ok;}
static bool race(){if(!setReady(0)||!setReady(1))return false;pump();return peers[0].phase==RUNNING&&peers[1].phase==RUNNING&&starts[0]==starts[1];}
static void finish(unsigned p,int qf,bool eligible=true,int entry=2){select(p);onILResult(entry,qf,eligible);keep();}
static bool equal(const void*a,const void*b,unsigned bytes){const auto*x=(const u8*)a;const auto*y=(const u8*)b;while(bytes--)if(*x++!=*y++)return false;return true;}
static bool syncedDraft(){return equal(&peers[0].draft,&peers[1].draft,sizeof(peers[0].draft));}
static bool choose(unsigned p,unsigned candidate){select(p);const bool ok=chooseDraft(candidate);keep();return ok;}
static bool chooseAndPump(unsigned p,unsigned candidate){if(!choose(p,candidate))return false;pump();return syncedDraft();}
static bool openingDraft(){
 if(!chooseAndPump(0,0)||!chooseAndPump(1,1)||!chooseAndPump(1,2)||!chooseAndPump(0,3))return false;
 return peers[0].phase==WAIT_READY&&peers[1].phase==WAIT_READY&&!peers[0].localReady&&!peers[1].localReady;
}
static bool counterDraft(unsigned winner){
 if(peers[0].draft.phase!=LiveDraft::COUNTER_WINNER_BAN||LiveDraft::currentActor(peers[1].draft)!=winner)return false;
 return chooseAndPump(winner,0)&&chooseAndPump(winner^1,1)&&peers[0].phase==WAIT_READY&&peers[1].phase==WAIT_READY;
}
static bool completeDraftRound(unsigned winner,bool eligible=true){
 if(!race())return false;
 const int entry=opts[0].entry;
 finish(0,winner==1?200:100,eligible,entry);finish(1,winner==0?200:100,true,entry);pump();
 return syncedDraft();
}
#define CHECK(x) do{if(!(x))return __LINE__;}while(0)
#define API extern "C" __declspec(dllexport)
API int peerState(unsigned p,unsigned what){const Runtime&r=peers[p&1];
 const int v[]={(int)r.phase,(int)r.round,(int)r.localWins,(int)r.peerWins,r.localResult,r.peerResult,r.connected,r.resultSent,
  r.offerNeeded,r.readyNeeded,(int)r.session.info.pending,(int)r.session.info.state,extras[p&1].reconnecting,r.localReady,r.peerReady};
 return what<sizeof(v)/sizeof(v[0])?v[what]:-1;}
API unsigned scenario(unsigned test){
 CHECK(connect(test==1||test>=9?1:3,test==11));
 if(test==0){
  CHECK(!starts[0]&&!starts[1]);CHECK(setReady(0));pump();CHECK(!starts[0]&&!starts[1]);
  blocked[1]=1;CHECK(!setReady(1));blocked[1]=0;CHECK(setReady(1));pump();
  CHECK(peers[0].phase==RUNNING&&peers[1].phase==RUNNING&&starts[0]==1&&starts[1]==1);
  finish(0,100,true,3);CHECK(!peers[0].localResult);finish(0,100);finish(1,120);pump();
  CHECK(peers[0].localWins==1&&peers[1].peerWins==1&&peers[0].peerWins==0&&peers[1].localWins==0);
  CHECK(peers[0].round==2&&peers[1].round==2&&peers[0].phase==WAIT_READY&&peers[1].phase==WAIT_READY);
  CHECK(!peers[0].localReady&&!peers[1].localReady&&starts[0]==1&&starts[1]==1);
  CHECK(race());finish(0,100);finish(1,100);pump();
  CHECK(peers[0].localWins==1&&peers[1].peerWins==1&&peers[0].round==3&&peers[1].round==3);
  CHECK(race());finish(0,90,false);finish(1,120);pump();
  CHECK(peers[0].localWins==1&&peers[1].peerWins==1&&peers[0].round==4&&peers[1].round==4);
 }else if(test==1){
  CHECK(race());finish(0,200);finish(1,100);pump();
  CHECK(peers[0].phase==MATCH_DONE&&peers[1].phase==MATCH_DONE);
  CHECK(peers[0].peerWins==1&&peers[1].localWins==1);CHECK(!setReady(0)&&!setReady(1));
  const unsigned before=queueEnd;finish(1,0);pump();CHECK(peers[0].round==1&&peers[1].round==1);(void)before;
 }else if(test==2){
  CHECK(setReady(0)&&setReady(1));service(0);service(1);
  CHECK(deliver(0,MSR_READY));CHECK(deliver(1,MSR_READY));CHECK(deliver(0,MSR_ACK));
  service(0);CHECK(starts[0]==1);CHECK(deliver(1,MSR_START));
  CHECK(peers[1].startNeeded&&peers[1].session.info.pending);CHECK(setReady(1));
  pump();CHECK(starts[1]==0&&peers[0].phase==WAIT_READY&&peers[1].phase==WAIT_READY);
  CHECK(peers[0].round==2&&peers[1].round==2);
 }else if(test==3){
  CHECK(race());finish(1,200);service(1);CHECK(deliver(0,MSR_RESULT));CHECK(deliver(1,MSR_ACK));
  finish(0,100);service(0);CHECK(deliver(1,MSR_RESULT));CHECK(deliver(0,MSR_ACK));
  service(0);CHECK(deliver(1,MSR_READY));service(1);pump();
  CHECK(peers[0].round==2&&peers[1].round==2&&peers[1].phase==WAIT_READY);
  CHECK(peers[0].localWins==1&&peers[1].peerWins==1);
 }else if(test==4){
  CHECK(setReady(0)&&setReady(1));service(0);service(1);
  CHECK(deliver(0,MSR_READY));CHECK(deliver(1,MSR_READY));CHECK(deliver(0,MSR_ACK));
  service(0);CHECK(deliver(1,MSR_START));CHECK(deliver(0,MSR_ACK));
  CHECK(peers[1].session.info.pending);finish(0,100);service(0);CHECK(deliver(1,MSR_RESULT));
  CHECK(deliver(1,MSR_ACK));service(1);CHECK(peers[1].phase==RUNNING);
  CHECK(peers[1].peerResult&&peers[1].peerQf==100);finish(1,120);pump();
  CHECK(peers[0].localWins==1&&peers[1].peerWins==1&&peers[0].round==2&&peers[1].round==2);
 }else if(test==5){
  CHECK(race());finish(0,90);service(0);int i=find(1,MSR_RESULT);CHECK(i>=0);Datagram duplicate=queue[i];
  CHECK(deliver(1,MSR_RESULT));CHECK(deliver(0,MSR_ACK));finish(1,100);pump();
  select(1);CHECK(!LiveRaceSession::receivePacket(s.session,endpoints[0],duplicate.data,duplicate.bytes,clockMs));keep();
  CHECK(peers[0].localWins==1&&peers[1].peerWins==1);CHECK(!peers[1].peerResult);
  select(1);MSRHeader h={};h.kind=MSR_START;h.round=1;u8 body[12];configPayload(body,START);receivedControl(nullptr,h,body,12);keep();
  CHECK(peers[1].phase==WAIT_READY&&!peers[1].startNeeded&&starts[1]==1);
 }else if(test==6){
  congested[0]=true;CHECK(setReady(0));service(0);CHECK(peers[0].readyNeeded&&!peers[0].session.info.pending);
  CHECK(setReady(1));pump(5);CHECK(!starts[0]&&!starts[1]);congested[0]=false;pump();
  CHECK(peers[0].phase==RUNNING&&peers[1].phase==RUNNING&&starts[0]==1&&starts[1]==1);
 }else if(test==7){
  select(0);s.active=false;Options option=sOptions;for(unsigned i=2;i<16;++i)option.name[i]='x';option.name[1]=0;
  CHECK(configure(option));for(unsigned i=1;i<17;++i)CHECK(!sOptions.name[i]);
  CHECK(!dirtyMarks&&!stores);  // a kernel without the name block keeps nothing
  savedAvailable=true;savedBlock={};CHECK(configure(option));
  CHECK(savedBlock.magic==SUSAMUNE_ONLINE_NAME_MAGIC&&savedBlock.name[0]==sOptions.name[0]&&!savedBlock.name[1]);
  CHECK(dirtyMarks==1&&stores==1);CHECK(configure(option));CHECK(dirtyMarks==1&&stores==1);
  option.name[1]='y';CHECK(configure(option));CHECK(savedBlock.name[1]=='y'&&savedBlock.name[2]=='x'&&!savedBlock.name[16]&&dirtyMarks==2);
  savedAvailable=false;
 }else if(test==8){
  CHECK(setReady(1));blocked[1]=1;CHECK(setReady(1));
  CHECK(!peers[1].localReady);blocked[1]=0;CHECK(setReady(0));pump();
  CHECK(!starts[0]&&!starts[1]&&peers[1].phase==WAIT_READY);
 }else if(test==9){
  CHECK(race());finish(0,100);finish(1,120);pump();
  select(1);CHECK(!newMatch());keep();select(0);Options next=sOptions;next.entry=4;next.episode=5;next.bestOf=3;
  CHECK(configure(next));CHECK(newMatch());CHECK(!newMatch());keep();pump();
  CHECK(peers[0].connected&&peers[1].connected&&peers[0].round==2&&peers[1].round==2);
  CHECK(peers[0].phase==WAIT_READY&&peers[1].phase==WAIT_READY);
  CHECK(!peers[0].localWins&&!peers[1].peerWins&&!peers[0].localResult&&!peers[1].peerResult);
  CHECK(opts[0].entry==4&&opts[1].entry==4&&opts[1].episode==5&&opts[1].bestOf==3);
  CHECK(starts[0]==1&&starts[1]==1);CHECK(race());CHECK(starts[0]==2&&starts[1]==2);
  finish(0,90,true,4);finish(1,110,true,4);pump();CHECK(peers[0].localWins==1&&peers[1].peerWins==1);
 }else if(test==10){
  CHECK(race());finish(0,100);finish(1,120);pump();
  select(0);CHECK(newMatch());keep();congested[0]=true;pump();
  CHECK(peers[0].newMatchNeeded&&peers[0].phase==MATCH_DONE&&peers[0].localWins==1);
  congested[0]=false;pump();CHECK(peers[0].round==2&&peers[1].round==2);
  CHECK(race());finish(0,130);finish(1,100);pump();
  CHECK(peers[0].peerWins==1&&peers[1].localWins==1);
  select(0);CHECK(newMatch());keep();pump();CHECK(peers[0].round==3&&peers[1].round==3);
 }else if(test==11){
  CHECK(!setReady(0)&&!setReady(1));finish(0,100);finish(1,120);pump();
  CHECK(!peers[0].localResult&&!peers[1].peerResult&&!starts[0]&&!starts[1]);
  select(0);Options next=sOptions;next.freeRoam=false;next.entry=6;CHECK(configure(next));CHECK(newMatch());keep();pump();
  CHECK(peers[0].phase==WAIT_READY&&peers[1].phase==WAIT_READY&&!opts[1].freeRoam);
  CHECK(!starts[0]&&!starts[1]);CHECK(race());finish(0,100,true,6);finish(1,120,true,6);pump();
  select(0);next=sOptions;next.freeRoam=true;CHECK(configure(next));CHECK(newMatch());keep();pump();
  CHECK(peers[0].phase==ROAMING&&peers[1].phase==ROAMING&&opts[1].freeRoam);
  CHECK(!peers[0].localWins&&!peers[1].peerWins&&starts[0]==1&&starts[1]==1);
 }else if(test==12){
  CHECK(race());select(1);MSRHeader h={};h.kind=MSR_READY;h.round=s.round+1;u8 body[12];configPayload(body,NEW_MATCH);
  receivedControl(nullptr,h,body,12);CHECK(s.phase==RUNNING&&s.round==1);keep();
  finish(0,100);finish(1,120);pump();select(0);Options invalid=sOptions;invalid.name[0]++;
  CHECK(!configure(invalid));
  CHECK(newMatch());keep();pump();select(1);h.round=2;configPayload(body,NEW_MATCH);
  receivedControl(nullptr,h,body,12);CHECK(s.phase==WAIT_READY&&s.round==2);keep();
 }else if(test==13){
  CHECK(race());finish(0,100);service(0);const int lost=find(1,MSR_RESULT);CHECK(lost>=0);queue[lost].used=false;
  CHECK(reconnect());finish(1,120);pump();  // Bo1: the result ends the match on both sides
  CHECK(peers[0].localWins==1&&peers[1].peerWins==1&&!peers[0].peerWins&&!peers[1].localWins);
  CHECK(peers[0].phase==MATCH_DONE&&peers[1].phase==MATCH_DONE&&starts[0]==1&&starts[1]==1);
 }else if(test==14){
  CHECK(setReady(0)&&setReady(1));service(0);service(1);
  CHECK(deliver(0,MSR_READY));CHECK(deliver(1,MSR_READY));CHECK(deliver(0,MSR_ACK));
  service(0);CHECK(starts[0]==1&&peers[0].phase==RUNNING);const int lost=find(1,MSR_START);CHECK(lost>=0);queue[lost].used=false;
  CHECK(peers[1].phase==WAIT_READY&&peers[1].localReady);
  CHECK(reconnect());pump();CHECK(starts[1]==1&&peers[1].phase==RUNNING&&peers[0].phase==RUNNING);
  finish(0,100);finish(1,120);pump();CHECK(peers[0].localWins==1&&peers[1].peerWins==1&&peers[1].phase==MATCH_DONE);
 }else if(test==15){
  CHECK(race());
  // Deaths and resets keep the clock: the second attempt starts 1001 ms after the first.
  select(0);++gQFTTimer.serial;sampleAttempt(5000);++gQFTTimer.serial;sampleAttempt(6001);
  onILResult(2,100,true);CHECK(s.localQf==100+120);keep();
  select(1);++gQFTTimer.serial;sampleAttempt(7000);onILResult(2,100,true);CHECK(s.localQf==100);keep();
 }
 return 0;
}
API unsigned draftScenario(unsigned test){
 CHECK(connect(3,false,true,test==2));CHECK(syncedDraft());
 CHECK(opts[1].draft&&opts[1].bestOf==3&&opts[1].setBo5==(test==2));
 if(test==0){
  CHECK(peers[0].draft.phase==LiveDraft::OPENING_HOST_BAN&&!starts[0]&&!starts[1]);
  CHECK(!setReady(0)&&!setReady(1)&&!choose(1,0)&&!choose(0,5));
  CHECK(chooseAndPump(0,0));CHECK(peers[0].draft.phase==LiveDraft::OPENING_GUEST_BANS);
  CHECK(!choose(0,1)&&!choose(1,0));CHECK(chooseAndPump(1,1));
  CHECK(peers[0].draft.phase==LiveDraft::OPENING_GUEST_BANS&&peers[0].draft.bannedMask==3);
  CHECK(chooseAndPump(1,2));CHECK(peers[0].draft.phase==LiveDraft::OPENING_HOST_PICK);
  CHECK(!choose(1,3)&&!choose(0,2));const unsigned chosen=peers[0].draft.candidates[4];
  CHECK(chooseAndPump(0,4));CHECK(opts[0].entry==(int)chosen&&opts[1].entry==(int)chosen);
  CHECK(opts[0].episode==ILing::onlineDefaultEpisode(chosen)&&opts[1].episode==opts[0].episode);
  CHECK(peers[0].phase==WAIT_READY&&peers[1].phase==WAIT_READY&&peers[0].round==2&&peers[1].round==2);
  CHECK(!starts[0]&&!starts[1]);CHECK(setReady(1));pump();CHECK(!starts[0]&&!starts[1]);
  CHECK(setReady(0));pump();CHECK(starts[0]==1&&starts[1]==1&&peers[0].phase==RUNNING&&peers[1].phase==RUNNING);
 }else if(test==1||test==2){
  CHECK(openingDraft());const unsigned total=test==1?3:5;
  for(unsigned match=0;match<total;++match){
   const unsigned winner=(match+(test==2))&1;
   CHECK(completeDraftRound(winner));CHECK(peers[0].draft.phase==LiveDraft::IL_MATCH);
   CHECK(completeDraftRound(winner^1));CHECK(peers[0].draft.phase==LiveDraft::IL_MATCH);
   const unsigned before=starts[0];CHECK(completeDraftRound(winner));CHECK(starts[0]==before+1&&starts[1]==before+1);
   CHECK(peers[0].draft.setWins[winner]==match/2+1&&peers[0].draft.previousWinner==winner);
   if(match+1<total){
    CHECK(peers[0].phase==DRAFTING&&peers[1].phase==DRAFTING&&!setReady(0)&&!setReady(1));
    CHECK(counterDraft(winner));CHECK(starts[0]==before+1&&starts[1]==before+1);
   }
  }
  CHECK(peers[0].phase==MATCH_DONE&&peers[1].phase==MATCH_DONE&&peers[0].draft.phase==LiveDraft::SET_DONE);
  CHECK(!setReady(0)&&!setReady(1)&&!choose(0,0)&&!choose(1,0));
 }else if(test==3){
  CHECK(openingDraft());unsigned revision=peers[0].draft.revision;
  CHECK(completeDraftRound(2));CHECK(peers[0].draft.revision==revision+1);
  CHECK(!peers[0].draft.roundWins[0]&&!peers[0].draft.roundWins[1]);
  CHECK(completeDraftRound(0,false));CHECK(!peers[0].localWins&&!peers[0].peerWins);
  CHECK(completeDraftRound(1));CHECK(peers[0].draft.roundWins[1]==1);
  CHECK(completeDraftRound(2));CHECK(peers[0].draft.roundWins[1]==1);
  CHECK(completeDraftRound(0,false));CHECK(peers[0].draft.roundWins[1]==1);
  CHECK(completeDraftRound(1));CHECK(peers[0].draft.setWins[1]==1&&!peers[0].draft.setWins[0]);
  CHECK(peers[0].draft.phase==LiveDraft::COUNTER_WINNER_BAN&&syncedDraft());
 }else if(test==4){
  MSRHeader h={};h.kind=MSR_READY;h.round=peers[0].round;u8 body[24]={};
  select(0);const auto initial=s.draft;draftPayload(body,DRAFT_REQUEST,LiveDraft::token(initial));
  for(unsigned actor=0;actor<3;++actor){body[1]=actor;body[2]=1;receivedControl(nullptr,h,body,12);CHECK(equal(&initial,&s.draft,sizeof(initial))&&!s.choiceNeeded);}
  draftPayload(body,DRAFT_APPLY,LiveDraft::token(initial));body[1]=0;body[2]=1;
  receivedControl(nullptr,h,body,12);CHECK(equal(&initial,&s.draft,sizeof(initial))&&!s.choiceNeeded);keep();
  select(1);const auto original=s.draft;
  for(unsigned mode=0;mode<7;++mode){
   draftPayload(body,DRAFT_APPLY,LiveDraft::token(original));body[1]=0;body[2]=1;h.round=s.round;
   if(mode==0)body[1]=1;else if(mode==1)body[2]=5;else if(mode==2)body[3]=1;
   else if(mode==3)MSRWrite32(body+4,original.generation+1);else if(mode==4)MSRWrite32(body+8,original.revision+1);
   else if(mode==5)--h.round;else body[0]=DRAFT_REQUEST;
   receivedControl(nullptr,h,body,12);CHECK(equal(&original,&s.draft,sizeof(original)));
  }
  h.round=s.round;s.draft={};
  for(unsigned mode=0;mode<7;++mode){
   draftPayload(body,DRAFT_BEGIN,{s.round,0});for(unsigned i=0;i<5;++i)MSRWrite16(body+12+2*i,i);
   body[22]=body[23]=0;
   if(mode==0)MSRWrite16(body+12,15);else if(mode==1)MSRWrite16(body+12,8);
   else if(mode==2)MSRWrite16(body+12,1);else if(mode==3)body[22]=1;
   else if(mode==4)MSRWrite32(body+4,s.round+1);else if(mode==5)MSRWrite32(body+8,1);else body[1]=1;
   receivedControl(nullptr,h,body,24);CHECK(s.draft.phase==LiveDraft::UNINITIALIZED&&!s.draft.generation);
  }
  s.draft=original;Options bad=sOptions;bad.pool=3;CHECK(!validOptions(bad));bad=sOptions;bad.freeRoam=true;CHECK(!validOptions(bad));bad=sOptions;bad.bestOf=5;CHECK(!validOptions(bad));keep();
 }else if(test==5){
  CHECK(chooseAndPump(0,0));const auto before=peers[0].draft;
  congested[1]=true;CHECK(choose(1,1));service(1);
  CHECK(peers[1].choiceNeeded&&!peers[1].choiceSent&&syncedDraft()&&!choose(1,2));
  congested[1]=false;service(1);CHECK(peers[1].choiceSent&&peers[1].session.info.pending);
  CHECK(deliver(0,MSR_READY));CHECK(peers[0].choiceNeeded&&syncedDraft());
  congested[0]=true;service(0);CHECK(peers[0].choiceNeeded&&equal(&before,&peers[0].draft,sizeof(before)));
  CHECK(deliver(1,MSR_ACK));CHECK(!peers[1].session.info.pending&&peers[1].choiceSent&&!choose(1,2));
  congested[0]=false;service(0);CHECK(peers[0].draft.revision==before.revision+1&&!syncedDraft());
  CHECK(deliver(1,MSR_READY));pump();CHECK(syncedDraft()&&!peers[1].choiceSent);
  CHECK(chooseAndPump(1,2));CHECK(chooseAndPump(0,3));CHECK(peers[0].phase==WAIT_READY&&!starts[0]);
 }else if(test==6){
  CHECK(choose(0,0));service(0);const int index=find(1,MSR_READY);CHECK(index>=0);
  const Datagram dropped=queue[index];queue[index].used=false;
  CHECK(peers[0].session.info.pending&&!choose(0,1)&&!syncedDraft());
  clockMs+=251;service(0);CHECK(deliver(1,MSR_READY));pump();CHECK(syncedDraft());
  const auto after=peers[1].draft;select(1);
  CHECK(LiveRaceSession::receivePacket(s.session,endpoints[0],dropped.data,dropped.bytes,clockMs));
  CHECK(equal(&after,&s.draft,sizeof(after)));keep();pump();
  CHECK(chooseAndPump(1,1));CHECK(chooseAndPump(1,2));CHECK(chooseAndPump(0,3));
  select(1);MSRHeader stale={};stale.kind=MSR_READY;stale.round=s.round-1;u8 body[12];
  draftPayload(body,DRAFT_APPLY,{after.generation,after.revision});body[1]=1;body[2]=4;
  const auto currentDraft=s.draft;receivedControl(nullptr,stale,body,12);CHECK(equal(&currentDraft,&s.draft,sizeof(currentDraft)));keep();
 }else if(test==7){
  CHECK(openingDraft());for(unsigned match=0;match<2;++match){CHECK(completeDraftRound(0));CHECK(completeDraftRound(0));if(!match)CHECK(counterDraft(0));}
  CHECK(peers[0].phase==MATCH_DONE);const unsigned oldGeneration=peers[0].draft.generation;
  const unsigned oldRound=peers[0].round,oldStarts=starts[0];
  select(0);Options next=sOptions;next.pool=2;next.setBo5=true;CHECK(configure(next));CHECK(newMatch());keep();
  congested[0]=true;pump();CHECK(peers[0].draft.setWins[0]==2&&peers[0].round==oldRound&&peers[0].newMatchNeeded);
  congested[0]=false;pump();CHECK(syncedDraft()&&peers[0].draft.generation>oldGeneration&&peers[0].round==oldRound+1);
  CHECK(peers[0].draft.bestOf==5&&opts[1].pool==2&&!peers[0].draft.setWins[0]&&starts[0]==oldStarts);
  CHECK(openingDraft());for(unsigned match=0;match<3;++match){CHECK(completeDraftRound(1));CHECK(completeDraftRound(1));if(match<2)CHECK(counterDraft(1));}
  select(0);next=sOptions;next.draft=false;next.freeRoam=true;CHECK(configure(next));CHECK(newMatch());keep();pump();
  CHECK(peers[0].phase==ROAMING&&peers[1].phase==ROAMING&&!opts[1].draft&&!peers[0].draft.generation&&!setReady(0));
  select(0);next=sOptions;next.freeRoam=false;next.draft=true;next.pool=1;next.setBo5=false;CHECK(configure(next));CHECK(newMatch());keep();pump();
  CHECK(peers[0].phase==DRAFTING&&peers[1].phase==DRAFTING&&opts[1].pool==1&&syncedDraft());
 }else if(test==8){
  CHECK(openingDraft());CHECK(completeDraftRound(0));CHECK(race());const int entry=opts[0].entry;
  finish(1,200,true,entry);service(1);CHECK(deliver(0,MSR_RESULT));CHECK(deliver(1,MSR_ACK));
  finish(0,100,true,entry);service(0);CHECK(peers[0].phase==DRAFTING&&peers[1].phase==RUNNING);
  CHECK(peers[0].session.info.pending&&peers[0].draft.phase==LiveDraft::NEED_CANDIDATES);
  CHECK(deliver(1,MSR_RESULT));CHECK(peers[1].phase==DRAFTING&&syncedDraft());
  CHECK(deliver(0,MSR_ACK));service(0);CHECK(deliver(1,MSR_READY));pump();
  CHECK(syncedDraft()&&peers[0].draft.phase==LiveDraft::COUNTER_WINNER_BAN);
  CHECK(counterDraft(0));CHECK(!peers[0].localResult&&!peers[1].peerResult);
 }else if(test==9){
  for(unsigned pool=0;pool<3;++pool){
   CHECK(connect(3,false,true,false,pool));CHECK(syncedDraft()&&opts[1].pool==pool);
   for(unsigned i=0;i<5;++i){CHECK(ILing::onlinePoolContains(peers[0].draft.candidates[i],pool));for(unsigned j=0;j<i;++j)CHECK(peers[0].draft.candidates[i]!=peers[0].draft.candidates[j]);}
  }
 }else if(test==10){
  for(unsigned draft=0;draft<2;++draft){
   CHECK(connect(3,false,draft));if(draft)CHECK(openingDraft());CHECK(race());
   const int entry=opts[0].entry;finish(0,100,true,entry);finish(1,200,true,entry);service(0);service(1);
   CHECK(deliver(1,MSR_RESULT));CHECK(peers[1].phase==ROUND_DONE);CHECK(deliver(0,MSR_RESULT));
   CHECK(deliver(0,MSR_ACK));CHECK(deliver(1,MSR_ACK));select(1);
   const auto before=s;const auto beforeOptions=sOptions;MSRHeader h={};h.kind=MSR_READY;h.round=s.round+1;
   for(unsigned change=0;change<5;++change){
    u8 body[12];configPayload(body,OFFER);
    if(change==0){MSRWrite16(body+4,(entry+1)%ILing::count());MSRWrite16(body+6,ILing::persistentSlot((entry+1)%ILing::count()));}
    else if(change==1)body[3]^=0x10;else if(change==2)body[2]=5;
    else if(change==3)body[1]=(sOptions.episode+1)%8;else body[3]^=8;
    receivedControl(nullptr,h,body,12);CHECK(equal(&before,&s,sizeof(s))&&equal(&beforeOptions,&sOptions,sizeof(sOptions)));
   }
   keep();service(0);pump();CHECK(peers[0].phase==WAIT_READY&&peers[1].phase==WAIT_READY&&syncedDraft());
  }
 }else if(test==11){
  CHECK(choose(0,0));service(0);const int lost=find(1,MSR_READY);CHECK(lost>=0);queue[lost].used=false;
  CHECK(!syncedDraft());CHECK(reconnect());pump();CHECK(syncedDraft());
  CHECK(chooseAndPump(1,1));CHECK(chooseAndPump(1,2));CHECK(chooseAndPump(0,3));CHECK(peers[0].phase==WAIT_READY);
 }else if(test==12){
  CHECK(choose(0,0));pump();CHECK(choose(1,1));service(1);const int lost=find(0,MSR_READY);CHECK(lost>=0);queue[lost].used=false;
  CHECK(peers[1].choiceSent);CHECK(reconnect());pump();CHECK(syncedDraft()&&!peers[1].choiceSent);
  CHECK(chooseAndPump(1,2));CHECK(chooseAndPump(0,3));CHECK(peers[1].phase==WAIT_READY);
 }
 return 0;
}
'''
        cls.generated = code
        cpp, dll = work / "test.cpp", work / "test.dll"
        cpp.write_text(code)
        result = subprocess.run([str(ROOT / "toolchain/clang++.exe"),
            "--target=x86_64-pc-windows-msvc", "-shared", "-nostdlib", "-fno-builtin",
            "-fuse-ld=lld", "-Wl,/noentry", "-O2", "-ffast-math",
            "-I", str(work), "-I", str(ROOT / "include"), str(cpp),
            str(ROOT / "src/live_draft.cpp"), "-o", str(dll)],
            capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: _ctypes.FreeLibrary(cls.lib._handle))

    def test_match_packet_ordering(self):
        for number, name in enumerate(("round/tie/void", "best-of completion", "queued start unready",
                "result then offer", "start then result", "duplicate/stale round", "TX backpressure", "edited name",
                "unready while busy", "new match and changed IL", "repeated matches under backpressure",
                "free roam to race and back", "unauthorized and stale new match",
                "reconnect resends a lost result", "reconnect resends a lost start",
                "round clock across resets")):
            with self.subTest(name=name):
                line = self.lib.scenario(number)
                detail = self.generated.splitlines()[line - 1] if line else ""
                self.assertEqual(line, 0, detail)

    def test_draft_and_set_packet_ordering(self):
        for number, name in enumerate(("initial draft and both Ready", "Bo3 set with changing winners",
                "Bo5 set with changing winners", "ties and assisted rounds", "invalid commands and pool candidates",
                "request and event backpressure", "lost event and duplicate retransmission",
                "same-room rematch, changed pool and free roam", "final IL result before next candidates",
                "candidate sampling in every pool", "continuing offer cannot change agreed setup",
                "reconnect resends a lost draft event", "reconnect resends a lost draft request")):
            with self.subTest(name=name):
                line = self.lib.draftScenario(number)
                detail = self.generated.splitlines()[line - 1] if line else ""
                self.assertEqual(line, 0, detail)


if __name__ == "__main__":
    unittest.main()
