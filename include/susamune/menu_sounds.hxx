#ifndef SUSAMUNE_MENU_SOUNDS_HXX
#define SUSAMUNE_MENU_SOUNDS_HXX

#include <Dolphin/types.h>

namespace MenuSounds {
enum Cue { NONE, CURSOR, SELECT, BACK };

struct Transition {
    bool wasShown, shown, changed, navigation, enabled, recording;
    u16 pressed;
};

Cue choose(const Transition &transition);
void play(Cue cue);
}

#endif
