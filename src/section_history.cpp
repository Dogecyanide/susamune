#include "susamune/section_history.hxx"
#include "susamune/settings.hxx"
#include "susamune/menu.hxx"
#include "susamune/qft_timer.hxx"
#include "Dolphin/printf.h"
#include "Dolphin/string.h"
#include "Dolphin/mem.h"

namespace {
u8 sStyle = 15;
struct HistorySnapshot {
    u32 timer[4];
    s32 sections[16], last;
    u32 serial;
    u8 count, next, flags[6];
};
static_assert(sizeof(HistorySnapshot) == sizeof(QFTTimer::SavestateData), "history snapshot layout");
}
u8 SectionHistoryDisplay::style() { return sStyle; }
void SectionHistoryDisplay::adopt(u8 value) { sStyle = value < 96 ? value : 15; }
void SectionHistoryDisplay::toggle(unsigned row) {
    if (row == 0) gSettings.cycle(SETTING_TIMER_SECTIONS, 1);
    else if (row <= 5) sStyle ^= 1u << (row - 1);
    else if (row == 6) sStyle = (sStyle & 31u) | (((sStyle >> 5) + 1u) % 3u << 5);
    gSettings.markDirty();
}
const char *SectionHistoryDisplay::name(unsigned row) {
    static const char *const names[] = {"Show history", "Title", "Section numbers", "Times", "Background", "Raw QFs", "Recent sections", "Events / QFT freezes"};
    return row < 8 ? names[row] : "";
}
const char *SectionHistoryDisplay::value(unsigned row) {
    if (row == 7) return "Choose";
    if (row == 6) return sStyle >> 5 == 0 ? "16" : sStyle >> 5 == 1 ? "8" : "4";
    return (row == 0 ? gSettings.getBool(SETTING_TIMER_SECTIONS) : (sStyle & (1u << (row - 1))) != 0) ? "On" : "Off";
}
void SectionHistoryDisplay::draw(Menu *menu, bool timer) {
    // Suppress only the old presentation for this synchronous draw. The timer
    // and its captured section history remain the protected implementation.
    const u8 enabled = gSettings.mValues[SETTING_TIMER_SECTIONS];
    gSettings.mValues[SETTING_TIMER_SECTIONS] = 0;
    if (timer) gQFTTimer.draw(menu);
    gSettings.mValues[SETTING_TIMER_SECTIONS] = enabled;
    s32 qf;
    if (!enabled || !gQFTTimer.currentQf(&qf)) return;
    QFTTimer::SavestateData raw;
    gQFTTimer.captureSavestate(raw);
    HistorySnapshot snapshot;
    memcpy(&snapshot, &raw, sizeof(snapshot));
    if (!snapshot.count || snapshot.count > 16 || snapshot.next >= 16) return;
    const unsigned limit = 16u >> (sStyle >> 5);
    const unsigned count = snapshot.count < limit ? snapshot.count : limit;
    const unsigned first = (snapshot.next + 16 - count) % 16;
    const int heading = (sStyle & 1u) ? 16 : 0;
    const int height = 8 + heading + count * 13;
    const int y = 408 - height;
    if (sStyle & 8u) menu->fillBox(16, y, 186, height, JUtility::TColor(0, 0, 0, 175));
    if (heading) menu->drawText("QF Sections", 25, y + 4, 11, 11, JUtility::TColor(160, 220, 255, 255));
    for (unsigned row = 0; row < count; ++row) {
        const s32 value = snapshot.sections[(first + row) % 16];
        if (value < 0) continue;
        char line[64] = {}, part[32];
        if (sStyle & 2u) snprintf(line, sizeof(line), "%2u  ", snapshot.count - count + row + 1);
        if (sStyle & 4u) {
            const u32 ms = static_cast<u32>((u64)(u32)value * 1001u / 120u);
            snprintf(part, sizeof(part), "%lu:%02lu.%03lu", ms / 60000u, ms / 1000u % 60u, ms % 1000u);
            strcat(line, part);
        }
        if (sStyle & 16u) { snprintf(part, sizeof(part), "  %ld QF", value); strcat(line, part); }
        menu->drawText(line, 25, y + 4 + heading + row * 13, 10, 10, JUtility::TColor(245, 248, 255, 255));
    }
}
