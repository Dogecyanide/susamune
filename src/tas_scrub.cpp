#include "susamune/tas_scrub.hxx"
#include "susamune/menu.hxx"
#include "susamune/binds.hxx"
#include "susamune/practice_session.hxx"
#include "susamune/tas_project.hxx"
#include "susamune/input_display.hxx"
#include "JSystem/JUtility/JUTGamePad.hxx"
#include <Dolphin/printf.h>

namespace {
u32 sScrubTarget;
u16 sScrubPrevious;
bool sScrubWasBusy;
const char kScrubFrameFormat[] = "Frame %lu / %lu";
const char kScrubTitle[] = "Scrub recording";
const char kScrubMarksHelp[] = "Checkpoints: green here, gray in another area";
const char kScrubReplayHelp[] = "A previews the selected frame in the paused game.";
const char kScrubContinueHelp[] = "Continue replaces the recorded future from that frame.";
const char kScrubInputHelp[] = "Recorded inputs (highlighted: selected frame)";
const char kScrubInputFrame[] = "%lu";
const char kScrubMoveHelp[] = "Left/Right: 1 frame   Up/Down: 30   L/R: 300";
const char kScrubActionHelp[] = "X: beginning   Y: end   A: seek   B: back";
const char kScrubProgressFormat[] = "Seeking frame %lu / %lu  -  B: cancel";
using Color = JUtility::TColor;
void scrubBar(Menu *menu, int x, int y, int width, u32 frame, u32 total) {
    menu->fillBox(x, y, width, 8, Color(64, 74, 88, 220));
    const int progress = total ? static_cast<int>(frame * (width - 1) / total) : 0;
    menu->fillBox(x, y, progress, 8, Color(74, 190, 220, 255));
    menu->fillBox(x + progress - 1, y - 5, 3, 18, Color(255, 225, 100, 255));
}
void scrubInputs(Menu *menu, int x, int y, int width, u32 target, u32 total) {
    const u32 cells = 7;
    u32 first = target > 4 ? target - 4 : 0;
    if (total > cells && first > total - cells) first = total - cells;
    const int cellWidth = width / cells;
    InputDisplay timeline;
    // Timeline cells keep fixed geometry regardless of overlay customisation.
    timeline.resetDefaults();
    for (u32 cell = 0; cell < cells && first + cell < total; ++cell) {
        SusamunePracticeInput input;
        if (!PracticeSession::recordedInput(first + cell, &input)) break;
        const int left = x + cell * cellWidth;
        const u32 frame = first + cell + 1;
        menu->fillBox(left, y, cellWidth - 2, 82,
            frame == target ? Color(65, 71, 40, 240) : Color(20, 28, 42, 230));
        char label[12];
        snprintf(label, sizeof(label), kScrubInputFrame, frame);
        menu->drawText(label, left + 3, y + 3, 11, 11, Color(235, 240, 255, 255));
        timeline.drawSnapshot(menu, input, left, y + 18, 40, nullptr);
        char dpad[] = {
            input.buttons & JUTGamePad::DPAD_UP ? 'U' : '-',
            input.buttons & JUTGamePad::DPAD_DOWN ? 'D' : '-',
            input.buttons & JUTGamePad::DPAD_LEFT ? 'L' : '-',
            input.buttons & JUTGamePad::DPAD_RIGHT ? 'R' : '-', 0};
        menu->drawText(dpad, left + 8, y + 68, 10, 10, Color(170, 205, 220, 255));
    }
}
}

namespace TasScrub {
void begin() {
    sScrubTarget = PracticeSession::takePosition();
    if (sScrubTarget > PracticeSession::recordedFrames())
        sScrubTarget = PracticeSession::recordedFrames();
}
bool update(Menu *menu, u32 navigation, u16 pressed) {
    s32 delta = 0;
    if ((pressed & JUTGamePad::DPAD_LEFT) || (navigation & TMarioGamePad::CSTICK_LEFT)) --delta;
    if ((pressed & JUTGamePad::DPAD_RIGHT) || (navigation & TMarioGamePad::CSTICK_RIGHT)) ++delta;
    if ((pressed & JUTGamePad::DPAD_DOWN) || (navigation & TMarioGamePad::CSTICK_DOWN)) delta -= 30;
    if ((pressed & JUTGamePad::DPAD_UP) || (navigation & TMarioGamePad::CSTICK_UP)) delta += 30;
    if (pressed & JUTGamePad::L) delta -= 300;
    if (pressed & JUTGamePad::R) delta += 300;
    const u32 total = PracticeSession::recordedFrames();
    const s32 next = static_cast<s32>(sScrubTarget) + delta;
    sScrubTarget = next < 0 ? 0 : static_cast<u32>(next) > total ? total : next;
    if (pressed & JUTGamePad::X) sScrubTarget = 0;
    if (pressed & JUTGamePad::Y) sScrubTarget = total;
    if (!(pressed & JUTGamePad::A)) return false;
    if (TasProject::seek(sScrubTarget)) return true;
    if (menu) menu->toast(TasProject::status());
    return false;
}
void draw(Menu *menu, int x, int y, int width, int height) {
    if (!menu) return;
    const u32 total = PracticeSession::recordedFrames();
    char text[72];
    snprintf(text, sizeof(text), kScrubFrameFormat, sScrubTarget, total);
    menu->drawMenuText(kScrubTitle, x + 4, y + 30, 18, 18, Color(255, 225, 100, 255));
    menu->drawMenuText(text, x + 4, y + 54, 16, 16, Color(235, 240, 255, 255));
    scrubBar(menu, x + 12, y + 82, width - 40, sScrubTarget, total);
    for (u32 role = 0; role < 3; ++role) {
        const auto checkpoint = TasProject::checkpoint(role);
        if (!checkpoint.present || checkpoint.frames > total) continue;
        const int offset = total ? checkpoint.frames * (width - 41) / total : 0;
        menu->fillMenuBox(x + 11 + offset, y + 93, 3, 6,
            checkpoint.loadableHere ? Color(110, 240, 150, 255) : Color(140, 140, 140, 255));
    }
    menu->drawMenuText(kScrubMarksHelp, x + 4, y + 101, 10, 10, Color(190, 205, 220, 255));
    menu->drawMenuText(kScrubInputHelp, x + 4, y + 117, 11, 11, Color(190, 205, 220, 255));
    scrubInputs(menu, x + 4, y + 132, width - 8, sScrubTarget, total);
    menu->drawMenuText(kScrubReplayHelp, x + 4, y + 218, 11, 11, Color(220, 230, 240, 255));
    menu->drawMenuText(kScrubContinueHelp, x + 4, y + 232, 10, 10, Color(220, 230, 240, 255));
    menu->drawMenuText(kScrubMoveHelp, x + 4, y + height - 26, 11, 11, Color(220, 230, 240, 255));
    menu->drawMenuText(kScrubActionHelp, x + 4, y + height - 12, 11, 11, Color(255, 225, 100, 255));
}
bool poll() {
    const bool busy = PracticeSession::seekBusy();
    const u16 held = JUTGamePad::mPadStatus[0].mButton;
    if (busy && sScrubWasBusy &&
        (((held & ~sScrubPrevious) & JUTGamePad::B) || gBinds.wasPressedRaw(BIND_PRACTICE_STOP)))
        PracticeSession::cancelSeek();
    if (sScrubWasBusy && !PracticeSession::seekBusy() && gMenu)
        gMenu->toast(PracticeSession::status());
    sScrubPrevious = held;
    sScrubWasBusy = PracticeSession::seekBusy();
    return busy;
}
void drawProgress(Menu *menu) {
    if (!menu || !PracticeSession::seekBusy()) return;
    const u32 frame = PracticeSession::seekPosition(), target = PracticeSession::seekTarget();
    char text[64];
    snprintf(text, sizeof(text), kScrubProgressFormat, frame, target);
    menu->fillBox(66, 344, 508, 62, Color(8, 16, 30, 235));
    menu->drawText(text, 80, 354, 14, 14, Color(235, 240, 255, 255));
    scrubBar(menu, 80, 386, 480, frame > target ? target : frame, target);
}
}
