#include "susamune/ghost_visual_provider.hxx"
#include "susamune/ghost_format.h"

namespace GhostVisualProvider {
namespace {
Provider *current;
bool busy;
bool finitePosition(float v) { unsigned bits;__builtin_memcpy(&bits,&v,4);return (bits&0x7fffffffu)<=0x49742400u; }
bool validFrame(const Frame &f) {
    const auto &v=f.visual;
    if(!finitePosition(v.x)||!finitePosition(v.y)||!finitePosition(v.z)||v.animationId>335||v.animationPhase>4095||v.yoshi>5||
       !SusamuneGhostVisualValid(reinterpret_cast<const unsigned char*>(&v.fludd),1)||
       !SusamuneGhostRunFlagsValid(f.runFlags))return false;
    return !f.hasInput||(!(f.input.buttons&~0x1f7fu)&&!f.input.flags);
}
bool sample(const Query &q,Frame &f) {
    if(!current||q.runner>=current->config.runners||q.flags&~(WATCH|HISTORY)||q.scene>0xffffu||q.qf<0)return false;
    f={};
    if(!current->config.sample(current->config.context,q,f)||!validFrame(f))return false;
    f.visual.recordingToken=q.token?q.token:current->config.token;
    return true;
}
}
bool prepare(Provider &p,const Config &config,unsigned &generation) {
    const __UINTPTR_TYPE__ destination=reinterpret_cast<__UINTPTR_TYPE__>(&generation),base=reinterpret_cast<__UINTPTR_TYPE__>(&p);
    if(destination>=base&&destination<base+sizeof(p))return false;
    const Config desired=config;
    generation=0;
    if(busy||current==&p||!desired.context||!desired.valid||!desired.sample||!desired.runners||desired.runners>2||
       !desired.sourceGeneration||!desired.token||p.generation==~0u)return false;
    busy=true;const bool valid=desired.valid(desired.context,desired.sourceGeneration);busy=false;
    if(!valid)return false;
    const unsigned next=p.generation+1;p={};p.config=desired;p.generation=next;p.prepared=1;generation=next;return true;
}
bool activate(Provider &p,unsigned generation) {
    if(busy||current||!p.prepared||!generation||generation!=p.generation)return false;
    busy=true;const bool valid=p.config.valid(p.config.context,p.config.sourceGeneration);busy=false;
    if(!valid)return false;
    current=&p;p.readyMask=0;return true;
}
bool stop(Provider &p,unsigned generation) {
    if(busy||!p.prepared||!generation||p.generation!=generation)return false;
    if(current==&p)current=nullptr;
    p.prepared=0;p.readyMask=0;p.frames[0]={};p.frames[1]={};return true;
}
bool stopActive() { return !current||stop(*current,current->generation); }
bool active() { return current!=nullptr; }
unsigned runners() { return current?current->config.runners:0; }
void suspend() { if(current&&!busy)current->readyMask=0; }
bool refresh(const Query *queries,unsigned count,bool atomicPair) {
    if(!current||busy)return false;
    current->readyMask=0;
    if(!queries||count!=current->config.runners)return false;
    busy=true;
    if(!current->config.valid(current->config.context,current->config.sourceGeneration)) { busy=false;return false; }
    Frame frames[2]={};unsigned mask=0;
    for(unsigned i=0;i<count;++i)if(queries[i].runner==i&&!(queries[i].flags&HISTORY)&&sample(queries[i],frames[i]))mask|=1u<<i;
    busy=false;
    if(atomicPair&&mask!=(1u<<count)-1)return false;
    for(unsigned i=0;i<count;++i)if(mask&(1u<<i))current->frames[i]=frames[i];
    current->readyMask=mask;return mask!=0;
}
bool historical(const Query &query,Frame &out) {
    if(!current||busy||!(query.flags&HISTORY))return false;
    busy=true;const bool valid=current->config.valid(current->config.context,current->config.sourceGeneration)&&sample(query,out);busy=false;
    return valid;
}
bool read(unsigned runner,Frame &out) {
    if(!current||busy||runner>=current->config.runners||!(current->readyMask&(1u<<runner)))return false;
    out=current->frames[runner];return true;
}
bool input(unsigned runner,SusamunePracticeInput &out) {
    Frame frame;if(!read(runner,frame)||!frame.hasInput||!frame.visual.visible)return false;
    out=frame.input;return true;
}
unsigned runFlags(unsigned runner) { Frame frame;return read(runner,frame)?frame.runFlags:0; }
bool cameraAvailable() { return current&&current->config.camera; }
bool camera(const Query &query,GhostCamera::View &out) {
    if(!current||busy||!current->config.camera||!(current->readyMask&1u)||query.runner||
       !(query.flags&WATCH)||(query.flags&~WATCH)||query.qf<0)return false;
    busy=true;
    const bool valid=current->config.valid(current->config.context,current->config.sourceGeneration)&&
        current->config.camera(current->config.context,query,out);
    busy=false;
    SusamuneGhostCameraSample checked;
    return valid&&GhostCamera::encode(out,static_cast<u32>(query.qf),0,&checked);
}
bool path(const Query &query,const SusamuneGhostPoseSample *&out,unsigned &count) {
    out=nullptr;count=0;
    if(!current||busy||!current->config.path||query.runner>=current->config.runners||
       !(query.flags&WATCH)||(query.flags&~WATCH))return false;
    busy=true;
    const bool valid=current->config.valid(current->config.context,current->config.sourceGeneration)&&
        current->config.path(current->config.context,query,current->pathScratch,97,count);
    busy=false;
    if(!valid||count<2||count>97) { count=0;return false; }
    for(unsigned i=0;i<count;++i) {
        const unsigned char *p=reinterpret_cast<const unsigned char*>(current->pathScratch+i)+4;
        for(unsigned axis=0;axis<3;++axis,p+=3) {
            const unsigned bits=(unsigned(p[0])<<16)|(unsigned(p[1])<<8)|p[2];
            const int value=bits&0x800000u?int(bits)-0x1000000:int(bits);
            if(value<-8000000||value>8000000) { count=0;return false; }
        }
    }
    out=current->pathScratch;return true;
}
bool fromSample(const GhostTraceIndex::Sample &s,unsigned token,Frame &out) {
    if(!token||s.qf<0)return false;
    out={};auto &v=out.visual;
    v.x=s.x;v.y=s.y;v.z=s.z;v.yaw=s.yaw;v.animationId=s.animationId;v.animationPhase=s.animationPhase;
    v.heldObjectId=s.heldObjectId;v.heldNameKey=s.heldNameKey;v.yoshi=s.yoshi;
    v.visible=(s.flags&GhostTraceIndex::POSE)&&s.visible;v.fludd=s.fludd;v.visualQf=static_cast<unsigned>(s.qf);v.recordingToken=token;
    out.hasInput=(s.flags&GhostTraceIndex::INPUT)!=0;
    if(out.hasInput) { __builtin_memcpy(&out.input,&s.raw,sizeof(out.input));out.input.flags=0; }
    return validFrame(out);
}
}
