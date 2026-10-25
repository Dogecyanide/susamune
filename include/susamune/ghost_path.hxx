#ifndef SUSAMUNE_GHOST_PATH_HXX
#define SUSAMUNE_GHOST_PATH_HXX

#include <Dolphin/types.h>
#include "susamune/ghost_format.h"

class Menu;
namespace GhostPath {
// Borrow a validated current-scene segment; never retain its pose-bank pointer.
void draw(Menu *menu, const SusamuneGhostPoseSample *poses, u32 count,
          bool secondary);
}

#endif
