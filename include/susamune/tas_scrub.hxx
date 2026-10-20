#ifndef SUSAMUNE_TAS_SCRUB_HXX
#define SUSAMUNE_TAS_SCRUB_HXX
#include <Dolphin/types.h>
class Menu;
namespace TasScrub {
void begin();
bool update(Menu *menu, u32 navigation, u16 pressed);
void draw(Menu *menu, int x, int y, int width, int height);
// True includes the cancellation frame, which must retain input ownership.
bool poll();
void drawProgress(Menu *menu);
}
#endif
