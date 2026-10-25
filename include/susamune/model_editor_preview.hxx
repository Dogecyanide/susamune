#pragma once
#include <Dolphin/types.h>

class CPolarSubCamera;
class Menu;
namespace JDrama { class TGraphics; }

namespace ModelEditorPreview {
void begin(bool fludd);
void end();
void update();
bool wanted();
void apply(CPolarSubCamera *camera);
void restore();
void restoreAll();
void perform(CPolarSubCamera *camera, u32 cue, JDrama::TGraphics *graphics);
void drawHint(Menu *menu);
}
