#ifndef SUSAMUNE_TAS_PROJECT_HXX
#define SUSAMUNE_TAS_PROJECT_HXX
#include <Dolphin/types.h>
#include "susamune/state_storage.h"
#include "susamune/binds.hxx"
namespace TasProject {
enum { BEGINNING, CHECKPOINT1, CHECKPOINT2, ROLE_COUNT };
struct Checkpoint { bool present; u32 frames; };
void update();
void afterDraw();
bool active();
bool busy();
bool dirty();
bool named();
const char *name();
const char *status();
const char *roleName(u32 role);
Checkpoint checkpoint(u32 role);
bool newProject();
bool saveCheckpoint(u32 role);
bool promptPending();
bool checkpointOverwritePending();
u32 pendingCheckpointRole();
bool confirmCheckpointOverwrite(bool accept);
// Called once for a fresh shortcut edge; true includes a handled refusal.
bool dispatchShortcut(BindId id);
bool loadCheckpoint(u32 role);
bool continueEditing();
bool replay();
bool save(const char *name);
bool open(u32 id, u32 checksum);
bool refresh(u32 afterId = 0);
bool rename(u32 id, u32 checksum, const char *name);
bool remove(u32 id, u32 checksum);
bool catalogReady();
const SusamuneStateCatalog &catalog();
bool replacementNeeded();
bool replacementAllowed(u32 slot);
bool replace(u32 slot, u32 generation);
void cancelReplacement();
}
#endif
