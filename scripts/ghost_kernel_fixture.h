/* In-memory FatFS adapter for the unmodified production state machine. */
typedef __builtin_va_list va_list;
#define va_start(a,b) __builtin_va_start(a,b)
#define va_end(a) __builtin_va_end(a)
#define va_arg(a,t) __builtin_va_arg(a,t)
typedef unsigned long long size_t;
typedef _Bool bool;
#define true 1
#define false 0
#define NULL ((void*)0)
#include "susamune/ghost_storage.h"
#include "susamune/ghost_camera.h"
#include "susamune/data_paths.h"
#include "susamune/mod_bin.h"
#include "susamune/ghost_service.h"
typedef unsigned char u8;
typedef signed char s8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef signed int s32;
typedef unsigned long long u64;
typedef unsigned int UINT;
typedef unsigned int FSIZE_t;
typedef unsigned short WCHAR;
typedef WCHAR TCHAR;
typedef struct { int index; u32 position; } FIL;
typedef struct { u32 position; char path[128]; } DIR;
typedef struct { WCHAR fname[256]; u32 fsize; u8 fattrib; } FILINFO;
enum { FR_OK, FR_DISK_ERR, FR_NOT_READY, FR_NO_FILE, FR_NO_PATH,
       FR_WRITE_PROTECTED, FR_DENIED, FR_INVALID_DRIVE, FR_NO_FILESYSTEM,
       FR_EXIST, FR_INVALID_OBJECT };
enum { FA_READ=1, FA_WRITE=2, FA_OPEN_EXISTING=0, FA_CREATE_ALWAYS=4,
       FA_CREATE_NEW=8, AM_DIR=16 };
void *memcpy(void *d,const void *s,size_t n) { u8 *a=d; const u8 *b=s; while(n--) *a++=*b++; return d; }
void *memset(void *d,int c,size_t n) { u8 *a=d; while(n--) *a++=(u8)c; return d; }
int memcmp(const void *a,const void *b,size_t n) { const u8 *x=a,*y=b; while(n--) { if(*x!=*y) return *x-*y; ++x; ++y; } return 0; }
int strcmp(const char *a,const char *b) { while(*a && *a==*b) { ++a; ++b; } return (u8)*a-(u8)*b; }
static u32 length(const char *s) { u32 n=0; while(s[n]) ++n; return n; }
static void copystr(char *d,const char *s) { do { *d++=*s; } while(*s++); }
static size_t strlen(const char *s) { return length(s); }
static char *strcpy(char *d,const char *s) { copystr(d,s);return d; }
static char *strcat(char *d,const char *s) { copystr(d+length(d),s);return d; }
static int _sprintf(char *dst,const char *fmt,...) {
 char *out=dst; va_list args; va_start(args,fmt);
 while(*fmt) {
  if(*fmt!='%') { *out++=*fmt++; continue; }
  ++fmt; u32 width=0; char pad=' ';
  if(*fmt=='0') { pad='0'; ++fmt; }
  while(*fmt>='0' && *fmt<='9') width=width*10+(*fmt++-'0');
  if(*fmt=='s') { const char *s=va_arg(args,const char*); while(*s) *out++=*s++; }
  else if(*fmt=='c') *out++=(char)va_arg(args,int);
  else { u32 value=va_arg(args,u32),base=*fmt=='X'?16:10,n=0; char tmp[32];
   do { tmp[n++]="0123456789ABCDEF"[value%base]; value/=base; } while(value);
   while(width>n) { *out++=pad; --width; }
   while(n) *out++=tmp[--n];
  }
  ++fmt;
 }
 *out=0; va_end(args); return (int)(out-dst);
}
#define FIXTURE_FILES 60000
#define FIXTURE_WRITES 80
#define FIXTURE_FILE_BYTES 1400000
struct TestFile { char path[128]; const u8 *bytes; u32 size; int live; int writable; };
static struct TestFile testFiles[FIXTURE_FILES];
static u8 writePool[FIXTURE_WRITES][FIXTURE_FILE_BYTES];
static u32 testCount,writeCount,readBytes,readCalls,dirCalls,maxRead,failWriteAfter,writeBytes,openCalls;
static bool failSync;
static int directoryResult;
static int lookup(const char *path) { for(u32 i=0;i<testCount;++i) if(testFiles[i].live && !strcmp(testFiles[i].path,path)) return (int)i; return -1; }
static int f_open_char(FIL *f,const char *path,u32 flags) {
 ++openCalls;
 int i=lookup(path);
 if(flags&(FA_CREATE_ALWAYS|FA_CREATE_NEW)) {
  if(i>=0 && (flags&FA_CREATE_NEW)) return FR_EXIST;
  if(writeCount==FIXTURE_WRITES) return FR_DENIED;
  if(i<0) { if(testCount==FIXTURE_FILES) return FR_DENIED; i=(int)testCount++; copystr(testFiles[i].path,path); }
  testFiles[i].bytes=writePool[writeCount++]; testFiles[i].size=0; testFiles[i].live=1; testFiles[i].writable=1;
 }
 if(i<0) return FR_NO_FILE;
 f->index=i; f->position=0; return FR_OK;
}
static u32 f_size(FIL *f) { return testFiles[f->index].size; }
static int f_read(FIL *f,void *dst,UINT size,UINT *got) {
 struct TestFile *v=&testFiles[f->index]; ++readCalls;
 if(size>maxRead) maxRead=size;
 *got=size; if(*got>v->size-f->position) *got=v->size-f->position;
 memcpy(dst,v->bytes+f->position,*got); f->position+=*got; readBytes+=*got; return FR_OK;
}
static int f_write(FIL *f,const void *src,UINT size,UINT *got) {
 struct TestFile *v=&testFiles[f->index]; *got=size;
 if(writeBytes>=failWriteAfter) *got=0;
 else if(*got>failWriteAfter-writeBytes) *got=failWriteAfter-writeBytes;
 if(f->position+*got>FIXTURE_FILE_BYTES) *got=0;
 if(!v->writable) return FR_DENIED;
 memcpy((u8*)v->bytes+f->position,src,*got); f->position+=*got; writeBytes+=*got;
 if(f->position>v->size) v->size=f->position;
 return FR_OK;
}
static int f_lseek(FIL *f,u32 offset) { f->position=offset; return FR_OK; }
static int f_close(FIL *f) { (void)f; return FR_OK; }
static int f_sync(FIL *f) { (void)f; return failSync?FR_DISK_ERR:FR_OK; }
static int f_unlink_char(const char *path) { int i=lookup(path); if(i<0) return FR_NO_FILE; testFiles[i].live=0; return FR_OK; }
static int f_stat_char(const char *path,FILINFO *info) { int i=lookup(path); if(i<0) return FR_NO_FILE; memset(info,0,sizeof(*info)); info->fsize=testFiles[i].size; return FR_OK; }
static int f_mkdir_char(const char *path) { (void)path;return directoryResult; }
static int f_rename_char(const char *old,const char *dest) {
 int i=lookup(old);if(i<0)return FR_NO_FILE;if(lookup(dest)>=0)return FR_EXIST;
 copystr(testFiles[i].path,dest);return FR_OK;
}
static int f_opendir_char(DIR *dir,const char *path) { if(directoryResult) return directoryResult; dir->position=0; copystr(dir->path,path); return FR_OK; }
static int f_closedir(DIR *dir) { (void)dir; return FR_OK; }
static int f_readdir(DIR *dir,FILINFO *info) {
 ++dirCalls; memset(info,0,sizeof(*info)); u32 n=length(dir->path);
 while(dir->position<testCount) {
  struct TestFile *v=&testFiles[dir->position++];
  if(!v->live || memcmp(v->path,dir->path,n) || v->path[n]!='/') continue;
  const char *leaf=v->path+n+1; bool nested=false;
  for(u32 i=0;leaf[i];++i) if(leaf[i]=='/') nested=true;
  if(nested) continue;
  for(u32 i=0;;++i) { info->fname[i]=(u8)leaf[i]; if(!leaf[i]) break; }
  info->fsize=v->size; return FR_OK;
 }
 return FR_OK;
}
static const char *testStoragePrefix=MOONSHINE_DATA_ROOT;
static const char *SusamuneCfgStoragePrefix(void) { return testStoragePrefix; }
static bool SusamuneCfgStorageAvailable(void) { return true; }
static void sync_before_read(void *ptr,u32 size) { (void)ptr; (void)size; }
static void sync_after_write(void *ptr,u32 size) { (void)ptr; (void)size; }
u32 GAME_ID=SUSAMUNE_GHOST_GAME_ID_JP;
static struct SusamuneGhostStorageMailbox testMailbox;
static u8 testPayload[SUSAMUNE_GHOST_STORAGE_PAYLOAD_SIZE];
#undef SUSAMUNE_GHOST_STORAGE_PHYS_PTR
#undef SUSAMUNE_GHOST_STORAGE_DATA_PHYS_PTR
#define SUSAMUNE_GHOST_STORAGE_PHYS_PTR (&testMailbox)
#define SUSAMUNE_GHOST_STORAGE_DATA_PHYS_PTR testPayload

static u32 get_fattime(void) { return (46u<<25)|(9u<<21)|(6u<<16); }
static u32 GetCurrentTime(void) { return 1792900000u; }
#ifndef ALIGNED
#define ALIGNED(n) __attribute__((aligned(n)))
#endif
static bool webEnabled,webHold,webCancelled;
static const u8 *webData;
static u32 webSize,webRead,webRelease;
static int webResult;
static int GhostServiceStart(void *stage,unsigned size,const char *region,unsigned time,const struct GhostServiceEntry *entry,void *session) {
 (void)stage;(void)size;(void)region;(void)time;(void)entry;webRead=webRelease=0;webCancelled=false;return webEnabled;
}
static void GhostServiceCancel(void) { webCancelled=true; }
struct GhostAccountSecret { char access[48],refresh[48],user[48]; };
struct GhostAccount { struct GhostAccountSecret secret; char device[48],code[12]; unsigned expires,nextPoll,interval,changed; };
static int GhostAccountSecretValid(const struct GhostAccountSecret *s){return !memcmp(s->access,"dga_",4) && !memcmp(s->refresh,"dgr_",4) && !s->access[47] && !s->refresh[47];}
static int GhostServiceAction(void *stage,unsigned size,unsigned time,unsigned action,unsigned bytes,struct GhostAccount *account,void *session,const struct GhostServiceUpload *upload){
 (void)action;(void)bytes;(void)account;return GhostServiceStart(stage,size,"jp",time,NULL,session);
}
static void GhostServiceForget(void) { }
static unsigned GhostServiceProgress(void) { return GHOST_WEB_HTTP; }
static int GhostServicePoll(unsigned *bytes) {
 if(webHold)return 0;*bytes=webSize;return webCancelled?GHOST_SERVICE_CANCELLED:webResult?webResult:1;
}
static unsigned GhostServiceRead(void **data) {
 unsigned n=webSize-webRead;if(n>16384)n=16384;if(webHold || webCancelled)n=0;
 *data=(void*)(webData+webRead);return n;
}
static void GhostServiceReadAck(unsigned n) { webRead+=n; }
static void GhostServiceRelease(void) { ++webRelease; }

#ifndef TEST_TRANSFER_EXTERNAL
#include "susamune/transfer_layout.h"
#include "susamune/state_storage.h"
static bool SusamuneTransferActive(void) { return webEnabled; }
static bool SusamuneTransferAllows(u32 owner,u32 seq,u32 session,u32 command) {
 (void)owner;(void)seq;(void)session;(void)command;return true;
}
static bool SusamuneTransferCancelled(u32 owner) { (void)owner;return false; }
static u8 *SusamuneTransferGhostBase(void) { return testPayload; }
static u32 SusamuneTransferStageSize(void) { return SUSAMUNE_STATE_STAGING_SIZE; }
static u32 SusamuneTransferPoolSize(void) { return SUSAMUNE_STATE_POOL_EXPANDED_SIZE; }
static u8 *SusamuneTransferPoolPiece(u32 offset,u32 *size) { (void)offset;*size=0;return NULL; }
static bool SusamuneTransferPoolRange(u32 offset,u32 size) { return SusamuneStatePoolRange(offset,size); }
static bool SusamuneTransferImportRange(u32 offset,u32 size) { return SusamuneStateImportRange(offset,size); }
static bool SusamuneTransferWindowRange(u32 packed,u32 offset,u32 size) { return SusamuneStateWindowRange(packed,offset,size); }
#endif
