#include "susamune/dolphin_ghost_library.hxx"
#if IS_EMULATOR && TIMEWARP_LIVE_RACING
#include "susamune/dolphin_storage_api.hxx"
#include "susamune/addresses.hxx"
namespace DolphinGhostLibrary {
bool ready(){return DolphinFiles::available() && dolphinStorageApi();}
bool begin(const SusamuneGhostStorageRequest &r){const auto *p=dolphinStorageApi();return p && p->libraryBegin(r,dolphinStorageHost(),SUSAMUNE_GAME_VERSION);}
void update(){const auto *p=dolphinStorageApi();if(p)p->libraryUpdate();}
bool take(SusamuneGhostStorageResponse *out){const auto *p=dolphinStorageApi();return p && p->libraryTake(out);}
}
#endif
