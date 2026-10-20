#pragma once
#include <Dolphin/types.h>
class Menu;
namespace GhostScrub {
bool begin();
bool update(Menu *menu, u32 navigation, u16 pressed);
void draw(Menu *menu, int x, int y, int width, int height);
void end();
void drawStatus(Menu *menu);
}
