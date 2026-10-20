#pragma once
#include "susamune/hoverless.h"
#include "Dolphin/types.h"
namespace Hoverless {
void init();
void adopt(const volatile SusamuneCfg *cfg);
bool available();
int selectedProfile(int legacy);
void setProfile(int profile);
s32 *values();
void dirty();
void service();
}
