#include "susamune/dolphin_https.h"
#include "../../launcher/kernel/GhostServiceTls.c"

struct Work {
    struct GhostTls tls;
    const unsigned char *body;
    unsigned bodyBytes, sent, length, running, ready;
};
static int initialize(void *memory,unsigned unixTime,const unsigned char *entropy) {
    struct Work *w=memory;
    if(!w || !entropy)return GHOST_SERVICE_RANDOM;
    memset(w,0,sizeof(*w));
    {int result=init(&w->tls,unixTime,entropy);w->ready=result==0;return result;}
}
static int start(void *memory,const char *path,const struct DolphinHttpsRequest *req,
                 void *output,unsigned capacity) {
    struct Work *w=memory;struct GhostTls *t=&w->tls;
    unsigned n,i;
    if(!w->ready || w->running || !path || !output || !capacity)return GHOST_SERVICE_RESPONSE;
    n=strlen(path);
    if(!n || n>700 || *path!='/')return GHOST_SERVICE_RESPONSE;
    for(i=0;i<n;++i)if((unsigned char)path[i]<=32 || (unsigned char)path[i]>=127)return GHOST_SERVICE_RESPONSE;
    if(req && (!req->method || !req->headers ||
       (strcmp(req->method,"POST") && strcmp(req->method,"PUT")) ||
       (req->bytes && !req->body) || req->bytes>2u*1024u*1024u ||
       strlen(req->headers)+n+200>=sizeof(t->request)))return GHOST_SERVICE_RESPONSE;
    strcpy(t->request,req?req->method:"GET");strcat(t->request," ");strcat(t->request,path);
    strcat(t->request," HTTP/1.1\r\nHost: " GHOST_SERVICE_HOST "\r\nUser-Agent: Moonshine/3.0\r\nAccept-Encoding: identity\r\nConnection: keep-alive\r\n");
    if(req){
        char digits[11];unsigned k=0;n=req->bytes;
        do{digits[k++]='0'+n%10;n/=10;}while(n);
        strcat(t->request,req->headers);strcat(t->request,"Content-Length: ");
        n=strlen(t->request);while(k)t->request[n++]=digits[--k];t->request[n]=0;
        strcat(t->request,"\r\n");
    }
    strcat(t->request,"\r\n");
    w->length=strlen(t->request);w->sent=0;w->body=req?req->body:NULL;w->bodyBytes=req?req->bytes:0;
    GhostHttpInit(&t->http,output,capacity);t->http.jsonResponse=req!=NULL;
    w->running=1;t->active=0;
    return 0;
}
static int step(void *memory,const struct DolphinHttpsIo *io) {
    struct Work *w=memory;struct GhostTls *t=&w->tls;
    unsigned state;int result;size_t n;unsigned char *p;
    if(!w->running || !io || !io->send || !io->recv)return GHOST_SERVICE_RESPONSE;
    state=br_ssl_engine_current_state(&t->client.eng);
    if(state&BR_SSL_CLOSED)return GHOST_SERVICE_TLS;
    if(state&BR_SSL_SENDREC){
        p=br_ssl_engine_sendrec_buf(&t->client.eng,&n);if(n>2048)n=2048;
        result=io->send(io->context,p,n);
        if(result<0)return GHOST_SERVICE_NETWORK;
        if((unsigned)result>n)return GHOST_SERVICE_NETWORK;
        if(result)br_ssl_engine_sendrec_ack(&t->client.eng,result);
    }else if(state&BR_SSL_RECVAPP){
        p=br_ssl_engine_recvapp_buf(&t->client.eng,&n);
        if(!GhostHttpFeed(&t->http,p,n))return t->http.status==429?GHOST_SERVICE_RATE_LIMIT:
            t->http.status>=500?GHOST_SERVICE_UNAVAILABLE:GHOST_SERVICE_RESPONSE;
        br_ssl_engine_recvapp_ack(&t->client.eng,n);
        if(t->http.complete){w->running=0;t->active=!t->http.close;return 0;}
    }else if((state&BR_SSL_SENDAPP) && w->sent<w->length+w->bodyBytes){
        p=br_ssl_engine_sendapp_buf(&t->client.eng,&n);
        if(w->sent<w->length){if(n>w->length-w->sent)n=w->length-w->sent;memcpy(p,t->request+w->sent,n);}
        else{unsigned pos=w->sent-w->length;if(n>w->bodyBytes-pos)n=w->bodyBytes-pos;memcpy(p,w->body+pos,n);}
        w->sent+=n;br_ssl_engine_sendapp_ack(&t->client.eng,n);
        if(w->sent==w->length+w->bodyBytes)br_ssl_engine_flush(&t->client.eng,0);
    }else if(state&BR_SSL_RECVREC){
        p=br_ssl_engine_recvrec_buf(&t->client.eng,&n);if(n>2048)n=2048;
        result=io->recv(io->context,p,n);
        if(result<0 || (unsigned)result>n)return GHOST_SERVICE_NETWORK;
        if(result)br_ssl_engine_recvrec_ack(&t->client.eng,result);
    }
    return 1;
}
static void info(const void *memory,struct DolphinHttpsInfo *out) {
    const struct Work *w=memory;
    out->used=w->tls.http.used;out->httpStatus=w->tls.http.status;
    out->tlsError=br_ssl_engine_last_error(&w->tls.client.eng);
    out->reusable=w->tls.active;out->complete=w->tls.http.complete;
}
static void sha256(const void *data,unsigned bytes,void *out) {
    br_sha256_context hash;br_sha256_init(&hash);br_sha256_update(&hash,data,bytes);br_sha256_out(&hash,out);
}
static void derive(const void *seed,void *next,void *session) {
    br_hmac_key_context key;br_hmac_context h;
    static const char nextLabel[]="Moonshine Dolphin seed v1";
    static const char tlsLabel[]="Moonshine Dolphin TLS v1";
    br_hmac_key_init(&key,&br_sha256_vtable,seed,32);
    br_hmac_init(&h,&key,32);br_hmac_update(&h,nextLabel,sizeof(nextLabel)-1);br_hmac_out(&h,next);
    br_hmac_init(&h,&key,32);br_hmac_update(&h,tlsLabel,sizeof(tlsLabel)-1);br_hmac_out(&h,session);
    memset(&h,0,sizeof(h));memset(&key,0,sizeof(key));
}
__attribute__((section(".api"),used)) const struct DolphinHttpsApi moonshine_https_api={
    DOLPHIN_HTTPS_MAGIC,DOLPHIN_HTTPS_VERSION,sizeof(struct DolphinHttpsApi),sizeof(struct Work),
    initialize,start,step,info,derive,sha256
};
