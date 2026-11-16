#include "susamune/dolphin_web_api.h"
#include "susamune/ghost_camera.h"
extern "C" {
#include <string.h>
}
typedef unsigned char u8;typedef unsigned short u16;typedef unsigned int u32;typedef int s32;
namespace {
#include "susamune/ghost_catalog_validation.inc"
}
extern "C" int moonshine_catalog_slot(const SusamuneGhostSlotInfo *raw,SusamuneGhostSlotInfo *out,unsigned imported,unsigned region) {
    if(!raw || region<1 || region>3 || imported>1)return 0;
    const u32 game=region==1?SUSAMUNE_GHOST_GAME_ID_JP:region==2?SUSAMUNE_GHOST_GAME_ID_US:SUSAMUNE_GHOST_GAME_ID_PAL;
    const u8 code=region==1?SUSAMUNE_GHOST_REGION_JP:region==2?SUSAMUNE_GHOST_REGION_US:SUSAMUNE_GHOST_REGION_PAL;
    return validateCatalogSlot(*raw,out,imported!=0,game,code);
}
