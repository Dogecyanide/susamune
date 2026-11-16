#include "susamune/ghost_recording_native.hxx"
#if MOONSHINE_GHOST_TRACE && !IS_EMULATOR
#include "susamune/ghost_recording.hxx"
#include "susamune/ghost_trace.hxx"
#include "susamune/ghost_trace_branch_io.hxx"
#include "susamune/ghost_trace_stream_native.hxx"
#include "susamune/ghost_trace_flat.hxx"
#include "susamune/ghost_world_runtime.hxx"
#include "susamune/ghost_replay_report.hxx"
#include "susamune/ghost_memory.hxx"
#include "susamune/ghost_visual_provider.hxx"
#include "susamune/ghost.hxx"
#include "susamune/split_stats.hxx"
#include "susamune/iling.hxx"
#include "susamune/menu.hxx"
#include "susamune/addresses.hxx"
#include "Dolphin/printf.h"
#include "Dolphin/mem.h"

namespace GhostRecordingNative {
namespace {
namespace M=GhostTraceBranchIo;
enum Mode { IDLE, DELETE_LOOKUP, DELETE_ISSUE, DELETE_WAIT, WATCH_READY, WATCHING, WATCH_CLOSING };
struct Native {
    M::Client files;
    unsigned char manifest[256];
    unsigned mode,hash,error,detail;
    bool two;
};
static_assert(sizeof(Native)<=MS_TRACE_NATIVE_BYTES,"native ghost controls exceed their lease");
Native &state=*reinterpret_cast<Native*>(MS_TRACE_CONTROL_PPC+MS_TRACE_NATIVE_OFFSET);
bool installed;
unsigned game(){return *reinterpret_cast<volatile const unsigned*>(0x80000000u);}
void message(const char *text){if(gMenu)gMenu->toast(text);}
__attribute__((noinline)) bool loadImpl(const void *raw,unsigned bytes,bool observer,bool secondary){
    if(!installed||!observer||secondary||state.two||state.mode!=IDLE||bytes!=256||!raw||!Ghost::observerPreparing())return false;
    const auto *p=static_cast<const unsigned char*>(raw);
    if(MsRecordingWord(p+32)!=game())return false;
    memcpy(state.manifest,p,256);state.mode=WATCH_READY;return true;
}
bool checkpoint(GhostRecording::Checkpoint &,bool){return false;}
__attribute__((noinline)) int discardImpl(GhostRecording::Identity id,bool){
    if(!installed||state.mode>=WATCH_READY||GhostWorldRuntime::busy()||GhostTraceFlat::active()||GhostVisualProvider::active()||GhostTrace::continuationPending())return 0;
    auto &c=state.files;
    if(state.mode==IDLE){
        // The completion receipt already identifies this draft. ARM still checks
        // the file and every durable reference before it permits deletion.
        if(GhostRecording::discardHeaderHash(id,state.hash)){
            if(!M::erase(c,id.nonce,id.run,state.hash))return 0;
            state.mode=DELETE_WAIT;
        }else{
            if(!M::lookup(c,id.nonce,id.run,game()))return 0;
            state.mode=DELETE_LOOKUP;
        }
    }
    if(c.fileNonce!=id.nonce||c.run!=id.run)return 0;
    const auto phase=M::poll(c);
    if(phase==M::FAILED){M::cancel(c);state.mode=IDLE;return -1;}
    if(GhostTrace::checkpointSourceOwned(id.nonce,id.run)){
        if(!M::cancel(c))return 0;state.mode=IDLE;return 1;
    }
    if(state.mode==DELETE_LOOKUP&&phase==M::READY){
        const auto *found=M::result(c);if(!found){M::cancel(c);state.mode=IDLE;return -1;}
        state.hash=found->file.headerHash;M::consume(c);state.mode=DELETE_ISSUE;
    }
    if(state.mode==DELETE_ISSUE){
        if(M::erase(c,id.nonce,id.run,state.hash))state.mode=DELETE_WAIT;
        return 0;
    }
    if(state.mode==DELETE_WAIT&&phase==M::READY){M::consume(c);state.mode=IDLE;return 1;}
    return 0;
}
// Address-taken callbacks stay in MEM1; their larger bodies use checked call gates.
bool load(const void *p,unsigned n,bool observer,bool secondary){return loadImpl(p,n,observer,secondary);}
int discard(GhostRecording::Identity id,bool begin){return discardImpl(id,begin);}
const GhostRecording::Backend backend={load,checkpoint,discard};
}
void poll(){
    if(!installed){
        unsigned nonce=0;
        if(!GhostMemory::ready()||!GhostTrace::backendIdentity(nonce))return;
        state={};if(!M::configureNative(state.files,nonce))return;
        auto &runtime=*reinterpret_cast<GhostRecording::Runtime*>(MS_TRACE_CONTROL_PPC+0x2400);
        installed=GhostRecording::install(runtime,nonce,GhostRecordingLifecycle::kRequired,backend);
        return;
    }
    if(state.mode==WATCHING){
        unsigned status[32];GhostWorldRuntime::status(status);
        if(status[3]){
            GhostWorldRuntime::stop();state.mode=WATCH_CLOSING;state.error=status[3];state.detail=status[4];
            char text[64];snprintf(text,sizeof(text),"Replay stopped at check %u (%u)",status[3],status[4]);message(text);
        }else if(!GhostWorldRuntime::active()){state.mode=WATCH_CLOSING;message("Replay ended");}
    }
    const unsigned report=GhostReplayReport::poll();
    if(report&&state.mode==WATCH_CLOSING&&state.error){
        char text[80];snprintf(text,sizeof(text),"Replay stopped at check %u (%u) - report %s",
            state.error,state.detail,report==1?"saved":"unavailable");message(text);
    }
    if(state.mode==WATCH_CLOSING&&!GhostWorldRuntime::busy())state.mode=IDLE;
}
void prepareWatch(bool two){if(installed&&state.mode==IDLE){state.two=two;state.error=state.detail=0;memset(state.manifest,0,256);}}
void cancelWatch(){
    if(!installed)return;
    if(state.mode==WATCH_READY)state.mode=IDLE;
    if(state.mode==WATCHING){GhostWorldRuntime::stop();state.mode=WATCH_CLOSING;}
}
bool fileBusy(){return installed&&state.mode>=DELETE_LOOKUP&&state.mode<=DELETE_WAIT;}
bool watchReady(){return installed&&state.mode==WATCH_READY;}
bool watchWaiting(){return watchReady()&&!GhostTraceStreamNative::idleWriter(state.files.nonce);}
bool startWatch(){
    if(!watchReady()||watchWaiting())return false;
    const auto *p=state.manifest;
    if(!GhostWorldRuntime::armFile(MsRecordingWord(p+16),MsRecordingWord(p+20),p[37]+1)||
       !GhostWorldRuntime::setSourceRunFlags(MsRecordingWord(p+28))||!GhostWorldRuntime::startRecorded()){
        GhostWorldRuntime::stop();return false;
    }
    state.mode=WATCHING;return true;
}
}
#else
namespace GhostRecordingNative {
void poll(){}
void prepareWatch(bool){}
void cancelWatch(){}
bool watchReady(){return false;}
bool watchWaiting(){return false;}
bool startWatch(){return false;}
bool fileBusy(){return false;}
}
#endif
