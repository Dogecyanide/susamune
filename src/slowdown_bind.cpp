#include "susamune/slowdown_bind.hxx"
#include "susamune/binds.hxx"
#include "susamune/settings.hxx"
#include "susamune/practice_session.hxx"
#include "susamune/menu.hxx"
#include "Dolphin/printf.h"

namespace { const char kSlowdownToggleFormat[] = "Gameplay speed: %u pct"; }
namespace SlowdownBind {
void update(bool allowed) {
    if (!allowed || !gBinds.wasPressed(BIND_SLOWDOWN_TOGGLE)) return;
    const unsigned current = gSettings.get(SETTING_GAMEPLAY_SPEED);
    const unsigned preset = gSettings.get(SETTING_SLOWDOWN_PRESET);
    const unsigned value = current && current < 100 ? 0 : (preset < 100 ? preset : 50);
    gSettings.set(SETTING_GAMEPLAY_SPEED, value);
    PracticeSession::resetGameplaySpeed();
    if (gMenu) {
        char message[32];
        snprintf(message, sizeof(message), kSlowdownToggleFormat, value ? value : 100);
        gMenu->toast(message);
    }
}
}
