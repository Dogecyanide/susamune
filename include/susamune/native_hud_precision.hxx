#pragma once

class J2DScreen;

namespace NativeHudPrecision {
// Capture beside the pre-direct native HUD update, before its render phase.
void capture(bool practiceHolding);
bool beginDraw(J2DScreen *screen);
void endDraw();
unsigned normalDigits();
bool extraDigit();
}
