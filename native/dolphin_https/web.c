#include "susamune/dolphin_web_api.h"
#include "../../../launcher/kernel/GhostServiceJson.h"
#include <string.h>
typedef unsigned char u8;typedef unsigned short u16;typedef unsigned int u32;typedef int s32;
typedef _Bool bool;
#define true 1
#define false 0
enum ValidateResult {VALIDATE_INVALID,VALIDATE_OK,VALIDATE_FORWARD};
#include "../../../launcher/kernel/GhostCanonical.inc"
static struct GhostJson *json(void) { return (struct GhostJson *)DOLPHIN_WEB_JSON_BASE; }
typedef char JsonFits[(DOLPHIN_WEB_JSON_BASE+sizeof(struct GhostJson)<=DOLPHIN_HTTPS_IMAGE_BASE)?1:-1];
static int append(char *out,unsigned cap,const char *text) {
    unsigned used=strlen(out),n=strlen(text);
    if(used>=cap || n>=cap-used)return 0;
    memcpy(out+used,text,n+1);return 1;
}
static int number(char *out,unsigned cap,unsigned value) {
    char text[11];unsigned n=10;text[n]=0;
    do{text[--n]='0'+value%10;value/=10;}while(value);
    return append(out,cap,text+n);
}
static int query(const struct GhostServiceQuery *q,unsigned region,char *out,unsigned cap) {
    unsigned i,n;static const char hex[]="0123456789ABCDEF";
    if(!q || !out || !cap || region<1 || region>3 || q->sortRoute>1 || q->filter>>24 ||
       (q->filter&255)>61 || ((q->filter>>8)&255)>10 ||
       (q->filter && (!(q->filter&255) || !((q->filter>>8)&255))))return 0;
    for(n=0;n<sizeof(q->cursor) && q->cursor[n];++n){}
    if(n==sizeof(q->cursor))return 0;
    out[0]=0;
    if(!append(out,cap,GHOST_SERVICE_API "/ghosts?limit=4&sort=") ||
       !append(out,cap,q->sortRoute?"route":"newest") || !append(out,cap,"&playable_on=") ||
       !append(out,cap,region==1?"jp":region==2?"us":"pal"))return 0;
    if(q->filter && (!append(out,cap,"&area=") || !number(out,cap,(q->filter&255)-1) ||
       !append(out,cap,"&episode=") || !number(out,cap,((q->filter>>8)&255)-1)))return 0;
    if(!n)return 1;
    if(!append(out,cap,"&cursor="))return 0;
    for(i=0;i<n;++i){
        unsigned c=(unsigned char)q->cursor[i];char text[4]={0};
        if((c>='A'&&c<='Z') || (c>='a'&&c<='z') || (c>='0'&&c<='9') || strchr("-._~",c))text[0]=c;
        else{text[0]='%';text[1]=hex[c>>4];text[2]=hex[c&15];}
        if(!append(out,cap,text))return 0;
    }
    return 1;
}
static int page(const void *data,unsigned size,struct GhostServicePage *out) {
    return GhostServiceParsePage(json(),data,size,out);
}
static int routeSort(const void *data,unsigned size) {
    return GhostServiceRouteSortSupported(json(),data,size);
}
static int describe(const void *data,unsigned bytes,unsigned profile,unsigned region,int imported,struct SusamuneGhostSlotInfo *out) {
    unsigned game=region==1?SUSAMUNE_GHOST_GAME_ID_JP:region==2?SUSAMUNE_GHOST_GAME_ID_US:SUSAMUNE_GHOST_GAME_ID_PAL;
    unsigned gameRegion=region==1?SUSAMUNE_GHOST_REGION_JP:region==2?SUSAMUNE_GHOST_REGION_US:SUSAMUNE_GHOST_REGION_PAL;
    if(!data || !out || region<1 || region>3 || profile>0xffff)return 0;
    if(ValidateCanonicalHeader(data,bytes,profile,imported!=0,game,gameRegion)!=VALIDATE_OK)return 0;
    FillInfo(out,data,ReadBe32((const u8 *)data+12),imported?SUSAMUNE_GHOST_SLOT_IMPORTED:0);return 1;
}
int moonshine_catalog_slot(const struct SusamuneGhostSlotInfo *,struct SusamuneGhostSlotInfo *,unsigned,unsigned);
__attribute__((section(".webapi"),used)) const struct DolphinWebApi moonshine_web_api={
    DOLPHIN_WEB_API_MAGIC,3,sizeof(struct DolphinWebApi),query,page,GhostServiceEntryValid,routeSort,describe,moonshine_catalog_slot
};
