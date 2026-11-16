#include "susamune/memory_capture.hxx"
#if MOONSHINE_MEMORY_TELEMETRY && (!defined(MOONSHINE_MEMORY_CAPTURE) || MOONSHINE_MEMORY_CAPTURE)
#include "susamune/memory_telemetry_scan.h"
#include "susamune/addresses.hxx"
#include "susamune/practice_session.hxx"
#include "SMS/System/Application.hxx"
#include "Dolphin/OS.h"
#include "Dolphin/string.h"
#include "Dolphin/mem.h"
#include "susamune/retail_input.hxx"
extern "C" bool memoryTelemetryStates(unsigned *);
extern "C" bool memoryTelemetryGhosts(unsigned *);
namespace MemoryCapture {
namespace {
struct Row { unsigned kind, object, data, bytes, used, children, parent, flags; char name[16]; };
static_assert(sizeof(Row) == 48, "capture row wire size");
Row rows[64];
unsigned request, phase, started, count, cursor, lastRequest;
bool ownPause;
unsigned word(unsigned p) { return *reinterpret_cast<volatile const unsigned *>(p); }
unsigned scene() { return ((SUSAMUNE_GAME_VERSION - 1u) << 24) |
    (static_cast<unsigned>(gpApplication.mContext) << 16) |
    (static_cast<unsigned>(gpApplication.mCurrentScene.mAreaID) << 8) | gpApplication.mCurrentScene.mEpisodeID; }
void name(Row &row, const char *text) { unsigned n=0; for (; n<15 && text[n]; ++n) row.name[n]=text[n]; row.name[n]=0; }
Row *add(unsigned kind, unsigned object, unsigned data, unsigned bytes, const char *label) {
    if (count == 64) { rows[0].flags |= 1; return nullptr; }
    Row &row=rows[count++]; row={};row.kind=kind;row.object=object;row.data=data;row.bytes=bytes;name(row,label);return &row;
}
void resume() {
    if (ownPause && (PracticeSession::manualPaused() || PracticeSession::pausePending()))
        PracticeSession::requestPauseToggle(false);
    ownPause=false;
}
void failure(unsigned reason) {
    count=cursor=0;Row *row=add(0,scene(),0,0,"Capture failed");row->flags=2;row->used=reason;phase=3;resume();
}
void bankName(Row &row, unsigned node) {
    unsigned pointer=0;
    if (MemoryReadable(node-4,0x40) && word(node-4)==SUSAMUNE_MEM1_ADDR(0x803aae30u,0x803e26b0u,0x803da070u))
        pointer=word(node+0x38);
    else if (MemoryReadable(node-0x14,0x44) && word(node-0x14)==SUSAMUNE_MEM1_ADDR(0x803aaedcu,0x803e275cu,0x803da11cu))
        pointer=word(node-4);
    if (pointer<0x80000000u || pointer>0x81800000u-16) return;
    const char *text=reinterpret_cast<const char *>(pointer);
    for (unsigned i=0;i<16;++i) {
        if (!text[i]) { name(row,text);row.flags=0x80000000u|word(node+0x2c);return; }
        if (text[i]<32 || text[i]>126) return;
    }
}
void audioChildren(unsigned parent, unsigned depth) {
    if (!MemoryReadable(parent,44) || depth>4) { rows[0].flags|=1;return; }
    const unsigned base=word(parent+8), size=word(parent+16), expected=word(parent)&0xffffu;
    if (base<0x4000 || base>=0x1000000 || size>0x1000000-base || expected>64) { rows[0].flags|=4;return; }
    unsigned node=word(parent+20), seen=0, end=base;
    while (node && seen<64) {
        if (!MemoryReadable(node,44) || word(node+24)!=parent) { rows[0].flags|=4;return; }
        const unsigned at=word(node+8), bytes=word(node+16);
        if (at<end || at>base+size || !bytes || bytes>base+size-at) { rows[0].flags|=4;return; }
        Row *row=add(2,node,at,bytes,"Audio allocation");if(!row)return;
        row->used=word(node+12);row->children=word(node)&0xffffu;row->parent=parent;bankName(*row,node);
        if (row->children) audioChildren(node,depth+1);
        end=at+bytes;node=word(node+28);++seen;
    }
    if (node || seen!=expected) rows[0].flags|=4;
}
void heapRow(unsigned heap, const char *label) {
    if (!MemoryReadable(heap,0x78)) return;
    MemoryPoolSample sample={};
    if (word(heap)==SUSAMUNE_MEM1_ADDR(0x803a8548u,0x803dff38u,0x803d78f0u)) {
        if(!MemoryExpSample(heap,word(heap),word,sample))return;
    } else if (word(heap)==SUSAMUNE_MEM1_ADDR(0x803a8690u,0x803e0070u,0x803d7a28u)) {
        sample.capacity=word(heap+0x38);const unsigned free=word(heap+0x68);
        if(free>sample.capacity || sample.capacity>0x1800000)return;
        sample.used=sample.capacity-free;sample.largestFree=free;
    } else return;
    Row *row=add(4,heap,word(heap+0x30),sample.capacity,label);
    if(row){row->used=sample.used;row->flags=sample.largestFree;}
}
void capture(unsigned now) {
    count=cursor=0;add(0,scene(),now,0,"Allocator map");
    const bool interrupts=OSDisableInterrupts();
    const unsigned root=SUSAMUNE_MEM1_ADDR(0x803e6334u,0x803fd82cu,0x803f4fccu);
    MemoryPoolSample sample={};
    if(MemoryWaveSample(root,word,sample)) {
        Row *row=add(1,root,word(root+8),sample.capacity,"Audio bank pool");
        row->used=sample.used;row->children=word(root)&0xffffu;row->flags=sample.largestFree;audioChildren(root,0);
    } else rows[0].flags|=4;
    const unsigned manager=word(SUSAMUNE_MEM1_ADDR(0x804097c8u,0x8040e230u,0x80405908u));
    const unsigned list=SUSAMUNE_MEM1_ADDR(0x80400b8cu,0x80404290u,0x803fba30u);
    if(MemoryArchiveSample(manager,list,word,sample)) {
        unsigned node=word(list),limit=word(list+8);
        for(unsigned i=0;node && i<limit;++i){
            const unsigned block=word(node);Row *row=add(3,block,word(block+20),word(block+24),"ARAM archive");
            if(!row)break;row->flags=word(block+28);node=word(node+12);
        }
    } else rows[0].flags|=8;
    heapRow(word(SUSAMUNE_MEM1_ADDR(0x80409830u,0x8040e298u,0x80405970u)),"Root heap");
    heapRow(word(SUSAMUNE_MEM1_ADDR(0x80409828u,0x8040e290u,0x80405968u)),"System heap");
    heapRow(reinterpret_cast<unsigned>(gpApplication.mCurrentHeap),"Stage heap");
    heapRow(word(SUSAMUNE_MEM1_ADDR(0x80409cc0u,0x8040e690u,0x80405d68u)),"Audio MEM1 heap");
    OSRestoreInterrupts(interrupts);
    unsigned states[6]={};
    if(memoryTelemetryStates(states)) {
        Row *row=add(5,0,0,states[0],"Savestate pool");if(row){row->used=states[5];row->flags=states[1];}
        for(unsigned i=0;i<3;++i){row=add(6,i+1,0,states[2+i],"Savestate slot");if(row)row->used=states[2+i];}
    }
    unsigned ghosts[4]={};
    if(memoryTelemetryGhosts(ghosts))for(unsigned i=0;i<2;++i){Row *row=add(7,i,0,ghosts[i*2]+ghosts[i*2+1],"Ghost payload");if(row){row->used=ghosts[i*2];row->flags=ghosts[i*2+1];}}
    rows[0].bytes=count;phase=3;resume();
}
}
void cancel(){resume();phase=0;count=cursor=0;}
bool receive(LiveRaceSession::Session &session,const void *data,unsigned bytes) {
    const unsigned char *body=static_cast<const unsigned char *>(data);
    if(bytes!=16 || MSRRead32(body)!=0x4d4d5131u)return false;
    if(!session.info.connected || session.info.host || strcmp(session.info.remoteName,"Memory monitor"))return true;
    const unsigned id=MSRRead32(body+4), operation=MSRRead32(body+8);
    if(!id || MSRRead32(body+12) || operation<1 || operation>2 || id==lastRequest)return true;
    lastRequest=id;
    if(operation==2){cancel();return true;}
    if(phase)return true;
    request=id;started=session.nowMs;phase=1;return true;
}
void poll(unsigned now) {
    if(!phase)return;
    if(now-started>30000u){cancel();return;}
    if(phase==1) {
        const TMarDirector *director=RetailInput::stageDirector();
        if(!PracticeSession::available() || PracticeSession::pausePending() ||
           !director || !director->_260){failure(1);return;}
        if(!PracticeSession::manualPaused() && !PracticeSession::nativePaused()) {
            if(!PracticeSession::requestPauseToggle(false)){failure(2);return;}
            ownPause=true;
        }
        phase=2;return;
    }
    if(phase==2) {
        if(PracticeSession::pausePending()){if(now-started>5000)failure(3);return;}
        if(!PracticeSession::manualPaused() && !PracticeSession::nativePaused()){failure(4);return;}
        capture(now);
    }
}
bool send(LiveRaceSession::Session &session,unsigned) {
    if(!phase)return false;
    if(!session.info.connected){cancel();return false;}
    if(phase!=3 || session.info.pending)return true;
    if(cursor==count){phase=0;return false;}
    unsigned char body[64];MSRWrite32(body,0x4d4d4431u);MSRWrite32(body+4,request);
    MSRWrite32(body+8,cursor);MSRWrite32(body+12,count);
    const Row &row=rows[cursor];const unsigned *words=&row.kind;
    for(unsigned i=0;i<8;++i)MSRWrite32(body+16+i*4,words[i]);
    memcpy(body+48,row.name,16);
    if(LiveRaceSession::sendReliable(session,MSR_READY,body,sizeof(body),session.nowMs))++cursor;
    return true;
}
}
#endif
