#include "susamune/ghost_attempt.hxx"
#include "susamune/ghost_recording.hxx"
#include "susamune/ghost_trace.hxx"
#include "susamune/ghost_clock.h"
#include "susamune/ghost_stage_context.hxx"
#include "susamune/replay_session.hxx"
#include "susamune/qft_timer.hxx"
#include "susamune/iling.hxx"
#include "susamune/warp_wheel.hxx"
#include "susamune/retail_input.hxx"
#include "susamune/mem2_map.h"
#include "susamune/susamune_cfg.h"
#include "SMS/System/Application.hxx"
#include "SMS/System/MarDirector.hxx"
#include "SMS/Manager/FlagManager.hxx"
#include "Dolphin/mem.h"
#include "Dolphin/printf.h"
namespace GhostAttempt {
namespace {
const unsigned kSnapshotMagic=0x4d474131u;
struct State {
    GhostRecording::Info info;
    GhostRecording::Identity source;
    SusamuneGhostClock clock;
    unsigned frames;
    bool haveTime,completed,restored,frozen,assisted;
};
struct Snapshot {
    unsigned magic,version;
    GhostRecording::Info info;
    GhostRecording::Identity source;
    unsigned frames,serial,omittedQf;
    int liveQf;
};
static_assert(sizeof(State)<=SUSAMUNE_GHOST_TRACKS_SIZE,"attempt metadata exceeds retired Track control reservation");
static_assert(sizeof(Snapshot)<=sizeof(Ghost::SavestateData),"attempt snapshot exceeds existing state sidecar");
State &s=*reinterpret_cast<State*>(SUSAMUNE_GHOST_TRACKS_PPC_BASE);
bool nameValid(const char *name){
    for(unsigned n=0;n<48;++n){const unsigned char c=name[n];if(!c)return n!=0;if(c<32||c>126||c=='/'||c=='\\')return false;}
    return false;
}
bool decode(const Ghost::SavestateData &data,Snapshot &saved){
    memcpy(&saved,&data,sizeof(saved));const auto &i=saved.info;
    if(saved.magic!=kSnapshotMagic||saved.version!=1||!saved.source.nonce||!saved.source.run||!i.ownerToken||
       !saved.frames||saved.liveQf<0||saved.omittedQf>static_cast<unsigned>(saved.liveQf)||
       i.startQf>i.endQf||i.endQf>0x7fffffffu||i.resultQf!=SUSAMUNE_GHOST_RESULT_QF_NONE||
       !SusamuneGhostRunFlagsValid(i.runFlags)||!(i.runFlags&SUSAMUNE_GHOST_RUN_INCOMPLETE)||
       !SusamuneGhostPersonalProfile(i.sourceProfile)||i.area>0x3c||i.episode>9||
       (i.parent!=255&&i.parent>0x3c)||(i.routeFlags&~3u)||((i.routeFlags&1u)!=0)!=(i.parent!=255)||
       ((i.routeFlags&2u)&&i.parent==255)||i.routeVariant< -1||i.routeVariant>255||i.splitCount>8||!nameValid(i.name))return false;
    for(unsigned n=0;n<i.splitCount;++n){const auto &v=i.splits[n];
        if(v.endpoint!=n||v.reserved||v.schema!=SUSAMUNE_SPLIT_STATS_SCHEMA_HASH||v.route>=SUSAMUNE_SPLIT_STATS_ROUTE_COUNT||
           (n&&v.route!=i.splits[0].route)||v.qf<i.startQf||v.qf>i.endQf||(n&&v.qf<i.splits[n-1].qf))return false;
    }
    for(unsigned n=sizeof(Snapshot);n<sizeof(data);++n)if(reinterpret_cast<const unsigned char*>(&data)[n])return false;
    return true;
}
void finish(bool completed){
    if(!s.haveTime||s.completed||s.info.endQf<=s.info.startQf)return;
    GhostRecording::Info result=s.info;
    if(completed){result.runFlags&=~SUSAMUNE_GHOST_RUN_INCOMPLETE;result.resultQf=result.endQf;}
    else {result.runFlags|=SUSAMUNE_GHOST_RUN_INCOMPLETE;result.resultQf=SUSAMUNE_GHOST_RESULT_QF_NONE;}
    const u64 millis=static_cast<u64>(result.endQf-result.startQf)*1001u/120u;
    snprintf(result.name,sizeof(result.name),"%s%s - %lu:%02lu.%03lu",
        result.runFlags&SUSAMUNE_GHOST_RUN_TAS?"TAS ":"",s.info.name,
        static_cast<u32>(millis/60000),static_cast<u32>((millis/1000)%60),static_cast<u32>(millis%1000));
    if(GhostRecording::finish(result)){s.info=result;s.completed=true;}
}
}
void init(){memset(&s,0,sizeof(s));}
void frameControl(bool frozen,bool assisted){
    s.frozen=frozen;s.assisted=assisted;
    s32 qf;
    if(s.haveTime&&gQFTTimer.currentQf(&qf))
        SusamuneGhostClockObserve(&s.clock,gQFTTimer.attemptSerial(),qf,frozen&&(assisted||(s.info.runFlags&SUSAMUNE_GHOST_RUN_TAS)));
}
void update(){
    if(ReplaySession::blocksResults())return;
    GhostRecording::Identity source;unsigned owner;
    if(!GhostRecording::activeIdentity(source,owner)||!GhostTrace::recording())return;
    TMarDirector *director=RetailInput::stageDirector();GhostStageContext::Sample stage;
    s32 qf;bool stopped;
    if(!director||!director->_260||!GhostStageContext::sample(&stage)||!gQFTTimer.currentQf(&qf,&stopped)||qf<0)return;
    if(!GhostRecordingLifecycle::same(source,s.source)){
        const bool continued=s.restored&&s.haveTime;
        const bool frozen=s.frozen,assisted=s.assisted;
        if(!continued){s={};s.frozen=frozen;s.assisted=assisted;}
        s.source=source;s.info.ownerToken=owner;s.restored=false;
        if(!continued){
            auto &i=s.info;i.resultQf=SUSAMUNE_GHOST_RESULT_QF_NONE;i.runFlags=SUSAMUNE_GHOST_RUN_INCOMPLETE;
            i.area=stage.area;i.episode=stage.episode;i.parent=LevelWarp::parentArea(stage.area);i.routeFlags=i.parent==255?0:1;
            i.routeVariant=TFlagManager::smInstance?TFlagManager::smInstance->getFlag(0x40003):-1;
            i.sourceProfile=ILing::pbProfile()==4?SUSAMUNE_GHOST_HOVERLESS_PROFILE:ILing::pbProfile();
            const int entry=ILing::activeEntry();
            if(entry>=0)snprintf(i.name,sizeof(i.name),"%s",ILing::label(entry));
            else snprintf(i.name,sizeof(i.name),"Area %u Episode %u",unsigned(i.area),unsigned(i.episode)+1);
        }
    }
    if(s.completed)return;
    if(s.assisted||gQFTTimer.practiceAssisted())s.info.runFlags|=SUSAMUNE_GHOST_RUN_ASSISTED|SUSAMUNE_GHOST_RUN_TAS;
    SusamuneGhostClockObserve(&s.clock,gQFTTimer.attemptSerial(),qf,s.frozen&&(s.info.runFlags&SUSAMUNE_GHOST_RUN_TAS));
    const s32 mapped=SusamuneGhostClockMap(&s.clock,qf);if(mapped<0)return;
    if(!s.haveTime){s.info.startQf=0;s.haveTime=true;}
    if(static_cast<unsigned>(mapped)<s.info.endQf)return;
    s.info.endQf=mapped;++s.frames;
    if(stopped)finish(true);
}
void depart(){
    if(!GhostRecording::capturing())return;
    if(s.haveTime&&s.info.endQf>s.info.startQf)finish(false);
    else GhostRecording::cancelActive();
}
void split(u16 route,u8 endpoint,s32 qf){
    if(ReplaySession::blocksResults()||!s.haveTime||qf<0||endpoint!=s.info.splitCount||endpoint>=8||
       route>=SUSAMUNE_SPLIT_STATS_ROUTE_COUNT)return;
    const s32 mapped=SusamuneGhostClockMap(&s.clock,qf);
    if(mapped<0||(endpoint&&(s.info.splits[0].route!=route||s.info.splits[endpoint-1].qf>static_cast<unsigned>(mapped))))return;
    auto &v=s.info.splits[s.info.splitCount++];v={static_cast<u32>(mapped),SUSAMUNE_SPLIT_STATS_SCHEMA_HASH,route,endpoint,0};
    GhostRecording::split(s.info.ownerToken,v);
}
void assisted(){if(s.haveTime&&!s.completed)s.info.runFlags|=SUSAMUNE_GHOST_RUN_ASSISTED|SUSAMUNE_GHOST_RUN_TAS;}
bool markPB(s32 qf){
    if(qf<0||!s.completed||s.info.resultQf!=static_cast<unsigned>(qf)||
       s.info.runFlags&(SUSAMUNE_GHOST_RUN_ASSISTED|SUSAMUNE_GHOST_RUN_TAS))return false;
    GhostRecording::protect(s.info.ownerToken,s.info.ownerToken);return GhostRecording::protectedToken(s.info.ownerToken);
}
void resetAfterLoad(){init();}
bool capture(Ghost::SavestateData &out){
    memset(&out,0,sizeof(out));
    if(!GhostRecording::capturing()||!s.haveTime||s.completed)return true;
    Snapshot saved={};saved.magic=kSnapshotMagic;saved.version=1;saved.info=s.info;saved.source=s.source;
    saved.frames=s.frames;saved.serial=s.clock.serial;saved.omittedQf=s.clock.omittedQf;saved.liveQf=s.clock.liveQf;
    memcpy(&out,&saved,sizeof(saved));Snapshot checked;return decode(out,checked);
}
bool owns(const Ghost::SavestateData &data){return data.words[0]==kSnapshotMagic;}
bool valid(const Ghost::SavestateData &data){Snapshot saved;return decode(data,saved);}
void restore(const Ghost::SavestateData &data){
    Snapshot saved;if(!decode(data,saved))return;
    s={};s.info=saved.info;s.source=saved.source;s.frames=saved.frames;s.haveTime=s.restored=true;
    s.info.runFlags|=MS_TRACE_CONTINUATION_RUN_FLAGS;
    s.clock={gQFTTimer.attemptSerial(),saved.liveQf,saved.omittedQf,true};
}
}
