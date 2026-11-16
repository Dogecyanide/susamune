#include "GhostServiceJson.h"
#include "susamune/ghost_format.h"
#include <string.h>
#define field GhostJsonField
#define string GhostJsonString
#define integer GhostJsonInteger

static void space(struct GhostJson *j) {
    while (j->pos < j->size && (j->text[j->pos] == ' ' || j->text[j->pos] == '\n' ||
        j->text[j->pos] == '\r' || j->text[j->pos] == '\t')) ++j->pos;
}
static int hex(unsigned c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}
static int value(struct GhostJson *j, unsigned depth) {
    unsigned id, c, n;
    struct GhostJsonToken *t;
    space(j);
    if (depth > 20 || j->count == 2048 || j->pos == j->size) return -1;
    id = ++j->count; t = &j->tokens[id-1];
    t->start = j->pos; c = j->text[j->pos++]; t->type = c;
    if (c == '{' || c == '[') {
        unsigned close = c == '{' ? '}' : ']';
        space(j);
        if (j->pos < j->size && j->text[j->pos] == close) ++j->pos;
        else for (;;) {
            if (c == '{') {
                space(j);
                if (j->pos == j->size || j->text[j->pos] != '"' || value(j, depth+1) < 0) return -1;
                space(j); if (j->pos == j->size || j->text[j->pos++] != ':') return -1;
            }
            if (value(j, depth+1) < 0) return -1;
            space(j); if (j->pos == j->size) return -1;
            n = j->text[j->pos++]; if (n == close) break;
            if (n != ',') return -1;
        }
    } else if (c == '"') {
        for (;;) {
            if (j->pos == j->size) return -1;
            n = (unsigned char)j->text[j->pos++];
            if (n == '"') break;
            if (n < 32) return -1;
            if (n == '\\') {
                if (j->pos == j->size) return -1;
                n = j->text[j->pos++];
                if (n == 'u') {
                    unsigned k;
                    for (k=0; k<4; ++k) if (j->pos == j->size || hex(j->text[j->pos++]) < 0) return -1;
                } else if (!strchr("\"\\/bfnrt", n)) return -1;
            }
        }
    } else {
        const char *literal = c == 'n' ? "null" : c == 't' ? "true" : c == 'f' ? "false" : 0;
        if (literal) {
            unsigned len = strlen(literal);
            if (len > j->size - t->start || memcmp(j->text+t->start, literal, len)) return -1;
            j->pos = t->start + len;
        } else {
            /* Metadata can contain decimals; selected integer fields are checked below. */
            j->pos = t->start;
            if (j->text[j->pos] == '-') ++j->pos;
            if (j->pos == j->size || j->text[j->pos] < '0' || j->text[j->pos] > '9') return -1;
            if (j->text[j->pos++] != '0')
                while (j->pos < j->size && j->text[j->pos] >= '0' && j->text[j->pos] <= '9') ++j->pos;
            if (j->pos < j->size && j->text[j->pos] == '.') {
                n = ++j->pos;
                while (j->pos < j->size && j->text[j->pos] >= '0' && j->text[j->pos] <= '9') ++j->pos;
                if (n == j->pos) return -1;
            }
            if (j->pos < j->size && (j->text[j->pos] == 'e' || j->text[j->pos] == 'E')) {
                ++j->pos;
                if (j->pos < j->size && (j->text[j->pos] == '+' || j->text[j->pos] == '-')) ++j->pos;
                n = j->pos;
                while (j->pos < j->size && j->text[j->pos] >= '0' && j->text[j->pos] <= '9') ++j->pos;
                if (n == j->pos) return -1;
            }
        }
    }
    t->end = j->pos; t->next = j->count + 1;
    return (int)id;
}
unsigned field(struct GhostJson *j, unsigned obj, const char *name) {
    unsigned i, found = 0, len = strlen(name);
    if (!obj || j->tokens[obj-1].type != '{') return 0;
    for (i=obj+1; i<j->tokens[obj-1].next;) {
        struct GhostJsonToken *key = &j->tokens[i-1];
        unsigned val = i+1;
        if (key->end - key->start == len+2 && !memcmp(j->text+key->start+1, name, len)) {
            if (found) return 0;
            found = val;
        }
        i = j->tokens[val-1].next;
    }
    return found;
}
int integer(struct GhostJson *j, unsigned id, unsigned *out) {
    unsigned i, v=0;
    if (!id) return 0;
    for (i=j->tokens[id-1].start; i<j->tokens[id-1].end; ++i) {
        unsigned c = (unsigned char)j->text[i];
        if (c < '0' || c > '9' || v > (0xffffffffu - (c-'0'))/10u) return 0;
        v = v*10 + c-'0';
    }
    *out=v; return 1;
}
int string(struct GhostJson *j, unsigned id, char *out, unsigned cap, int label) {
    unsigned i, end, used=0;
    if (!id || j->tokens[id-1].type != '"') return 0;
    i=j->tokens[id-1].start+1; end=j->tokens[id-1].end-1;
    while (i < end) {
        unsigned c = (unsigned char)j->text[i++];
        if (c == '\\') {
            c=j->text[i++];
            if (c=='u') { unsigned k; c=0; for(k=0;k<4;++k)c=c*16+hex(j->text[i++]); }
            else if (c != '\\' && c != '/' && c != '"') c=' ';
        }
        if (c < 32 || c > 126) { if (!label) return 0; c='?'; }
        if (used+1 >= cap) { if (!label) return 0; continue; }
        out[used++]=(char)c;
    }
    out[used]=0; return 1;
}
int GhostServicePathValid(const char *path) {
    unsigned i, segment=0, dots=1, prefix=sizeof(GHOST_SERVICE_STORAGE)-1;
    if (strncmp(path,GHOST_SERVICE_STORAGE,prefix)) return 0;
    for (i=prefix; i<384 && path[i]; ++i) {
        unsigned c=(unsigned char)path[i];
        if (!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||strchr("-._~/%",c))) return 0;
        if(c=='%') {
            int high,low;
            if(i+2>=384 || !path[i+1] || !path[i+2] ||
                (high=hex(path[i+1]))<0 || (low=hex(path[i+2]))<0)return 0;
            c=(high<<4)|low;i+=2;
            /* Keep decoding from changing path boundaries or adding another escape. */
            if(c<32 || c==127 || c=='/' || c=='\\' || c=='%' || c=='?' || c=='#')return 0;
        }
        if(c=='/') {
            if(!segment || (dots && segment<=2))return 0;
            segment=0;dots=1;
        }else{++segment;if(c!='.')dots=0;}
    }
    return i<384 && segment && !(dots && segment<=2);
}
int GhostJsonParse(struct GhostJson *j,const void *data,unsigned size) {
    j->text=data;j->size=size;j->pos=j->count=0;
    if(size>32768 || value(j,0)!=1 || j->tokens[0].type!='{')return 0;
    space(j);return j->pos==size;
}
int GhostServiceEntryValid(const struct GhostServiceEntry *e) {
    return e->bytes >= SUSAMUNE_GHOST_FILE_HEADER_SIZE && e->bytes <= SUSAMUNE_GHOST_MAX_FILE_SIZE &&
        GhostServicePathValid(e->path);
}
int GhostServiceParsePage(struct GhostJson *j, const void *data, unsigned size, struct GhostServicePage *page) {
    unsigned i, items, v, cursor;
    memset(page,0,sizeof(*page));
    j->text=data; j->size=size; j->pos=j->count=0;
    if (size > 32768 || value(j,0) != 1) return 0;
    space(j); if(j->pos!=size)return 0;
    if (!integer(j,field(j,1,"api_version"),&v)||v!=1 ||
        !integer(j,field(j,1,"catalogue_schema"),&v)||v!=1 ||
        !integer(j,field(j,1,"total"),&page->total))return 0;
    items=field(j,1,"items"); cursor=field(j,1,"next_cursor");
    if(!items || j->tokens[items-1].type!='[' || !cursor)return 0;
    if(j->tokens[cursor-1].type!='n' && !string(j,cursor,page->next,sizeof(page->next),0))return 0;
    for(i=items+1;i<j->tokens[items-1].next;i=j->tokens[i-1].next){
        struct GhostServiceEntry *e;
        unsigned file, author, timing, k; char sha[65], url[448];
        static const char origin[]="https://" GHOST_SERVICE_HOST;
        if(page->count==GHOST_SERVICE_PAGE_COUNT)return 0;
        e=&page->entries[page->count++];
        file=field(j,i,"file"); author=field(j,i,"author"); timing=field(j,i,"timing");
        if(!string(j,field(j,i,"title"),e->title,sizeof(e->title),1)||
           !string(j,field(j,i,"id"),e->id,sizeof(e->id),0)||
           !string(j,field(j,author,"username"),e->author,sizeof(e->author),1)||
           !string(j,field(j,file,"sha256"),sha,sizeof(sha),0)||strlen(sha)!=64||
           !integer(j,field(j,file,"byte_length"),&e->bytes)||
           !string(j,field(j,file,"download_url"),url,sizeof(url),0)||
           strncmp(url,origin,sizeof(origin)-1))return 0;
        if(strlen(url+sizeof(origin)-1)>=sizeof(e->path))return 0;
        strcpy(e->path,url+sizeof(origin)-1);
        if(!GhostServiceEntryValid(e))return 0;
        for(k=0;k<32;++k){int a=hex(sha[k*2]),b=hex(sha[k*2+1]);if(a<0||b<0)return 0;e->sha256[k]=(a<<4)|b;}
        e->resultQf=SUSAMUNE_GHOST_RESULT_QF_NONE;
        v=field(j,timing,"result_qf");
        if(!v || (j->tokens[v-1].type!='n' &&
           (!integer(j,v,&e->resultQf) || e->resultQf>SUSAMUNE_GHOST_QF_MAX)) ||
           !integer(j,field(j,timing,"duration_qf"),&e->durationQf) ||
           e->durationQf>SUSAMUNE_GHOST_QF_MAX)return 0;
    }
    page->magic=GHOST_SERVICE_PAGE_MAGIC; return 1;
}
int GhostServiceRouteSortSupported(struct GhostJson *j,const void *data,unsigned size) {
    unsigned list,i;
    j->text=data;j->size=size;j->pos=j->count=0;
    if(size>32768 || value(j,0)!=1)return 0;
    space(j);if(j->pos!=size)return 0;
    list=field(j,field(j,1,"catalogue"),"sorts");
    if(!list || j->tokens[list-1].type!='[')return 0;
    for(i=list+1;i<j->tokens[list-1].next;i=j->tokens[i-1].next) {
        char name[24];if(string(j,i,name,sizeof(name),0) && !strcmp(name,"route"))return 1;
    }
    return 0;
}
