#include "susamune/replay_camera.hxx"
#include "susamune/practice_session.hxx"
#include "susamune/ghost_recording_native.hxx"
#include "susamune/ghost_provenance.h"
#include "susamune/ghost_replay_start.hxx"
#include "susamune/replay_session.hxx"
#include "susamune/state_save_probe.hxx"
#include "susamune/ghost_world_runtime.hxx"
#if MOONSHINE_GHOST_TRACE
#include "susamune/ghost_trace.hxx"
#include "susamune/ghost_trace_hooks.hxx"
#include "susamune/ghost_trace_reader.hxx"
#include "susamune/ghost_trace_stream.hxx"
#include "susamune/ghost_trace_logical.hxx"
#include "susamune/ghost_trace_flat.hxx"
#include "susamune/qft_timer.hxx"
#include "SMS/MSound/MSound.hxx"
#include "susamune/ghost_trace_stream_native.hxx"
#include "susamune/ghost_world_replay.hxx"
#include "susamune/ghost_world_input.hxx"
#include "susamune/ghost_replay_report.h"
#include "susamune/ghost_replay_report.hxx"
#include "SMS/Enemy/Conductor.hxx"
#include "susamune/ghost_trace_initial_flags.hxx"
#include "susamune/ghost_memory.hxx"
#include "susamune/ghost_stage_context.hxx"
#include "susamune/ghost_simulation.hxx"
#include "susamune/settings.hxx"
#include "susamune/retail_input.hxx"
#include "susamune/iling.hxx"
#include "susamune/warp_wheel.hxx"
#include "susamune/records.hxx"
#include "susamune/ghost.hxx"
#include "susamune/addresses.hxx"
#include "SMS/System/Application.hxx"
#include "SMS/System/MarDirector.hxx"
#include "SMS/Manager/FlagManager.hxx"
#include "SMS/Player/Mario.hxx"
#if IS_EMULATOR
#include "SMS/Camera/PolarSubCamera.hxx"
#endif
#include "Dolphin/CARD.h"
#include "Dolphin/OS.h"
#include "Dolphin/mem.h"

namespace GhostWorldRuntime {
namespace {
namespace R = GhostWorldReplay;
namespace D = GhostTraceDecode;
namespace I = GhostWorldInput;
namespace F = GhostTraceReader;
namespace S = GhostTraceStream;
namespace L = GhostTraceLogical;
namespace M = GhostTraceBranchIo;
namespace Flags = GhostTraceInitialFlags;
enum { kMagic = 0x57525031u, kControlOffset = 0x5000,
       kRandomBase = MS_TRACE_ACTOR_CACHE_PPC,
       kPackedBase = MS_TRACE_UPPER_PPC + MS_TRACE_STREAM_PACKED_OFFSET,
       kDiagnosticImage = 0x81860000u, kDiagnosticBytes = 0x7a0000u };
static_assert(kDiagnosticImage >= SUSAMUNE_DOLPHIN_GHOST_MODEL_PPC_BASE + SUSAMUNE_DOLPHIN_GHOST_MODEL_SPAN &&
              kDiagnosticImage + kDiagnosticBytes <= 0x82000000u, "diagnostic image excludes model memory");
struct State {
    unsigned magic, error, detail, bytes, generation, token, ordinal, startEntry, waitReason;
#if IS_EMULATOR
    volatile unsigned diagnosticSourceWait;
    volatile unsigned diagnosticObserve;
#endif
    bool active, started, decoderReady, chunkOpen, eventPending, sourceEnded;
    bool guardIrq, streaming, continuationApplying, reported;
    unsigned fileNonce,fileRun,declaredRunFlags;
    bool flagsDeclared;
    F::Reader reader;
    D::Decoder decoder;
    D::Event event;
    D::Visual observedVisual;
    GhostWorldWitness::Record observedWorld;
    R::Replay replay;
    R::Movement moves[8];
    I::Borrow borrow;
    I::Plan plan;
    Flags::Snapshot liveFlags;
    GhostSimulation::SettingsLease settingsLease;
    TFlagManager *flagOwner;
    bool haveLiveFlags;
};
struct FileControl {
    GhostArena::Arena arena;
    GhostTraceIo::Transport transport;
    GhostTraceStreamNative::Context context;
    S::Stream stream;
    L::Stream logical;
    M::Client maps;
    unsigned ticket;
    bool configured;
};
constexpr unsigned kLogicalBase = MS_TRACE_BUFFER1_PPC + MS_TRACE_BUFFER_BYTES + 0x1000;
static_assert(kLogicalBase + sizeof(L::Workspace) <= MS_TRACE_UPPER_PPC + MOONSHINE_GHOST_UPPER_SIZE,
              "logical plan stays inside the admitted upper tail");
static_assert(sizeof(State) <= 0x2000, "replay state ends before stream controls");
static_assert(sizeof(FileControl) <= 0x1000, "stream controls end before blob cache");
FileControl &file = *reinterpret_cast<FileControl *>(MS_TRACE_CONTROL_PPC + 0x7000);
static_assert(kPackedBase + 0x4000 <= MS_TRACE_BUFFER1_PPC, "reader scratch precedes file image");
static_assert(R::kMaxRandomCalls * sizeof(R::RandomCall) <= MOONSHINE_GHOST_ARAM_BYTES,
              "replay RNG reuses the idle recording actor cache");
State &s = *reinterpret_cast<State *>(MS_TRACE_CONTROL_PPC + kControlOffset);
bool enabled;
unsigned lastStartError;

int getFlag(void *owner,unsigned id) { return static_cast<int>(static_cast<TFlagManager*>(owner)->getFlag(id)); }
void setFlag(void *owner,unsigned id,int value) { static_cast<TFlagManager*>(owner)->setFlag(id,value); }
Flags::Access flagAccess(TFlagManager *owner) { return {owner,getFlag,setFlag}; }
bool flagOwnerValid(TFlagManager *owner) {
    const unsigned address=reinterpret_cast<unsigned>(owner);
    return owner&&owner==TFlagManager::smInstance&&!(address&3u)&&address>=0x80003100u&&address<=0x81800000u-sizeof(TFlagManager);
}
bool captureFlags() {
    if(!flagOwnerValid(TFlagManager::smInstance)||!OSIsThreadTerminated(&gSetupThread))return false;
    s.flagOwner=TFlagManager::smInstance;
    const bool irq=OSDisableInterrupts();
    s.haveLiveFlags=Flags::capture(s.liveFlags,flagAccess(s.flagOwner));
    OSRestoreInterrupts(irq);return s.haveLiveFlags;
}
void restoreFlags() {
    if(!s.haveLiveFlags||!OSIsThreadTerminated(&gSetupThread))return;
    if(flagOwnerValid(s.flagOwner))Flags::restore(s.liveFlags,flagAccess(s.flagOwner));
    s.haveLiveFlags=false;s.flagOwner=nullptr;
}
unsigned scenarioCount(unsigned area) {
    if(area<=1||(area>=0x14&&area<=0x18)||area==0x3c)return 1;
    const unsigned parent=LevelWarp::parentArea(area);
    if((area>=2&&area<=9)||(parent>=2&&parent<=9))return 8;
    return 0;
}
bool fail(unsigned error, unsigned detail = 0) {
    if (!s.error) { s.error = error; s.detail = detail; }
    return false;
}
bool noCards() {
    s32 bytes = 0, sector = 0;
    return CARDProbeEx(0, &bytes, &sector) == CARD_ERROR_NOCARD &&
           CARDProbeEx(1, &bytes, &sector) == CARD_ERROR_NOCARD;
}
__attribute__((noinline)) R::FeedResult consumeEvent() {
    const bool irq=OSDisableInterrupts();
    if(s.event.type!=D::CONTINUATION) {
        const R::FeedResult result=R::feed(s.replay,s.event);
        OSRestoreInterrupts(irq);return result;
    }
    const R::FeedResult boundary=R::sealBoundary(s.replay,s.event.frame,s.event.tick);
    OSRestoreInterrupts(irq);
    if(boundary!=R::ACCEPTED)return boundary;
    const auto &c=s.event.continuation;
    s32 qf=0;const bool timed=gQFTTimer.currentQf(&qf);
    if(timed!=((c.contextFlags&MS_TRACE_CONTINUATION_QF_VALID)!=0)||
       (timed&&!R::clockMatches(s.replay,c.qf,qf))||(c.actions&&!gpMSound)) {
        fail(413);return R::FEED_FAILED;
    }
    if(!R::continueSource(s.replay,c))return R::FEED_FAILED;
    // Restore audio calls are outside the recorded tail; its final seed is explicit.
    s.continuationApplying=true;
    if(c.actions&MS_TRACE_AUDIO_STOP)gpMSound->stopAllSound();
    if(c.actions&MS_TRACE_AUDIO_PAUSE_ON)gpMSound->pauseOn(false);
    if(c.actions&MS_TRACE_AUDIO_PAUSE_OFF)gpMSound->pauseOff(2);
    *reinterpret_cast<volatile unsigned*>(SUSAMUNE_ADDR_LIBC_RAND_SEED)=c.rngSeed;
    s.continuationApplying=false;
    return R::ACCEPTED;
}
bool pumpMemory() {
#if IS_EMULATOR
    if (s.error || s.sourceEnded) return !s.error;
    for (;;) {
        if (s.eventPending) {
            const R::FeedResult result = consumeEvent();
            if (result == R::FRAME_PENDING) return true;
            if (result == R::FEED_FAILED) return fail(100 + s.replay.error, s.replay.detail);
            s.eventPending = false;
        }
        if (s.chunkOpen) {
            const D::Result result = D::next(s.decoder, s.event);
            if (result == D::FAILED) return fail(200 + s.decoder.error, s.decoder.offset);
            if (result == D::EVENT) { s.eventPending = true; continue; }
            s.chunkOpen = false;
            if (!F::releaseChunk(s.reader)) return fail(300 + s.reader.error);
        }
        const F::Status state = F::status(s.reader);
        if (state == F::FAILED) return fail(300 + s.reader.error);
        if (state == F::COMPLETE) {
            s.sourceEnded = true;
            return R::finishSource(s.replay) || fail(100 + s.replay.error, s.replay.detail);
        }
        if (state == F::CHUNK_READY) {
            if (!s.decoderReady) {
                const unsigned game = *reinterpret_cast<volatile const unsigned *>(0x80000000u);
                if (!F::sameRegion(s.reader, game) ||
                    !D::begin(s.decoder, s.reader.version, s.reader.game, s.reader.capabilities, R::kRequiredCapabilities) ||
                    !R::begin(s.replay, s.reader.version, s.reader.game, game, s.reader.capabilities,
                              R::EXPERIMENTAL, s.moves, 8, reinterpret_cast<R::RandomCall *>(kRandomBase), R::kMaxRandomCalls))
                    return fail(400, s.replay.error);
                if(!GhostSpinObservation::uninstall())return fail(422);
                if(!R::attachSpinQueue(s.replay,GhostTrace::spinQueue()))return fail(100+s.replay.error,s.replay.detail);
                s.decoderReady = true;
            }
            if (!D::pushChunk(s.decoder, s.reader.output, s.reader.chunkBytes)) return fail(200 + s.decoder.error);
            s.chunkOpen = true; continue;
        }
        F::Read request;
        if (!F::nextRead(s.reader, request) || request.offset > s.bytes || request.bytes > s.bytes - request.offset)
            return fail(401);
        const unsigned source=s.bytes>MS_TRACE_BUFFER_BYTES?kDiagnosticImage:MS_TRACE_BUFFER1_PPC;
        memcpy(request.destination, reinterpret_cast<const void *>(source + request.offset), request.bytes);
        if (!F::acceptRead(s.reader, request.bytes)) return fail(300 + s.reader.error);
    }
#else
    return fail(409);
#endif
}
bool pumpStream() {
    L::poll(file.logical,8);
    if(!s.decoderReady && file.stream.decoderReady) {
        const F::Reader &reader=file.stream.reader;
        if(!D::begin(s.decoder,reader.version,reader.game,reader.capabilities,R::kRequiredCapabilities) ||
           !R::begin(s.replay,reader.version,reader.game,*reinterpret_cast<volatile const unsigned *>(0x80000000u),
            reader.capabilities,R::EXPERIMENTAL,s.moves,8,reinterpret_cast<R::RandomCall *>(kRandomBase),R::kMaxRandomCalls))
            return fail(100+s.replay.error,s.replay.detail);
        if(!GhostSpinObservation::uninstall())return fail(422);
        if(!R::attachSpinQueue(s.replay,GhostTrace::spinQueue()))return fail(100+s.replay.error,s.replay.detail);
        s.decoderReady=true;
    }
    for(unsigned work=0;work<4096;++work) {
        if(s.eventPending) {
            const R::FeedResult result=consumeEvent();
            if(result==R::FRAME_PENDING)return true;
            if(result==R::FEED_FAILED)return fail(100+s.replay.error,s.replay.detail);
            if(!L::releaseEvent(file.logical,file.ticket))return fail(410);
            file.ticket=0;s.eventPending=false;
        }
        const L::Result result=L::nextEvent(file.logical,s.event,file.ticket);
        if(result==L::WAIT)return true;
        if(result==L::END) {
            s.sourceEnded=true;
            return R::finishSource(s.replay)||fail(100+s.replay.error,s.replay.detail);
        }
        if(result!=L::EVENT&&result!=L::BOUNDARY)return fail(420+file.logical.error,file.logical.detail);
        s.eventPending=true;
    }
    return true;
}
__attribute__((noinline)) bool pump() {
    if(s.error||s.sourceEnded)return !s.error;
#if IS_EMULATOR
    if(s.diagnosticSourceWait)return true;
#endif
    return s.streaming?pumpStream():pumpMemory();
}

I::GuardResult enter(void *, const I::Owner &owner, const I::Targets &targets) {
    const bool irq = OSDisableInterrupts();
    if (!enabled || !s.active || owner.token != s.token || owner.generation != s.generation ||
        GhostStageContext::generation() != s.generation || targets.pad != gpApplication.mGamePads[0] ||
        (targets.work && (!gpMarioOriginal || targets.work != gpMarioOriginal->mControllerWork))) {
        OSRestoreInterrupts(irq); return I::STALE;
    }
    s.guardIrq = irq; return I::OWNED;
}
void leave(void *) { OSRestoreInterrupts(s.guardIrq); }
bool apply(const D::Input &input, bool frozen, bool suppressed, bool setupResetsMode=false) {
    // Old experimental captures lack the shared mirrors; the report retains that gap.
    const I::MirrorPolicy policy = input.sharedKnown ? I::CAPTURED_SHARED : I::EXPERIMENTAL_PAD_MIRROR;
    const I::Error prepared = I::prepare(s.plan, input, policy);
    I::Controls control={frozen,suppressed,setupResetsMode,!s.replay.playedFrames};
    control.practiceHistory=((s.declaredRunFlags|s.replay.runFlags)&SUSAMUNE_GHOST_RUN_TAS)!=0;
    control.haveHistory=(input.flags&D::kFrameInput)&&!setupResetsMode&&
        PracticeSession::replayModeHistory(control.history.flags,control.history.stickTimer,control.history.disabledFrames);
    const I::Error applied = prepared == I::OK ? I::apply(s.borrow, s.plan, control) : prepared;
    R::inputApplied(s.replay, applied == I::OK);
    return applied == I::OK || fail(500 + applied);
}
}
bool temporarySettings() { return enabled&&s.settingsLease.active; }
bool busy() { return enabled && (s.active || s.haveLiveFlags || s.settingsLease.active || L::status(file.logical).pending || GhostReplayReport::pending()); }
bool active() { return enabled && s.active; }
bool hooksActive() { return enabled && s.active && s.started && !s.error && !s.continuationApplying; }
bool inputState(SusamunePracticeInput &out) {
    if (!hooksActive() || !s.borrow.applications) return false;
    static_assert(sizeof(D::RawPad) == sizeof(out) &&
        __builtin_offsetof(D::RawPad, stickX) == __builtin_offsetof(SusamunePracticeInput, stickX) &&
        __builtin_offsetof(D::RawPad, triggerL) == __builtin_offsetof(SusamunePracticeInput, triggerL) &&
        __builtin_offsetof(D::RawPad, error) == __builtin_offsetof(SusamunePracticeInput, error),
        "recorded HUD input uses the canonical raw-pad layout");
    memcpy(&out, &s.plan.input.raw, sizeof(out));
    out.flags = 0;
    return true;
}

bool wantsRenderFeedback(){return enabled&&s.active&&(s.replay.stage.observations&1u);}
bool wantsWaterFeedback(){return enabled&&s.active&&(s.replay.stage.observations&4u);}
bool wantsSpinFeedback(){return enabled&&s.active&&(s.replay.stage.observations&8u);}
bool ready() { return enabled && s.active && !s.started && !s.error && s.decoderReady && s.replay.sealed && R::state(s.replay)==R::INITIALIZATION_READY; }
bool arm(unsigned bytes) {
#if IS_EMULATOR
    if (StateSaveProbe::enabled() || GhostRecordingNative::fileBusy() || busy() || GhostTraceFlat::active() || !GhostMemory::ready() || GhostTrace::recording() || !noCards() || bytes < 96 || bytes > kDiagnosticBytes)
        return false;
    // Large private source images use only emulator RAM beyond the retail arena.
    if(bytes>MS_TRACE_BUFFER_BYTES&&
       (*reinterpret_cast<volatile const unsigned*>(0x80000028u)<0x02000000u||
        *reinterpret_cast<volatile const unsigned*>(0x800000f0u)!=0x01800000u))return false;
    const auto &box = *reinterpret_cast<volatile const MsTraceMailbox *>(MS_TRACE_CONTROL_PPC);
    DCInvalidateRange(const_cast<MsTraceMailbox *>(&box), sizeof(box));
    if (box.request.sequence != box.response.ackRequest ||
        (box.response.phase != MS_TRACE_IDLE && box.response.phase != MS_TRACE_SAVED && box.response.phase != MS_TRACE_DISCARDED))
        return false;
    const unsigned token = enabled ? s.token + 1 : 1;
    if (!enabled) memset(&file,0,sizeof(file));
    memset(&s, 0, sizeof(s)); enabled = true;
    s.magic = kMagic; s.bytes = bytes; s.token = token ? token : 1;
    if (!F::begin(s.reader, bytes, reinterpret_cast<void *>(MS_TRACE_BUFFER0_PPC), MS_TRACE_BUFFER_BYTES,
                  reinterpret_cast<void *>(kPackedBase), 0x4000) || !pump()) return false;
    R::InitialView initial;
    if (!R::initialView(s.replay, initial)) return fail(402);
    if(!captureFlags())return fail(418);
    const unsigned char *source=reinterpret_cast<const unsigned char*>(bytes>MS_TRACE_BUFFER_BYTES?kDiagnosticImage:MS_TRACE_BUFFER1_PPC);
    s.fileNonce=MsReplayReportGet(source+16);s.fileRun=s.reader.run;
    s.active = true;
    return true;
#else
    (void)bytes;return false;
#endif
}
unsigned startError() {return lastStartError;}
bool armFile(unsigned nonce,unsigned run,unsigned region) {
    unsigned boot=0;
    lastStartError=StateSaveProbe::enabled()?1:GhostRecordingNative::fileBusy()?12:busy()?2:GhostTraceFlat::active()?3:
        !GhostMemory::ready()?4:GhostTrace::recording()?5:!noCards()?6:!GhostTrace::backendIdentity(boot)?7:0;
    if(lastStartError)return false;
    if(!enabled) {memset(&s,0,sizeof(s));memset(&file,0,sizeof(file));enabled=true;}
    if(!file.configured) {
        if(!GhostTraceStreamNative::configure(file.context,file.transport,file.arena,boot)){lastStartError=8;return false;}
        if(!M::configureNative(file.maps,boot)){lastStartError=9;return false;}
        file.configured=true;
    }
    auto &work=*reinterpret_cast<L::Workspace*>(kLogicalBase);
    const L::Plan plan={work.segments,L::kMaxSegments,work.hash,L::kMaxHashSlots,0};
    if(file.context.nonce!=boot || !L::open(file.logical,plan,file.maps,file.stream,file.transport,0,{nonce,run,region},
        *reinterpret_cast<volatile const unsigned *>(0x80000000u),R::kRequiredCapabilities)){lastStartError=10;return false;}
    const unsigned token=s.token+1;memset(&s,0,sizeof(s));
    s.magic=kMagic;s.token=token?token:1;s.active=s.streaming=true;s.fileNonce=nonce;s.fileRun=run;file.ticket=0;
    if(!captureFlags()){lastStartError=11;fail(418);stop();return false;}
    return true;
}

bool setSourceRunFlags(unsigned flags) {
    if(!enabled||!s.active||!SusamuneGhostRunFlagsValid(flags))return false;
    if(s.flagsDeclared&&((flags^s.declaredRunFlags)&SUSAMUNE_GHOST_RUN_TAS))return fail(421);
    s.flagsDeclared=true;s.declaredRunFlags|=flags;
    if((s.replay.runFlags&SUSAMUNE_GHOST_RUN_TAS)&&!(flags&SUSAMUNE_GHOST_RUN_TAS))return fail(421);
    return true;
}
bool startAt(int entry) {
    if(!enabled||!s.active||s.started||s.error||entry< -1||entry>=ILing::count())return false;
    s.startEntry=entry<0?~0u:unsigned(entry)+1;ReplaySession::begin(((s.declaredRunFlags|s.replay.runFlags)&SUSAMUNE_GHOST_RUN_TAS)!=0);return true;
}
bool startRecorded() {return startAt(-1);}
bool permitsStartWarp(unsigned scene) {
    return ready()&&!s.startEntry&&s.replay.stage.scene==scene;
}


void prepareStartDeparture() {
    if(!enabled||!s.active||s.started||s.error||s.startEntry||!ready())return;
    // checkAdditionalMovie runs before stageSetup; its flags must already match.
    const auto &stage=s.replay.stage;
    if(memcmp(&gpApplication.mNextScene,&stage.current,4)){fail(406);return;}
    Flags::Snapshot candidate;const unsigned scenarios=scenarioCount(stage.current.area);
    if(!Flags::decode(candidate,s.replay.flagBytes,sizeof(s.replay.flagBytes),scenarios)){fail(417,stage.scene);return;}
    if(!s.haveLiveFlags||!flagOwnerValid(s.flagOwner)||!OSIsThreadTerminated(&gSetupThread)||
       !Flags::apply(candidate,scenarios,flagAccess(s.flagOwner)))fail(418);
}

void saveFailure() {
    if(!enabled||!s.error||s.reported||!s.fileNonce||!s.fileRun||!GhostReplayReport::reserve())return;
    auto *out=reinterpret_cast<unsigned char*>(MS_REPLAY_REPORT_DATA_PPC);
    unsigned count=0;GhostWorldWitness::Record snapshot=GhostWorldWitness::unavailable();
    TMarDirector *director=RetailInput::stageDirector();
    const bool irq=OSDisableInterrupts();
    if(director&&director->_260&&OSIsThreadTerminated(&gSetupThread))
        snapshot=GhostWorldWitness::snapshotNative(reinterpret_cast<unsigned>(gpConductor),
            reinterpret_cast<unsigned*>(MS_TRACE_BUFFER1_PPC+MS_TRACE_BUFFER_BYTES),1024,
            out+MS_REPLAY_REPORT_MIN_BYTES,MS_REPLAY_REPORT_MAX_ACTORS,count);
    OSRestoreInterrupts(irq);
    const unsigned bytes=MS_REPLAY_REPORT_MIN_BYTES+count*MS_REPLAY_REPORT_ACTOR_BYTES;
    unsigned header[16]={MS_REPLAY_REPORT_MAGIC,1,64,bytes,*reinterpret_cast<volatile const unsigned*>(0x80000000u),
        s.fileNonce,s.fileRun,s.error,s.detail,count,MS_REPLAY_REPORT_ACTOR_BYTES,snapshot.status,snapshot.hash,snapshot.scope,snapshot.count,0};
    memcpy(out,header,sizeof(header));status(reinterpret_cast<unsigned*>(out+64));visualStatus(reinterpret_cast<unsigned*>(out+192));
    reinterpret_cast<unsigned*>(out+192)[15]=s.ordinal;
    reinterpret_cast<unsigned*>(out+192)[31]=s.replay.activeTick;
    s.reported=GhostReplayReport::submit(bytes,s.fileNonce,s.fileRun);
}
void stop() {
    if (!enabled) return;
    if(!s.error&&s.flagsDeclared&&(s.replay.stage.observations&2u)&&R::state(s.replay)==R::COMPLETE&&
       ((s.declaredRunFlags^s.replay.runFlags)&SUSAMUNE_GHOST_RUN_TAS))fail(421);
    saveFailure();
    if (s.borrow.active) I::restore(s.borrow);
    ReplayCamera::stop();
    if(!GhostSpinObservation::uninstall(GhostSpinObservation::PLAYBACK))fail(422);
    s.active = false;ReplaySession::stop();restoreFlags();
    if(OSIsThreadTerminated(&gSetupThread))GhostSimulation::restoreSettings(s.settingsLease);
    if(s.streaming || L::status(file.logical).pending) {
        if(file.ticket && L::releaseEvent(file.logical,file.ticket))file.ticket=0;
        s.eventPending=false;L::close(file.logical);
    }
    GhostTraceHooks::setActive(GhostTrace::recording());
}
void stageSetup(unsigned area, unsigned episode, unsigned generation) {
    ReplayCamera::stop();
    ReplaySession::stageEntry(enabled&&s.active);
    if (!enabled || !s.active || s.error) return;
    const bool transition=s.started;
    if(transition) {
        // The next setup precedes onUpdate; finish the departure frame here.
        if(s.borrow.active){fail(414);return;}
        const bool irq=OSDisableInterrupts();
        if(s.replay.running&&!R::endFrame(s.replay,false,false))fail(100+s.replay.error,s.replay.detail);
        OSRestoreInterrupts(irq);
        if(s.error)return;
        if(R::state(s.replay)==R::COMPLETE){stop();return;}
        s.started=false;
        const unsigned began=OSGetTick();
        while(!ready()) {
            if(!pump()||s.error)return;
            if(ready())break;
            if(!s.streaming||OSGetTick()-began>OSSecondsToTicks(5)){fail(415);return;}
            OSYieldThread();
        }
    }
    if (!ready() || s.replay.stage.scene != ((area << 8) | episode)) { fail(403); return; }
    const auto &stage = s.replay.stage;
    if(stage.discIdentity!=*reinterpret_cast<volatile const unsigned*>(0x80000004u)){fail(412);return;}
    if(memcmp(&gpApplication.mCurrentScene,&stage.current,4)||
       memcmp(&gpApplication.mNextScene,&stage.next,4)){fail(406);return;}
    if(memcmp(&gpApplication.mPrevScene,&stage.previous,4)){fail(406);return;}
    if(!noCards()){fail(407);return;}
    if(!flagOwnerValid(s.flagOwner)){fail(418);return;}
    if(transition) {
        if(!Flags::matchesImage(s.replay.flagBytes,sizeof(s.replay.flagBytes),flagAccess(s.flagOwner))){fail(405);return;}
    } else {
        Flags::Snapshot candidate;const unsigned scenarios=scenarioCount(area);
        if(!Flags::decode(candidate,s.replay.flagBytes,sizeof(s.replay.flagBytes),scenarios)) {fail(417,(area<<8)|episode);return;}
        if(!s.haveLiveFlags||!Flags::apply(candidate,scenarios,flagAccess(s.flagOwner))){fail(418);return;}
    }
    GhostSimulation::Snapshot settings;
    GhostSimulation::capture(settings);
    for(unsigned i=0;i<sizeof(settings.bytes);++i)if(settings.bytes[i]!=s.replay.settings[i]) {
        fail(404,(i<<16)|(unsigned(settings.bytes[i])<<8)|s.replay.settings[i]);return;
    }
    if(!GhostTraceHooks::setActive(true)){fail(407);return;}
    if(stage.observations&8u) {
        if(!s.replay.spin||!GhostSpinObservation::install(*s.replay.spin,GhostSpinObservation::PLAYBACK)){fail(422);return;}
    } else if(!GhostSpinObservation::uninstall(GhostSpinObservation::PLAYBACK)){fail(422);return;}
    if(stage.npcPollutionPhase!=0xffffffffu) {
        volatile unsigned &phase=*reinterpret_cast<volatile unsigned*>(SUSAMUNE_ADDR_NPC_POLLUTION_PHASE);
        if(transition&&phase!=stage.npcPollutionPhase){fail(419,phase);return;}
        phase=stage.npcPollutionPhase;
    }
    *reinterpret_cast<volatile unsigned *>(SUSAMUNE_ADDR_LIBC_RAND_SEED) = stage.rngSeed;
    s.generation = generation;
    if (!R::confirmInitialization(s.replay, R::SETTINGS_OWNERSHIP | R::INPUT_HOOKS | R::RNG_HOOKS, true)) {
        fail(100 + s.replay.error); return;
    }
    const unsigned parent=LevelWarp::parentArea(area);
    s.replay.inheritedClockPending=!transition&&parent>=2&&parent<=9&&
        (stage.previous.area==parent||LevelWarp::parentArea(stage.previous.area)==parent);
    s.started = true;
}
void afterWorldDraw() {
    if (enabled && s.borrow.active) {
        const I::Error result = I::restore(s.borrow);
        if (result != I::OK && result != I::STALE_OWNER) fail(500 + result);
    }
}
void beforeFrame() {
    if(enabled&&s.active&&!s.error&&!ReplaySession::advance()){fail(420);return;}
    if(!enabled)return;
    if(!s.active||s.error) {
        restoreFlags();
        if(OSIsThreadTerminated(&gSetupThread))GhostSimulation::restoreSettings(s.settingsLease);
    }
    if(s.streaming || L::status(file.logical).pending)L::poll(file.logical,8);
    if(!s.active)return;
    if(s.error){stop();return;}
    const unsigned physical=JUTGamePad::mPadStatus[0].mButton;
    if((physical&0x1200u)==0x1200u){stop();return;}
    if(s.error)return;
    const bool irq=OSDisableInterrupts();
    if(s.started && s.replay.running && !R::endFrame(s.replay,false,false))fail(100+s.replay.error,s.replay.detail);
    OSRestoreInterrupts(irq);
    if(!s.error)pump();
    if(s.decoderReady) {
        const unsigned headerFlags=s.streaming?L::runFlags(file.logical):MsTraceGet(s.reader.header+36);
        if(!s.streaming&&MsTraceGet(s.reader.header+40)==MS_TRACE_PROVENANCE_TAG&&
           !setSourceRunFlags(headerFlags))fail(421);
        const unsigned sourceFlags=s.replay.runFlags|headerFlags;
        if(s.flagsDeclared&&(sourceFlags&SUSAMUNE_GHOST_RUN_TAS)&&!(s.declaredRunFlags&SUSAMUNE_GHOST_RUN_TAS))fail(421);
        if((sourceFlags|s.declaredRunFlags)&SUSAMUNE_GHOST_RUN_TAS)ReplaySession::markSourceTas();
    }
    if(s.started&&s.replay.initialized&&!s.replay.sealed&&!s.sourceEnded&&!s.error) {
        // Returning through gameLoop would advance its fader/audio tail without a replay frame.
        const unsigned began=OSGetTick();const OSTime beganTime=OSGetTime();
        TMarDirector *owner=RetailInput::stageDirector();
        OSStopwatch *watch=owner&&owner->_260?&owner->mStopwatch:nullptr;
        const OSTime watchStart=watch?watch->mLast:0;
        const bool watchActive=watch&&watch->mActive;
        while(!s.replay.sealed&&!s.sourceEnded&&!s.error&&s.replay.initialized) {
            if(!pump())break;
            if(OSGetTick()-began>OSSecondsToTicks(5)){fail(415,2);break;}
            OSYieldThread();
        }
        if(watchActive&&owner==RetailInput::stageDirector()&&watch->mActive&&watch->mLast==watchStart)
            watch->mLast+=OSGetTime()-beganTime;
    }
    if(ready() && s.startEntry) {
        if(gSettings.saveState()==SETTINGS_SAVE_PENDING)return;
        const unsigned start=s.startEntry;s.startEntry=0;
        if(start==~0u) {
            LevelWarp::Dest source={},destination={};
            if(!GhostReplayStart::destination(s.replay.stage,s.replay.flagBytes,
                    scenarioCount(s.replay.stage.current.area),source,destination))fail(411);
            else if(!GhostSimulation::beginSettings(s.settingsLease,s.replay.settings))fail(419);
            else if(!WarpWheel::requestReplayStart(source,destination))fail(411);
        } else {
            const int entry=int(start-1);const unsigned filter=ILing::ghostBrowseFilter(entry);
            const unsigned scene=(((filter&255u)-1)<<8)|(((filter>>8)&255u)-1);
            if(!filter||scene!=s.replay.stage.scene)fail(411);
            else if(!GhostSimulation::beginSettings(s.settingsLease,s.replay.settings))fail(419);
            else if(!WarpWheel::requestExplicitILStart(entry))fail(411);
        }
    }
    if(!s.started)return;
    ILing::invalidateForAssist();Records::invalidateAttempt();Ghost::invalidateForAssist();
    if(!s.error && R::state(s.replay)==R::COMPLETE)stop();
}
void observeFrame() {
    if (!hooksActive()) return;
    unsigned char sample[64];GhostTrace::visualSample(sample);
    s.observedWorld = GhostTrace::worldSample(reinterpret_cast<unsigned *>(MS_TRACE_BUFFER1_PPC + MS_TRACE_BUFFER_BYTES), 1024);
    if (!D::decodeVisual(s.decoder, sample, sizeof(sample), s.observedVisual)) fail(408);
}
unsigned controls() {
    if(!hooksActive()||!s.replay.sealed)return 0;
    const unsigned flags=s.replay.boundary.flags&3u;
    const bool practiceHold=(flags&1u)&&(!(flags&2u)||s.replay.settings[GhostSimulation::FREE_CAMERA_ACTIVE]);
    return flags|(practiceHold?4u:0u);
}
bool beforeDirect(bool frozen, bool suppressed, unsigned directorState) {
    if (!enabled) return true;
    if(!s.active||!s.started){s.waitReason=0x10;return true;}
    if (s.error) {s.waitReason=0x20;return false;}
    s.waitReason=0x30;
    if (R::state(s.replay) == R::COMPLETE) { stop(); return true; }
    if (!noCards()) return fail(407);
    // A live overlay can pause playback, without consuming its next recorded input.
    s.waitReason=0x40;
    const unsigned actualControls=(frozen?1u:0u)|(suppressed?2u:0u),expectedControls=controls()&3u;
    if(actualControls!=expectedControls){s.waitReason=1u|(actualControls<<8)|(expectedControls<<16);return false;}
    TMarDirector *director = RetailInput::stageDirector();
    R::NativeFrame native = {
        (unsigned(gpApplication.mCurrentScene.mAreaID) << 8) | gpApplication.mCurrentScene.mEpisodeID,
        unsigned(gpApplication.mContext), directorState,
        director && director->_260, director && OSIsThreadTerminated(&gSetupThread), &s.observedVisual, &s.observedWorld};
    R::FrameView frame;
    s.waitReason=0x50;
    const R::Advance result = R::beginFrame(s.replay, native, frame);
    if(result==R::WAIT_SOURCE && s.generation && RetailInput::movieDirector() &&
       native.scene==s.replay.stage.scene && unsigned(gpApplication.mCutSceneID)==s.replay.stage.cutscene &&
       R::acceptSkippedMovie(s.replay)) {
        s.waitReason=0x400;return true;
    }
    if (result == R::WAIT_NATIVE_SETUP || result == R::WAIT_SOURCE) { s.waitReason=0x100u|unsigned(result);return false; }
    if (result != R::FRAME_STARTED) {
        fail(100+s.replay.error,s.replay.detail);
        status(reinterpret_cast<unsigned*>(MS_TRACE_CONTROL_PPC+0x3000));
        visualStatus(reinterpret_cast<unsigned*>(MS_TRACE_CONTROL_PPC+0x3080));
        return false;
    }
    s.ordinal = 0;
    I::Targets targets = {gpApplication.mGamePads[0], nullptr,
        &JUTGamePad::mPadButton[0], &JUTGamePad::mPadMStick[0], &JUTGamePad::mPadSStick[0]};
    s.waitReason=0x60;
    const I::Error borrowed = I::begin(s.borrow, targets, {s.generation, s.token}, {nullptr, enter, leave});
    if (borrowed != I::OK) return fail(500 + borrowed);
    s.waitReason=0x70;
    const bool applied=apply(*frame.boundary, frozen, suppressed,
        native.directorState==0&&!native.setupComplete&&native.setupTerminated);
    s.waitReason=applied?0x80:0x90;return applied;
}
void movement(TMario *mario, unsigned cue) {
    if (!hooksActive() || !(cue & 1u) || mario != gpMarioOriginal) return;
    const R::Movement *sample = nullptr;
    if (!R::movement(s.replay, cue, s.ordinal++, sample)) { fail(100 + s.replay.error, s.replay.detail); return; }
    apply(sample->input, (s.borrow.controls & 1) != 0, (s.borrow.controls & 2) != 0);
#if IS_EMULATOR
    // Private readback excludes both the game arena and the admitted source image.
    if(s.diagnosticObserve==0x50523634u&&!s.error&&!s.streaming&&s.bytes<=0x4a0000u) {
        auto *control=reinterpret_cast<volatile unsigned*>(0x81d00000u);
        if(control[1]==0x4f43434cu&&sample->tick<8192) {
            const unsigned value=*reinterpret_cast<const unsigned char*>(0x81d50000u+sample->tick);
            if(value<=1){auto *flags=reinterpret_cast<unsigned*>(reinterpret_cast<unsigned char*>(mario)+0x118);*flags=(*flags&~1u)|value;}
            else ++control[2];
        }
        const unsigned serial=control[0];
        auto *row=reinterpret_cast<unsigned char*>(0x81d01000u+(serial&63u)*0x1000u);
        unsigned header[]={s.replay.sourceFrame,sample->tick,cue,s.ordinal,
            reinterpret_cast<unsigned>(mario),reinterpret_cast<unsigned>(mario->mController),
            reinterpret_cast<unsigned>(mario->mControllerWork),reinterpret_cast<unsigned>(gpCamera)};
        memcpy(row,header,sizeof(header));memcpy(row+64,static_cast<const void*>(mario),0x574);
        if(mario->mController)memcpy(row+0x600,static_cast<const void*>(mario->mController),0xf0);
        if(mario->mControllerWork)memcpy(row+0x700,mario->mControllerWork,0x24);
        if(gpCamera)memcpy(row+0x800,static_cast<const void*>(gpCamera),0x350);
        control[0]=serial+1;
    }
#endif
}
void random(unsigned caller, unsigned result, unsigned seed) {
    if (!hooksActive()) return;
    const bool irq = OSDisableInterrupts();
    if (!R::verifyRandom(s.replay, caller, result, seed)) fail(100 + s.replay.error, s.replay.detail);
    OSRestoreInterrupts(irq);
}
unsigned renderFeedback(unsigned caller,unsigned nativeValue,unsigned seed) {
    if(!hooksActive()||!(s.replay.stage.observations&1u))return nativeValue;
    const bool irq=OSDisableInterrupts();unsigned value=nativeValue;
    if(!R::replayFeedback(s.replay,caller,seed,value))fail(100+s.replay.error,s.replay.detail);
    OSRestoreInterrupts(irq);return value;
}
void visualStatus(unsigned *out) {
    static_assert(sizeof(D::Visual)<=64,"visual diagnostic slots");
    memset(out,0,128);
    if(enabled){memcpy(out,&s.replay.visual,sizeof(D::Visual));memcpy(out+16,&s.observedVisual,sizeof(D::Visual));}
    DCStoreRange(out,128);
}
void status(unsigned *out) {
    memset(out, 0, 128);
    if (!enabled) return;
    const unsigned words[] = {s.magic, s.active, s.started, s.error, s.detail, s.generation,
        s.replay.error, s.replay.detail, s.replay.sourceFrame, s.replay.sourceTick,
        s.replay.playedFrames, s.replay.movementCalls, s.replay.randomCalls, s.replay.randomCount,
        s.borrow.error, s.borrow.observed.flags, s.borrow.expected.flags,
        unsigned(s.borrow.observed.stickTimer), unsigned(s.borrow.expected.stickTimer),
        unsigned(s.borrow.observed.disabledFrames), unsigned(s.borrow.expected.disabledFrames),
        s.replay.missingEvidence,
        unsigned(s.replay.haveFrame)|(unsigned(s.replay.sealed)<<1)|(unsigned(s.replay.running)<<2)|
        (unsigned(s.replay.pendingInput)<<3)|(unsigned(s.replay.initialized)<<4)|(unsigned(s.eventPending)<<5), s.waitReason};
    memcpy(out, words, sizeof(words));
    memcpy(out + 24, &s.replay.world, sizeof(s.replay.world));
    memcpy(out + 28, &s.observedWorld, sizeof(s.observedWorld));
}
}
#endif

#if MOONSHINE_GHOST_TRACE
namespace GhostWorldRuntime {
unsigned waterFeedback(unsigned caller,unsigned nativeValue,unsigned seed){
    if(!hooksActive()||!(s.replay.stage.observations&4u))return nativeValue;
    const bool irq=OSDisableInterrupts();unsigned value=nativeValue;
    if(!R::replayFloatFeedback(s.replay,caller,seed,value))fail(100+s.replay.error,s.replay.detail);
    OSRestoreInterrupts(irq);return value;
}
}
#endif
