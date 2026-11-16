#include "GhostServiceTls.h"
#include "susamune/ghost_service.h"
#include <string.h>
#include "GhostServiceRoots.inc"

/* Accelerate P-256 without changing the existing P-384/P-521 support. */
static const br_ec_impl *curveImpl(int curve) {
    return curve==BR_EC_secp256r1?&br_ec_p256_m15:&br_ec_prime_i15;
}
static const unsigned char *ecGenerator(int curve,size_t *len) {
    return curveImpl(curve)->generator(curve,len);
}
static const unsigned char *ecOrder(int curve,size_t *len) {
    return curveImpl(curve)->order(curve,len);
}
static size_t ecXoff(int curve,size_t *len) {
    return curveImpl(curve)->xoff(curve,len);
}
static uint32_t ecMul(unsigned char *p,size_t len,const unsigned char *k,size_t klen,int curve) {
    return curveImpl(curve)->mul(p,len,k,klen,curve);
}
static size_t ecMulgen(unsigned char *p,const unsigned char *k,size_t klen,int curve) {
    return curveImpl(curve)->mulgen(p,k,klen,curve);
}
static uint32_t ecMuladd(unsigned char *a,const unsigned char *b,size_t len,
    const unsigned char *x,size_t xlen,const unsigned char *y,size_t ylen,int curve) {
    return curveImpl(curve)->muladd(a,b,len,x,xlen,y,ylen,curve);
}
static const br_ec_impl kCurves={
    (1u<<BR_EC_secp256r1)|(1u<<BR_EC_secp384r1)|(1u<<BR_EC_secp521r1),
    ecGenerator,ecOrder,ecXoff,ecMul,ecMulgen,ecMuladd
};

static int init(struct GhostTls *t, unsigned unixTime, const unsigned char *entropy) {
    static const uint16_t suites[] = {BR_TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256,
        BR_TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256};
    if (unixTime < 1735689600u || unixTime > 4102444800u) return GHOST_SERVICE_CLOCK;
    memset(t,0,sizeof(*t));
    br_ssl_client_zero(&t->client);
    br_ssl_engine_set_versions(&t->client.eng,BR_TLS12,BR_TLS12);
    br_ssl_engine_set_suites(&t->client.eng,suites,2);
    br_ssl_engine_set_prf_sha256(&t->client.eng,br_tls12_sha256_prf);
    br_ssl_engine_set_hash(&t->client.eng,br_sha256_ID,&br_sha256_vtable);
    br_ssl_engine_set_hash(&t->client.eng,br_sha384_ID,&br_sha384_vtable);
    br_ssl_engine_set_ec(&t->client.eng,&kCurves);
    br_ssl_engine_set_ecdsa(&t->client.eng,br_ecdsa_i15_vrfy_asn1);
    br_ssl_engine_set_rsavrfy(&t->client.eng,br_rsa_i15_pkcs1_vrfy);
    br_ssl_engine_set_aes_ctr(&t->client.eng,&br_aes_ct_ctr_vtable);
    br_ssl_engine_set_ghash(&t->client.eng,br_ghash_ctmul32);
    br_ssl_engine_set_gcm(&t->client.eng,&br_sslrec_in_gcm_vtable,&br_sslrec_out_gcm_vtable);
    br_x509_minimal_init(&t->cert,&br_sha256_vtable,ghost_roots,sizeof(ghost_roots)/sizeof(ghost_roots[0]));
    br_x509_minimal_set_hash(&t->cert,br_sha256_ID,&br_sha256_vtable);
    br_x509_minimal_set_hash(&t->cert,br_sha384_ID,&br_sha384_vtable);
    br_x509_minimal_set_rsa(&t->cert,br_rsa_i15_pkcs1_vrfy);
    br_x509_minimal_set_ecdsa(&t->cert,&kCurves,br_ecdsa_i15_vrfy_asn1);
    br_x509_minimal_set_time(&t->cert,719528u+unixTime/86400u,unixTime%86400u);
    br_ssl_engine_set_x509(&t->client.eng,&t->cert.vtable);
    br_ssl_engine_set_buffer(&t->client.eng,t->records,sizeof(t->records),0);
    br_ssl_engine_inject_entropy(&t->client.eng,entropy,32);
    return br_ssl_client_reset(&t->client,GHOST_SERVICE_HOST,0) ? 0 : GHOST_SERVICE_TLS;
}
int GhostTlsRequest(struct GhostTls *t,const struct GhostTlsIo *io,const char *path,
    const struct GhostTlsRequest *req,void *output,unsigned capacity,unsigned *used,unsigned unixTime,const unsigned char entropy[32]) {
    unsigned sent=0, length, i;
    int result=t->active?0:init(t,unixTime,entropy);
    if(result)return result;
    t->active=0;
    length=strlen(path);
    if(!length || length>700 || *path!='/')return GHOST_SERVICE_RESPONSE;
    for(i=0;i<length;++i)if((unsigned char)path[i]<=32 || (unsigned char)path[i]>=127)return GHOST_SERVICE_RESPONSE;
    if(req && (strcmp(req->method,"POST") && strcmp(req->method,"PUT")))return GHOST_SERVICE_RESPONSE;
    if(req && strlen(req->headers)+length+200>=sizeof(t->request))return GHOST_SERVICE_RESPONSE;
    strcpy(t->request,req?req->method:"GET");strcat(t->request," ");strcat(t->request,path);
    strcat(t->request," HTTP/1.1\r\nHost: " GHOST_SERVICE_HOST "\r\nUser-Agent: Moonshine/3.0\r\nAccept-Encoding: identity\r\nConnection: keep-alive\r\n");
    if(req){
        char digits[11];unsigned n=req->bytes,k=0;
        do{digits[k++]='0'+n%10;n/=10;}while(n);
        strcat(t->request,req->headers);strcat(t->request,"Content-Length: ");
        n=strlen(t->request);while(k)t->request[n++]=digits[--k];t->request[n]=0;
        strcat(t->request,"\r\n");
    }
    strcat(t->request,"\r\n");
    length=strlen(t->request);
    GhostHttpInit(&t->http,output,capacity);
    t->http.jsonResponse=req!=NULL;
    t->http.sink=io->sink; t->http.sinkContext=io->context;
    for(;;){
        unsigned state=br_ssl_engine_current_state(&t->client.eng);
        size_t n; unsigned char *p;
        result=io->wait(io->context); if(result<0)return result;
        if(state&BR_SSL_CLOSED)return GHOST_SERVICE_TLS;
        if(state&BR_SSL_SENDREC){
            p=br_ssl_engine_sendrec_buf(&t->client.eng,&n); if(n>2048)n=2048;
            result=io->send(io->context,p,(unsigned)n);
            if(result<0)return result;
            if(result){if((unsigned)result>n)return GHOST_SERVICE_NETWORK;br_ssl_engine_sendrec_ack(&t->client.eng,result);}
        } else if(state&BR_SSL_RECVAPP){
            p=br_ssl_engine_recvapp_buf(&t->client.eng,&n);
            if(!GhostHttpFeed(&t->http,p,(unsigned)n))return t->http.status==429?GHOST_SERVICE_RATE_LIMIT:
                t->http.status>=500?GHOST_SERVICE_UNAVAILABLE:GHOST_SERVICE_RESPONSE;
            br_ssl_engine_recvapp_ack(&t->client.eng,n);
            if(t->http.complete){*used=t->http.used;t->active=!t->http.close;return 0;}
        } else if((state&BR_SSL_SENDAPP) && sent<length+(req?req->bytes:0)){
            p=br_ssl_engine_sendapp_buf(&t->client.eng,&n);
            if(sent<length){if(n>length-sent)n=length-sent;memcpy(p,t->request+sent,n);}
            else{if(n>req->bytes-(sent-length))n=req->bytes-(sent-length);
                memcpy(p,(const unsigned char*)req->body+sent-length,n);}
            sent+=(unsigned)n;
            br_ssl_engine_sendapp_ack(&t->client.eng,n);
            if(sent==length+(req?req->bytes:0))br_ssl_engine_flush(&t->client.eng,0);
        } else if(state&BR_SSL_RECVREC){
            p=br_ssl_engine_recvrec_buf(&t->client.eng,&n);if(n>2048)n=2048;
            result=io->recv(io->context,p,(unsigned)n);
            if(result<0)return result;
            if(result){if((unsigned)result>n)return GHOST_SERVICE_NETWORK;br_ssl_engine_recvrec_ack(&t->client.eng,result);}
        }
    }
}
int GhostTlsGet(struct GhostTls *t,const struct GhostTlsIo *io,const char *path,
    void *output,unsigned capacity,unsigned *used,unsigned unixTime,const unsigned char entropy[32]) {
    return GhostTlsRequest(t,io,path,NULL,output,capacity,used,unixTime,entropy);
}
