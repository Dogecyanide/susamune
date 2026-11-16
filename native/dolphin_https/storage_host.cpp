#include "susamune/dolphin_storage_api.hxx"
#include "susamune/dolphin_entropy.hxx"
extern "C" { extern const DolphinHttpsApi moonshine_https_api; void MoonshineNativeInit(void); }
namespace NativeStorage {
const DolphinStorageHost *host;
unsigned region;
bool libraryBegin(const SusamuneGhostStorageRequest &request,const DolphinStorageHost *callbacks,unsigned game){
    MoonshineNativeInit();
    if(!callbacks || game<1 || game>3)return false;
    host=callbacks;region=game;return DolphinGhostLibrary::begin(request);
}
}
namespace DolphinFiles {
bool available(){return NativeStorage::host!=nullptr;}
u32 read(const char *n,void *p,u32 size,u32 offset){return NativeStorage::host->read(n,p,size,offset);}
u32 write(const char *n,const void *p,u32 size,u32 offset){return NativeStorage::host->write(n,p,size,offset);}
u32 create(const char *n,u32 size){return NativeStorage::host->create(n,size);}
u32 remove(const char *n){return NativeStorage::host->remove(n);}
u32 list(Entry *p,u32 size){return NativeStorage::host->list(p,size);}
bool take(u32 ticket,Result *out){return NativeStorage::host->fileTake(ticket,out);}
}
namespace DolphinHttps { const DolphinHttpsApi *api(){return &moonshine_https_api;} }
namespace Ghost {bool inspectFile(const void *data,u32 size,SusamuneGhostFileHeader *out){return NativeStorage::host->inspectGhost(data,size,out);}}

#include "susamune/dolphin_http_api.hxx"
#include "susamune/dolphin_tcp.hxx"
#include "susamune/dolphin_tcp_api.h"
namespace NativeStorage {
bool httpBegin(const DolphinStorageHost *callbacks,unsigned game,const char *path,const DolphinHttpsRequest *request,void *out,unsigned capacity){
    MoonshineNativeInit();if(!callbacks || game<1 || game>3)return false;
    host=callbacks;region=game;return DolphinHttp::begin(path,request,out,capacity);
}
bool entropyBegin(const DolphinStorageHost *callbacks,unsigned game){
    MoonshineNativeInit();if(!callbacks || game<1 || game>3)return false;
    host=callbacks;region=game;return DolphinEntropy::begin();
}
}
namespace DolphinNetwork {
bool resolve(const char *name,unsigned server){return NativeStorage::host->resolve(name,server);}
DnsResult dnsResult(){return NativeStorage::host->dnsResult();}
void cancelResolve(){if(NativeStorage::host)NativeStorage::host->cancelResolve();}
}
namespace DolphinTcp {
bool connect(unsigned ip,unsigned short port){return dolphin_tcp_api.connect(ip,port);}
int send(const void *p,unsigned bytes){return dolphin_tcp_api.send(p,bytes);}
int read(void *p,unsigned bytes){return dolphin_tcp_api.read(p,bytes);}
State state(){return static_cast<State>(dolphin_tcp_api.state());}
void close(){dolphin_tcp_api.close();}
}
__attribute__((section(".httpapi"),used)) const DolphinHttpApi moonshine_http_api={
    DOLPHIN_HTTP_API_MAGIC,1,sizeof(DolphinHttpApi),NativeStorage::httpBegin,DolphinHttp::update,DolphinHttp::take,
    DolphinHttp::phase,DolphinHttp::cancel,DolphinHttp::close,NativeStorage::entropyBegin,DolphinEntropy::update,DolphinEntropy::take};
