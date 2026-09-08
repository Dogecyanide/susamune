#ifndef SUSAMUNE_STATE_STORAGE_HXX
#define SUSAMUNE_STATE_STORAGE_HXX
#include <Dolphin/types.h>
#include "susamune/state_storage.h"
namespace StateStorage {
struct Result {
    u32 command, status, id;
    SusamuneStateArchiveHeader header;
    const void *metadata;
};
void init();
void update();
bool available();
bool busy();
u32 configId();
bool startExport(const SusamuneStateArchiveHeader &, const void *metadata, u32 poolOffset);
bool startImport(u32 id, u32 expectedHeaderCrc, u32 packedSize, u32 freePoolOffset);
bool refresh(u32 afterId = 0);
// Cancellation retains ownership until the ARM has closed the old operation.
bool cancel();
// Borrowed metadata stays valid until another request is accepted.
bool takeResult(Result &);
bool catalogReady();
const SusamuneStateCatalog &catalog();
}
#endif
