#ifndef SUSAMUNE_BINDS_LIST_H
#define SUSAMUNE_BINDS_LIST_H

// =====================================================================
// binds_list.h
//
// The canonical list of configurable button binds, shared by every
// toolchain exactly like settings_list.h: the mod (C++, Kuribo clang),
// the Nintendont ARM kernel (devkitARM) and the PPC loader (devkitPPC).
// Keep this file plain C.
//
// Each row is (enumerator, ini_key):
//   - the enumerator defines BindId and therefore the binds[] layout of
//     the MEM2 handoff block, so ROWS MUST NOT BE REORDERED OR REMOVED
//     once a build has shipped -- append instead.
//   - the ini_key is what appears under [binds_<region>] in susamune.ini. Only
//     the launcher expands the keys into strings; the mod reads by index.
//
// The menu display name and default combo stay in binds_descs.inc; the
// launcher has no use for them.
// =====================================================================

#define SUSAMUNE_BIND_LIST(X)                                                 \
    X(BIND_REGRAB_OBJECT,      "regrab_object")                             \
    X(BIND_SPAWN_YOSHI_GREEN,  "spawn_yoshi_green")                         \
    X(BIND_SPAWN_YOSHI_ORANGE, "spawn_yoshi_orange")                        \
    X(BIND_SPAWN_YOSHI_PURPLE, "spawn_yoshi_purple")                        \
    X(BIND_SPAWN_YOSHI_PINK,   "spawn_yoshi_pink")                          \
    X(BIND_FAST_FORWARD_4X,    "fast_forward_4x")                           \
    X(BIND_FAST_FORWARD_8X,    "fast_forward_8x")                           \
    X(BIND_MENU_TOGGLE,        "menu_toggle")                               \
    X(BIND_SAVESTATE_SAVE,     "savestate_save")                            \
    X(BIND_SAVESTATE_LOAD,     "savestate_load")                            \
    X(BIND_WARP_WHEEL,         "warp_wheel")                                \
    X(BIND_FULL_RESTART,       "full_restart")                              \
    X(BIND_WARP_LAST,          "warp_last")                                 \
    X(BIND_INSTANT_RESTART,    "instant_restart")                           \
    X(BIND_TOGGLE_INPUT_DISPLAY, "toggle_input_display")                    \
    X(BIND_ATTEMPT_SHOW,         "attempt_show")                            \
    X(BIND_ATTEMPT_ADD,          "attempt_add")                             \
    X(BIND_ATTEMPT_DEC,          "attempt_decrease")                        \
    X(BIND_ATTEMPT_INC,          "attempt_increase")                        \
    X(BIND_SUCCESS_DEC,          "success_decrease")                        \
    X(BIND_SUCCESS_INC,          "success_increase")                        \
    X(BIND_POSITION_SAVE,        "position_save")                           \
    X(BIND_POSITION_LOAD,        "position_load")                           \
    X(BIND_PRACTICE_PAUSE,       "practice_pause")                          \
    X(BIND_PRACTICE_STEP,        "practice_step")                           \
    X(BIND_FREE_CAMERA,          "free_camera")                             \
    X(BIND_PRACTICE_RECORD,      "practice_record")                         \
    X(BIND_PRACTICE_REPLAY,      "practice_replay")                         \
    X(BIND_PRACTICE_STOP,        "practice_stop")                           \
    X(BIND_PRACTICE_SPIN_CW,     "practice_spin_clockwise")                 \
    X(BIND_PRACTICE_SPIN_CCW,    "practice_spin_counterclockwise")          \
    X(BIND_SAVESTATE_CYCLE,     "savestate_cycle")                          \
    X(BIND_SAVESTATE_CYCLE_SAVE, "savestate_cycle_save")                    \
    X(BIND_SAVESTATE_CYCLE_LOAD, "savestate_cycle_load")                    \
    X(BIND_TAS_BEGINNING,        "tas_beginning")                           \
    X(BIND_TAS_SAVE_CHECKPOINT1, "tas_save_checkpoint1")                    \
    X(BIND_TAS_LOAD_CHECKPOINT1, "tas_load_checkpoint1")                    \
    X(BIND_TAS_SAVE_CHECKPOINT2, "tas_save_checkpoint2")                    \
    X(BIND_TAS_LOAD_CHECKPOINT2, "tas_load_checkpoint2")                    \
    X(BIND_TAS_CONTINUE,         "tas_continue")                            \
    X(BIND_TAS_REPLAY,           "tas_replay")                              \
    X(BIND_SLOWDOWN_TOGGLE,      "slowdown_toggle")                         \
    X(BIND_SAVESTATE_SAVE_2,     "savestate_save_2")                        \
    X(BIND_SAVESTATE_LOAD_2,     "savestate_load_2")                        \
    X(BIND_SAVESTATE_SAVE_3,     "savestate_save_3")                        \
    X(BIND_SAVESTATE_LOAD_3,     "savestate_load_3")                        \
    X(BIND_FEATURE_FAST_TEXT, "feature_fast_text")                          \
    X(BIND_FEATURE_FLUDD_SECRETS, "feature_fludd_secrets")                  \
    X(BIND_FEATURE_AREA_LOCK, "feature_area_lock")                          \
    X(BIND_FEATURE_INFINITE_JUICE, "feature_infinite_juice")                \
    X(BIND_FEATURE_NOZZLE_LOCK, "feature_nozzle_lock")                      \
    X(BIND_FEATURE_STAGE_INTRO, "feature_stage_intro")                      \
    X(BIND_FEATURE_SHINE_ANIMATION, "feature_shine_animation")              \
    X(BIND_FEATURE_FRUIT_TIMEOUT, "feature_fruit_timeout")                  \
    X(BIND_FEATURE_MUTE_BGM, "feature_mute_bgm")                            \
    X(BIND_FEATURE_SHADOW_HP, "feature_shadow_hp")                          \
    X(BIND_FEATURE_UNLOCK_YOSHI, "feature_unlock_yoshi")                    \
    X(BIND_FEATURE_UNLOCK_NOZZLES, "feature_unlock_nozzles")                \
    X(BIND_MENU_SEARCH, "menu_search")

// The bindable buttons, as (GameCube button bit, ini token, menu glyph). The
// mod defines the regional glyph macros in glyphs.hxx; the launcher ignores
// that field. The bits are the hardware PADStatus::mButton bits, which is also
// what JUTGamePad::EButtons uses.
//
// Order matters twice over: it is the order buttons are listed in the menu
// and in susamune.ini ("X+DUp"). The analog sticks are
// deliberately absent; the menu reserves the C-stick for navigating while a
// bind is being recorded.
#define SUSAMUNE_BIND_BUTTON_LIST(X)                                          \
    X(0x0100u, "A",      SUSAMUNE_GLYPH_A)                                   \
    X(0x0200u, "B",      SUSAMUNE_GLYPH_B)                                   \
    X(0x0400u, "X",      SUSAMUNE_GLYPH_X)                                   \
    X(0x0800u, "Y",      SUSAMUNE_GLYPH_Y)                                   \
    X(0x0040u, "L",      SUSAMUNE_GLYPH_L)                                   \
    X(0x0020u, "R",      SUSAMUNE_GLYPH_R)                                   \
    X(0x0010u, "Z",      SUSAMUNE_GLYPH_Z)                                   \
    X(0x1000u, "Start",  "Start")                                             \
    X(0x0001u, "DLeft",  "D" SUSAMUNE_GLYPH_LEFT)                            \
    X(0x0004u, "DDown",  "D" SUSAMUNE_GLYPH_DOWN)                            \
    X(0x0008u, "DUp",    "D" SUSAMUNE_GLYPH_UP)                              \
    X(0x0002u, "DRight", "D" SUSAMUNE_GLYPH_RIGHT)

// Union of the bits above: everything a bind may contain. Input is masked with
// this before comparing, so a bind matches on the bindable buttons only and
// ignores the stick-derived pseudo-buttons JUTGamePad folds into the same word.
#define SUSAMUNE_BIND_BUTTON_MASK 0x1F7Fu

// A bind holds at most this many buttons; recording commits as soon as the
// fourth is pressed.
#define SUSAMUNE_BIND_MAX_BUTTONS 4

// Separator between buttons in the ini and the token written for a bind with
// no buttons at all. The menu uses the font's ampersand glyph instead.
#define SUSAMUNE_BIND_SEPARATOR '+'
#define SUSAMUNE_BIND_NONE_TOKEN "none"

#endif  // SUSAMUNE_BINDS_LIST_H
