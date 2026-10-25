#include "susamune/menu_sounds.hxx"
#include "susamune/settings.hxx"
#include "SMS/MSound/MSound.hxx"
#include "SMS/System/Application.hxx"
#include "SMS/System/MarDirector.hxx"
#include "JSystem/JUtility/JUTGamePad.hxx"

namespace MenuSounds {
Cue choose(const Transition &t) {
    if (!t.enabled || t.recording || (!t.pressed && !t.navigation)) return NONE;
    if (t.wasShown != t.shown) return t.shown ? SELECT : BACK;
    if (!t.shown || !t.changed) return NONE;
    if (t.pressed & JUTGamePad::B) return BACK;
    if (t.pressed & (JUTGamePad::A | JUTGamePad::X | JUTGamePad::Y |
                     JUTGamePad::Z | JUTGamePad::START)) return SELECT;
    return t.navigation ? CURSOR : NONE;
}

void play(Cue cue) {
    if (cue == NONE || !gSettings.getBool(SETTING_MENU_SOUNDS) || !gpMSound ||
        gpApplication.mContext != TApplication::CONTEXT_DIRECT_STAGE ||
        !gpMarDirector || !gpMarDirector->_260 ||
        gpMarDirector->mCurState < TMarDirector::STATE_GAME_STARTING ||
        gpMarDirector->mCurState == TMarDirector::STATE_STAGE_EXIT ||
        gpMarDirector->mCurState == TMarDirector::STATE_STAGE_EXIT_2) return;
    const u32 sound = cue == CURSOR ? MSD_SE_SY_CURSOR_COMMON :
                      cue == BACK ? MSD_SE_SY_CANCEL_COMMON : MSD_SE_SY_SELECT_COMMON;
    // Retail options/card menus use this wrapper, including its sound gate.
    gpMSound->startSoundSystemSE(sound, 0, nullptr, 0);
}
}
