#ifndef SUSAMUNE_DOLPHIN_FILES_HXX
#define SUSAMUNE_DOLPHIN_FILES_HXX
#include <Dolphin/types.h>
namespace DolphinFiles {
struct Entry { char name[32];u32 bytes,index; };
struct Result { s32 error;u32 bytes; };
void init();
bool available();
bool pending();
// Buffers remain owned by the request until take() completes.
u32 read(const char *name,void *out,u32 bytes,u32 offset=0);
u32 write(const char *name,const void *data,u32 bytes,u32 offset=0);
u32 create(const char *name,u32 bytes);
u32 remove(const char *name);
u32 list(Entry *out,u32 capacity);
bool take(u32 ticket,Result *out);
// Called only while Slot B is mounted and the retail CARD buffers are owned.
void perform(void *sector);
void fail(s32 error);
}
#endif
