#include "susamune/ghost_provenance.h"
#include "susamune/ghost_world_replay.hxx"
#include "susamune/ghost_trace_observation.h"
#include "susamune/ghost_simulation_settings.h"

namespace GhostWorldReplay {
namespace {
bool game(unsigned value) {
    return value==0x474d534au||value==0x474d5345u||value==0x474d5350u;
}
bool fail(Replay &r,Error error,unsigned detail=0) {
    if(!r.error){r.error=error;r.detail=detail;}return false;
}
bool separate(const void *a,unsigned an,const void *b,unsigned bn) {
    const auto x=reinterpret_cast<__UINTPTR_TYPE__>(a),y=reinterpret_cast<__UINTPTR_TYPE__>(b);
    return a&&b&&x+an>=x&&y+bn>=y&&(x+an<=y||y+bn<=x);
}
// Retail can finish setup and perform Mario inside a call that began in state 0.
bool ready(const Replay &r) { return (r.frame.flags&4u)!=0&&r.frame.directorState!=0xffffffffu; }
const RandomCall *head(const Replay &r) { return r.randomCount?&r.randomFront:nullptr; }
unsigned randomBytes(const Replay &r) { return r.randomCapacity*sizeof(RandomCall); }
// Checked packet spans never advance an offset by more than one capacity.
unsigned randomOffset(const Replay &r,unsigned at) {
    const unsigned bytes=randomBytes(r);return at<bytes?at:at-bytes;
}
unsigned randomWord(const Replay &r,unsigned at) {
    unsigned value;
    __builtin_memcpy(&value,reinterpret_cast<const unsigned char*>(r.random)+randomOffset(r,at),4);
    return value;
}
void writeRandom(Replay &r,unsigned at,const void *data,unsigned bytes) {
    at=randomOffset(r,at);
    unsigned first=randomBytes(r)-at;if(first>bytes)first=bytes;
    auto *out=reinterpret_cast<unsigned char*>(r.random);
    __builtin_memcpy(out+at,data,first);
    if(bytes>first)__builtin_memcpy(out,static_cast<const unsigned char*>(data)+first,bytes-first);
}
// Header: frame, tick, seed, count:10/callers:7/setup:1. Packets are padded to 4 bytes.
unsigned randomPacketBytes(unsigned meta) {
    const unsigned callers=(meta>>10)&127u;
    return callers?16+callers*4+(((meta&1023u)+3)&~3u):24;
}
void readRandom(Replay &r,unsigned meta) {
    RandomCall &out=r.randomFront;
    if(!r.randomIndex) {
        out.frame=randomWord(r,r.randomHead);out.tick=randomWord(r,r.randomHead+4);
        out.seed=randomWord(r,r.randomHead+8);out.setup=(meta>>17)&1u;
    } else out.seed=out.seed*1103515245u+12345u;
    const unsigned callers=(meta>>10)&127u;
    if(callers) {
        const unsigned at=randomOffset(r,r.randomHead+16+callers*4+r.randomIndex);
        const unsigned index=reinterpret_cast<const unsigned char*>(r.random)[at];
        out.caller=randomWord(r,r.randomHead+16+index*4);out.result=(out.seed>>16)&32767u;
    } else {
        out.caller=randomWord(r,r.randomHead+16);out.result=randomWord(r,r.randomHead+20);
    }
}
bool missing(Replay &r,unsigned bits) {
    r.missingEvidence|=bits;
    return r.mode==EXPERIMENTAL||fail(r,MISSING_EVIDENCE,bits);
}
bool spinReady(Replay &r,bool requireEmpty) {
    if(!(r.stage.observations&8u))return true;
    if(!r.spin)return fail(r,CAPACITY);
    const auto &q=*r.spin;
    if(q.error||q.mode!=GhostSpinObservation::PLAYBACK)return fail(r,SPIN_MISMATCH,q.error?q.error:q.mode);
    if(q.count>GhostSpinObservation::kCapacity||q.read>q.count)return fail(r,CAPACITY,q.count);
    if(requireEmpty&&q.read!=q.count)return fail(r,SPIN_NOT_CONSUMED,q.ticks[q.read]);
    return true;
}
bool closeSourceFrame(Replay &r) {
    if((r.stage.observations&2u)&&r.provenanceFrame!=r.sourceFrame)return fail(r,FORMAT);
    if(!r.haveBoundary)return fail(r,MISSING_INPUT);
    if(ready(r)) {
        if((r.boundary.flags&Trace::kInputFrozen)&&r.movementCount)return fail(r,INPUT_ORDER);
        r.sealed=true;r.sawReady=true;
    } else {
        if(r.movementCount)return fail(r,UNSUPPORTED_TRANSITION);
        if(!spinReady(r,true))return false;
        ++r.loadingFrames;r.haveFrame=false;
    }
    return true;
}
unsigned visualDifference(const Replay &r,const Trace::Visual &source,const Trace::Visual &actual) {
    unsigned difference=(source.scene!=actual.scene?1u:0u)|(source.directorTick!=actual.directorTick?2u:0u)|
        ((source.flags&actual.flags)!=source.flags?4u:0u)|((source.flags&2u)&&!clockMatches(r,source.qf,actual.qf)?8u:0u);
    if(!(source.flags&1u))return difference;
    if(source.x!=actual.x||source.y!=actual.y||source.z!=actual.z)difference|=16;
    if(source.yaw!=actual.yaw)difference|=32;
    if(source.animationId!=actual.animationId)difference|=64;
    if(source.animationPhase!=actual.animationPhase)difference|=128;
    if(source.heldObjectId!=actual.heldObjectId)difference|=256;
    if(source.heldNameKey!=actual.heldNameKey)difference|=512;
    if(source.yoshi!=actual.yoshi)difference|=1024;
    if(source.visible!=actual.visible)difference|=2048;
    if(__builtin_memcmp(&source.fludd,&actual.fludd,8))difference|=4096;
    return difference;
}

unsigned word(const unsigned char *p) {
    return unsigned(p[0])<<24|unsigned(p[1])<<16|unsigned(p[2])<<8|p[3];
}
}
bool begin(Replay &r,unsigned version,unsigned sourceGame,unsigned targetGame,unsigned capabilities,
           Mode mode,Movement *movements,unsigned movementCapacity,RandomCall *random,unsigned randomCapacity) {
    r.error=r.detail=0;
    if(!movementCapacity||movementCapacity>kMaxMovements||!randomCapacity||randomCapacity>kMaxRandomCalls||
       !separate(&r,sizeof(r),movements,movementCapacity*sizeof(Movement))||
       !separate(&r,sizeof(r),random,randomCapacity*sizeof(RandomCall))||
       !separate(movements,movementCapacity*sizeof(Movement),random,randomCapacity*sizeof(RandomCall)))
        return fail(r,ARGUMENT);
    r={};r.game=sourceGame;r.capabilities=capabilities;r.mode=mode;r.missingEvidence=kInitialEvidence;
    r.movieScene=0xffffffffu;
    r.movements=movements;r.movementCapacity=movementCapacity;r.random=random;r.randomCapacity=randomCapacity;
    if(version<1||version>3||!game(sourceGame)||!game(targetGame))return fail(r,FORMAT);
    if(sourceGame!=targetGame)return fail(r,REGION);
    if((capabilities&0xff000000u)||(capabilities&kRequiredCapabilities)!=kRequiredCapabilities)return fail(r,CAPABILITY);
    if(mode!=EXPERIMENTAL&&mode!=REQUIRE_EVIDENCE)return fail(r,ARGUMENT);
    return true;
}
bool attachSpinQueue(Replay &r,GhostSpinObservation::Queue &q) {
    if(r.error||r.haveStage||r.haveFrame||r.running||r.spin)return fail(r,ORDER);
    if(!separate(&r,sizeof(r),&q,sizeof(q))||
       !separate(r.movements,r.movementCapacity*sizeof(Movement),&q,sizeof(q))||
       !separate(r.random,randomBytes(r),&q,sizeof(q)))return fail(r,ARGUMENT);
    q.count=q.error=q.sequence=q.read=q.frame=q.tick=0;q.mode=GhostSpinObservation::PLAYBACK;
    r.spin=&q;r.spinLastSequence=0;return true;
}
FeedResult feed(Replay &r,const Trace::Event &e) {
    if(r.error)return FEED_FAILED;
    if(r.sealed||r.running)return FRAME_PENDING;
    if(r.ended){fail(r,ORDER);return FEED_FAILED;}
    if (r.pendingStage.generation &&
        (e.type != Trace::OBSERVATION || e.observation.subtype != MS_OBSERVE_SPIN)) {
        return closeSourceFrame(r) ? FRAME_PENDING : FEED_FAILED;
    }
    if(e.type==Trace::OBSERVATION&&e.observation.subtype!=4) {
        const auto &o=e.observation;
        if(!MsTraceObservationValid(o.data,o.bytes)||word(o.data+4)!=o.subtype||
           e.frame!=r.sourceFrame||e.tick!=r.sourceTick){fail(r,FORMAT);return FEED_FAILED;}
        return ACCEPTED;
    }
    if(e.type==Trace::STAGE_START) {
        if(e.stage.game!=r.game||(e.stage.flags&7u)!=7u||!e.stage.generation||!e.stage.flagBytes) {
            fail(r,NO_PRE_STAGE_CAPTURE);return FEED_FAILED;
        }
        bool deferStage = false;
        if(r.haveStage) {
            if(e.frame!=r.sourceFrame||e.tick!=r.sourceTick||e.stage.generation==r.stage.generation) {
                fail(r,UNSUPPORTED_TRANSITION);return FEED_FAILED;
            }
            if(r.haveFrame) {
                // Older captures can flush the departing frame's spin queue after this marker.
                deferStage = r.initialized && ready(r) && (r.stage.observations & e.stage.observations & 8u);
                if (!deferStage) {
                    if(!closeSourceFrame(r))return FEED_FAILED;
                    if(r.sealed)return FRAME_PENDING;
                }
            }
            if(!deferStage&&(!r.initialized||r.randomCount||!r.playedFrames)){fail(r,ORDER);return FEED_FAILED;}
        } else if(r.haveFrame||e.frame||e.tick){fail(r,UNSUPPORTED_TRANSITION);return FEED_FAILED;}
        if(r.haveStage&&!deferStage&&!spinReady(r,true))return FEED_FAILED;
        if((e.stage.observations&8u)&&!r.spin){fail(r,CAPACITY);return FEED_FAILED;}
        auto &target = deferStage ? r.pendingStage : r.stage;
        target = e.stage;
        // The departing stage has already applied its flag image.
        __builtin_memcpy(r.flagBytes, e.stage.flagBytes, sizeof(r.flagBytes));
        target.flagBytes = r.flagBytes;
        if (deferStage) r.stage.flagBytes = nullptr;
        else { r.haveStage = true; r.initialized = false; }
        return ACCEPTED;
    }
    if(!r.haveStage) {
        if(e.type!=Trace::SESSION){fail(r,NO_PRE_STAGE_CAPTURE);return FEED_FAILED;}
        if(e.frame||e.tick||!e.settings||!SusamuneGhostSimulationSettingsValid(e.settings)) {
            fail(r,FORMAT);return FEED_FAILED;
        }
        if(r.haveSettings&&__builtin_memcmp(r.settings,e.settings,sizeof(r.settings))) {
            fail(r,SETTINGS_CHANGED);return FEED_FAILED;
        }
        __builtin_memcpy(r.settings,e.settings,sizeof(r.settings));r.haveSettings=true;return ACCEPTED;
    }
    if(e.type==Trace::FRAME) {
        if(r.haveFrame) {
            if(!closeSourceFrame(r))return FEED_FAILED;
            if(r.sealed)return FRAME_PENDING;
        }
        if(e.frame!=r.sourceFrame+1||e.tick!=r.sourceTick||e.frameData.movementTick!=e.tick) {
            fail(r,ORDER);return FEED_FAILED;
        }
        if(e.frameData.scene!=r.stage.scene&&
           (e.frameData.directorState!=0xffffffffu||(e.frameData.flags&6u))) {
            fail(r,UNSUPPORTED_TRANSITION,e.frameData.scene);return FEED_FAILED;
        }
        if(e.frameData.directorState==0xffffffffu&&e.frameData.scene!=r.stage.scene&&
           (e.frameData.context==5||e.frameData.context==6)) {
            if(r.movieFrames&&r.movieScene!=e.frameData.scene){fail(r,UNSUPPORTED_TRANSITION);return FEED_FAILED;}
            r.movieScene=e.frameData.scene;++r.movieFrames;
        }
        r.frame=e.frameData;r.sourceFrame=e.frame;r.frameTick=e.tick;r.haveFrame=true;
        r.haveBoundary=r.haveVisual=r.haveWorld=false;r.movementCount=r.consumedMovements=0;return ACCEPTED;
    }
    if(e.frame!=r.sourceFrame){fail(r,ORDER);return FEED_FAILED;}
    if(e.type==Trace::INPUT) {
        if(!r.haveFrame){fail(r,ORDER);return FEED_FAILED;}
        const Trace::Input &input=e.input;
        if(ready(r)&&!input.sharedKnown&&!missing(r,SHARED_MIRRORS))return FEED_FAILED;
        if(input.flags&Trace::kFrameInput) {
            if(r.haveBoundary||r.movementCount||e.tick!=r.sourceTick||input.cue||
               (input.flags&~(Trace::kFrameInput|3u))||(input.valid&~1u)) {
                fail(r,INPUT_ORDER);return FEED_FAILED;
            }
            if(ready(r)&&(input.valid!=1||input.raw.error)){fail(r,MISSING_INPUT);return FEED_FAILED;}
            r.boundary=input;r.haveBoundary=true;
        } else {
            if(!ready(r)){fail(r,UNSUPPORTED_TRANSITION);return FEED_FAILED;}
            if(!r.haveBoundary||e.tick!=r.sourceTick+1||!(input.cue&1u)||input.flags) {
                fail(r,INPUT_ORDER);return FEED_FAILED;
            }
            if(!(input.valid&1u)||(input.valid&~3u)||input.raw.error){fail(r,MISSING_INPUT);return FEED_FAILED;}
            if(r.movementCount==r.movementCapacity){fail(r,CAPACITY,r.movementCount+1);return FEED_FAILED;}
            r.movements[r.movementCount++]={input,e.tick};r.sourceTick=e.tick;
        }
        return ACCEPTED;
    }
    if(e.tick!=r.sourceTick){fail(r,ORDER);return FEED_FAILED;}
    switch(e.type) {
    case Trace::SESSION:
        if(!e.settings||!SusamuneGhostSimulationSettingsValid(e.settings)){fail(r,FORMAT);return FEED_FAILED;}
        if(r.haveSettings&&__builtin_memcmp(r.settings,e.settings,sizeof(r.settings))){fail(r,SETTINGS_CHANGED);return FEED_FAILED;}
        __builtin_memcpy(r.settings,e.settings,sizeof(r.settings));r.haveSettings=true;return ACCEPTED;
    case Trace::IDENTITY:
        if(e.identity.game!=r.game||e.identity.discIdentity!=r.stage.discIdentity){fail(r,REGION);return FEED_FAILED;}
        return ACCEPTED;
    case Trace::VISUAL:
        if(!r.haveFrame||r.haveVisual||r.haveBoundary){fail(r,ORDER);return FEED_FAILED;}
        if(e.visual.scene!=r.frame.scene){fail(r,UNSUPPORTED_TRANSITION);return FEED_FAILED;}
        if(r.frame.scene!=r.stage.scene) {
            if(e.visual.flags||e.visual.generation||e.visual.directorTick){fail(r,UNSUPPORTED_TRANSITION);return FEED_FAILED;}
        } else if(e.visual.generation!=r.stage.generation){fail(r,UNSUPPORTED_TRANSITION);return FEED_FAILED;}
        if((r.capabilities&MS_TRACE_HAS_STAGE_OWNED_CLOCK)&&!(r.frame.flags&2u)&&(e.visual.flags&2u)) {
            fail(r,FORMAT);return FEED_FAILED;
        }
        r.visual=e.visual;r.haveVisual=true;return ACCEPTED;
    case Trace::WORLD_WITNESS:
        if(!r.haveFrame||r.haveWorld||r.haveBoundary){fail(r,ORDER);return FEED_FAILED;}
        r.world=e.world;r.haveWorld=true;return ACCEPTED;
    case Trace::RNG: {
        if(r.haveFrame&&ready(r)&&!r.haveBoundary){fail(r,RNG_ORDER);return FEED_FAILED;}
        if(r.haveFrame&&r.frame.directorState==0xffffffffu)r.movieRandom=true;
        const Trace::Rng &rng=e.rng;
        if(!rng.count||rng.count>512) {
            fail(r,CAPACITY,r.randomCount+rng.count);return FEED_FAILED;
        }
        if(rng.callerCount) {
            if(!rng.callers||!rng.indices||rng.callerCount>64){fail(r,FORMAT);return FEED_FAILED;}
        } else if(rng.count!=1){fail(r,FORMAT);return FEED_FAILED;}
        unsigned seed=rng.firstSeed;
        for(unsigned i=0;i<rng.count;++i) {
            if(rng.callerCount&&rng.indices[i]>=rng.callerCount){fail(r,FORMAT);return FEED_FAILED;}
            if(i)seed=seed*1103515245u+12345u;
        }
        if(seed!=rng.lastSeed){fail(r,FORMAT);return FEED_FAILED;}
        const unsigned setup=(!r.haveFrame||!ready(r))?1u:0u;
        const unsigned meta=rng.count|(rng.callerCount<<10)|(setup<<17);
        unsigned bytes=randomPacketBytes(meta);
        // Sparse caller tables must never cost more than the old literal queue.
        const bool literal=bytes>rng.count*sizeof(RandomCall)||!rng.callerCount;
        if(literal)bytes=rng.count*sizeof(RandomCall);
        if(bytes>randomBytes(r)-r.randomUsed) {
            fail(r,CAPACITY,r.randomCount+rng.count);return FEED_FAILED;
        }
        unsigned at=randomOffset(r,r.randomHead+r.randomUsed);
        if(literal) {
            seed=rng.firstSeed;
            for(unsigned i=0;i<rng.count;++i) {
                if(i)seed=seed*1103515245u+12345u;
                const unsigned caller=rng.callerCount?word(rng.callers+rng.indices[i]*4):rng.caller;
                const unsigned result=rng.callerCount?(seed>>16)&32767u:rng.result;
                const unsigned row[]={e.frame,e.tick,seed,1u|(setup<<17),caller,result};
                writeRandom(r,at,row,sizeof(row));at=randomOffset(r,at+sizeof(row));
            }
        } else {
            const unsigned header[]={e.frame,e.tick,rng.firstSeed,meta};
            writeRandom(r,at,header,sizeof(header));at=randomOffset(r,at+sizeof(header));
            for(unsigned i=0;i<rng.callerCount;++i) {
                const unsigned caller=word(rng.callers+i*4);
                writeRandom(r,at,&caller,4);at=randomOffset(r,at+4);
            }
            writeRandom(r,at,rng.indices,rng.count);at=randomOffset(r,at+rng.count);
            const unsigned padding=0;
            writeRandom(r,at,&padding,(-rng.count)&3u);
        }
        // Event pointers expire when the checked source chunk is released.
        r.randomUsed+=bytes;
        const bool empty=!r.randomCount;r.randomCount+=rng.count;
        if(empty)readRandom(r,randomWord(r,r.randomHead+12));
        return ACCEPTED;
    }
    case Trace::OBSERVATION: {
        const auto &o=e.observation;
        if(!(r.stage.observations&8u)||!r.haveFrame||!ready(r)||!r.haveBoundary||!r.spin||
           o.subtype!=4||o.bytes!=28||!o.data||word(o.data)!=1||word(o.data+4)!=4) {
            fail(r,FORMAT);return FEED_FAILED;
        }
        const unsigned sequence=word(o.data+8),caller=word(o.data+12),result=word(o.data+16),
            direction=word(o.data+20),valid=word(o.data+24);
        if(!sequence||sequence!=r.spinLastSequence+1||caller<1||caller>9||valid!=1||
           result>1||(!result?direction!=4:(direction!=2&&direction!=3))) {
            fail(r,SPIN_ORDER,sequence);return FEED_FAILED;
        }
        auto &q=*r.spin;
        if(q.error||q.read||q.count>=GhostSpinObservation::kCapacity){fail(r,CAPACITY,q.count+1);return FEED_FAILED;}
        q.events[q.count]={sequence,caller,result,direction,valid};
        q.frames[q.count]=e.frame;q.ticks[q.count]=e.tick;++q.count;
        r.spinLastSequence=sequence;return ACCEPTED;
    }
    case Trace::PROVENANCE:
        if(!MsTraceProvenanceValid(e.runFlags)||(r.runFlags&~e.runFlags)){fail(r,FORMAT);return FEED_FAILED;}
        r.runFlags=e.runFlags;r.provenanceFrame=e.frame;return ACCEPTED;
    default:fail(r,FORMAT);return FEED_FAILED;
    }
}
FeedResult sealBoundary(Replay &r,unsigned frame,unsigned tick) {
    if(r.error)return FEED_FAILED;
    if(!r.initialized||r.ended||frame!=r.sourceFrame||tick!=r.sourceTick) {
        fail(r,ORDER);return FEED_FAILED;
    }
    if(r.sealed||r.running)return FRAME_PENDING;
    if(r.haveFrame) {
        if(!closeSourceFrame(r))return FEED_FAILED;
        if(r.sealed)return FRAME_PENDING;
    }
    if(!r.playedFrames){fail(r,EMPTY_SOURCE);return FEED_FAILED;}
    if(r.randomCount){fail(r,RNG_NOT_CONSUMED,head(r)->tick);return FEED_FAILED;}
    return ACCEPTED;
}
bool continueSource(Replay &r,const MsTraceContinuation &c) {
    if(r.error)return false;
    if(!r.initialized||r.ended||r.haveFrame||r.running||r.sealed||r.randomCount||!r.playedFrames)
        return fail(r,ORDER);
    if(!(r.capabilities&MS_TRACE_HAS_CONTINUATION))return fail(r,CAPABILITY);
    if(c.runFlags!=MS_TRACE_CONTINUATION_RUN_FLAGS||(c.actions&~7u)||(c.actions&6u)==6u||
       !c.parentNonce||!c.parentRun||!c.parentChunk||(c.contextFlags&~1u)||
       ((c.contextFlags&1u)?c.qf>0x7fffffffu:c.qf!=0)||
       (c.generation&&c.generation!=r.stage.generation))return fail(r,FORMAT);
    if(!spinReady(r,true))return false;
    if(r.spin){r.spin->count=r.spin->read=r.spin->sequence=0;r.spinLastSequence=0;}
    r.stage.generation=c.generation;r.runFlags|=c.runFlags;
    return true;
}
bool acceptSkippedMovie(Replay &r) {
    if(r.error||r.initialized||r.running||!r.sealed||!r.movieFrames||
       r.movieScene!=r.stage.scene||r.movieRandom||!r.settings[5])return false;
    return missing(r,MOVIE_TIMING);
}
bool finishSource(Replay &r) {
    if(r.error)return false;
    if(r.ended||r.running)return fail(r,ORDER);
    if(!r.haveStage||!r.haveSettings)return fail(r,MISSING_EVIDENCE,SETTINGS_OWNERSHIP);
    if(r.haveFrame&&!r.sealed&&!closeSourceFrame(r))return false;
    if(!r.haveFrame&&!spinReady(r,true))return false;
    if(!r.sawReady)return fail(r,EMPTY_SOURCE);
    r.ended=true;return true;
}
State state(const Replay &r) {
    if(r.error)return STOPPED;
    if(r.running)return RUNNING;
    if(r.ended&&!r.haveFrame&&!r.randomCount)return COMPLETE;
    if(!r.haveStage||!r.haveSettings)return PREPARING;
    if(!r.initialized)return INITIALIZATION_READY;
    if(r.sealed)return READY;
    if(r.haveFrame&&!ready(r))return LOADING;
    return NEED_SOURCE;
}
bool initialView(const Replay &r,InitialView &out) {
    if(r.error||!r.haveStage||!r.haveSettings||!r.stage.flagBytes)return false;
    out={r.stage,r.settings,r.missingEvidence};return true;
}
bool confirmInitialization(Replay &r,unsigned reconstructedEvidence,bool persistentWritesBlocked) {
    if(r.error)return false;
    if(!r.haveStage||!r.haveSettings||r.initialized||r.running||(reconstructedEvidence&~kInitialEvidence))return fail(r,ORDER);
    if(!persistentWritesBlocked)return fail(r,PLATFORM_REFUSED);
    r.missingEvidence=(r.missingEvidence&~kInitialEvidence)|(kInitialEvidence&~reconstructedEvidence);
    if(r.mode==REQUIRE_EVIDENCE&&r.missingEvidence)return fail(r,MISSING_EVIDENCE,r.missingEvidence);
    r.initialized=true;r.movieScene=0xffffffffu;r.movieFrames=0;r.movieRandom=false;return true;
}
Advance beginFrame(Replay &r,const NativeFrame &native,FrameView &out) {
    if(r.error)return ADVANCE_FAILED;
    if(r.running){fail(r,INPUT_ORDER);return ADVANCE_FAILED;}
    if(!r.initialized||!r.sealed)return WAIT_SOURCE;
    if(!native.setupTerminated||((r.frame.flags&2u)&&!native.setupComplete))return WAIT_NATIVE_SETUP;
    if(!(r.frame.flags&2u)&&native.setupComplete) {
        fail(r,NATIVE_STATE,native.directorState);return ADVANCE_FAILED;
    }
    if(native.scene!=r.stage.scene||native.context!=r.frame.context||native.directorState!=r.frame.directorState) {
        fail(r,NATIVE_STATE,native.directorState);return ADVANCE_FAILED;
    }
    if(head(r)&&head(r)->setup){fail(r,RNG_NOT_CONSUMED,head(r)->frame);return ADVANCE_FAILED;}
    if(r.haveVisual&&native.visual) {
        const Trace::Visual *expected=&r.visual,*observed=native.visual;
        Trace::Visual migratedSource,migratedActual;
        // Early schema-1 captures borrowed an old clock through a reused director address.
        if(r.capabilities==0x3fffffu&&r.frame.directorState==0&&!(r.frame.flags&2u)&&
           native.directorState==0&&!native.setupComplete&&r.visual.flags==2u&&(!r.visual.qf||r.playedFrames)&&
           !r.visual.directorTick&&r.visual.scene==r.stage.scene&&r.visual.generation==r.stage.generation&&
           !(native.visual->flags&1u)&&!native.visual->directorTick) {
            if(!missing(r,CLOCK_MODEL|LEGACY_LOADING_CLOCK))return ADVANCE_FAILED;
            migratedSource=r.visual;migratedActual=*native.visual;
            migratedSource.flags&=~2u;migratedSource.qf=0;
            migratedActual.flags&=~2u;migratedActual.qf=0;
            expected=&migratedSource;observed=&migratedActual;
        }
        if(r.inheritedClockPending&&(expected->flags&observed->flags&2u)&&
           expected->scene==observed->scene&&expected->directorTick==observed->directorTick) {
            r.inheritedClockPending=false;
            if(observed->qf>=0&&expected->qf>observed->qf) {
                if(!missing(r,CLOCK_MODEL))return ADVANCE_FAILED;
                r.clockOrigin=expected->qf-observed->qf;
                r.clockAttempt=expected->attempt;
            }
        }
        const unsigned difference=visualDifference(r,*expected,*observed);
        if(difference){fail(r,VISUAL_MISMATCH,difference);return ADVANCE_FAILED;}
    } else if(!missing(r,VISUAL_WITNESS))return ADVANCE_FAILED;
    r.worldMatched=false;
    if(r.haveWorld&&native.world) {
        if(r.world.scope!=native.world->scope||r.world.status!=native.world->status) {
            fail(r,WORLD_MISMATCH);return ADVANCE_FAILED;
        }
        if(r.world.status==GhostWorldWitness::COMPLETE) {
            if(!GhostWorldWitness::matches(r.world,*native.world)){fail(r,WORLD_MISMATCH);return ADVANCE_FAILED;}
            r.worldMatched=true;
        }
    }
    if(!spinReady(r,false))return ADVANCE_FAILED;
    if((r.stage.observations&8u)&&r.spin){r.spin->frame=r.sourceFrame;r.spin->tick=r.frameTick;}
    r.running=true;r.pendingInput=true;r.activeTick=r.frameTick;r.consumedMovements=0;
    out={&r.frame,&r.boundary,r.haveVisual?&r.visual:nullptr,r.sourceFrame,r.frameTick,r.movementCount};
    return FRAME_STARTED;
}
bool movement(Replay &r,unsigned cue,unsigned ordinal,const Movement *&out) {
    out=nullptr;if(r.error)return false;
    if(!r.running||r.pendingInput||ordinal!=r.consumedMovements||ordinal>=r.movementCount)return fail(r,INPUT_ORDER,ordinal);
    const Movement &expected=r.movements[ordinal];
    if(expected.input.cue!=cue)return fail(r,INPUT_ORDER,cue);
    const RandomCall *random=head(r);
    if(random&&(!random->setup&&random->frame==r.sourceFrame&&random->tick<expected.tick))return fail(r,RNG_NOT_CONSUMED,random->tick);
    if(!spinReady(r,false))return false;
    if((r.stage.observations&8u)&&r.spin) {
        auto &q=*r.spin;
        if(q.read<q.count&&q.ticks[q.read]<expected.tick)return fail(r,SPIN_NOT_CONSUMED,q.ticks[q.read]);
        q.tick=expected.tick;
    }
    r.activeTick=expected.tick;r.pendingInput=true;++r.consumedMovements;++r.movementCalls;out=&expected;return true;
}
bool inputApplied(Replay &r,bool success) {
    if(r.error)return false;
    if(!r.running||!r.pendingInput)return fail(r,INPUT_ORDER);
    if(!success)return fail(r,INPUT_NOT_APPLIED);
    r.pendingInput=false;return true;
}
bool verifyRandom(Replay &r,unsigned caller,unsigned result,unsigned seed) {
    if(r.error)return false;
    if(!r.initialized||r.pendingInput)return fail(r,RNG_ORDER);
    const RandomCall *expected=head(r);
    if(!expected)return fail(r,RNG_UNDERRUN);
    if(r.running?(expected->setup||expected->frame!=r.sourceFrame||expected->tick!=r.activeTick):!expected->setup)
        return fail(r,RNG_ORDER,expected->tick);
    if(caller!=expected->caller||result!=expected->result||seed!=expected->seed)return fail(r,RNG_MISMATCH,expected->caller);
    unsigned meta=randomWord(r,r.randomHead+12);
    --r.randomCount;++r.randomCalls;
    if(++r.randomIndex==(meta&1023u)) {
        const unsigned bytes=randomPacketBytes(meta);
        r.randomHead=randomOffset(r,r.randomHead+bytes);r.randomUsed-=bytes;r.randomIndex=0;
        if(r.randomCount)meta=randomWord(r,r.randomHead+12);
    }
    if(r.randomCount)readRandom(r,meta);
    return true;
}
bool replayFeedback(Replay &r,unsigned caller,unsigned seed,unsigned &value) {
    if(r.error)return false;
    const RandomCall *expected=head(r);
    if(!expected)return fail(r,RNG_UNDERRUN);
    if(expected->result>1||((randomWord(r,r.randomHead+12)>>10)&127u))return fail(r,RNG_MISMATCH,caller);
    const unsigned recorded=expected->result;
    if(!verifyRandom(r,caller,recorded,seed))return false;
    value=recorded;return true;
}
bool endFrame(Replay &r,bool worldObserved,bool worldMatches) {
    if(r.error)return false;
    if(!r.running||r.pendingInput||r.consumedMovements!=r.movementCount)return fail(r,INPUT_ORDER,r.consumedMovements);
    const RandomCall *random=head(r);
    if(random&&random->frame<=r.sourceFrame)return fail(r,RNG_NOT_CONSUMED,random->tick);
    if(worldObserved) {
        if(!worldMatches)return fail(r,WORLD_MISMATCH);
    } else if(!r.worldMatched&&!missing(r,WORLD_WITNESS))return false;
    if(!spinReady(r,true))return false;
    if(r.spin)r.spin->count=r.spin->read=0;
    if (r.pendingStage.generation) {
        if (r.randomCount) return fail(r, ORDER);
        r.stage = r.pendingStage;
        r.pendingStage.generation = 0;
        r.initialized = false;
    }
    ++r.playedFrames;r.running=r.sealed=r.haveFrame=false;return true;
}
bool refuseAction(Replay &r,PersistentAction action) {
    return fail(r,UNSUPPORTED_ACTION,action);
}
void cancel(Replay &r) { fail(r,CANCELLED); }
Report report(const Replay &r) {
    return {static_cast<Error>(r.error),r.detail,r.sourceFrame,r.running?r.activeTick:r.sourceTick,r.missingEvidence,
        r.loadingFrames,r.playedFrames,r.movementCalls,r.randomCalls,r.mode==EXPERIMENTAL,state(r)==COMPLETE};
}
}

namespace GhostWorldReplay {
bool replayFloatFeedback(Replay &r,unsigned caller,unsigned seed,unsigned &value) {
    if(r.error)return false;
    const RandomCall *expected=head(r);
    if(!expected)return fail(r,RNG_UNDERRUN);
    if((expected->result&0x7fffffffu)>0x49742400u||((randomWord(r,r.randomHead+12)>>10)&127u))
        return fail(r,RNG_MISMATCH,caller);
    const unsigned recorded=expected->result;
    if(!verifyRandom(r,caller,recorded,seed))return false;
    value=recorded;return true;
}
}
