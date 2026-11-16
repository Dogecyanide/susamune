#include "susamune/dolphin_archive.hxx"
#include "susamune/state_storage.h"
#include "susamune/state_pool_memory.h"
extern "C" {
#include <string.h>
void MoonshineNativeInit(void);
}
namespace {
constexpr unsigned kSector=8192;
struct Counters { unsigned magic,version,generation,state,project,reserved[10],checksum; };
static_assert(sizeof(Counters)==64,"Archive ID journal layout");
struct ProjectRecord { unsigned magic,version,id,generation,state,reserved[2],checksum; SusamuneTasManifest manifest; };
static_assert(sizeof(ProjectRecord)==192,"Native project journal");
enum Phase {IDLE,START,LIST,SCAN,HEADER,METADATA,PAYLOAD,NAMES0,NAMES1,NAMEWRITE,NAMEVERIFY,
    CREATE,BLANK,COMMIT,VERIFY,CLEANUP,REMOVE,COUNTERS0,COUNTERS1,COUNTERCREATE,COUNTERBLANK,COUNTERWRITE,COUNTERVERIFY,PROJECT0,PROJECT1,PROJECTCREATE,PROJECTBLANK,PROJECTWRITE,PROJECTVERIFY,PROJECTPART,PROJECTCLEAN,PROJECTREMOVE,PROJECTFINAL};
struct Work {
    const DolphinStorageHost *host;
    SusamuneStateStorageMailbox *mailbox;
    StatePoolMemory memory;
    SusamuneStateRequest request;
    SusamuneTasRequest context;
    SusamuneStateArchiveHeader header,check;
    DolphinFiles::Entry files[127];
    Counters counters[2],counterNext,counterCheck;
    SusamuneStateNameRecord names[2],nameNext,nameCheck;
    ProjectRecord projects[2],projectNext,projectCheck;
    SusamuneTasManifest project;
    char projectFile[32];
    unsigned projectId,projectBank,part,cleanIndex;
    bool projectChecked,verifyParts;
    unsigned char buffer[2*SUSAMUNE_STATE_CHUNK_SIZE];
    char filename[32],name[32];
    unsigned game,config,ack,id,scan,count,offset,crc,nameBase,nameBank,counterBank;
    u32 ticket,ioSize;void *ioData;
    Phase phase;unsigned status;
    bool initialized,created,countersLoaded,countersExist,countersBroken;
};
Work s;
static_assert(sizeof(Work)<0xC000,"Archive work exceeds native BSS allowance");
const char kCounters[]="ms_archive_ids";
bool zero(const void *data,unsigned n){const auto *p=static_cast<const unsigned char *>(data);while(n--)if(*p++)return false;return true;}
void filename(unsigned id,char *out){memcpy(out,"ms_state_",9);out[17]=0;for(int i=16;i>=9;--i){out[i]='0'+id%10;id/=10;}}
unsigned fileId(const char *name){
    if(memcmp(name,"ms_state_",9) || name[17])return 0;
    unsigned id=0;for(unsigned i=9;i<17;++i){if(name[i]<'0'||name[i]>'9')return 0;id=id*10+name[i]-'0';}return id;
}
unsigned totalSize(){return sizeof(s.header)+s.header.metadataSize+s.header.packedSize;}
unsigned allocation(){return ((totalSize()+kSector-1)&~(kSector-1))+2*kSector;}
void finish(unsigned status){
    auto &m=*s.mailbox;m.receipt={};auto &r=m.receipt;
    r.session=s.request.session;r.command=s.request.command;r.id=s.request.id;r.seq=s.request.seq;
    if(!status && (s.request.command==SUSAMUNE_STATE_CMD_TAS_READ || s.request.command==SUSAMUNE_STATE_CMD_TAS_COMMIT || s.request.command==SUSAMUNE_STATE_CMD_TAS_RENAME)){
        m.tasProject=s.project;r.headerCrc=s.project.checksum;
    }
    if(!status && s.request.command<SUSAMUNE_STATE_CMD_TAS_BEGIN && s.request.command!=SUSAMUNE_STATE_CMD_CATALOG && s.request.command!=SUSAMUNE_STATE_CMD_CANCEL){
        m.header=s.header;memcpy(m.resultName,s.name,32);
        r.metadataSize=s.header.metadataSize;r.packedSize=s.header.packedSize;r.headerCrc=s.header.headerCrc;r.reserved=SusamuneStateCrc(s.name,32);
        if(s.request.command==SUSAMUNE_STATE_CMD_READ_WINDOW){m.window={};m.window.offset=s.request.poolOffset;m.window.size=s.offset;m.window.checksum=~s.crc;}
    }
    m.response.status=status;m.response.resultId=s.id;m.response.transferred=s.offset;m.response.ackSeq=s.ack=s.request.seq;
    s.phase=IDLE;s.created=false;
}
void fail(unsigned status){if(s.created){s.status=status;s.phase=CLEANUP;}else finish(status);}
unsigned ioError(int error){return error==-4?SUSAMUNE_STATE_NOT_FOUND:error==-8||error==-9||error==-11?SUSAMUNE_STATE_FULL:SUSAMUNE_STATE_IO_ERROR;}
bool validHeader(){
    return SusamuneStateHeaderValidCapacity(&s.header,StatePoolMemoryCapacity(&s.memory)) &&
        s.header.gameId==s.game && totalSize()<=0x1000000u-2*kSector;
}
void startNames(){s.nameBase=(totalSize()+kSector-1)&~(kSector-1);memcpy(s.name,s.header.name,32);s.names[0]={};s.names[1]={};s.phase=NAMES0;}
bool nameValid(const SusamuneStateNameRecord &n){return n.magic==SUSAMUNE_STATE_NAME_MAGIC && n.version==1 && n.archiveId==s.id && n.generation &&
    n.archiveChecksum==s.header.headerCrc && !n.reserved[0] && !n.reserved[1] && SusamuneStateNameValid(n.name) && n.name[0] && n.checksum==SusamuneStateNameCrc(&n);}
void namesDone(){
    const bool a=nameValid(s.names[0]),b=nameValid(s.names[1]);
    s.nameBank=b && (!a || s.names[1].generation>s.names[0].generation)?1:0;
    const unsigned generation=a||b?s.names[s.nameBank].generation:0;
    if(generation)memcpy(s.name,s.names[s.nameBank].name,32);
    if(s.request.command==SUSAMUNE_STATE_CMD_RENAME){
        if(generation==0xffffffffu){finish(SUSAMUNE_STATE_FULL);return;}
        s.nameNext={};auto &n=s.nameNext;n.magic=SUSAMUNE_STATE_NAME_MAGIC;n.version=1;n.archiveId=s.id;n.generation=generation+1;
        n.archiveChecksum=s.header.headerCrc;memcpy(n.name,s.mailbox->requestName,32);n.checksum=SusamuneStateNameCrc(&n);s.phase=NAMEWRITE;
    }else if(s.request.command==SUSAMUNE_STATE_CMD_DELETE)s.phase=REMOVE;
    else if(s.request.command==SUSAMUNE_STATE_CMD_CATALOG){
        auto &c=s.mailbox->catalog;auto &e=c.entries[c.count++];e.id=s.id;e.packedSize=s.header.packedSize;e.metadataSize=s.header.metadataSize;
        e.rawSize=s.header.rawSize;e.gameId=s.header.gameId;e.buildCrc=s.header.buildCrc;e.headerCrc=s.header.headerCrc;e.sceneKey=s.header.sceneKey;memcpy(e.name,s.name,32);
        c.nextId=s.id;++s.scan;s.phase=SCAN;
    }else finish(0);
}
bool counterValid(const Counters &c){return c.magic==0x4d414944u && c.version==1 && c.generation && c.state<=SUSAMUNE_STATE_MAX_ARCHIVE_ID &&
    c.project<=SUSAMUNE_STATE_MAX_ARCHIVE_ID && zero(c.reserved,sizeof(c.reserved)) && c.checksum==SusamuneStateCrc(&c,60);}
void countersDone(){
    const bool a=counterValid(s.counters[0]),b=counterValid(s.counters[1]);
    if(a&&b){s.counterBank=s.counters[1].generation>s.counters[0].generation?1:0;s.countersBroken=s.counters[s.counterBank].generation-s.counters[1-s.counterBank].generation!=1;}
    else if(a||b){s.counterBank=b?1:0;s.countersBroken=s.counters[s.counterBank].generation!=1 || !zero(&s.counters[1-s.counterBank],64);}
    else s.countersBroken=true;
    s.countersLoaded=true;s.phase=START;
}
unsigned projectFileId(const char *name);
unsigned partFileId(const char *name);
void projectName(unsigned id,char *out);
void archiveName(unsigned id,char *out);
void allocateId(){
    if(s.countersBroken){finish(SUSAMUNE_STATE_BAD_FILE);return;}
    const bool project=s.request.command==SUSAMUNE_STATE_CMD_TAS_BEGIN;
    auto &old=s.counters[s.counterBank];unsigned id=project?old.project:old.state;
    // Imported project components also reserve IDs after a fresh install.
    for(unsigned i=0;i<s.count;++i){
        unsigned v=project?projectFileId(s.files[i].name):fileId(s.files[i].name);
        if(!project){unsigned part=partFileId(s.files[i].name);if(part>v)v=part;}
        if(v>id)id=v;
    }
    if(id>=SUSAMUNE_STATE_MAX_ARCHIVE_ID || old.generation==0xffffffffu){finish(SUSAMUNE_STATE_FULL);return;}
    s.id=id+1;s.counterNext=old;auto &n=s.counterNext;n.magic=0x4d414944u;n.version=1;n.generation=old.generation+1;if(project)n.project=s.id;else n.state=s.id;n.checksum=SusamuneStateCrc(&n,60);
    if(project){s.projectId=s.id;projectName(s.projectId,s.projectFile);memcpy(s.filename,s.projectFile,32);}
    else archiveName(s.id,s.filename);s.phase=s.countersExist?COUNTERWRITE:COUNTERCREATE;
}
#include "archive_tas.inc"
void start(){
    auto &r=s.request;
    if(!r.seq || !r.session || !SusamuneTasRequestValid(&s.context) ||
       (r.reserved && r.command!=SUSAMUNE_STATE_CMD_READ_WINDOW)){finish(SUSAMUNE_STATE_BAD_REQUEST);return;}
    if(!s.projectChecked && (s.context.projectId || r.command>=SUSAMUNE_STATE_CMD_TAS_BEGIN)){projectStart();return;}
    if(r.command==SUSAMUNE_STATE_CMD_CANCEL){finish(SUSAMUNE_STATE_CANCELLED);return;}
    if(r.command==SUSAMUNE_STATE_CMD_CATALOG){
        if(r.id>SUSAMUNE_STATE_MAX_ARCHIVE_ID){finish(SUSAMUNE_STATE_BAD_REQUEST);return;}
        s.mailbox->catalog={};s.mailbox->catalog.afterId=s.mailbox->catalog.nextId=r.id;s.phase=LIST;return;
    }
    if(r.command==SUSAMUNE_STATE_CMD_EXPORT){
        s.header=s.mailbox->header;
        if(!validHeader() || s.header.configId!=s.config || !transferHeaderValid() ||
           s.header.packedSize!=r.packedSize || !StatePoolMemoryRangeValid(&s.memory,r.poolOffset,r.packedSize) ||
           SusamuneStateCrc(s.mailbox->metadata,s.header.metadataSize)!=s.header.metadataCrc || !tapeMetadataValid(false)){finish(SUSAMUNE_STATE_BAD_REQUEST);return;}
        if(!s.countersLoaded){s.phase=COUNTERS0;return;}
        s.phase=LIST;return;
    }
    if(r.command<SUSAMUNE_STATE_CMD_IMPORT || r.command>SUSAMUNE_STATE_CMD_READ_WINDOW || !r.id || r.id>SUSAMUNE_STATE_MAX_ARCHIVE_ID){finish(SUSAMUNE_STATE_BAD_REQUEST);return;}
    if(r.command==SUSAMUNE_STATE_CMD_READ_WINDOW && !SusamuneStateWindowRange(r.packedSize,r.poolOffset,r.reserved)){finish(SUSAMUNE_STATE_BAD_REQUEST);return;}
    if(r.command==SUSAMUNE_STATE_CMD_IMPORT && !SusamuneStateImportRange(r.poolOffset,r.packedSize)){finish(SUSAMUNE_STATE_BAD_REQUEST);return;}
    if(r.command==SUSAMUNE_STATE_CMD_RENAME && (!SusamuneStateNameValid(s.mailbox->requestName) || !s.mailbox->requestName[0])){finish(SUSAMUNE_STATE_BAD_REQUEST);return;}
    s.id=r.id;archiveName(s.id,s.filename);s.phase=HEADER;
}
void scan(){
    auto &c=s.mailbox->catalog;
    while(s.scan<s.count && (!fileId(s.files[s.scan].name) || fileId(s.files[s.scan].name)<=s.request.id))++s.scan;
    if(s.scan==s.count){finish(0);return;}
    if(c.count==SUSAMUNE_STATE_CATALOG_COUNT){c.more=1;finish(0);return;}
    s.id=fileId(s.files[s.scan].name);memcpy(s.filename,s.files[s.scan].name,32);s.phase=HEADER;
}
void initialize(const DolphinStorageHost *host,unsigned region){
    MoonshineNativeInit();if(s.initialized)return;
    if(!host || region<1 || region>3)return;
    memset(&s,0,sizeof(s));s.host=host;s.game=region==1?0x474d534au:region==2?0x474d5345u:0x474d5350u;s.config=0x444f4c30u+region;
    s.mailbox=reinterpret_cast<SusamuneStateStorageMailbox *>(SUSAMUNE_DOLPHIN_STATE_STORAGE_PPC_BASE);
    s.memory={};
    s.memory.banks[0]=reinterpret_cast<unsigned char *>(SUSAMUNE_DOLPHIN_SNAPSHOT_PPC_BASE);s.memory.sizes[0]=SUSAMUNE_STATE_POOL_SIZE;
    s.memory.banks[1]=reinterpret_cast<unsigned char *>(SUSAMUNE_DOLPHIN_STATE_POOL_EXTRA_PPC_BASE);s.memory.sizes[1]=SUSAMUNE_STATE_POOL_EXTRA_SIZE;
    memset(s.mailbox,0,sizeof(*s.mailbox));auto &r=s.mailbox->response;r.magic=SUSAMUNE_STATE_STORAGE_MAGIC;r.version=SUSAMUNE_STATE_STORAGE_VERSION;r.available=1;r.configId=s.config;
    s.counterBank=1;s.initialized=true;
}
void update(){
    if(!s.initialized)return;
    if(s.phase==IDLE){
        if(s.mailbox->request.seq==s.ack)return;
        s.request=s.mailbox->request;s.context=s.mailbox->tasRequest;s.id=s.offset=s.scan=s.count=0;s.crc=0xffffffffu;s.created=false;s.projectChecked=s.verifyParts=false;s.projectId=0;s.phase=START;
    }
    if(!s.ticket && s.phase!=CLEANUP && memcmp(&s.request,&s.mailbox->request,sizeof(s.request))){fail(SUSAMUNE_STATE_CANCELLED);return;}
    if(s.phase==START){start();return;}
    if(s.phase==SCAN){if(s.request.command==SUSAMUNE_STATE_CMD_TAS_CATALOG)projectScan();else scan();return;}
    if(s.phase==PROJECTPART){projectPart();return;}
    if(s.phase==PROJECTCLEAN){projectClean();return;}
    if(!s.ticket){
        if(s.phase>=PROJECT0){projectIo();return;}
        if(s.phase==LIST)s.ticket=s.host->list(s.files,127);
        else if(s.phase==HEADER)s.ticket=s.host->read(s.filename,&s.header,sizeof(s.header),0);
        else if(s.phase==CREATE)s.ticket=s.host->create(s.filename,allocation());
        else if(s.phase==BLANK){s.check={};s.ticket=s.host->write(s.filename,&s.check,sizeof(s.check),0);}
        else if(s.phase==METADATA)s.ticket=s.request.command==SUSAMUNE_STATE_CMD_EXPORT?
            s.host->write(s.filename,s.mailbox->metadata,s.header.metadataSize,sizeof(s.header)):s.host->read(s.filename,s.mailbox->metadata,s.header.metadataSize,sizeof(s.header));
        else if(s.phase==PAYLOAD){
            const bool window=s.request.command==SUSAMUNE_STATE_CMD_READ_WINDOW;
            unsigned size=(window?s.request.reserved:s.header.packedSize)-s.offset;if(size>sizeof(s.buffer))size=sizeof(s.buffer);
            unsigned at=sizeof(s.header)+s.header.metadataSize+s.offset+(window?s.request.poolOffset:0);
            if(s.request.command==SUSAMUNE_STATE_CMD_EXPORT){
                StatePoolMemorySpan span;
                if(s.context.projectId && s.context.role==SUSAMUNE_TAS_TAPE_ROLE){span.data=reinterpret_cast<unsigned char *>(SUSAMUNE_DOLPHIN_STATE_STAGING_PPC_BASE)+s.offset;span.size=size;}
                else if(!StatePoolMemorySpanAt(&s.memory,s.request.poolOffset+s.offset,size,&span) || !span.size){fail(SUSAMUNE_STATE_BAD_REQUEST);return;}
                s.ioData=span.data;s.ioSize=span.size;s.ticket=s.host->write(s.filename,span.data,span.size,at);
            }else{s.ioSize=size;s.ioData=s.buffer;s.ticket=s.host->read(s.filename,s.buffer,size,at);}
        }else if(s.phase==COMMIT)s.ticket=s.host->write(s.filename,&s.header,sizeof(s.header),0);
        else if(s.phase==VERIFY)s.ticket=s.host->read(s.filename,&s.check,sizeof(s.check),0);
        else if(s.phase==NAMES0 || s.phase==NAMES1){unsigned bank=s.phase==NAMES1;s.ticket=s.host->read(s.filename,&s.names[bank],64,s.nameBase+bank*kSector);}
        else if(s.phase==NAMEWRITE)s.ticket=s.host->write(s.filename,&s.nameNext,64,s.nameBase+(1-s.nameBank)*kSector);
        else if(s.phase==NAMEVERIFY)s.ticket=s.host->read(s.filename,&s.nameCheck,64,s.nameBase+(1-s.nameBank)*kSector);
        else if(s.phase==REMOVE || s.phase==CLEANUP)s.ticket=s.host->remove(s.filename);
        else if(s.phase==COUNTERS0 || s.phase==COUNTERS1){unsigned bank=s.phase==COUNTERS1;s.ticket=s.host->read(kCounters,&s.counters[bank],64,bank*kSector);}
        else if(s.phase==COUNTERCREATE)s.ticket=s.host->create(kCounters,2*kSector);
        else if(s.phase==COUNTERBLANK){s.counterCheck={};s.ticket=s.host->write(kCounters,&s.counterCheck,64,kSector);}
        else if(s.phase==COUNTERWRITE)s.ticket=s.host->write(kCounters,&s.counterNext,64,(1-s.counterBank)*kSector);
        else if(s.phase==COUNTERVERIFY)s.ticket=s.host->read(kCounters,&s.counterCheck,64,(1-s.counterBank)*kSector);
        return;
    }
    DolphinFiles::Result result;if(!s.host->fileTake(s.ticket,&result))return;s.ticket=0;
    if(s.phase==CLEANUP){finish(s.status);return;}
    if(s.phase==COUNTERS0 && result.error==-4){s.countersLoaded=true;s.countersExist=false;s.phase=START;return;}
    if(s.phase>=PROJECT0){projectResult(result);return;}
    if(result.error){
        if(s.phase>=COUNTERS0)s.countersBroken=true;
        if(s.request.command==SUSAMUNE_STATE_CMD_CATALOG && s.phase==HEADER){++s.scan;s.phase=SCAN;return;}
        fail(ioError(result.error));return;
    }
    if(s.phase==COUNTERS0){s.countersExist=true;s.phase=COUNTERS1;return;}
    if(s.phase==COUNTERS1){countersDone();return;}
    if(s.phase==COUNTERCREATE){s.countersExist=true;s.phase=COUNTERBLANK;return;}
    if(s.phase==COUNTERBLANK){s.phase=COUNTERWRITE;return;}
    if(s.phase==COUNTERWRITE){s.phase=COUNTERVERIFY;return;}
    if(s.phase==COUNTERVERIFY){
        if(memcmp(&s.counterNext,&s.counterCheck,64) || !counterValid(s.counterCheck)){s.countersBroken=true;finish(SUSAMUNE_STATE_IO_ERROR);return;}
        s.counterBank=1-s.counterBank;s.counters[s.counterBank]=s.counterNext;s.phase=s.request.command==SUSAMUNE_STATE_CMD_TAS_BEGIN?PROJECTCREATE:CREATE;return;
    }
    if(s.phase==LIST){
        s.count=result.bytes;
        if(s.request.command==SUSAMUNE_STATE_CMD_TAS_DELETE){s.cleanIndex=0;s.phase=PROJECTCLEAN;return;}
        if(s.request.command==SUSAMUNE_STATE_CMD_EXPORT || s.request.command==SUSAMUNE_STATE_CMD_TAS_BEGIN){allocateId();return;}
        if(s.request.command==SUSAMUNE_STATE_CMD_TAS_CATALOG){projectSort();s.phase=SCAN;return;}
        for(unsigned i=1;i<s.count;++i)for(unsigned j=i;j && fileId(s.files[j].name)<fileId(s.files[j-1].name);--j){auto a=s.files[j];s.files[j]=s.files[j-1];s.files[j-1]=a;}
        s.phase=SCAN;return;
    }
    if(s.phase==HEADER){
        if(!validHeader() || (s.verifyParts?!projectHeaderMatches(s.project,s.part):!transferHeaderValid())){
            if(s.request.command==SUSAMUNE_STATE_CMD_CATALOG){++s.scan;s.phase=SCAN;}else finish(SUSAMUNE_STATE_BAD_FILE);return;
        }
        if(s.verifyParts){s.offset=0;s.crc=0xffffffffu;s.phase=METADATA;return;}
        if(s.request.command==SUSAMUNE_STATE_CMD_CATALOG){startNames();return;}
        if(s.header.headerCrc!=s.request.expectedHeaderCrc || ((s.request.command==SUSAMUNE_STATE_CMD_IMPORT || s.request.command==SUSAMUNE_STATE_CMD_READ_WINDOW) && s.header.packedSize!=s.request.packedSize)){finish(SUSAMUNE_STATE_STALE);return;}
        if(s.request.command==SUSAMUNE_STATE_CMD_RENAME || s.request.command==SUSAMUNE_STATE_CMD_DELETE){startNames();return;}
        if(s.header.configId!=s.config){finish(SUSAMUNE_STATE_WRONG_CONFIG);return;}
        s.phase=METADATA;return;
    }
    if(s.phase==CREATE){s.created=true;s.phase=BLANK;return;}
    if(s.phase==BLANK){s.phase=METADATA;return;}
    if(s.phase==METADATA){if(SusamuneStateCrc(s.mailbox->metadata,s.header.metadataSize)!=s.header.metadataCrc || !tapeMetadataValid(s.verifyParts || s.request.command!=SUSAMUNE_STATE_CMD_EXPORT)){fail(SUSAMUNE_STATE_BAD_FILE);return;}s.phase=PAYLOAD;return;}
    if(s.phase==PAYLOAD){
        if(!s.offset && isTape() && !zero(s.ioData,4)){fail(SUSAMUNE_STATE_BAD_FILE);return;}
        s.crc=SusamuneStateCrcUpdate(s.crc,s.ioData,s.ioSize);
        if(s.request.command!=SUSAMUNE_STATE_CMD_EXPORT && !s.verifyParts){
            const unsigned first=s.offset<SUSAMUNE_STATE_STAGING_SIZE?(s.ioSize<SUSAMUNE_STATE_STAGING_SIZE-s.offset?s.ioSize:SUSAMUNE_STATE_STAGING_SIZE-s.offset):0;
            if(first)memcpy(reinterpret_cast<unsigned char *>(SUSAMUNE_DOLPHIN_STATE_STAGING_PPC_BASE)+s.offset,s.buffer,first);
            if(first<s.ioSize && !StatePoolMemoryCopyIn(&s.memory,s.request.poolOffset+s.offset+first-SUSAMUNE_STATE_STAGING_SIZE,s.buffer+first,s.ioSize-first)){fail(SUSAMUNE_STATE_BAD_REQUEST);return;}
        }
        s.offset+=s.ioSize;
        if(s.offset<(s.request.command==SUSAMUNE_STATE_CMD_READ_WINDOW?s.request.reserved:s.header.packedSize))return;
        if(s.request.command==SUSAMUNE_STATE_CMD_EXPORT){s.header.payloadCrc=~s.crc;s.header.headerCrc=SusamuneStateHeaderCrc(&s.header);s.phase=COMMIT;}
        else if(s.request.command!=SUSAMUNE_STATE_CMD_READ_WINDOW && s.header.payloadCrc!=~s.crc)fail(SUSAMUNE_STATE_BAD_FILE);
        else if(s.verifyParts){++s.part;s.phase=PROJECTPART;}else if(s.context.projectId){memcpy(s.name,s.header.name,32);finish(0);}else startNames();return;
    }
    if(s.phase==COMMIT){s.phase=VERIFY;return;}
    if(s.phase==VERIFY){if(memcmp(&s.header,&s.check,sizeof(s.header))){fail(SUSAMUNE_STATE_IO_ERROR);return;}s.created=false;if(s.context.projectId){memcpy(s.name,s.header.name,32);finish(0);}else startNames();return;}
    if(s.phase==NAMES0){s.phase=NAMES1;return;}
    if(s.phase==NAMES1){namesDone();return;}
    if(s.phase==NAMEWRITE){s.phase=NAMEVERIFY;return;}
    if(s.phase==NAMEVERIFY){if(memcmp(&s.nameNext,&s.nameCheck,64) || !nameValid(s.nameCheck)){finish(SUSAMUNE_STATE_IO_ERROR);return;}memcpy(s.name,s.nameNext.name,32);finish(0);return;}
    if(s.phase==REMOVE)finish(0);
}
}
__attribute__((section(".archiveapi"),used)) const DolphinArchiveApi moonshine_archive_api={DOLPHIN_ARCHIVE_API_MAGIC,1,sizeof(DolphinArchiveApi),initialize,update};
