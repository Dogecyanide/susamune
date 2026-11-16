#pragma once
#include "susamune/ghost.hxx"
namespace GhostAttempt {
void init();
void frameControl(bool frozen,bool assisted);
void update();
void depart();
void split(u16 route,u8 endpoint,s32 qf);
void assisted();
bool markPB(s32 resultQf);
void resetAfterLoad();
bool capture(Ghost::SavestateData &);
bool valid(const Ghost::SavestateData &);
void restore(const Ghost::SavestateData &);
bool owns(const Ghost::SavestateData &);
}
