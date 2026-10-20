#pragma once

#include <Dolphin/types.h>

struct ResTIMG;

namespace MenuThemeAssets {
enum Asset {
    Paper, Shine, Palm, Fish, Hand, Boat, Postcard,
    TabShine, TabPad, TabMario, TabCoin, TabGhost, TabGlasses, TabPianta,
    Count
};

// Call before the first stage setup; later calls keep the capture hook installed.
void service();

// Main thread, after setup/storage work is idle; own-disc extraction runs once.
void prepare();

// Palm/Fish/Hand/Boat have native pose 0/1; other assets ignore pose.
// Borrowed pointers are valid only for the current draw, never across setup/load.
const ResTIMG *get(Asset asset, unsigned int pose = 0);
}
