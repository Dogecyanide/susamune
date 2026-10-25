#ifndef SUSAMUNE_FINISH_BREAKDOWN_HXX
#define SUSAMUNE_FINISH_BREAKDOWN_HXX

#include <Dolphin/types.h>
class Menu;
class TMarioGamePad;
struct SusamuneFinishBreakdownCfg;

namespace FinishBreakdown {
void onStageSetup();
void onDeparture();
void sample();
void finish(int entry, s32 qf);
void invalidate();
void draw(Menu *menu);
void resetDefaults();
void adopt(const volatile SusamuneFinishBreakdownCfg *cfg);
void stageInto(volatile SusamuneFinishBreakdownCfg *cfg);
bool dirty();
void clearDirty();
void beginEditor();
bool editing();
void updateEditor(Menu *menu, TMarioGamePad *pad);
void drawEditor(Menu *menu);
}

#endif
