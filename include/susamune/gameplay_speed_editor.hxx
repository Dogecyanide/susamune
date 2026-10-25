#ifndef _SUSAMUNE_GAMEPLAY_SPEED_EDITOR_HXX
#define _SUSAMUNE_GAMEPLAY_SPEED_EDITOR_HXX

class Menu;

namespace NumberEditor {
void begin(const void *owner, const char *title, unsigned value,
           unsigned minimum, unsigned maximum, const char *unit);
bool active(const void *owner);
void cancel(const void *owner);
// acceptedDigits, when supplied, receives three digits and a terminator only on acceptance.
int update(Menu *menu, unsigned *value, char *acceptedDigits = nullptr);
void draw(Menu *menu);
}

namespace GameplaySpeedEditor {
void begin(const void *owner, bool preset = false);
bool active(const void *owner);
void cancel(const void *owner);
void update(Menu *menu);
void draw(Menu *menu);
}

#endif
