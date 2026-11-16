#ifndef SUSAMUNE_DOLPHIN_GHOST_LIBRARY_HXX
#define SUSAMUNE_DOLPHIN_GHOST_LIBRARY_HXX
#include "ghost_storage.h"
namespace DolphinGhostLibrary {
bool ready();
bool begin(const SusamuneGhostStorageRequest &);
void update();
bool take(SusamuneGhostStorageResponse *);
}
#endif
