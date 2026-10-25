#ifndef _SUSAMUNE_MOVEMENT_TIMING_DISPLAY_HXX
#define _SUSAMUNE_MOVEMENT_TIMING_DISPLAY_HXX

class Menu;

namespace MovementTimingDisplay {

void onStageSetup();
void onSavestateLoaded();
void beforeDirect(bool active);
void afterDirect(bool active);
// Each result has its own layout; true means at least one was drawn.
bool draw(Menu *menu);

}  // namespace MovementTimingDisplay

#endif
