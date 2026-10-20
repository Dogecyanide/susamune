#include "susamune/ghost_scrub.hxx"
#include "susamune/ghost.hxx"
#include "susamune/menu.hxx"
#include "JSystem/JUtility/JUTGamePad.hxx"
#include <Dolphin/printf.h>

namespace {
using Color = JUtility::TColor;
u8 sSelected;
bool sSelectionFailed;
bool jumpSplit(u8 index) {
    if (Ghost::observerGhostCount() > 1) return Ghost::observerAlignSplit(index);
    Ghost::ObserverSplit split;
    return Ghost::observerSplit(index, &split) && Ghost::observerSeek(split.qf);
}
void timeText(char *out, u32 size, u32 qf) {
    const u32 ms = qf * 1001u / 120u;
    snprintf(out, size, "%lu:%02lu.%03lu", ms / 60000, ms / 1000 % 60, ms % 1000);
}
void bar(Menu *menu, int x, int y, int width, const Ghost::ObserverTimeline &timeline) {
    const u32 total = timeline.endQf - timeline.startQf;
    const u32 at = timeline.qf < timeline.startQf ? 0 :
        timeline.qf > timeline.endQf ? total : timeline.qf - timeline.startQf;
    const int progress = total ? at * (width - 1) / total : 0;
    menu->fillBox(x, y, width, 7, Color(60, 75, 92, 230));
    menu->fillBox(x, y, progress, 7, Color(95, 190, 235, 255));
    for (u8 i = 0; i < timeline.splitCount; ++i) {
        Ghost::ObserverSplit split;
        if (!Ghost::observerSplit(i, &split) || split.qf < timeline.startQf ||
            split.qf > timeline.endQf) continue;
        const int mark = total ? (split.qf - timeline.startQf) * (width - 1) / total : 0;
        menu->fillBox(x + mark - 2, y - 7, 5, 5, i == sSelected && !sSelectionFailed
            ? Color(255, 220, 100, 255) : Color(170, 190, 215, 255));
    }
    menu->fillBox(x + progress - 1, y - 2, 3, 12, Color(255, 235, 145, 255));
}
}

namespace GhostScrub {
bool begin() {
    if (!Ghost::observerPause(true)) return false;
    Ghost::ObserverTimeline timeline;
    sSelected = Ghost::observerTimeline(&timeline) && timeline.alignedSplit >= 0
        ? static_cast<u8>(timeline.alignedSplit) : 0xff;
    sSelectionFailed = false;
    return true;
}
void end() {}
bool update(Menu *menu, u32 navigation, u16 pressed) {
    Ghost::ObserverTimeline timeline;
    if (!Ghost::observerTimeline(&timeline)) return true;
    if (pressed & JUTGamePad::B) return true;
    bool select = false;
    if (timeline.splitCount) {
        if (pressed & JUTGamePad::L) {
            sSelected = sSelected && sSelected < timeline.splitCount
                ? sSelected - 1 : timeline.splitCount - 1;
            select = true;
        } else if (pressed & JUTGamePad::R) {
            sSelected = sSelected < timeline.splitCount
                ? (sSelected + 1) % timeline.splitCount : 0;
            select = true;
        }
    }
    s32 delta = 0;
    if ((pressed & JUTGamePad::DPAD_LEFT) || (navigation & TMarioGamePad::CSTICK_LEFT)) --delta;
    if ((pressed & JUTGamePad::DPAD_RIGHT) || (navigation & TMarioGamePad::CSTICK_RIGHT)) ++delta;
    if ((pressed & JUTGamePad::DPAD_DOWN) || (navigation & TMarioGamePad::CSTICK_DOWN)) delta -= 120;
    if ((pressed & JUTGamePad::DPAD_UP) || (navigation & TMarioGamePad::CSTICK_UP)) delta += 120;
    bool attempted = false, accepted = true;
    if (select || (pressed & (JUTGamePad::X | JUTGamePad::Y))) {
        if (sSelected >= timeline.splitCount) sSelected = 0;
        attempted = true;
        accepted = jumpSplit(sSelected);
        sSelectionFailed = !accepted;
        if (!accepted && menu) menu->toast("No matching split and scene for both ghosts");
    } else if (delta) {
        const s32 next = static_cast<s32>(timeline.qf) + delta;
        attempted = true;
        accepted = Ghost::observerSeek(next < 0 ? 0 : next);
        if (accepted) sSelected = 0xff;
    } else if (pressed & JUTGamePad::Z) {
        attempted = true;
        accepted = Ghost::observerClearAlignment();
        if (accepted) sSelected = 0xff;
    } else if (pressed & JUTGamePad::A) {
        if (sSelectionFailed) {
            if (menu) menu->toast("Choose a matching split before playing");
        } else if (Ghost::observerPause(false)) {
            if (menu) menu->hide();
            return true;
        }
    }
    if (attempted && accepted) sSelectionFailed = false;
    if (attempted && !accepted && !select &&
        !(pressed & (JUTGamePad::X | JUTGamePad::Y)) && menu)
        menu->toast("No recorded position or split available");
    if (Ghost::observerLoading()) { if (menu) menu->hide(); return true; }
    return false;
}
void draw(Menu *menu, int x, int y, int width, int height) {
    Ghost::ObserverTimeline timeline;
    if (!menu || !Ghost::observerTimeline(&timeline)) return;
    char now[20], end[20], text[96];
    timeText(now, sizeof(now), timeline.qf > timeline.startQf ? timeline.qf - timeline.startQf : 0);
    timeText(end, sizeof(end), timeline.endQf - timeline.startQf);
    snprintf(text, sizeof(text), "Watch timeline   %s / %s", now, end);
    menu->drawMenuText(text, x + 5, y + 29, 16, 16, Color(255, 225, 100, 255));
    bar(menu, x + 12, y + 65, width - 30, timeline);
    menu->drawMenuText("Split     Ghost 1       Ghost 2        Difference", x + 8, y + 86,
                   11, 11, Color(190, 205, 225, 255));
    for (u8 i = 0; i < timeline.splitCount; ++i) {
        Ghost::ObserverSplit split;
        if (!Ghost::observerSplit(i, &split)) continue;
        const int rowY = y + 104 + i * 18;
        if (i == sSelected && !sSelectionFailed)
            menu->fillMenuBox(x + 3, rowY - 2, width - 10, 18, Color(62, 66, 40, 235));
        timeText(now, sizeof(now), split.qf - timeline.startQf);
        if (split.comparable) {
            timeText(end, sizeof(end), split.secondaryQf - timeline.secondaryStartQf);
            const s32 delta = static_cast<s32>(split.secondaryQf - timeline.secondaryStartQf) -
                              static_cast<s32>(split.qf - timeline.startQf);
            char difference[20];
            timeText(difference, sizeof(difference), delta < 0 ? -delta : delta);
            snprintf(text, sizeof(text), "%u%s     %s     %s     %c%s", split.endpoint + 1,
                timeline.alignedSplit == static_cast<s8>(i) ? "*" : " ", now, end,
                delta < 0 ? '-' : '+', difference);
        } else snprintf(text, sizeof(text), "%u      %s       --", split.endpoint + 1, now);
        menu->drawMenuText(text, x + 8, rowY, 11, 11, Color(230, 238, 250, 255));
    }
    if (!timeline.splitCount) menu->drawMenuText("This recording has no split checkpoints.",
        x + 8, y + 108, 12, 12, Color(200, 210, 225, 255));
    menu->drawMenuText(timeline.alignedSplit >= 0 ? "* Matching split. Both are paused until A plays." :
        "L/R jumps both to their own split; -- means no match.",
        x + 5, y + height - 58, 10, 10, Color(190, 210, 225, 255));
    menu->drawMenuText("Left/Right: 1 QF   Up/Down: 120 QF   L/R: jump split", x + 5,
        y + height - 40, 10, 10, Color(220, 230, 240, 255));
    menu->drawMenuText("X/Y: jump selected split   Z: reset alignment", x + 5,
        y + height - 25, 11, 11, Color(220, 230, 240, 255));
    menu->drawMenuText("A: play and close   B: back, keep paused", x + 5,
        y + height - 10, 11, 11, Color(255, 225, 100, 255));
}
void drawStatus(Menu *menu) {
    if (!menu || menu->shown() || !Ghost::observerPaused()) return;
    Ghost::ObserverTimeline timeline;
    if (!Ghost::observerTimeline(&timeline)) return;
    menu->fillBox(100, 352, 440, 56, Color(10, 18, 30, 225));
    menu->drawText("Watch paused - Ghosts > Watch timeline to resume", 112, 361,
        11, 11, Color(235, 240, 255, 255));
    bar(menu, 114, 389, 412, timeline);
}
}
