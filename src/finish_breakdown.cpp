#include "susamune/finish_breakdown.hxx"
#include "susamune/qft_segments.h"
#include "susamune/qft_timer.hxx"
#include "susamune/settings.hxx"
#include "susamune/iling.hxx"
#include "susamune/ghost.hxx"
#include "susamune/menu.hxx"
#include "susamune/stage_loader.hxx"
#include "susamune/warp_wheel.hxx"
#include "susamune/creation.hxx"
#include "susamune/packed_text.hxx"
#include "susamune/susamune_cfg.h"
#include "SMS/System/Application.hxx"
#include "SMS/System/MarDirector.hxx"
#include "SMS/Player/MarioGamePad.hxx"
#include <Dolphin/OS.h>
#include <Dolphin/mem.h>
#include <Dolphin/printf.h>

namespace {
MoonshineQftSegments sBreakdownSegments;
MoonshineQftSegments::Stage sBreakdownResult[MoonshineQftSegments::CAPACITY];
u32 sBreakdownSetup, sBreakdownLoadMs = ~0u;
u16 sBreakdownResultFrames;
u8 sBreakdownResultCount;
int sBreakdownEntry;
OSTime sBreakdownDeparture;
bool sBreakdownLoading, sBreakdownDirty;
CreationStyle sBreakdownStyle;
u8 sBreakdownRgb[3][3], sBreakdownBackupRgb[3][3];
u8 sBreakdownRows, sBreakdownHalfSeconds, sBreakdownEditorPage, sBreakdownEditorRow;
CreationEditor sBreakdownEditor;
const u8 kDurations[] = {1, 2, 4, 6, 10, 20, 40, 60, 120, 0};
const char kRowNames[] = "Title\0IL name\0Entry segment\0Later segments\0Actual load\0QFT transition\0QFT total";
enum { ROW_TITLE=1, ROW_NAME=2, ROW_ENTRY=4, ROW_STAGES=8,
       ROW_LOAD=16, ROW_ALLOWANCE=32, ROW_TOTAL=64 };
CreationStyle styleOf(const volatile SusamuneFinishBreakdownCfg &cfg) {
    return {cfg.x, cfg.y, cfg.scale, cfg.textA, cfg.bgR, cfg.bgG, cfg.bgB,
            cfg.bgA, cfg.textBrightness, cfg.padding};
}
const char *stageName(u16 scene) {
    switch ((u8)scene) {
    case TGameSequence::AREA_DOLPIC: return "Plaza";
    case TGameSequence::AREA_BIANCO: return "Bianco";
    case TGameSequence::AREA_RICCO: return "Ricco";
    case TGameSequence::AREA_MAMMA: return "Gelato";
    case TGameSequence::AREA_PINNABEACH: return "Beach";
    case TGameSequence::AREA_SIRENA: return "Sirena";
    case TGameSequence::AREA_MONTE: return "Pianta";
    case TGameSequence::AREA_MARE: return "Noki";
    case TGameSequence::AREA_COROEX6: return "Corona";
    case TGameSequence::AREA_BIANCOBOSS: return "Windmill";
    case TGameSequence::AREA_RICOEX0: return "Blooper race";
    case TGameSequence::AREA_RICCOBOSS: return "Blooper";
    case TGameSequence::AREA_MAMMAEX1: return "Sand Bird";
    case TGameSequence::AREA_MAMMAEX0:
    case TGameSequence::AREA_SIRENAEX0:
    case TGameSequence::AREA_SIRENAEX1:
    case TGameSequence::AREA_COROEX0:
    case TGameSequence::AREA_COROEX1:
    case TGameSequence::AREA_COROEX2:
    case TGameSequence::AREA_COROEX4:
    case TGameSequence::AREA_COROEX5:
    case TGameSequence::AREA_MONTEEX0:
    case TGameSequence::AREA_RICOEX1: return "Secret";
    case TGameSequence::AREA_PINNAPARCO: return "Park";
    case TGameSequence::AREA_PINNABOSS: return scene >> 8 ? "Mecha-Bowser" : "Balloons";
    case TGameSequence::AREA_DELFINO: return "Hotel";
    case TGameSequence::AREA_CASINO: return "Casino";
    case TGameSequence::AREA_DELFINOBOSS: return "King Boo";
    case TGameSequence::AREA_MAREEX0: return "Bottle";
    case TGameSequence::AREA_MAREBOSS: return "Eel";
    case TGameSequence::AREA_MAREUNDERSEA: return "Red fish";
    case TGameSequence::AREA_CORONABOSS: return "Bowser";
    default: return "Stage";
    }
}

void duration(s32 qf, char *text, u32 capacity) { ILing::formatTime(qf, text, capacity); }
void milliseconds(u32 ms, char *text, u32 capacity) {
    if (ms == ~0u) snprintf(text, capacity, "--");
    else snprintf(text, capacity, "%lu:%02lu.%03lu", ms / 60000, ms / 1000 % 60, ms % 1000);
}
void drawPanel(Menu *menu, bool preview) {
    const MoonshineQftSegments::Stage demo[] = {{0, 1524, 900, 3}, {1632, 5268, ~0u, 42}};
    const auto *stages = preview ? demo : sBreakdownResult;
    const unsigned count = preview ? 2 : sBreakdownResultCount;
    char lines[MoonshineQftSegments::CAPACITY * 3 + 3][72];
    u8 colors[MoonshineQftSegments::CAPACITY * 3 + 3];
    unsigned rows = 0;
    if (sBreakdownRows & ROW_TITLE) { snprintf(lines[rows], 72, "Finish breakdown"); colors[rows++] = 0; }
    if (sBreakdownRows & ROW_NAME) { snprintf(lines[rows], 72, "%s", preview ? "Ricco 4 Full" : ILing::shortLabel(sBreakdownEntry)); colors[rows++] = 1; }
    for (unsigned i = 0; i < count; ++i) {
        char time[24];
        if (sBreakdownRows & (i ? ROW_STAGES : ROW_ENTRY)) {
            duration(stages[i].end - stages[i].begin, time, sizeof(time));
            snprintf(lines[rows], 72, "%s: %s", i ? stageName(stages[i].scene) : "Entry", time);
            colors[rows++] = 1;
        }
        if (i + 1 == count) continue;
        if (sBreakdownRows & ROW_LOAD) {
            milliseconds(stages[i].loadMs, time, sizeof(time));
            snprintf(lines[rows], 72, "  Load (real): %s", time);
            colors[rows++] = 1;
        }
        if (sBreakdownRows & ROW_ALLOWANCE) {
            duration(stages[i + 1].begin - stages[i].end, time, sizeof(time));
            snprintf(lines[rows], 72, "  QFT transition: %s", time);
            colors[rows++] = 1;
        }
    }
    if (sBreakdownRows & ROW_TOTAL) {
        char time[24]; duration(stages[count - 1].end, time, sizeof(time));
        snprintf(lines[rows], 72, "QFT total: %s", time); colors[rows++] = 2;
    }
    if (!rows) return;
    const int size = 12 * sBreakdownStyle.scale / 100;
    const int rowH = 17 * sBreakdownStyle.scale / 100;
    int width = 0;
    for (unsigned i = 0; i < rows; ++i) {
        const int w = Creation::textWidth(lines[i], size);
        if (w > width) width = w;
    }
    const int pad = sBreakdownStyle.padding == 255 ? 0 : sBreakdownStyle.padding;
    if (sBreakdownStyle.padding != 255) menu->fillBox(sBreakdownStyle.x, sBreakdownStyle.y, width + pad * 2,
                  rows * rowH + pad * 2,
                  JUtility::TColor(sBreakdownStyle.bgR, sBreakdownStyle.bgG, sBreakdownStyle.bgB, sBreakdownStyle.bgA));
    for (unsigned i = 0; i < rows; ++i)
        Creation::drawTextLine(menu, sBreakdownStyle, &sBreakdownRgb[colors[i]], 1, lines[i],
            sBreakdownStyle.x + pad, sBreakdownStyle.y + pad + i * rowH,
            size, 0, true);
}
}

namespace FinishBreakdown {
void onStageSetup() {
    ++sBreakdownSetup;
    if (sBreakdownResultFrames == 0xffff) sBreakdownResultFrames = 0;
    sBreakdownLoadMs = ~0u;
    if (sBreakdownLoading) {
        const OSTime elapsed = OSGetTime() - sBreakdownDeparture;
        if (elapsed >= 0 && elapsed < OSSecondsToTicks((OSTime)600))
            sBreakdownLoadMs = (u32)OSTicksToMilliseconds(elapsed);
        sBreakdownLoading = false;
    }
}
void onDeparture() {
    if (sBreakdownResultFrames == 0xffff) sBreakdownResultFrames = 0;
    if (sBreakdownSegments.valid && !sBreakdownSegments.complete && !sBreakdownLoading) {
        sBreakdownDeparture = OSGetTime();
        sBreakdownLoading = true;
    }
}
void invalidate() {
    sBreakdownSegments.invalidate();
    sBreakdownSegments.serial = gQFTTimer.attemptSerial();
    sBreakdownSegments.seen = true;
    sBreakdownResultFrames = 0;
    sBreakdownLoading = false;
}
void sample() {
    if (Ghost::observerStatsSuppressed()) { invalidate(); return; }
    s32 qf;
    if (!gQFTTimer.currentQf(&qf)) return;
    const TGameSequence &scene = gpApplication.mCurrentScene;
    if (sBreakdownSegments.serial != gQFTTimer.attemptSerial() && sBreakdownResultFrames == 0xffff)
        sBreakdownResultFrames = 0;
    sBreakdownSegments.sample(gQFTTimer.attemptSerial(), sBreakdownSetup,
                     (u16)((scene.mEpisodeID << 8) | scene.mAreaID), qf,
                     gpMarDirector->unk5C, sBreakdownLoadMs);
    u16 target;
    if (gQFTTimer.transitionEntryQf(&qf, &target)) sBreakdownSegments.transition(qf);
}
void finish(int entry, s32 qf) {
    sBreakdownResultFrames = 0;
    if (!sBreakdownSegments.finish(qf)) return;
    sBreakdownResultCount = sBreakdownSegments.count;
    for (unsigned i = 0; i < sBreakdownResultCount; ++i) sBreakdownResult[i] = sBreakdownSegments.stages[i];
    sBreakdownEntry = entry;
    sBreakdownResultFrames = sBreakdownHalfSeconds ? sBreakdownHalfSeconds * 15 : 0xffff;
}
void draw(Menu *menu) {
    if (!sBreakdownResultFrames || !menu || menu->shown() || StageLoader::modal() || WarpWheel::shown()) return;
    if (sBreakdownResultFrames != 0xffff) --sBreakdownResultFrames;
    if (gSettings.getBool(SETTING_FINISH_BREAKDOWN)) drawPanel(menu, false);
}
void resetDefaults() {
    SusamuneFinishBreakdownCfg defaults;
    SusamuneFinishBreakdownInit(&defaults);
    adopt(&defaults);
    sBreakdownEditorPage = 0;
    sBreakdownEditor.reset();
    sBreakdownDirty = true;
}
bool dirty() { return sBreakdownDirty; }
void clearDirty() { sBreakdownDirty = false; }
void adopt(const volatile SusamuneFinishBreakdownCfg *cfg) {
    if (!SusamuneFinishBreakdownValid(cfg)) return;
    sBreakdownStyle = styleOf(*cfg);
    memcpy(sBreakdownRgb, (const void *)cfg->rgb, sizeof(sBreakdownRgb));
    sBreakdownRows = cfg->rows;
    sBreakdownHalfSeconds = cfg->halfSeconds;
    sBreakdownDirty = false;
}
void stageInto(volatile SusamuneFinishBreakdownCfg *cfg) {
    memset((void *)cfg, 0, sizeof(*cfg));
    cfg->magic = SUSAMUNE_FINISH_BREAKDOWN_MAGIC; cfg->version = SUSAMUNE_FINISH_BREAKDOWN_VERSION;
    cfg->x = sBreakdownStyle.x; cfg->y = sBreakdownStyle.y; cfg->scale = sBreakdownStyle.scale;
    cfg->textA = sBreakdownStyle.textA; cfg->bgR = sBreakdownStyle.bgR; cfg->bgG = sBreakdownStyle.bgG;
    cfg->bgB = sBreakdownStyle.bgB; cfg->bgA = sBreakdownStyle.bgA;
    cfg->textBrightness = sBreakdownStyle.textBrightness; cfg->padding = sBreakdownStyle.padding;
    memcpy((void *)cfg->rgb, sBreakdownRgb, sizeof(sBreakdownRgb));
    cfg->rows = sBreakdownRows; cfg->halfSeconds = sBreakdownHalfSeconds;
}
void beginEditor() { sBreakdownEditorPage = 1; sBreakdownEditorRow = 0; }
bool editing() { return sBreakdownEditorPage != 0; }
void updateEditor(Menu *menu, TMarioGamePad *pad) {
    if (sBreakdownEditorPage == 2) {
        SusamuneFinishBreakdownCfg defaults;
        SusamuneFinishBreakdownInit(&defaults);
        const u8 result = sBreakdownEditor.update(pad, styleOf(defaults), defaults.rgb, 3);
        if (result & CreationEditor::UPDATE_CHANGED) sBreakdownDirty = true;
        if (result & CreationEditor::UPDATE_FINISHED) sBreakdownEditorPage = 1;
        return;
    }
    const u32 rapid = menu->navigationInput(pad);
    if (rapid & TMarioGamePad::B) { sBreakdownEditorPage = 0; return; }
    if (rapid & TMarioGamePad::CSTICK_UP) sBreakdownEditorRow = (sBreakdownEditorRow + 10) % 11;
    else if (rapid & TMarioGamePad::CSTICK_DOWN) sBreakdownEditorRow = (sBreakdownEditorRow + 1) % 11;
    const int dir = rapid & TMarioGamePad::CSTICK_LEFT ? -1 :
        rapid & (TMarioGamePad::CSTICK_RIGHT | TMarioGamePad::A) ? 1 : 0;
    if (!dir) return;
    if (sBreakdownEditorRow == 0) gSettings.cycle(SETTING_FINISH_BREAKDOWN, dir);
    else if (sBreakdownEditorRow == 1) {
        sBreakdownEditor.begin(&sBreakdownStyle, sBreakdownRgb, sBreakdownBackupRgb, 3, 3, "Title\0Rows\0Total");
        sBreakdownEditor.setScaleLimits(25, 150);
        sBreakdownEditorPage = 2;
    } else if (sBreakdownEditorRow == 2) {
        unsigned i = 0;
        while (i < sizeof(kDurations) && kDurations[i] != sBreakdownHalfSeconds) ++i;
        sBreakdownHalfSeconds = kDurations[(i + sizeof(kDurations) + dir) % sizeof(kDurations)];
        sBreakdownDirty = true;
    } else if (sBreakdownEditorRow < 10) {
        sBreakdownRows ^= 1u << (sBreakdownEditorRow - 3);
        sBreakdownDirty = true;
    } else { resetDefaults(); sBreakdownEditorPage = 1; sBreakdownEditorRow = 10; }
}
void drawEditor(Menu *menu) {
    if (sBreakdownEditorPage == 2) {
        drawPanel(menu, true);
        sBreakdownEditor.draw(menu, "Finish breakdown style", nullptr);
        return;
    }
    menu->fillBox(36, 38, 568, 402, JUtility::TColor(8, 14, 25, 245));
    menu->drawText("Finish breakdown", 54, 52, 18, 18, JUtility::TColor(210, 235, 255, 255));
    for (unsigned i = 0; i < 11; ++i) {
        const char *name = i == 0 ? "Show breakdown" : i == 1 ? "Position, size and colours" :
            i == 2 ? "Keep visible" : i == 10 ? "Reset breakdown style" : PackedText::at(kRowNames, i - 3);
        char value[32];
        if (i == 0) snprintf(value, sizeof(value), "%s", gSettings.getBool(SETTING_FINISH_BREAKDOWN) ? "On" : "Off");
        else if (i == 1) snprintf(value, sizeof(value), "Edit");
        else if (i == 2) {
            if (sBreakdownHalfSeconds) snprintf(value, sizeof(value), "%u.%u s", sBreakdownHalfSeconds / 2, sBreakdownHalfSeconds % 2 * 5);
            else snprintf(value, sizeof(value), "Until leaving level");
        } else if (i < 10) snprintf(value, sizeof(value), "%s", (sBreakdownRows & (1u << (i - 3))) ? "Show" : "Hide");
        else value[0] = 0;
        const int y = 86 + i * 25;
        if (sBreakdownEditorRow == i) menu->fillBox(47, y - 2, 546, 23, JUtility::TColor(40, 75, 110, 235));
        menu->drawText(name, 56, y, 13, 13, JUtility::TColor(240, 245, 255, 255));
        menu->drawText(value, 582 - Menu::textWidth(value, 13), y, 13, 13, JUtility::TColor(150, 230, 200, 255));
    }
    menu->drawText("Actual load is separate from QFT's transition time.", 54, 378, 11, 11, JUtility::TColor(175, 205, 230, 255));
    menu->drawText("C-stick: choose/change   A: edit/toggle   B: back", 54, 405, 12, 12, JUtility::TColor(220, 230, 245, 255));
}
}
