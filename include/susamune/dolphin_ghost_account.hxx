#ifndef SUSAMUNE_DOLPHIN_GHOST_ACCOUNT_HXX
#define SUSAMUNE_DOLPHIN_GHOST_ACCOUNT_HXX
#include "ghost_storage.h"
namespace DolphinGhostAccount {
bool begin(const SusamuneGhostStorageRequest &);
void update();
bool take(SusamuneGhostStorageResponse *);
}
#endif
