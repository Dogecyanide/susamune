#include "susamune/ghost_replay_test.hxx"
#if MOONSHINE_GHOST_TRACE
#include "susamune/ghost_trace.hxx"
#include "susamune/ghost_world_runtime.hxx"
#include "susamune/ghost_replay_report.hxx"
#include "susamune/iling.hxx"
#include "susamune/warp_wheel.hxx"
#include "susamune/menu.hxx"
#include "susamune/addresses.hxx"
#include "Dolphin/OS.h"
#include "Dolphin/printf.h"
#include "Dolphin/mem.h"
namespace GhostReplayTest {
namespace {
struct State {
    unsigned nonce,run,lastNonce,lastRun,lastFlags,phase;
    int entry,lastEntry;
    bool finishRequested,watching;
    char text[96];
};
static_assert(sizeof(State)<=0x100,"replay test control lease");
State &s=*reinterpret_cast<State*>(MS_TRACE_CONTROL_PPC+0x3100);
bool initialized;
void init() {if(!initialized){memset(&s,0,sizeof(s));s.entry=s.lastEntry=-1;initialized=true;}}
void message(const char *text) {snprintf(s.text,sizeof(s.text),"%s",text);if(gMenu)gMenu->toast(s.text);}
__attribute__((noinline)) bool watch(unsigned nonce,unsigned run,int entry) {
    if(s.phase){message("Capture is still saving - please wait");return false;}
    if(!GhostWorldRuntime::armFile(nonce,run,SUSAMUNE_GAME_VERSION)) {
        const unsigned why=GhostWorldRuntime::startError();
        if(why==6)message("Remove the GameCube memory card for this replay test");
        else {snprintf(s.text,sizeof(s.text),"Replay could not start (check %u)",why);if(gMenu)gMenu->toast(s.text);}
        return false;
    }
    if(nonce==s.lastNonce&&run==s.lastRun&&!GhostWorldRuntime::setSourceRunFlags(s.lastFlags)) {
        GhostWorldRuntime::stop();message("Replay metadata is inconsistent");return false;
    }
    if(!GhostWorldRuntime::startAt(entry)){GhostWorldRuntime::stop();message("Cannot start this replay");return false;}
    s.watching=true;message("Loading full-world replay...");return true;
}
}
const char *status() {init();return s.text[0]?s.text:"Enter an IL to record it. B + Start stops playback.";}
const char *recordLabel() {const int entry=ILing::activeEntry();return entry>=0?ILing::shortLabel(entry):"Enter an IL first";}
bool action(unsigned row) {
    init();
    if(row==(SUSAMUNE_GAME_VERSION==3?6u:5u)){GhostWorldRuntime::stop();s.watching=false;message("Replay stopped");return false;}
    if(row==1) {
        if(s.phase==2){s.finishRequested=true;message("Finishing capture...");}
        else message("No active capture to save");
        return false;
    }
    if(row==2) {
        if(!s.lastRun){message("Record and save an IL first");return false;}
        return watch(s.lastNonce,s.lastRun,s.lastEntry);
    }
    if(SUSAMUNE_GAME_VERSION==3&&row==5)return watch(0xc1a6804bu,0x3f630002u,85);
    if(row==3||row==4) {
        if(SUSAMUNE_GAME_VERSION==3)
            return watch(0xea96a493u,row==3?0x31eb5436u:0x3f630001u,row==3?3:52);
        if(SUSAMUNE_GAME_VERSION!=1){message("These samples need Japanese Sunshine");return false;}
        return watch(0x12345678u,row==3?1235u:1236u,row==3?57:68);
    }
    if(row||s.phase||GhostWorldRuntime::busy()){message("Finish the current recording or replay first");return false;}
    const int entry=ILing::activeEntry();
    if(entry<0){message("Choose an IL in Runs, then record it here");return false;}
    const unsigned filter=ILing::ghostBrowseFilter(entry);
    const unsigned scene=(((filter&255u)-1)<<8)|(((filter>>8)&255u)-1);
    unsigned nonce=0,run=OSGetTick()&0x3fffffffu;if(!run)run=1;
    if(!filter||!GhostTrace::backendIdentity(nonce)||!GhostTrace::armOrdinaryStage(scene,run)) {
        message("Capture unavailable - wait for storage");return false;
    }
    s.nonce=nonce;s.run=run;s.entry=entry;s.phase=1;s.finishRequested=false;
    message("Preparing capture; restarting this IL...");return true;
}
// Seal on the following frame so the finish's remaining events are retained.
void finished() {if(initialized&&s.phase==2)s.finishRequested=true;}
void update() {
    if(!initialized)return;
    const unsigned savedReport=GhostReplayReport::poll();
    if(savedReport) {
        unsigned report[32];GhostWorldRuntime::status(report);
        snprintf(s.text,sizeof(s.text),"Replay stopped at check %u (%u) - report %s",report[3],report[4],savedReport==1?"saved":"unavailable");
        if(gMenu)gMenu->toast(s.text);
    }
    if(s.watching) {
        unsigned report[32];GhostWorldRuntime::status(report);
        if(report[3]) {
            GhostWorldRuntime::stop();s.watching=false;
            snprintf(s.text,sizeof(s.text),"Replay stopped at check %u (%u)",report[3],report[4]);
            if(gMenu)gMenu->toast(s.text);
        } else if(!GhostWorldRuntime::busy()) {s.watching=false;message("Replay finished");}
    }
    if(!s.phase)return;
    const unsigned error=GhostTrace::failure(s.run);
    if(error){s.phase=0;snprintf(s.text,sizeof(s.text),"Capture error %u",error);if(gMenu)gMenu->toast(s.text);return;}
    if(GhostTrace::discarded(s.run)){s.phase=0;message("Capture discarded after the attempt changed");return;}
    if(s.phase==1&&GhostTrace::stageArmed()) {
        if(WarpWheel::requestExplicitILStart(s.entry))s.phase=2;
        else {GhostTrace::reset();s.phase=0;message("Could not restart this IL");}
    }
    if(s.phase==2&&s.finishRequested&&GhostTrace::finishOrdinary(s.run)) {
        s.phase=3;s.finishRequested=false;message("Saving capture...");
    }
    GhostTrace::Completion completed;
    if(s.phase==3&&GhostTrace::completion(s.run,completed)) {
        s.lastNonce=completed.nonce;s.lastRun=completed.run;s.lastFlags=GhostTrace::completedRunFlags(completed.run);s.lastEntry=s.entry;s.phase=0;
        message("Capture saved - choose Watch latest capture");
    }
}
}
#endif
