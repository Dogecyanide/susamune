#ifndef SUSAMUNE_PRACTICE_SESSION_HXX
#define SUSAMUNE_PRACTICE_SESSION_HXX

#include <Dolphin/types.h>
#include "susamune/practice_input.h"

class Menu;

namespace PracticeSession {

void init();
void beforeStageSetup();
// Call before borrowing a director state; modal includes menu/wheel/editors.
void beforeDirect(bool modalOwnsInput);
bool freezeRequested();
bool ownsGameplayInput();
// Call after restoring the real director state, before gameplay observers.
void afterDirect(s32 appState, bool gameplayActive);
// Service replay loads only after the existing GX completion barrier.
void afterDraw();
void onSavestateSaved(u32 slot, u32 generation);
void onSavestateCleared(u32 slot, u32 generation);
void onSavestateLoaded();
void armLoadHold(u16 buttons);
void cancelLoadHold();
bool holdingLoad();
void draw(Menu *menu);

bool requestPauseToggle(bool fromMenu = false);
bool requestStep(bool fromMenu = false);
bool requestFreeCameraToggle();
bool requestRecord();
bool requestPlayback();
void requestStop();
// Approved warps must release the hold so the retail transition can run.
void releaseForDeparture();
void recenterCamera();

// Timer presentation includes Load holds; menu actions use the manual toggle.
bool paused();
bool manualPaused();
// An armed hold survives loading and waits for Mario's controls to return.
bool pausePending();
bool freeCamera();
bool recording();
bool replaying();
bool starting();
bool assisted();
bool available();
u32 stepCount();
u32 recordedFrames();
u32 replayFrame();
u32 capacityFrames();
const char *status();
// False for frozen/UI frames. Physical input remains separate from replay.
bool consumedInput(SusamunePracticeInput *out);

} // namespace PracticeSession

#endif
