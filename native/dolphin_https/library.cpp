#include "susamune/dolphin_ghost_library.hxx"
#if IS_EMULATOR && TIMEWARP_LIVE_RACING
extern "C" {
#include <string.h>
}
namespace NativeStorage { extern unsigned region; }
#include "susamune/dolphin_files.hxx"
#include "susamune/dolphin_entropy.hxx"
#include "susamune/dolphin_web_api.h"
namespace Ghost { bool inspectFile(const void *,u32,SusamuneGhostFileHeader *); }
namespace DolphinGhostLibrary {
namespace {
enum Phase {IDLE,LIST,SCAN,READ,REMOVE,CREATE,BLANK,BODY,COMMIT,VERIFY,CLEANUP,DONE};
struct Work {
    DolphinFiles::Entry files[127];SusamuneGhostCatalogPage page;
    SusamuneGhostStorageRequest request;SusamuneGhostStorageResponse response;
    SusamuneGhostFileHeader header,check;char file[32],leaf[SUSAMUNE_GHOST_IMPORT_LEAF_SIZE];
    u32 ticket,count,scan,bytes;Phase phase;bool created;
};
Work &s=*reinterpret_cast<Work *>(DOLPHIN_LIBRARY_WORK_BASE);
static_assert(sizeof(Work)<=0x8000u,"Native ghost library work overflow");
bool initialized;
void *payload(){return reinterpret_cast<void *>(SUSAMUNE_DOLPHIN_GHOST_FILE_TRANSFER_PPC_BASE);}
void finish(int error) {
    auto &r=s.response;r={};r.responseMagic=SUSAMUNE_GHOST_STORAGE_MAGIC;
    r.protocolVersion=SUSAMUNE_GHOST_STORAGE_VERSION;r.flags=SUSAMUNE_GHOST_RESPONSE_READY;
    r.ackSeq=s.request.requestSeq;r.status=error;r.profile=s.request.profile;r.slot=s.request.slot;
    if(!error && (s.request.command==SUSAMUNE_GHOST_CMD_LIST || s.request.command==SUSAMUNE_GHOST_CMD_IMPORT_SCAN)){
        memcpy(payload(),&s.page,sizeof(s.page));r.payloadSize=sizeof(s.page);r.slot=0;r.slotCount=s.page.count;
    }else if(!error){r.generation=s.header.fileChecksum?s.header.fileChecksum:1;
        if(s.request.command==SUSAMUNE_GHOST_CMD_LOAD)r.payloadSize=s.bytes;
        if(s.request.command==SUSAMUNE_GHOST_CMD_SAVE)r.slot=0;
    }
    s.phase=DONE;
}
bool imported(){return s.request.profile==SUSAMUNE_GHOST_IMPORTED_PROFILE;}
bool nameMatches(const char *name) {
    if(imported())return !memcmp(name,"ms_import_",10);
    return !memcmp(name,"ms_p",4) && name[4]=='0'+s.request.profile && name[5]=='_';
}
bool leafName() {
    u32 n=0;while(n<sizeof(s.leaf) && s.leaf[n])++n;
    if(n<=9 || n-9>=sizeof(s.file) || memcmp(s.leaf+n-9,".smsghost",9))return false;
    memset(s.file,0,sizeof(s.file));memcpy(s.file,s.leaf,n-9);
    if(!nameMatches(s.file))return false;
    for(u32 i=0;i<n-9;++i)if(!((s.file[i]>='a'&&s.file[i]<='z') || (s.file[i]>='0'&&s.file[i]<='9') || s.file[i]=='_'))return false;
    return true;
}
bool describe(SusamuneGhostSlotInfo *info) {
    const auto *api=reinterpret_cast<const DolphinWebApi *>(DOLPHIN_WEB_API_BASE);
    if(api->magic!=DOLPHIN_WEB_API_MAGIC || api->version!=3 || api->apiBytes!=sizeof(*api))return false;
    const u32 address=reinterpret_cast<u32>(api->describe);
    if(address&3 || address<DOLPHIN_WEB_API_BASE+sizeof(*api) || address>=DOLPHIN_HTTPS_IMAGE_BASE+DOLPHIN_HTTPS_IMAGE_CAPACITY)return false;
    if(s.header.fileSize<256 || s.header.fileSize>s.files[s.scan].bytes || s.header.fileSize>SUSAMUNE_GHOST_MAX_FILE_SIZE)return false;
    if(!api->describe(&s.header,s.header.fileSize,s.request.profile,NativeStorage::region,imported(),info))return false;
    if(!info->generation)info->generation=1;return true;
}
void ioError(int error) {
    const int code=error==-7?SUSAMUNE_GHOST_STATUS_SLOT_OCCUPIED:
        error==-8 || error==-9 || error==-11?SUSAMUNE_GHOST_STATUS_QUOTA_EXCEEDED:SUSAMUNE_GHOST_STATUS_IO(1);
    if(s.created){s.response.status=code;s.phase=CLEANUP;}else finish(code);
}
}
bool ready(){return DolphinFiles::available();}
bool begin(const SusamuneGhostStorageRequest &request) {
    if(!initialized){memset(&s,0,sizeof(s));initialized=true;}
    if(!ready() || s.phase!=IDLE)return false;
    memset(&s,0,sizeof(s));s.request=request;
    if(request.requestMagic!=SUSAMUNE_GHOST_STORAGE_MAGIC || request.protocolVersion!=SUSAMUNE_GHOST_STORAGE_VERSION ||
        (!imported() && !SusamuneGhostPersonalProfile(request.profile))){finish(SUSAMUNE_GHOST_STATUS_INVALID_REQUEST);return true;}
    if(request.command==SUSAMUNE_GHOST_CMD_SAVE){
        if(request.slot!=SUSAMUNE_GHOST_SLOT_AUTO || !Ghost::inspectFile(payload(),request.payloadSize,&s.header) ||
            (!imported() && s.header.sourceProfile!=request.profile)){finish(SUSAMUNE_GHOST_STATUS_INVALID_FILE);return true;}
        static const char hex[]="0123456789abcdef";
        if(imported()){
            const auto *api=DolphinHttps::api();
            if(!api){finish(SUSAMUNE_GHOST_STATUS_STORAGE_UNAVAILABLE);return true;}
            u8 digest[32];api->sha256(payload(),request.payloadSize,digest);
            memcpy(s.file,"ms_import_",10);
            for(u32 i=0;i<8;++i){s.file[10+i*2]=hex[digest[i]>>4];s.file[11+i*2]=hex[digest[i]&15];}
        }else{
            memcpy(s.file,"ms_p0_",6);s.file[4]='0'+request.profile;
            const u32 id[2]={s.header.ghostIdHi,s.header.ghostIdLo};
            for(u32 n=0;n<16;++n)s.file[6+n]=hex[(id[n/8]>>(28-(n%8)*4))&15];
        }
        s.bytes=request.payloadSize;s.phase=CREATE;return true;
    }
    if(request.command==SUSAMUNE_GHOST_CMD_LOAD || request.command==SUSAMUNE_GHOST_CMD_DELETE){
        if(imported()){
            if(request.payloadSize!=sizeof(s.leaf)){finish(SUSAMUNE_GHOST_STATUS_INVALID_REQUEST);return true;}
            memcpy(s.leaf,payload(),sizeof(s.leaf));
            if(!leafName()){finish(SUSAMUNE_GHOST_STATUS_INVALID_REQUEST);return true;}
        }
    }else if(request.command!=SUSAMUNE_GHOST_CMD_LIST && request.command!=SUSAMUNE_GHOST_CMD_IMPORT_SCAN){finish(SUSAMUNE_GHOST_STATUS_INVALID_REQUEST);return true;}
    s.phase=LIST;return true;
}
void update() {
    if(!initialized || s.phase==IDLE || s.phase==DONE)return;
    if(s.phase==SCAN && !s.ticket){
        while(s.scan<s.count && !nameMatches(s.files[s.scan].name))++s.scan;
        if(s.scan==s.count){
            if(s.request.command==SUSAMUNE_GHOST_CMD_LIST || s.request.command==SUSAMUNE_GHOST_CMD_IMPORT_SCAN)finish(0);
            else finish(SUSAMUNE_GHOST_STATUS_NOT_FOUND);
            return;
        }
        if(s.request.command==SUSAMUNE_GHOST_CMD_LOAD || s.request.command==SUSAMUNE_GHOST_CMD_DELETE){
            if(imported()?memcmp(s.file,s.files[s.scan].name,32)!=0:s.files[s.scan].index!=s.request.slot){++s.scan;return;}
        }
        memcpy(s.file,s.files[s.scan].name,32);
    }
    if(!s.ticket){
        if(s.phase==LIST)s.ticket=DolphinFiles::list(s.files,127);
        else if(s.phase==SCAN)s.ticket=DolphinFiles::read(s.file,&s.header,256);
        else if(s.phase==READ)s.ticket=DolphinFiles::read(s.file,payload(),s.bytes);
        else if(s.phase==REMOVE || s.phase==CLEANUP)s.ticket=DolphinFiles::remove(s.file);
        else if(s.phase==CREATE)s.ticket=DolphinFiles::create(s.file,(s.bytes+8191)&~8191u);
        else if(s.phase==BLANK){memset(&s.check,0,256);s.ticket=DolphinFiles::write(s.file,&s.check,256);}
        else if(s.phase==BODY)s.ticket=DolphinFiles::write(s.file,static_cast<u8 *>(payload())+256,s.bytes-256,256);
        else if(s.phase==COMMIT)s.ticket=DolphinFiles::write(s.file,&s.header,256);
        else if(s.phase==VERIFY)s.ticket=DolphinFiles::read(s.file,&s.check,256);
        return;
    }
    DolphinFiles::Result result;if(!DolphinFiles::take(s.ticket,&result))return;s.ticket=0;
    if(s.phase==CLEANUP){finish(s.response.status);return;}
    if(result.error){ioError(result.error);return;}
    if(s.phase==LIST){
        s.count=result.bytes;s.phase=SCAN;s.page.magic=SUSAMUNE_GHOST_CATALOG_PAGE_MAGIC;
        s.page.version=SUSAMUNE_GHOST_CATALOG_PAGE_VERSION;s.page.first=s.request.slot;return;
    }
    if(s.phase==SCAN){
        SusamuneGhostSlotInfo info;
        if(!describe(&info)){
            if(s.request.command==SUSAMUNE_GHOST_CMD_LOAD || s.request.command==SUSAMUNE_GHOST_CMD_DELETE)finish(SUSAMUNE_GHOST_STATUS_INVALID_FILE);
            else ++s.scan;
            return;
        }
        if(s.request.command==SUSAMUNE_GHOST_CMD_LOAD || s.request.command==SUSAMUNE_GHOST_CMD_DELETE){
            if(info.generation!=s.request.expectedGeneration){finish(SUSAMUNE_GHOST_STATUS_SLOT_UNSAFE);return;}
            s.bytes=s.header.fileSize;s.phase=s.request.command==SUSAMUNE_GHOST_CMD_LOAD?READ:REMOVE;return;
        }
        auto &page=s.page;const u32 row=page.totalCount++;
        u64 duration=(u64(page.totalDurationQfHi)<<32)|page.totalDurationQfLo;duration+=info.durationQf;
        page.totalDurationQfHi=u32(duration>>32);page.totalDurationQfLo=u32(duration);
        if(row>=page.first && page.count<SUSAMUNE_GHOST_CATALOG_PAGE_ENTRIES){
            auto &entry=page.entries[page.count++];entry.id=s.files[s.scan].index;entry.info=info;
            if(imported()){u32 n=0;while(n<31 && s.file[n]){entry.leaf[n]=s.file[n];++n;}memcpy(entry.leaf+n,".smsghost",10);}
        }
        ++s.scan;return;
    }
    if(s.phase==READ){
        if(!Ghost::inspectFile(payload(),s.bytes,&s.check) || s.check.fileChecksum!=s.header.fileChecksum){finish(SUSAMUNE_GHOST_STATUS_INVALID_FILE);return;}
        finish(0);return;
    }
    if(s.phase==REMOVE){finish(0);return;}
    if(s.phase==CREATE){s.created=true;s.phase=BLANK;}
    else if(s.phase==BLANK)s.phase=BODY;
    else if(s.phase==BODY)s.phase=COMMIT;
    else if(s.phase==COMMIT)s.phase=VERIFY;
    else if(s.phase==VERIFY){
        if(memcmp(&s.header,&s.check,256))ioError(-5);else finish(0);
    }
}
bool take(SusamuneGhostStorageResponse *out) {
    if(!initialized || s.phase!=DONE || !out)return false;
    *out=s.response;s.phase=IDLE;return true;
}
}
#endif
