#ifndef SUSAMUNE_DOLPHIN_GHOST_WEB_HXX
#define SUSAMUNE_DOLPHIN_GHOST_WEB_HXX
#include "ghost_service.h"
#include "ghost_storage.h"
namespace DolphinGhostWeb {
bool begin(const GhostServiceQuery &);
bool download(const GhostServiceEntry &);
bool sanitizeSlot(const SusamuneGhostSlotInfo &,SusamuneGhostSlotInfo *,bool);
void update();
unsigned phase();
int take(GhostServicePage *);
void close();
}
#endif
