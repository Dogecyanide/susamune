#include "susamune/feature_binds.hxx"
#include "susamune/binds.hxx"
#include "susamune/settings.hxx"
#include "susamune/menu.hxx"
#include "Dolphin/printf.h"

#pragma clang section text=".foxtrot.text" rodata=".foxtrot.rodata"
namespace FeatureBinds {
namespace {
const u8 kFeatureBindSettings[] = {
    SETTING_FAST_TEXT,
    SETTING_FLUDD_SECRETS,
    SETTING_AREA_LOCK,
    SETTING_INFINITE_JUICE,
    SETTING_NOZZLE_LOCK,
    SETTING_STAGE_INTRO_SKIP,
    SETTING_NO_SHINE_ANIM,
    SETTING_FRUIT_NEVER_TIMEOUT,
    SETTING_MUTE_BGM,
    SETTING_SHADOW_MARIO_HP,
    SETTING_UNLOCK_YOSHI,
    SETTING_UNLOCK_NOZZLES,
};
static_assert(sizeof(kFeatureBindSettings) == BIND_FEATURE_UNLOCK_NOZZLES + 1 - BIND_FEATURE_FAST_TEXT,
              "feature bind mapping must follow its append-only tail");
}
void update() {
    if (!gMenu || gMenu->shown()) return;
    for (unsigned i = 0; i < sizeof(kFeatureBindSettings); ++i) {
        if (!gBinds.wasPressed((BindId)(BIND_FEATURE_FAST_TEXT + i))) continue;
        const SettingId id = (SettingId)kFeatureBindSettings[i];
        gSettings.cycle(id, 1);
        char text[48];
        snprintf(text, sizeof(text), "%s: %s", Settings::name(id), gSettings.valueLabel(id));
        gMenu->toast(text);
    }
}
}
