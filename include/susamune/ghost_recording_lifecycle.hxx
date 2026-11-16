#pragma once
namespace GhostRecordingLifecycle {
enum { kDrafts=3, kNone=3, kRequired=15 };
enum Capability { CAPTURE=1, PUBLICATION=2, LIBRARY=4, CHECKPOINT_FORK=8 };
enum Phase { EMPTY, ARMING, CAPTURING, FINALIZING, READY, SAVING, PUBLISHED, DISCARDING, FAILED };
struct Identity { unsigned nonce,run; };
struct Completion { Identity identity;unsigned bytes,chunks,frames,capabilities,headerHash,footerHash; };
struct Checkpoint {
    Identity identity;
    unsigned generation,frame,tick,chunk,recordOffset,prefixHash;
};
struct Draft {
    Identity identity;
    unsigned token,pbToken,ownerToken,phase,saveSequence,error,references;
    Completion completion;
    unsigned char manifest[256];
};
struct State { unsigned nonce,nextRun,serial,active,capabilities,error;Draft drafts[kDrafts];unsigned reservedRun; };
inline bool same(Identity a,Identity b){return a.nonce==b.nonce&&a.run==b.run;}
inline bool enabled(const State&s){return s.nonce&&(s.capabilities&kRequired)==kRequired;}
inline void init(State&s,unsigned nonce,unsigned capabilities){s={};s.nonce=nonce;s.capabilities=capabilities;s.active=kNone;s.nextRun=1;s.serial=1;}
inline unsigned token(const Draft&d){return d.pbToken?d.pbToken:d.token;}
inline Draft*find(State&s,unsigned value){if(!value)return nullptr;for(unsigned i=0;i<kDrafts;++i)if(s.drafts[i].phase!=EMPTY&&(s.drafts[i].token==value||s.drafts[i].pbToken==value))return s.drafts+i;return nullptr;}
inline const Draft*find(const State&s,unsigned value){return find(const_cast<State&>(s),value);}
inline Draft*active(State&s){return s.active<kDrafts?s.drafts+s.active:nullptr;}
inline unsigned reserveRun(State&s){
    if(!enabled(s))return 0;
    if(s.reservedRun)return s.reservedRun;
    if(!s.nextRun||s.nextRun>=0x80000000u)return 0;
    s.reservedRun=0x80000000u|s.nextRun++;
    return s.reservedRun;
}
inline unsigned takeRun(State&s){const unsigned run=reserveRun(s);s.reservedRun=0;return run;}
inline Draft*arm(State&s){
    if(!enabled(s)||s.active<kDrafts||(!s.reservedRun&&(!s.nextRun||s.nextRun>=0x80000000u))||!s.serial||s.serial>=0x40000000u)return nullptr;
    for(unsigned i=0;i<kDrafts;++i){auto&d=s.drafts[i];if((d.phase==EMPTY||d.phase==PUBLISHED||(d.phase==FAILED&&!d.pbToken))&&!d.references){
        d={};d.identity={s.nonce,takeRun(s)};d.token=0x40000000u|s.serial++;d.phase=ARMING;s.active=i;return &d;
    }}return nullptr;
}
inline bool captured(State&s,Identity id){Draft*d=active(s);if(!d||d->phase!=ARMING||!same(d->identity,id))return false;d->phase=CAPTURING;return true;}
inline bool finish(State&s,unsigned ownerToken){Draft*d=active(s);if(!d||d->phase!=CAPTURING||!ownerToken)return false;d->ownerToken=ownerToken;d->phase=FINALIZING;return true;}
inline bool completed(State&s,const Completion&value){Draft*d=active(s);if(!d||d->phase!=FINALIZING||!same(d->identity,value.identity)||value.bytes<96||!value.frames)return false;d->completion=value;d->phase=READY;s.active=kNone;return true;}
inline bool protect(State&s,unsigned ownerToken,unsigned pbToken){
    if(!ownerToken||!pbToken)return false;
    for(unsigned i=0;i<kDrafts;++i){auto&d=s.drafts[i];if(d.ownerToken!=ownerToken||(d.phase!=FINALIZING&&d.phase!=READY))continue;
        for(unsigned j=0;j<kDrafts;++j)if(i!=j&&s.drafts[j].phase!=EMPTY&&token(s.drafts[j])==pbToken)return false;
        d.pbToken=pbToken;return true;
    }return false;
}
inline Draft*selection(State&s){
    if(s.serial<=1)return nullptr;
    const unsigned latest=0x40000000u|(s.serial-1u);
    for(unsigned i=0;i<kDrafts;++i){auto&d=s.drafts[i];
        if(d.token==latest&&(d.phase==READY||d.phase==FINALIZING))return &d;
    }
    return nullptr;
}
inline bool beginSave(State&s,unsigned selected,unsigned sequence){Draft*d=find(s,selected);if(!d||d->phase!=READY||!sequence)return false;for(unsigned i=0;i<kDrafts;++i)if(s.drafts[i].phase==SAVING)return false;d->phase=SAVING;d->saveSequence=sequence;return true;}
inline bool saveResult(State&s,unsigned sequence,bool success){
    if(!sequence)return false;for(unsigned i=0;i<kDrafts;++i){auto&d=s.drafts[i];if(d.phase!=SAVING||d.saveSequence!=sequence)continue;
        d.saveSequence=0;d.phase=success?PUBLISHED:READY;if(success)d.pbToken=0;return true;
    }return false;
}
inline bool beginDiscard(State&s,unsigned selected){Draft*d=find(s,selected);if(!d||d->references||d->phase==SAVING||d->phase==PUBLISHED||d->phase==DISCARDING)return false;d->phase=DISCARDING;return true;}
inline bool discarded(State&s,Identity id){for(unsigned i=0;i<kDrafts;++i){auto&d=s.drafts[i];if(d.phase==DISCARDING&&same(d.identity,id)){d={};if(s.active==i)s.active=kNone;return true;}}return false;}
inline void failed(State&s,Identity id,unsigned error){for(unsigned i=0;i<kDrafts;++i){auto&d=s.drafts[i];if(d.phase!=EMPTY&&same(d.identity,id)){d.error=error;d.phase=FAILED;if(s.active==i)s.active=kNone;return;}}}
// A checkpoint names an acknowledged logical boundary; no file/lease pointer is stored.
inline bool retainCheckpoint(State&s,const Checkpoint&c){
    if(!enabled(s)||!c.generation||!c.frame||!c.chunk||c.recordOffset>0x80000u)return false;
    for(unsigned i=0;i<kDrafts;++i){auto&d=s.drafts[i];if((d.phase==CAPTURING||d.phase==FINALIZING||d.phase==READY||d.phase==PUBLISHED)&&same(d.identity,c.identity)&&c.generation==d.token&&d.references!=~0u){++d.references;return true;}}return false;
}
inline bool releaseCheckpoint(State&s,const Checkpoint&c){for(unsigned i=0;i<kDrafts;++i){auto&d=s.drafts[i];if(d.phase!=EMPTY&&same(d.identity,c.identity)&&c.generation==d.token&&d.references){--d.references;return true;}}return false;}
}
