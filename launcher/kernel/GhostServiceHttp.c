#include "GhostServiceHttp.h"
#include <string.h>

static int equal(const char *a, const char *b) {
    while (*a && *b) {
        unsigned x = (unsigned char)*a++, y = (unsigned char)*b++;
        if (x >= 'A' && x <= 'Z') x += 32;
        if (y >= 'A' && y <= 'Z') y += 32;
        if (x != y) return 0;
    }
    return !*a && !*b;
}
static int number(const char *s, unsigned base, unsigned *out) {
    unsigned value = 0, n = 0;
    for (; *s && *s != ';'; ++s, ++n) {
        unsigned digit = (unsigned char)*s;
        if (digit >= '0' && digit <= '9') digit -= '0';
        else if (base == 16 && digit >= 'a' && digit <= 'f') digit -= 'a' - 10;
        else if (base == 16 && digit >= 'A' && digit <= 'F') digit -= 'A' - 10;
        else return 0;
        if (digit >= base || value > (0xffffffffu - digit) / base) return 0;
        value = value * base + digit;
    }
    if (!n || (base == 10 && *s)) return 0;
    *out = value;
    return 1;
}
void GhostHttpInit(struct GhostHttp *h, void *body, unsigned capacity) {
    memset(h, 0, sizeof(*h)); h->body = body; h->capacity = capacity;
}
static int line(struct GhostHttp *h) {
    char *s = h->line, *v, *end;
    if (h->state == 0) {
        if (strlen(s) < 12 || (memcmp(s, "HTTP/1.1 ", 9) && memcmp(s, "HTTP/1.0 ", 9)) ||
            s[9] < '0' || s[9] > '9' || s[10] < '0' || s[10] > '9' ||
            s[11] < '0' || s[11] > '9' || (s[12] && s[12] != ' ')) return 0;
        h->status = (s[9]-'0')*100u + (s[10]-'0')*10u + s[11]-'0';
        h->close = s[7] == '0';
        h->state = 1; return 1;
    }
    if (h->state == 3) {
        if (!number(s, 16, &h->left) || h->left > h->capacity - h->used) return 0;
        if (!h->left) { h->trailer = 1; h->state = 1; }
        else h->state = 4;
        return 1;
    }
    if (!*s) {
        if (h->trailer) { h->complete = 1; return 1; }
        /* Error bodies are never streamed into a ghost file. */
        if (h->status != 200 && (!h->jsonResponse || h->sink || h->status<200 ||
            (h->status>=300 && h->status<400))) return 0;
        if (h->encoding || (h->chunked && h->hasLength) || (!h->chunked && !h->hasLength)) return 0;
        h->state = h->chunked ? 3 : 2;
        if (!h->chunked && !h->left) h->complete = 1;
        return 1;
    }
    v = strchr(s, ':'); if (!v || v == s || *s == ' ' || *s == '\t') return 0;
    *v++ = 0;
    while (*v == ' ' || *v == '\t') ++v;
    end = v + strlen(v); while (end > v && (end[-1] == ' ' || end[-1] == '\t')) *--end = 0;
    if (h->trailer) return !equal(s, "content-length") && !equal(s, "transfer-encoding");
    if (equal(s, "content-length")) {
        if (h->hasLength || !number(v, 10, &h->left) || h->left > h->capacity) return 0;
        h->hasLength = 1;
    } else if (equal(s, "transfer-encoding")) {
        if (h->chunked || !equal(v, "chunked")) return 0;
        h->chunked = 1;
    } else if (equal(s, "content-encoding") && !equal(v, "identity")) h->encoding = 1;
    else if (equal(s, "connection") && equal(v, "close")) h->close = 1;
    else if (equal(s, "retry-after")) {
        unsigned n;if(number(v,10,&n))h->retryAfter=n;
        else if(strlen(v)<sizeof(h->retryDate))strcpy(h->retryDate,v);
    }
    else {
        char *dst = NULL; unsigned cap = 0, i;
        if (equal(s,"sb-request-id")) { dst=h->requestId; cap=sizeof(h->requestId); }
        else if (equal(s,"date")) { dst=h->date; cap=sizeof(h->date); }
        else if (equal(s,"cf-ray")) { dst=h->cfRay; cap=sizeof(h->cfRay); }
        else if (equal(s,"server-timing")) { dst=h->serverTiming; cap=sizeof(h->serverTiming); }
        if (dst) { for(i=0;v[i] && i+1<cap;++i) dst[i]=(unsigned char)v[i]>=32 && (unsigned char)v[i]<127?v[i]:'?'; dst[i]=0; }
    }
    return 1;
}
int GhostHttpFeed(struct GhostHttp *h, const void *data, unsigned bytes) {
    const unsigned char *p = data;
    h->responseBytes += bytes;
    if (h->error || (h->complete && bytes)) return 0;
    while (bytes) {
        unsigned n;
        if (h->complete) goto bad;
        if (h->state == 2 || h->state == 4) {
            n = bytes < h->left ? bytes : h->left;
            if (n > h->capacity - h->used) goto bad;
            if (h->sink) { if (!h->sink(h->sinkContext,p,n)) goto bad; }
            else memcpy(h->body + h->used, p, n);
            h->used += n; h->left -= n; p += n; bytes -= n;
            if (!h->left) { if (h->state == 2) h->complete = 1; else h->state = 5; }
            continue;
        }
        if (h->state == 5 || h->state == 6) {
            if (*p++ != (h->state == 5 ? '\r' : '\n')) goto bad;
            --bytes; h->state = h->state == 5 ? 6 : 3; continue;
        }
        if (++h->headers > 16384u || h->lineSize + 1 >= sizeof(h->line)) goto bad;
        h->line[h->lineSize++] = *p++; --bytes;
        if (h->line[h->lineSize-1] == '\n') {
            if (h->lineSize < 2 || h->line[h->lineSize-2] != '\r') goto bad;
            h->line[h->lineSize-2] = 0;
            if (!line(h)) goto bad;
            h->lineSize = 0;
        } else if (h->line[h->lineSize-1] == 0) goto bad;
    }
    return 1;
bad:
    h->error = 1; return 0;
}
unsigned GhostHttpRetryDelay(const struct GhostHttp *h,unsigned now) {
    const char *s=h->retryDate;
    static const char months[]="JanFebMarAprMayJunJulAugSepOctNovDec";
    static const unsigned char days[]={31,28,31,30,31,30,31,31,30,31,30,31};
    unsigned year=0,month,day,hour,minute,second,i,total=0,stamp;
    if(h->retryAfter)return h->retryAfter;
    if(strlen(s)!=29 || s[3]!=',' || s[4]!=' ' || s[7]!=' ' || s[11]!=' ' ||
        s[16]!=' ' || s[19]!=':' || s[22]!=':' || strcmp(s+25," GMT"))return 0;
    for(i=0;i<4;++i){if(s[12+i]<'0'||s[12+i]>'9')return 0;year=year*10+s[12+i]-'0';}
    if(year<1970 || year>2100)return 0;
    for(month=0;month<12;++month)if(!memcmp(s+8,months+month*3,3))break;
    if(month==12)return 0;
    for(i=0;i<4;++i){unsigned at=i==0?5:i==1?17:i==2?20:23;
        if(s[at]<'0'||s[at]>'9'||s[at+1]<'0'||s[at+1]>'9')return 0;}
    day=(s[5]-'0')*10+s[6]-'0';hour=(s[17]-'0')*10+s[18]-'0';
    minute=(s[20]-'0')*10+s[21]-'0';second=(s[23]-'0')*10+s[24]-'0';
    if(!day || day>days[month]+(month==1 && year%4==0 && (year%100!=0 || year%400==0)) || hour>23 || minute>59 || second>59)return 0;
    for(i=1970;i<year;++i)total+=365+(i%4==0 && (i%100!=0 || i%400==0));
    for(i=0;i<month;++i)total+=days[i]+(i==1 && year%4==0 && (year%100!=0 || year%400==0));
    stamp=(total+day-1)*86400u+hour*3600u+minute*60u+second;
    return stamp>now?stamp-now:0;
}
