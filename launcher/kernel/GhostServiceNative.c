#ifdef GHOST_SERVICE_HOST_TEST
#include "GhostServiceTestPlatform.h"
#else
#include "global.h"
#endif
#include "GhostServiceNative.h"
#include "GhostServiceTls.h"
#include "GhostServiceJson.h"
#include "GhostServiceAccount.h"
#include <string.h>

#define WEB_BARRIER() __asm__ volatile("" ::: "memory")
#define WEB_RING_SIZE 65536u
#define WEB_JOB ((struct ipcmessage *)1)
#define WEB_CLOSE ((struct ipcmessage *)2)
#define WEB_RETIRE ((struct ipcmessage *)3)
extern s32 GhostServiceRandom(void *,u32);

struct WebWork {
    union { struct { struct GhostJson json; char body[32768]; } catalog;
        unsigned char ring[WEB_RING_SIZE]; } buffer;
    struct GhostServiceEntry download;
    br_sha256_context sha;
    char path[768];
    unsigned char entropy[32] ALIGNED(32);
    struct ipcmessage message ALIGNED(32);
    ioctlv vectors[3] ALIGNED(32);
    unsigned char args[64] ALIGNED(32), reply[1152] ALIGNED(32), data[2048] ALIGNED(32);
    struct GhostServiceTrace traces[8];
    unsigned traceCount, sortRoute, filter;
    struct GhostAccountWork accountWork;
    struct GhostAccount *account;
    unsigned action, uploadBytes;
};
typedef char WebWorkFits[sizeof(struct WebWork)<=GHOST_SERVICE_WORK_SIZE?1:-1];
typedef char WebSessionFits[sizeof(struct GhostTls)<=GHOST_SERVICE_SESSION_SIZE?1:-1];
static struct WebWork *sWork;
static struct GhostTls *sTls;
static void *sStage;
static unsigned sTime, sStarted, sBytes, sJobAt;
static volatile unsigned sBusy, sCancel, sDone, sWrite, sRead;
static int sResult, sQueue=-1, sThread=-1, sTop=-1, sSocket=-1;
static u8 sStack[8192] ALIGNED(32);
static u32 sQueueStorage[8] ALIGNED(32);
static unsigned sInitialized;
static volatile unsigned sClosing, sPhase;
static unsigned sNetworkBudget, sCapabilities, sCapabilitiesKnown, sBackoffUntil;
static int sIosError;
static unsigned sSentBytes, sReceivedBytes, sLastIo, sTlsAt, sHandshakeMs;
static unsigned sLastIoAt, sProcessingTicks;
static unsigned char sCloseArgs[32] ALIGNED(32);
#ifndef GHOST_SERVICE_HOST_TEST
extern s32 GhostServiceDestroyQueue(s32) __asm__("syscall_0b");
#endif

static unsigned word(const unsigned char *p) {return ((unsigned)p[0]<<24)|((unsigned)p[1]<<16)|((unsigned)p[2]<<8)|p[3];}
static void put(unsigned char *p,unsigned v){p[0]=v>>24;p[1]=v>>16;p[2]=v>>8;p[3]=v;}
static int cancelled(void) {
    if(sCancel)return GHOST_SERVICE_CANCELLED;
    if((unsigned)(read32(HW_TIMER)-sStarted)>120u*1898437u)
        return sNetworkBudget?GHOST_SERVICE_STARTUP:GHOST_SERVICE_TIMEOUT;
    return 0;
}
static int waitIo(int submitted) {
    struct ipcmessage *m;
    if(submitted<0)return submitted;
    /* Cancellation cannot release IOS buffers before the matching completion. */
    for(;;)if(mqueue_recv(sQueue,&m,0)>=0 && m==&sWork->message)
        return (int)sWork->message.result;
}
static int ioctl(int fd,unsigned cmd,unsigned in,unsigned out) {
    memset(&sWork->message,0,sizeof(sWork->message));
    sync_after_write(sWork->args,sizeof(sWork->args));
    sync_after_write(sWork->reply,sizeof(sWork->reply));
    sync_after_write(&sWork->message,sizeof(sWork->message));
    return waitIo(IOS_IoctlAsync(fd,cmd,in?sWork->args:NULL,in,
        out?sWork->reply:NULL,out,sQueue,&sWork->message));
}
static int vectors(unsigned cmd,unsigned in,unsigned out) {
    memset(&sWork->message,0,sizeof(sWork->message));
    sync_after_write(sWork->args,sizeof(sWork->args));
    sync_after_write(sWork->data,sizeof(sWork->data));
    sync_after_write(sWork->vectors,sizeof(sWork->vectors));
    sync_after_write(&sWork->message,sizeof(sWork->message));
    return waitIo(IOS_IoctlvAsync(sTop,cmd,in,out,sWork->vectors,sQueue,&sWork->message));
}
static int pauseIo(void *context) {
    int result=cancelled(); (void)context;
    if(sPhase==GHOST_WEB_TLS && sLastIoAt) {
        unsigned gap=read32(HW_TIMER)-sLastIoAt;
        if(gap>sProcessingTicks)sProcessingTicks=gap;
        sLastIoAt=0;
    }
    if(result)return result;
    if(sPhase==GHOST_WEB_TLS && (br_ssl_engine_current_state(&sTls->client.eng)&(BR_SSL_SENDAPP|BR_SSL_RECVAPP)))
        {sHandshakeMs=(read32(HW_TIMER)-sTlsAt)/1898u;sPhase=GHOST_WEB_HTTP;}
    udelay(1000); return 0;
}
static int sendIo(void *context,const void *data,unsigned bytes) {
    int r;(void)context;
    if(bytes>sizeof(sWork->data))return GHOST_SERVICE_NETWORK;
    memcpy(sWork->data,data,bytes);memset(sWork->args,0,sizeof(sWork->args));
    put(sWork->args,sSocket);
    sWork->vectors[0].data=sWork->data;sWork->vectors[0].len=bytes;
    sWork->vectors[1].data=sWork->args;sWork->vectors[1].len=40;
    sLastIo=13;r=vectors(13,2,0);sLastIoAt=read32(HW_TIMER);
    if(r>0)sSentBytes+=r;
    if(r<0 && r!=-6)sIosError=r;
    return r==-6?0:r<=0?GHOST_SERVICE_NETWORK:r;
}
static int recvIo(void *context,void *data,unsigned bytes) {
    int r;(void)context;
    if(bytes>sizeof(sWork->data))return GHOST_SERVICE_NETWORK;
    memset(sWork->args,0,sizeof(sWork->args));put(sWork->args,sSocket);put(sWork->args+4,4);
    sWork->vectors[0].data=sWork->args;sWork->vectors[0].len=8;
    sWork->vectors[1].data=sWork->data;sWork->vectors[1].len=bytes;
    sLastIo=12;r=vectors(12,1,1);sLastIoAt=read32(HW_TIMER);
    if(r>0)sReceivedBytes+=r;
    if(r<=0 && r!=-6)sIosError=r;
    if(r==-6)return 0;
    if(r<=0 || (unsigned)r>bytes)return GHOST_SERVICE_NETWORK;
    memcpy(data,sWork->data,r);return r;
}
static int sinkIo(void *context,const void *data,unsigned bytes) {
    const unsigned char *p=data;(void)context;
    br_sha256_update(&sWork->sha,data,bytes);
    while(bytes){
        unsigned used=sWrite-sRead, offset=sWrite&(WEB_RING_SIZE-1), n;
        if(cancelled())return 0;
        if(used==WEB_RING_SIZE){udelay(1000);continue;}
        n=WEB_RING_SIZE-used;if(n>WEB_RING_SIZE-offset)n=WEB_RING_SIZE-offset;if(n>bytes)n=bytes;
        memcpy(sWork->buffer.ring+offset,p,n);WEB_BARRIER();sWrite+=n;
        p+=n;bytes-=n;
    }
    return 1;
}
static int connectHost(void) {
    int kd,r;unsigned base,list,ip;
    static const char kdPath[] ALIGNED(32)="/dev/net/kd/request";
    static const char topPath[] ALIGNED(32)="/dev/net/ip/top";
    sPhase=GHOST_WEB_STARTUP;
    /* A new TLS socket does not need another global network startup. */
    if(sTop<0) {
    kd=IOS_Open(kdPath,0);if(kd<0){sIosError=kd;return GHOST_SERVICE_STARTUP;}
    for(;;) {
        if((r=cancelled())){IOS_Close(kd);return r;}
        r=ioctl(kd,6,0,32);
        if(r>=0)r=(int)word(sWork->reply);
        if(r!=-29)break;
        udelay(100000);
    }
    IOS_Close(kd);
    if(r<0 && r!=-15){sIosError=r;return GHOST_SERVICE_STARTUP;}
    if(cancelled())return cancelled();
    sTop=IOS_Open(topPath,0);if(sTop<0){sIosError=sTop;return GHOST_SERVICE_STARTUP;}
    r=ioctl(sTop,31,0,0);if(r<0 && r!=-15){sIosError=r;return GHOST_SERVICE_STARTUP;}
    }
    for(;;) {
        if((r=cancelled()))return r;
        r=ioctl(sTop,16,0,0);
        /* IOS carries an IPv4 address in a signed result field. */
        if((unsigned)r>=0x01000000u && (unsigned)r<0xe0000000u)break;
        if(r){sIosError=r;return GHOST_SERVICE_STARTUP;}
        udelay(100000);
    }
    sStarted=read32(HW_TIMER);sNetworkBudget=0;sPhase=GHOST_WEB_DNS;
    strcpy((char*)sWork->args,GHOST_SERVICE_HOST);
    r=ioctl(sTop,17,sizeof(GHOST_SERVICE_HOST),0x460);if(r<0){sIosError=r;return GHOST_SERVICE_DNS;}
    /* IOS returns relocated hostent pointers relative to h_name at reply+16. */
    base=word(sWork->reply)-16u;list=word(sWork->reply+12)-base;
    if(list>0x45cu || list<16 || sWork->reply[8] || sWork->reply[9]!=2 ||
        sWork->reply[10] || sWork->reply[11]!=4)return GHOST_SERVICE_DNS;
    ip=word(sWork->reply+list)-base;
    if(ip>0x45cu || ip<16)return GHOST_SERVICE_DNS;
    memcpy(sWork->data,sWork->reply+ip,4);
    put(sWork->args,2);put(sWork->args+4,1);put(sWork->args+8,0);
    sPhase=GHOST_WEB_TCP;
    sSocket=ioctl(sTop,15,12,0);if(sSocket<0){sIosError=sSocket;return GHOST_SERVICE_NETWORK;}
    /* Connect once in blocking socket mode, on this worker; caller remains responsive. */
    memset(sWork->args,0,sizeof(sWork->args));put(sWork->args,sSocket);put(sWork->args+4,1);
    sWork->args[8]=8;sWork->args[9]=2;sWork->args[10]=1;sWork->args[11]=187;
    memcpy(sWork->args+12,sWork->data,4);
    r=ioctl(sTop,4,16,0);if(r<0){sIosError=r;return GHOST_SERVICE_NETWORK;}
    put(sWork->args,sSocket);put(sWork->args+4,4);put(sWork->args+8,4);
    r=ioctl(sTop,5,12,0);if(r<0){sIosError=r;return GHOST_SERVICE_NETWORK;}return 0;
}
static int closeConnection(int retireNetwork) {
    int r=0;unsigned attempt;
    if(sSocket>=0) {
        put(sCloseArgs,sSocket);sync_after_write(sCloseArgs,sizeof(sCloseArgs));
        for(attempt=0;attempt<10;++attempt) {
            r=IOS_Ioctl(sTop,3,sCloseArgs,4,NULL,0);
            if(r>=0){sSocket=-1;break;}
            udelay(100000);
        }
    }
    if(retireNetwork && sSocket<0 && sTop>=0){IOS_Close(sTop);sTop=-1;}
    return r<0?GHOST_SERVICE_NETWORK:0;
}
static int fetch(const struct GhostTlsIo *io,const char *path,const struct GhostTlsRequest *req,void *output,unsigned capacity,unsigned *used) {
    unsigned attempt;
    for(attempt=0;attempt<2;++attempt) {
        unsigned begin=read32(HW_TIMER), connected, reused=sSocket>=0 && sTls->active;
        struct GhostServiceTrace *trace;
        int r=0;
        if(sWork->traceCount==8)return GHOST_SERVICE_RESPONSE;
        trace=&sWork->traces[sWork->traceCount++];
        memset(trace,0,sizeof(*trace));strcpy(trace->path,path);trace->reused=reused;
        trace->method=req?(!strcmp(req->method,"PUT")?2:1):0;
        memset(&sTls->http,0,sizeof(sTls->http));sIosError=0;
        sSentBytes=sReceivedBytes=sLastIo=sHandshakeMs=0;
        sLastIoAt=sProcessingTicks=0;
        if(!reused) {
            sTls->active=0;
            if(GhostServiceRandom(sWork->entropy,sizeof(sWork->entropy))!=0){r=GHOST_SERVICE_RANDOM;goto finished;}
            if((r=closeConnection(0)))goto finished;
            sNetworkBudget=1;sStarted=begin;
            r=connectHost();if(r)goto finished;
            trace->startupMs=(sStarted-begin)/1898u;
        } else {sNetworkBudget=0;sStarted=begin;}
        connected=read32(HW_TIMER);trace->connectMs=(connected-begin)/1898u;
        sPhase=reused?GHOST_WEB_HTTP:GHOST_WEB_TLS;sTlsAt=connected;
        r=req?GhostTlsRequest(sTls,io,path,req,output,capacity,used,sTime,sWork->entropy):
            GhostTlsGet(sTls,io,path,output,capacity,used,sTime,sWork->entropy);
finished:
        trace->phase=sPhase;trace->result=r;trace->iosError=sIosError;
        trace->sentBytes=sSentBytes;trace->receivedBytes=sReceivedBytes;trace->lastIo=sLastIo;
        trace->handshakeMs=sHandshakeMs;
        trace->processingMs=sProcessingTicks/1898u;
        trace->elapsedMs=(read32(HW_TIMER)-begin)/1898u;
        trace->httpStatus=sTls->http.status;
        trace->retryAfter=GhostHttpRetryDelay(&sTls->http,sTime+(read32(HW_TIMER)-sJobAt)/1898437u);
        trace->tlsError=br_ssl_engine_last_error(&sTls->client.eng);
        strcpy(trace->requestId,sTls->http.requestId);strcpy(trace->date,sTls->http.date);
        strcpy(trace->cfRay,sTls->http.cfRay);strcpy(trace->serverTiming,sTls->http.serverTiming);
        if(r==GHOST_SERVICE_RATE_LIMIT || r==GHOST_SERVICE_UNAVAILABLE) {
            unsigned seconds=trace->retryAfter?trace->retryAfter:5;
            unsigned now=sTime+(read32(HW_TIMER)-sJobAt)/1898437u;
            sBackoffUntil=seconds>0xffffffffu-now?0xffffffffu:now+seconds;
        }
        if(!r)return 0;
        if(cancelled())return cancelled();
        /* A dropped fresh handshake is retryable too; never replay a partial response. */
        if(req || attempt || sTls->http.responseBytes ||
            (r!=GHOST_SERVICE_NETWORK && !(reused && r==GHOST_SERVICE_TLS && !trace->tlsError)))return r;
        sTls->active=0;
        udelay(250000);
    }
    return GHOST_SERVICE_NETWORK;
}
static int get(const struct GhostTlsIo *io,const char *path,void *output,unsigned capacity,unsigned *used) {
    return fetch(io,path,NULL,output,capacity,used);
}
static int accountHttp(const char *path,const struct GhostTlsRequest *req,void *out,unsigned cap,unsigned *used,unsigned *status) {
    struct GhostTlsIo io={NULL,sendIo,recvIo,pauseIo,NULL};
    int r=fetch(&io,path,req,out,cap,used);*status=sTls->http.status;
    if(*status==429 || *status>=500) {
        unsigned now=sTime+(read32(HW_TIMER)-sJobAt)/1898437u,delay=GhostHttpRetryDelay(&sTls->http,now);
        if(!delay)delay=5;sBackoffUntil=delay>0xffffffffu-now?0xffffffffu:now+delay;
    }
    return r;
}
static int run(void) {
    struct GhostTlsIo io={NULL,sendIo,recvIo,pauseIo,NULL};
    unsigned used=0;int r;
    if(sTime<1735689600u || sTime>4102444800u)return GHOST_SERVICE_CLOCK;
    if(sBackoffUntil>sTime)return GHOST_SERVICE_RATE_LIMIT;
    if(sWork->account) {
        struct GhostAccountWork *w=&sWork->accountWork;
        w->clientName=NULL;w->json=&sWork->buffer.catalog.json;w->response=sWork->buffer.catalog.body;w->capacity=sizeof(sWork->buffer.catalog.body);
        r=GhostAccountRun(sWork->account,w,sWork->action,sTime,sStage,sWork->uploadBytes,accountHttp);
        memset(w->body,0,sizeof(w->body));memset(w->response,0,w->capacity);
        if(!r && sWork->action!=GHOST_ACCOUNT_UPLOAD){
            GhostAccountInfo(sWork->account,sTime,sStage);sBytes=sizeof(struct GhostServiceAccountInfo);
        }
        return r;
    }
    if(!sCapabilitiesKnown && !sWork->download.bytes) {
        r=get(&io,GHOST_SERVICE_API "/capabilities",sWork->buffer.catalog.body,sizeof(sWork->buffer.catalog.body),&used);
        if(r)return r;
        sCapabilities=GhostServiceRouteSortSupported(&sWork->buffer.catalog.json,sWork->buffer.catalog.body,used)?GHOST_SERVICE_CAN_SORT_ROUTE:0;
        sCapabilitiesKnown=1;
    }
    if(sWork->sortRoute && !(sCapabilities&GHOST_SERVICE_CAN_SORT_ROUTE))return GHOST_SERVICE_SORT_UNSUPPORTED;
    if(sWork->download.bytes){
        unsigned char hash[32];
        br_sha256_init(&sWork->sha);io.sink=sinkIo;
        r=get(&io,sWork->download.path,NULL,sWork->download.bytes,&used);
        if(r)return cancelled()?cancelled():r;
        br_sha256_out(&sWork->sha,hash);
        if(used!=sWork->download.bytes || memcmp(hash,sWork->download.sha256,32))return GHOST_SERVICE_HASH;
    } else {
        r=get(&io,sWork->path,sWork->buffer.catalog.body,sizeof(sWork->buffer.catalog.body),&used);
        if(r)return r;
        if(!GhostServiceParsePage(&sWork->buffer.catalog.json,sWork->buffer.catalog.body,used,sStage))return GHOST_SERVICE_RESPONSE;
        ((struct GhostServicePage*)sStage)->reserved=sCapabilities|(sWork->sortRoute?GHOST_SERVICE_SORTED_ROUTE:0)|(sWork->filter<<8);
        used=sizeof(struct GhostServicePage);
    }
    sPhase=GHOST_WEB_VALIDATE;sBytes=used;return 0;
}
static void performJob(void) {
    int result=run();
    if(result || !sTls->active){sTls->active=0;closeConnection(result==GHOST_SERVICE_STARTUP);}
    memset(sWork->entropy,0,sizeof(sWork->entropy));
    sResult=result;WEB_BARRIER();sDone=1;
}
static u32 worker(void *unused) {
    struct ipcmessage *m;(void)unused;
    for(;;)if(mqueue_recv(sQueue,&m,0)>=0) {
        if(m==WEB_JOB)performJob();
        else if(m==WEB_CLOSE || m==WEB_RETIRE){closeConnection(m==WEB_RETIRE);WEB_BARRIER();sClosing=0;}
    }
    return 0;
}
static int initialize(void) {
    if(sInitialized)return 1;
    if(sThread>=0 || sQueue>=0)return 0;
    sQueue=mqueue_create(sQueueStorage,8);if(sQueue<0)return 0;
    sThread=(int)do_thread_create(worker,(u32*)(sStack+sizeof(sStack)),sizeof(sStack),0x48);
    if(sThread<0 || thread_continue(sThread)<0){GhostServiceShutdown();return 0;}
    sInitialized=1;return 1;
}
static void appendNumber(char *out,unsigned value) {
    out+=strlen(out);
    if(value>=10)*out++='0'+value/10;
    *out++='0'+value%10;*out=0;
}
int GhostServiceStart(void *stage,unsigned stageSize,const char *region,unsigned unixTime,
    const struct GhostServiceEntry *download,void *session) {
    struct GhostServiceQuery query;unsigned i,used;
    static const char digits[]="0123456789ABCDEF";
    if(sBusy || sClosing || !session || stageSize<GHOST_SERVICE_WORK_SIZE+sizeof(struct GhostServicePage) || !initialize())return 0;
    if(download && !GhostServiceEntryValid(download))return 0;
    if(!download){memcpy(&query,stage,sizeof(query));if(!memchr(query.cursor,0,sizeof(query.cursor)) || query.sortRoute>1 ||
        (query.filter>>24) || (query.filter&255)>61 || ((query.filter>>8)&255)>10 ||
        (query.filter && (!(query.filter&255) || !((query.filter>>8)&255))))return 0;}
    sTls=session;
    sStage=stage;sWork=(struct WebWork*)((unsigned char*)stage+stageSize-GHOST_SERVICE_WORK_SIZE);
    memset(sWork,0,sizeof(*sWork));
    if(download)sWork->download=*download;
    else {
        sWork->sortRoute=query.sortRoute;
        sWork->filter=query.filter;
        strcpy(sWork->path,GHOST_SERVICE_API "/ghosts?limit=4&sort=");
        strcat(sWork->path,query.sortRoute?"route":"newest");strcat(sWork->path,"&playable_on=");
        if(strcmp(region,"jp") && strcmp(region,"us") && strcmp(region,"pal"))return 0;
        strcat(sWork->path,region);
        if(query.filter) {
            strcat(sWork->path,"&area=");appendNumber(sWork->path,(query.filter&255)-1);
            strcat(sWork->path,"&episode=");appendNumber(sWork->path,((query.filter>>8)&255)-1);
        }
        strcat(sWork->path,"&cursor=");used=strlen(sWork->path);
        for(i=0;query.cursor[i];++i){unsigned c=(unsigned char)query.cursor[i];
            if((c>='A'&&c<='Z')||(c>='a'&&c<='z')||(c>='0'&&c<='9')||strchr("-._~",c)) {
                if(used+1>=sizeof(sWork->path))return 0;sWork->path[used++]=c;continue;
            }
            if(used+3>=sizeof(sWork->path))return 0;
            sWork->path[used++]='%';sWork->path[used++]=digits[c>>4];sWork->path[used++]=digits[c&15];}
        sWork->path[used]=0;
        if(!query.cursor[0])sWork->path[used-8]=0;
    }
    sTime=unixTime;sJobAt=sStarted=read32(HW_TIMER);sBytes=sWrite=sRead=sDone=sCancel=0;
    sResult=0;sBusy=1;WEB_BARRIER();
    sNetworkBudget=!(sSocket>=0 && sTls->active);sPhase=sNetworkBudget?GHOST_WEB_STARTUP:GHOST_WEB_HTTP;
    if(mqueue_send_now(sQueue,WEB_JOB,1)<0){sBusy=0;return 0;}
    return 1;
}
void GhostServiceCancel(void){sCancel=1;}
int GhostServiceAction(void *stage,unsigned stageSize,unsigned unixTime,unsigned action,
    unsigned uploadBytes,struct GhostAccount *account,void *session,const struct GhostServiceUpload *upload) {
    if(sBusy || sClosing || !session || !account || action>GHOST_ACCOUNT_UPLOAD ||
        stageSize<GHOST_SERVICE_WORK_SIZE+sizeof(struct GhostServiceAccountInfo) ||
        uploadBytes>stageSize-GHOST_SERVICE_WORK_SIZE || !initialize())return 0;
    sTls=session;sStage=stage;sWork=(struct WebWork*)((unsigned char*)stage+stageSize-GHOST_SERVICE_WORK_SIZE);
    memset(sWork,0,sizeof(*sWork));sWork->account=account;sWork->action=action;sWork->uploadBytes=uploadBytes;
    if(upload)sWork->accountWork.upload=*upload;
    sTime=unixTime;sJobAt=sStarted=read32(HW_TIMER);sBytes=sWrite=sRead=sDone=sCancel=0;
    sResult=0;sBusy=1;sNetworkBudget=!(sSocket>=0 && sTls->active);sPhase=GHOST_WEB_STARTUP;
    WEB_BARRIER();if(mqueue_send_now(sQueue,WEB_JOB,1)<0){sBusy=0;return 0;}return 1;
}
void GhostServiceForget(void) {
    if(sBusy || sClosing)return;
    sTls=NULL;
    if(sSocket>=0 && sInitialized) {
        sClosing=1;WEB_BARRIER();
        if(mqueue_send_now(sQueue,WEB_CLOSE,1)<0)sClosing=0;
    }
}
unsigned GhostServiceProgress(void){return sPhase;}
unsigned GhostServiceMainDelay(void){
    /* TLS runs below main's priority: 20 us can starve a fresh handshake. */
    return sBusy && !sDone && sPhase==GHOST_WEB_TLS?200u:20u;
}
const struct GhostServiceTrace *GhostServiceTrace(unsigned index) {
    return sDone && sWork && index<sWork->traceCount?&sWork->traces[index]:NULL;
}
int GhostServicePoll(unsigned *bytes){
    if(!sDone)return 0;
    WEB_BARRIER();*bytes=sBytes;return sResult?sResult:1;
}
unsigned GhostServiceRead(void **data){
    unsigned count=sWrite-sRead,offset=sRead&(WEB_RING_SIZE-1);
    WEB_BARRIER();if(count>WEB_RING_SIZE-offset)count=WEB_RING_SIZE-offset;
    if(count>16384u)count=16384u;
    *data=sWork->buffer.ring+offset;return count;
}
void GhostServiceReadAck(unsigned bytes){WEB_BARRIER();sRead+=bytes;}
void GhostServiceRelease(void){if(sDone){sWork=NULL;sStage=NULL;WEB_BARRIER();sBusy=0;}}
int GhostServiceShutdown(void) {
    if(sBusy && !sDone){GhostServiceCancel();return 0;}
    if(sClosing)return 0;
    if(sSocket>=0 || sTop>=0){
        sBusy=0;sTls=NULL;sClosing=1;WEB_BARRIER();
        if(mqueue_send_now(sQueue,WEB_RETIRE,1)<0)sClosing=0;
        return 0;
    }
    if(sThread>=0){if(thread_cancel(sThread,0)<0)return 0;sThread=-1;}
    if(sQueue>=0){if(GhostServiceDestroyQueue(sQueue)<0)return 0;sQueue=-1;}
    sInitialized=sBusy=0;sWork=NULL;sStage=NULL;return 1;
}
