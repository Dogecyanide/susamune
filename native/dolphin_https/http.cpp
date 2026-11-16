#include "susamune/dolphin_http.hxx"
#include "susamune/dolphin_storage_api.hxx"
#include "susamune/dolphin_entropy.hxx"
#include "susamune/dolphin_dns.hxx"
#include "susamune/dolphin_tcp.hxx"
#include "susamune/live_transport.h"
#include "susamune/ghost_service.h"
extern "C" {
#include <string.h>
}
namespace NativeStorage {extern const DolphinStorageHost *host;}
namespace DolphinHttp {
namespace {
enum Phase {IDLE,SEED,NETWORK,DNS,TCP,TRANSFER,COMPLETE};
struct Work {
    char path[704],headers[384],method[5];
    DolphinHttpsRequest request;
    void *output;u32 capacity,timestamp,lastIo,started;
    DolphinHttpsInfo info;s32 result;Phase phase;
    bool hasRequest,ownsNetwork,cancelled,tlsStarted;
};
Work &s=*reinterpret_cast<Work *>(DOLPHIN_HTTPS_CONTROL_BASE);
static_assert(DOLPHIN_HTTPS_CONTROL_BASE+sizeof(Work)<=DOLPHIN_HTTPS_CONTROL_BASE+0x1000,"HTTP control budget");
bool initialized;
void *work(){return reinterpret_cast<void *>(DOLPHIN_HTTPS_WORK_BASE);}
u32 now(){return NativeStorage::host->milliseconds();}
bool copy(char *out,u32 size,const char *in) {
    if(!in)return false;
    for(u32 i=0;i<size;++i){out[i]=in[i];if(!in[i])return true;}
    return false;
}
void finish(int result) {
    if(s.tlsStarted)DolphinHttps::api()->info(work(),&s.info);
    s.result=result;s.phase=COMPLETE;
    if(result || !s.info.reusable){DolphinNetwork::cancelResolve();DolphinTcp::close();}
}
void transition(Phase phase){s.phase=phase;s.timestamp=s.lastIo=now();}
int send(void *,const void *data,unsigned bytes){int n=DolphinTcp::send(data,bytes);if(n>0)s.lastIo=now();return n;}
int receive(void *,void *data,unsigned bytes){int n=DolphinTcp::read(data,bytes);if(n>0)s.lastIo=now();return n;}
const DolphinHttpsIo io={nullptr,send,receive};
void startRequest() {
    const int result=DolphinHttps::api()->start(work(),s.path,s.hasRequest?&s.request:nullptr,s.output,s.capacity);
    if(result){finish(result);return;}transition(TRANSFER);
}
}
bool begin(const char *path,const DolphinHttpsRequest *request,void *out,unsigned capacity) {
    if(!initialized){memset(&s,0,sizeof(s));initialized=true;}
    if(s.phase!=IDLE || !path || !out || !capacity || capacity>2u*1024u*1024u || !DolphinHttps::api())return false;
    if(!copy(s.path,sizeof(s.path),path) || s.path[0]!='/')return false;
    s.hasRequest=request!=nullptr;
    if(request){
        if(!copy(s.headers,sizeof(s.headers),request->headers) || !copy(s.method,sizeof(s.method),request->method) ||
           (request->bytes && !request->body) || request->bytes>2u*1024u*1024u)return false;
        s.request=*request;s.request.method=s.method;s.request.headers=s.headers;
    }
    s.output=out;s.capacity=capacity;s.cancelled=false;s.result=0;s.started=now();
    DolphinHttpsInfo info={};
    if(s.tlsStarted)DolphinHttps::api()->info(work(),&info);
    if(info.reusable && DolphinTcp::state()==DolphinTcp::OPEN){startRequest();return true;}
    s.tlsStarted=false;memset(&s.info,0,sizeof(s.info));
    DolphinNetwork::cancelResolve();DolphinTcp::close();
    if(!DolphinEntropy::begin())return false;
    transition(SEED);return true;
}
void update() {
    if(!initialized || s.phase==IDLE || s.phase==COMPLETE)return;
    if(s.phase==SEED){
        DolphinEntropy::update();u8 entropy[32];int result=DolphinEntropy::take(entropy);
        if(result==1)return;
        if(s.cancelled){memset(entropy,0,sizeof(entropy));finish(GHOST_SERVICE_CANCELLED);return;}
        if(!result){
            const u64 seconds=static_cast<u64>(NativeStorage::host->seconds())+946684800u;
            result=seconds>0xffffffffu?GHOST_SERVICE_CLOCK:DolphinHttps::api()->initialize(work(),static_cast<u32>(seconds),entropy);
        }
        memset(entropy,0,sizeof(entropy));
        if(result){finish(result);return;}
        s.tlsStarted=true;transition(NETWORK);
    }
    if(s.cancelled){finish(GHOST_SERVICE_CANCELLED);return;}
    const u32 tick=now();
    if(tick-s.started>240000u || tick-s.lastIo>45000u){finish(GHOST_SERVICE_TIMEOUT);return;}
    const unsigned network=NativeStorage::host->networkState();
    if(s.phase==NETWORK){
        if(network==TW_LIVE_IDLE){if(NativeStorage::host->networkBegin())s.ownsNetwork=true;}
        else if(network==TW_LIVE_READY){
            if(!DolphinNetwork::resolve(GHOST_SERVICE_HOST)){finish(GHOST_SERVICE_DNS);return;}
            transition(DNS);
        }else if(network==TW_LIVE_FAILED || network==TW_LIVE_UNAVAILABLE){finish(GHOST_SERVICE_STARTUP);}
        return;
    }
    if(network!=TW_LIVE_READY){finish(GHOST_SERVICE_NETWORK);return;}
    if(s.phase==DNS){
        const auto dns=DolphinNetwork::dnsResult();
        if(dns.state==DolphinNetwork::DNS_RESOLVED){
            if(!DolphinTcp::connect(dns.address,443)){finish(GHOST_SERVICE_NETWORK);return;}
            transition(TCP);
        }else if(dns.state!=DolphinNetwork::DNS_WAITING)finish(GHOST_SERVICE_DNS);
        return;
    }
    if(s.phase==TCP){
        const auto tcp=DolphinTcp::state();
        if(tcp==DolphinTcp::OPEN)startRequest();
        else if(tcp!=DolphinTcp::CONNECTING)finish(GHOST_SERVICE_NETWORK);
        return;
    }
    // Each call performs bounded transport work; TLS retains its parser state.
    const int result=DolphinHttps::api()->step(work(),&io);
    if(result!=1)finish(result);
}
unsigned phase() {
    if(!initialized)return 0;
    return s.phase==DNS?GHOST_WEB_DNS:s.phase==TCP?GHOST_WEB_TCP:
        s.phase==TRANSFER?GHOST_WEB_TLS:GHOST_WEB_STARTUP;
}
int take(DolphinHttpsInfo *out) {
    if(!initialized || !out || s.phase==IDLE)return GHOST_SERVICE_RESPONSE;
    if(s.phase!=COMPLETE)return 1;
    *out=s.info;s.phase=IDLE;s.output=nullptr;s.request.body=nullptr;
    return s.result;
}
void cancel(){if(initialized && s.phase!=IDLE && s.phase!=COMPLETE)s.cancelled=true;}
bool close() {
    if(!initialized)return true;
    if(s.phase!=IDLE){cancel();return false;}
    DolphinNetwork::cancelResolve();DolphinTcp::close();
    if(s.ownsNetwork)NativeStorage::host->networkStopIfIdle();
    memset(work(),0,0x8000u);memset(&s,0,sizeof(s));return true;
}
}
