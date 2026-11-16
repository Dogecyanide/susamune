#include "susamune/dolphin_files.hxx"
#if IS_EMULATOR
#include <Dolphin/CARD.h>
#include <Dolphin/mem.h>
#include "susamune/dolphin_card.hxx"
#include "susamune/addresses.hxx"
#include "susamune/dolphin_https.h"

namespace DolphinFiles {
namespace {
enum Op { NONE, READ, WRITE, CREATE, REMOVE, LIST };
struct Work {
    char name[32];
    void *data;
    u32 bytes,offset,progress,ticket,sequence;
    Op op;
    Result result;
    bool complete;
};
constexpr u32 kBase=DOLPHIN_FILES_WORK_BASE;
static_assert(kBase+sizeof(Work)<=DOLPHIN_ENTROPY_WORK_BASE,"Dolphin file control overlaps Japanese assets");
Work &s=*reinterpret_cast<Work *>(kBase);
bool initialized;
bool nameValid(const char *name) {
    if(!name || name[0]!='m' || name[1]!='s' || name[2]!='_')return false;
    for(u32 i=3;i<32;++i){
        const unsigned char c=name[i];
        if(!c)return i>3;
        if(!((c>='a' && c<='z') || (c>='0' && c<='9') || c=='_'))return false;
    }
    return false;
}
u32 request(Op op,const char *name,void *data,u32 bytes,u32 offset) {
    if(!initialized || s.op!=NONE || (op!=LIST && !nameValid(name)) ||
       (op==LIST && (!data || !bytes || bytes>127)) ||
       ((op==READ || op==WRITE) && (!data || !bytes || offset>0x1000000u || bytes>0x1000000u-offset)) ||
       (op==CREATE && (!bytes || bytes>0x1000000u || (bytes&0x1fffu))))return 0;
    if(s.sequence==0xffffffffu)return 0;
    const u32 sequence=s.sequence+1;
    memset(&s,0,sizeof(s));s.sequence=s.ticket=sequence;s.op=op;s.data=data;s.bytes=bytes;s.offset=offset;
    if(name)for(u32 i=0;i<32 && (s.name[i]=name[i]);++i){}
    return s.ticket;
}
}
void init(){if(initialized)return;memset(&s,0,sizeof(s));initialized=true;}
bool available(){return initialized && s.sequence!=0xffffffffu;}
bool pending(){return initialized && s.op!=NONE && !s.complete;}
u32 read(const char *name,void *out,u32 bytes,u32 offset){return request(READ,name,out,bytes,offset);}
u32 write(const char *name,const void *data,u32 bytes,u32 offset){return request(WRITE,name,const_cast<void *>(data),bytes,offset);}
u32 create(const char *name,u32 bytes){return request(CREATE,name,nullptr,bytes,0);}
u32 remove(const char *name){return request(REMOVE,name,nullptr,0,0);}
u32 list(Entry *out,u32 capacity){return request(LIST,nullptr,out,capacity,0);}
bool take(u32 ticket,Result *out){
    if(!initialized || !ticket || ticket!=s.ticket || s.op==NONE || !s.complete || !out)return false;
    *out=s.result;s.op=NONE;s.data=nullptr;return true;
}
void fail(s32 error){if(pending()){s.result.error=error;s.complete=true;}}
void perform(void *sector) {
    if(!pending())return;
    if(!sector || (reinterpret_cast<__UINTPTR_TYPE__>(sector)&31)){fail(CARD_ERROR_FATAL_ERROR);return;}
    s32 error=CARD_ERROR_READY;
    if(s.op==LIST){
        Entry *entries=static_cast<Entry *>(s.data);u32 count=0;
        for(u32 i=0;i<127 && count<s.bytes;++i){
            CARDStat stat;
            error=CARDGetStatus(CARD_SLOTB,i,&stat);
            if(error==CARD_ERROR_NOFILE || error==CARD_ERROR_NOPERM){error=CARD_ERROR_READY;continue;}
            if(error)break;
            const char region=SUSAMUNE_GAME_VERSION==1?'J':SUSAMUNE_GAME_VERSION==2?'E':'P';
            const u32 game=0x474d5300u|u32(region);
            if(stat.mGameCode!=game || stat.mCompany!=0x5355 || !nameValid(stat.mFilename))continue;
            memcpy(entries[count].name,stat.mFilename,32);entries[count].bytes=stat.mLength;entries[count].index=i;++count;
        }
        s.result.bytes=count;s.complete=true;
    }else if(s.op==REMOVE){error=DolphinCard::remove(s.name);s.complete=true;}
    else {
        CARDFileInfo file;
        error=s.op==CREATE?CARDCreate(CARD_SLOTB,s.name,s.bytes,&file):CARDOpen(CARD_SLOTB,s.name,&file);
        if(!error){
            CARDStat stat;
            if(s.op!=CREATE)error=CARDGetStatus(CARD_SLOTB,file.mFileNo,&stat);
            if(s.op==CREATE){s.result.bytes=s.bytes;s.complete=true;}
            else if(!error && (!stat.mLength || (stat.mLength&0x1fffu) ||
                    s.offset>stat.mLength || s.bytes>stat.mLength-s.offset))error=CARD_ERROR_LIMIT;
            if(!error && s.op!=CREATE) {
                const u32 at=s.offset+s.progress,base=at&~0x1fffu,within=at-base;
                u32 count=s.bytes-s.progress;if(count>0x2000u-within)count=0x2000u-within;
                // CARD DMA always uses the borrowed aligned MEM1 sector.
                error=s.op==WRITE && !within && count==0x2000?0:CARDRead(&file,sector,0x2000,base);
                if(!error){
                    if(s.op==READ)memcpy(static_cast<u8 *>(s.data)+s.progress,static_cast<u8 *>(sector)+within,count);
                    else {
                        memcpy(static_cast<u8 *>(sector)+within,static_cast<u8 *>(s.data)+s.progress,count);
                        error=CARDWrite(&file,sector,0x2000,base);
                    }
                    if(!error){s.progress+=count;s.result.bytes=s.progress;s.complete=s.progress==s.bytes;}
                }
            }
            const s32 closed=CARDClose(&file);if(!error)error=closed;
        }
    }
    if(error)s.complete=true;
    s.result.error=error;
}
}
#endif
