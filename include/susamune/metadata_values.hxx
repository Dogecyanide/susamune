#pragma once
#include <Dolphin/types.h>
class TMario;
namespace MetadataValues {
struct Extra {
    float direction, gain, height, slope, water, hover;
    u32 action;
    u16 floor;
    bool moving, ground, fludd;
};
Extra read(const TMario *, u32 quarterFrame);
void reset();
void format(char *, u32, unsigned field, const Extra &);
const char *label(unsigned field, bool longLabel);
}
