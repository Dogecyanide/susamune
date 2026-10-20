#ifndef SUSAMUNE_NATIVE_TIMER_COLOR_HXX
#define SUSAMUNE_NATIVE_TIMER_COLOR_HXX
class J2DScreen;
namespace NativeTimerColor {
// Only between a successful NativeTimerLayout::beginDraw and its endDraw.
bool beginDraw(J2DScreen *screen);
void endDraw();
}
#endif
