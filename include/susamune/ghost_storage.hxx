#ifndef _SUSAMUNE_GHOST_STORAGE_HXX
#define _SUSAMUNE_GHOST_STORAGE_HXX

#include <Dolphin/types.h>
#include "susamune/ghost_storage.h"

namespace GhostStorage {

// Copy a selection before changing pages; rows themselves are only cache indices.
struct Identity {
    u32 id;
    u32 generation;
    u16 flags;
    u8 profile;
    u8 region;
    u8 nameLength;
    u8 reserved[3];
    char leaf[SUSAMUNE_GHOST_IMPORT_LEAF_SIZE];
    char name[SUSAMUNE_GHOST_NAME_SIZE];
};

void init();
void update();
void onSavestateLoaded();

bool refresh();
bool refreshImported();
bool refreshPage(bool imported, u32 offset);
bool scanImports();
u32 pageOffset(bool imported);
u32 pageCount(bool imported);
u32 totalCount(bool imported);
bool copyIdentity(bool imported, int row, Identity *out);
bool copyIdentityName(const Identity &identity, char *out, u32 size);
bool identityValid(const Identity &identity);
bool sameIdentity(const Identity &a, const Identity &b);
bool isLoaded(const Identity &identity);

bool saveNew(u32 expectedSelectionToken = 0);
bool load(const Identity &identity);
bool loadObserver(const Identity &identity, bool secondary);
bool remove(const Identity &identity);
bool exportShare(const Identity &identity);

// Integer arguments address rows in the current page, never persistent IDs.
bool save(int row);
bool save(int row, u32 expectedSelectionToken);
bool load(int row);
bool loadObserver(int row, bool secondary);
bool remove(int row);
bool exportShare(int row);
bool importShare(int row);
bool loadImported(int row);
bool loadImportedObserver(int row, bool secondary);
bool removeImported(int row);

bool busy();
// Late ARM acknowledgements remain valid after a timeout.
bool timedOut();
bool available();
bool catalogReady();
bool importedCatalogReady();
int profile();
int loadedSlot();
bool loadedImported();
int loadedImportedSlot();
u64 totalDurationQf();
u64 importedTotalDurationQf();
u32 importedOverflowCount();
const char *statusText();
bool copySlotName(int row, char *out, u32 size);
bool copyImportedSlotName(int row, char *out, u32 size);
const SusamuneGhostSlotInfo *slot(int row);
const SusamuneGhostSlotInfo *importedSlot(int row);

}  // namespace GhostStorage

#endif  // _SUSAMUNE_GHOST_STORAGE_HXX