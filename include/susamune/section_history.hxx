#pragma once
#include <Dolphin/types.h>
class Menu;
class SectionHistoryDisplay {
public:
    static void draw(Menu *, bool timer);
    static u8 style();
    static void adopt(u8 style);
    static void toggle(unsigned row);
    static const char *name(unsigned row);
    static const char *value(unsigned row);
};
