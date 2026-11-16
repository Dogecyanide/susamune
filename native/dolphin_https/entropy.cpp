#include "susamune/dolphin_entropy.hxx"
#include "susamune/dolphin_storage_api.hxx"
#include "susamune/ghost_service.h"
extern "C" {
#include <string.h>
}
namespace NativeStorage {extern unsigned region;}
namespace DolphinEntropy {
namespace {
struct Record {u32 magic,version,generation,region;u8 seed[32],hash[16];};
static_assert(sizeof(Record)==64,"seed file header");
enum Phase {IDLE,READ_FIRST,READ_SECOND,WRITE_NEXT,VERIFY_NEXT,READY,FAILED};
struct Work {Record records[2],next,check;u8 entropy[32];u32 ticket,target;Phase phase;};
static_assert(DOLPHIN_ENTROPY_WORK_BASE+sizeof(Work)<=DOLPHIN_HTTPS_CONTROL_BASE,"seed workspace");
Work &s=*reinterpret_cast<Work *>(DOLPHIN_ENTROPY_WORK_BASE);
bool initialized;
const char name[]="ms_tls_seed";
void fail(){memset(&s,0,sizeof(s));s.phase=FAILED;}
bool valid(const Record &r) {
    u8 hash[32];const auto *api=DolphinHttps::api();if(!api)return false;
    api->sha256(&r,48,hash);
    return r.magic==0x4d535345u && r.version==1 && r.generation && r.generation<0xfffffffeu &&
        r.region==NativeStorage::region && !memcmp(r.hash,hash,16);
}
}
bool begin() {
    if(!initialized){memset(&s,0,sizeof(s));initialized=true;}
    if(s.phase!=IDLE)return false;
    if(!DolphinHttps::api() || !DolphinFiles::available()){fail();return true;}
    s.phase=READ_FIRST;return true;
}
void update() {
    if(!initialized || s.phase==IDLE || s.phase==READY || s.phase==FAILED)return;
    if(!s.ticket){
        if(s.phase==READ_FIRST || s.phase==READ_SECOND){
            const u32 index=s.phase==READ_SECOND;
            s.ticket=DolphinFiles::read(name,&s.records[index],sizeof(Record),index*8192);
        }else if(s.phase==WRITE_NEXT)s.ticket=DolphinFiles::write(name,&s.next,sizeof(Record),s.target*8192);
        else s.ticket=DolphinFiles::read(name,&s.check,sizeof(Record),s.target*8192);
        return;
    }
    DolphinFiles::Result result;if(!DolphinFiles::take(s.ticket,&result))return;
    s.ticket=0;if(result.error || result.bytes!=sizeof(Record)){fail();return;}
    if(s.phase==READ_FIRST){s.phase=READ_SECOND;return;}
    const auto *api=DolphinHttps::api();if(!api){fail();return;}
    if(s.phase==READ_SECOND){
        // A damaged copy must not silently roll the TLS random stream backwards.
        if(!valid(s.records[0]) || !valid(s.records[1])){fail();return;}
        const u32 newer=s.records[1].generation>s.records[0].generation;
        const Record &current=s.records[newer],&older=s.records[newer^1];
        u8 next[32],unused[32];api->derive(older.seed,next,unused);
        if(current.generation!=older.generation+1 || memcmp(current.seed,next,32)){
            memset(next,0,32);memset(unused,0,32);fail();return;
        }
        memset(next,0,32);memset(unused,0,32);
        s.target=newer^1;s.next=current;++s.next.generation;
        api->derive(current.seed,s.next.seed,s.entropy);
        u8 hash[32];api->sha256(&s.next,48,hash);memcpy(s.next.hash,hash,16);
        s.phase=WRITE_NEXT;
    }else if(s.phase==WRITE_NEXT)s.phase=VERIFY_NEXT;
    else {
        if(memcmp(&s.check,&s.next,sizeof(Record))){fail();return;}
        memset(s.records,0,sizeof(s.records));memset(&s.next,0,sizeof(s.next));memset(&s.check,0,sizeof(s.check));
        s.phase=READY;
    }
}
int take(void *out) {
    if(!initialized || s.phase==IDLE || !out)return GHOST_SERVICE_RANDOM;
    if(s.phase==FAILED){memset(&s,0,sizeof(s));return GHOST_SERVICE_RANDOM;}
    if(s.phase!=READY)return 1;
    memcpy(out,s.entropy,32);memset(&s,0,sizeof(s));return 0;
}
}
