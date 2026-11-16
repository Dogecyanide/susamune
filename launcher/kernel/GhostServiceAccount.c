#include "GhostServiceAccount.h"
#include <string.h>
#define FIELD(j,o,k) GhostJsonField(j,o,k)
static int text(struct GhostJson *j,unsigned obj,const char *key,char *out,unsigned size) {
    return GhostJsonString(j,FIELD(j,obj,key),out,size,0);
}
static int token(const char *s,const char *prefix) {
    unsigned i;
    if(memcmp(s,prefix,4) || s[47])return 0;
    for(i=4;i<47;++i)if(!((s[i]>='a'&&s[i]<='z')||(s[i]>='A'&&s[i]<='Z')||
        (s[i]>='0'&&s[i]<='9')||s[i]=='_'||s[i]=='-'))return 0;
    return 1;
}
int GhostAccountSecretValid(const struct GhostAccountSecret *s) {
    return token(s->access,"dga_") && token(s->refresh,"dgr_") && memchr(s->user,0,sizeof(s->user));
}
void GhostAccountInfo(const struct GhostAccount *a,unsigned now,struct GhostServiceAccountInfo *out) {
    memset(out,0,sizeof(*out));out->magic=GHOST_SERVICE_ACCOUNT_MAGIC;
    out->linked=GhostAccountSecretValid(&a->secret);
    out->pending=a->device[0] && now<a->expires;
    out->retrySeconds=a->nextPoll>now?a->nextPoll-now:0;
    memcpy(out->code,a->code,sizeof(out->code));memcpy(out->user,a->secret.user,sizeof(out->user));
}
static int prepare(struct GhostAccountWork *w,const char *method,
    const char *suffix,const char *access,const void *body,unsigned bytes,int binary,const char *key) {
    strcpy(w->path,GHOST_SERVICE_API);strcat(w->path,suffix);
    strcpy(w->headers,binary?"Content-Type: application/octet-stream\r\n":"Content-Type: application/json\r\n");
    if(access){strcat(w->headers,"Authorization: Bearer ");strcat(w->headers,access);strcat(w->headers,"\r\n");}
    if(key){strcat(w->headers,"Idempotency-Key: ");strcat(w->headers,key);strcat(w->headers,"\r\n");}
    w->request.method=method;w->request.headers=w->headers;w->request.body=body;w->request.bytes=bytes;
    return 1;
}
static int response(struct GhostAccountWork *w,int transport,unsigned used,unsigned status) {
    char error[48];memset(w->headers,0,sizeof(w->headers));
    if(transport)return transport;
    if(used>w->capacity)return GHOST_SERVICE_RESPONSE;
    if(status==429)return GHOST_SERVICE_RATE_LIMIT;
    if(status>=500)return GHOST_SERVICE_UNAVAILABLE;
    if(!GhostJsonParse(w->json,w->response,used))return GHOST_SERVICE_RESPONSE;
    if(status>=200 && status<300)return 0;
    if(status==401)return GHOST_SERVICE_LINK_REQUIRED;
    if(text(w->json,FIELD(w->json,1,"error"),"code",error,sizeof(error))) {
        if(!strcmp(error,"authorization_pending") || !strcmp(error,"slow_down"))return 1;
        if(!strcmp(error,"expired_token") || !strcmp(error,"access_denied") || !strcmp(error,"invalid_grant"))return GHOST_SERVICE_LINK_EXPIRED;
        if(!strcmp(error,"account_limit_reached") || !strcmp(error,"too_many_open_uploads"))return GHOST_SERVICE_ACCOUNT_LIMIT;
    }
    return GHOST_SERVICE_UPLOAD_REJECTED;
}
static int tokens(struct GhostAccount *a,struct GhostJson *j) {
    struct GhostAccountSecret s;
    memset(&s,0,sizeof(s));
    if(!text(j,1,"access_token",s.access,sizeof(s.access)) ||
        !text(j,1,"refresh_token",s.refresh,sizeof(s.refresh)) ||
        !GhostJsonString(j,FIELD(j,FIELD(j,1,"user"),"username"),s.user,sizeof(s.user),1) ||
        !GhostAccountSecretValid(&s)){memset(&s,0,sizeof(s));return GHOST_SERVICE_RESPONSE;}
    a->secret=s;a->changed=1;memset(&s,0,sizeof(s));memset(a->device,0,sizeof(a->device));a->code[0]=0;
    return 0;
}
static void jsonToken(char *body,const char *key,const char *value) {
    strcpy(body,"{\"");strcat(body,key);strcat(body,"\":\"");strcat(body,value);strcat(body,"\"}");
}
static void decimal(char *out,unsigned value) {
    char digits[11];unsigned n=0;do{digits[n++]='0'+value%10;value/=10;}while(value);
    out+=strlen(out);while(n)*out++=digits[--n];*out=0;
}
enum AccountStep { ACCOUNT_DONE, ACCOUNT_CODE, ACCOUNT_TOKEN, ACCOUNT_REVOKE,
    ACCOUNT_REFRESH, ACCOUNT_METADATA, ACCOUNT_CONTENT, ACCOUNT_PUBLISH };
int GhostAccountBegin(struct GhostAccount *a,struct GhostAccountWork *w,struct GhostAccountFlow *f,
    unsigned op,unsigned now,const void *ghost,unsigned bytes) {
    memset(f,0,sizeof(*f));f->now=now;f->ghost=ghost;f->bytes=bytes;
    if(op==GHOST_ACCOUNT_STATUS)return 0;
    if(op==GHOST_ACCOUNT_UNLINK) {
        if(a->secret.refresh[0]){jsonToken(w->body,"token",a->secret.refresh);f->step=ACCOUNT_REVOKE;
            return prepare(w,"POST","/device/revoke",NULL,w->body,strlen(w->body),0,NULL);}
        memset(a,0,sizeof(*a));a->changed=1;return 0;
    }
    if(op==GHOST_ACCOUNT_LINK) {
        if(GhostAccountSecretValid(&a->secret) || (a->device[0] && now<a->expires))return 0;
        strcpy(w->body,w->clientName && !strcmp(w->clientName,"Moonshine Dolphin")?
            "{\"client_name\":\"Moonshine Dolphin\",\"client_version\":\"3.0.0\"}":
            "{\"client_name\":\"Moonshine Wii\",\"client_version\":\"3.0.0\"}");
        f->step=ACCOUNT_CODE;return prepare(w,"POST","/device/code",NULL,w->body,strlen(w->body),0,NULL);
    }
    if(op==GHOST_ACCOUNT_POLL) {
        if(GhostAccountSecretValid(&a->secret))return 0;
        if(!a->device[0] || now>=a->expires)return GHOST_SERVICE_LINK_EXPIRED;
        if(now<a->nextPoll)return 0;
        jsonToken(w->body,"device_code",a->device);a->nextPoll=now+60;f->step=ACCOUNT_TOKEN;
        return prepare(w,"POST","/device/token",NULL,w->body,strlen(w->body),0,NULL);
    }
    if(op!=GHOST_ACCOUNT_UPLOAD || !GhostAccountSecretValid(&a->secret))return GHOST_SERVICE_LINK_REQUIRED;
    if(!GhostServiceDescriptionValid(w->upload.description) || !ghost || !bytes)return GHOST_SERVICE_UPLOAD_REJECTED;
    /* The backend durably clears the old token before starting a rotation. */
    jsonToken(w->body,"refresh_token",a->secret.refresh);memset(&a->secret,0,sizeof(a->secret));a->changed=1;
    f->step=ACCOUNT_REFRESH;return prepare(w,"POST","/device/refresh",NULL,w->body,strlen(w->body),0,NULL);
}
int GhostAccountNext(struct GhostAccount *a,struct GhostAccountWork *w,struct GhostAccountFlow *f,
    int transport,unsigned used,unsigned status) {
    struct GhostJson *j=w->json;unsigned n;int r;char suffix[80],result[32];
    if(!f->step)return GHOST_SERVICE_RESPONSE;
    r=response(w,transport,used,status);
    if(f->step==ACCOUNT_REVOKE){memset(a,0,sizeof(*a));a->changed=1;f->step=ACCOUNT_DONE;return 0;}
    if(f->step==ACCOUNT_TOKEN && r==1){
        if(GhostJsonInteger(j,FIELD(j,1,"interval"),&n) && n>=5 && n<=60)a->interval=n;
        a->nextPoll=f->now+a->interval;f->step=ACCOUNT_DONE;return 0;
    }
    if(r){f->step=ACCOUNT_DONE;return r==1?GHOST_SERVICE_RESPONSE:r;}
    switch(f->step){
    case ACCOUNT_CODE:
        if(!text(j,1,"device_code",a->device,sizeof(a->device)) || !token(a->device,"dgd_") ||
            !text(j,1,"user_code",a->code,sizeof(a->code)) ||
            !GhostJsonInteger(j,FIELD(j,1,"expires_in"),&n) || !n || n>600){r=GHOST_SERVICE_RESPONSE;break;}
        a->expires=f->now+n;a->interval=5;
        if(GhostJsonInteger(j,FIELD(j,1,"interval"),&n) && n>=5 && n<=60)a->interval=n;
        a->nextPoll=f->now+a->interval;break;
    case ACCOUNT_TOKEN:r=tokens(a,j);break;
    case ACCOUNT_REFRESH: {
        br_sha256_context sha;unsigned char digest[32];static const char hex[]="0123456789abcdef";
        if((r=tokens(a,j)))break;
        br_sha256_init(&sha);br_sha256_update(&sha,f->ghost,f->bytes);br_sha256_out(&sha,digest);
        for(n=0;n<32;++n){f->hash[n*2]=hex[digest[n]>>4];f->hash[n*2+1]=hex[digest[n]&15];}f->hash[64]=0;
        strcpy(w->body,"{\"byte_length\":");decimal(w->body,f->bytes);strcat(w->body,",\"sha256\":\"");strcat(w->body,f->hash);
        strcat(w->body,"\",\"filename\":\"moonshine.smsghost\",\"tas_declared\":null");
        if(w->upload.description[0]) {
            char *p;unsigned encoded;
            /* Escaped ASCII is at most 2x; kana UTF-8 is 1.5x. */
            strcat(w->body,",\"description\":\"");p=w->body+strlen(w->body);
            encoded=MoonshineKanaJson(p,sizeof(w->body)-(unsigned)(p-w->body)-2,w->upload.description);
            if(!encoded){r=GHOST_SERVICE_UPLOAD_REJECTED;break;}
            p+=encoded-1;*p++='"';*p=0;
        }
        strcat(w->body,"}");f->step=ACCOUNT_METADATA;
        return prepare(w,"POST","/uploads",a->secret.access,w->body,strlen(w->body),0,f->hash);
    }
    case ACCOUNT_METADATA:
        if(text(j,1,"result",result,sizeof(result)) && !strcmp(result,"already_published"))break;
        if(!text(j,FIELD(j,1,"upload"),"upload_id",f->uploadId,sizeof(f->uploadId)) || strlen(f->uploadId)!=36){r=GHOST_SERVICE_RESPONSE;break;}
        for(n=0;n<36;++n)if(!((f->uploadId[n]>='0'&&f->uploadId[n]<='9')||(f->uploadId[n]>='a'&&f->uploadId[n]<='f')||f->uploadId[n]=='-')){r=GHOST_SERVICE_RESPONSE;break;}
        if(r)break;
        strcpy(suffix,"/uploads/");strcat(suffix,f->uploadId);strcat(suffix,"/content");f->step=ACCOUNT_CONTENT;
        return prepare(w,"PUT",suffix,a->secret.access,f->ghost,f->bytes,1,NULL);
    case ACCOUNT_CONTENT:
        strcpy(suffix,"/uploads/");strcat(suffix,f->uploadId);strcat(suffix,"/publish");f->step=ACCOUNT_PUBLISH;
        return prepare(w,"POST",suffix,a->secret.access,NULL,0,0,NULL);
    case ACCOUNT_PUBLISH:break;
    default:r=GHOST_SERVICE_RESPONSE;break;
    }
    f->step=ACCOUNT_DONE;return r;
}
int GhostAccountRun(struct GhostAccount *a,struct GhostAccountWork *w,unsigned op,
    unsigned now,const void *ghost,unsigned bytes,GhostAccountHttp http) {
    struct GhostAccountFlow f;int r=GhostAccountBegin(a,w,&f,op,now,ghost,bytes);
    while(r==1){unsigned used=0,status=0;
        r=http(w->path,&w->request,w->response,w->capacity,&used,&status);
        r=GhostAccountNext(a,w,&f,r,used,status);
    }
    return r;
}
