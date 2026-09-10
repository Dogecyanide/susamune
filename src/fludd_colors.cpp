#include "susamune/fludd_colors.hxx"

#include "Dolphin/mem.h"
#include "SMS/Player/MarioGamePad.hxx"
#include "susamune/creation.hxx"
#include "susamune/raw_prompt_input.hxx"
#include "susamune/susamune_cfg.h"

#pragma clang section text=".foxtrot.text" rodata=".foxtrot.rodata" data=".foxtrot.data" bss=".foxtrot.bss"

namespace FluddColors {
namespace {

const char kPartNames[] =
    "Body paint\0Metal\0Straps\0Tank\0Spray nozzle\0Hover nozzle\0"
    "Rocket nozzle\0Turbo nozzle\0Sprayed water\0Water highlights";
const CreationStyle kEditorStyle = {320, 420, 100, 255, 0, 0, 0, 0, 100, 255};
const u8 kDefaultRgb[1][3] = {{255, 255, 255}};
const u16 kPromptButtons = JUTGamePad::A | JUTGamePad::B |
                           JUTGamePad::Z | JUTGamePad::START;
struct State {
    CreationStyle style;
    CreationEditor editor;
    RawPromptInput input;
    u8 colors[PART_COUNT][3];
    u8 backup[PART_COUNT][3];
    u16 enabled;
    u16 enabledBefore;
    bool dirty;
    bool dirtyBefore;
    bool releaseGuard;
} sState;
static_assert(PART_COUNT == SUSAMUNE_FLUDD_COLORS_COUNT, "FLUDD colour slots moved");
static_assert(sizeof(State) <= 224, "FLUDD colour editor state grew");

} // namespace

const u8 *rgb(unsigned part) { return part < PART_COUNT ? sState.colors[part] : nullptr; }
bool enabled(unsigned part) { return part < PART_COUNT && (sState.enabled & (1u << part)); }
bool dirty() { return sState.editor.editing() ? sState.dirtyBefore : sState.dirty; }
void clearDirty() {
    if (sState.editor.editing()) sState.dirtyBefore = false;
    else sState.dirty = false;
}
bool editing() { return sState.editor.editing() || sState.releaseGuard; }

void resetDefaults() {
    Creation::fillWhite(sState.colors, PART_COUNT);
    sState.enabled = sState.enabledBefore = 0;
    sState.editor.reset();
    sState.input.clear();
    sState.dirty = sState.dirtyBefore = sState.releaseGuard = false;
}

void adopt(const volatile SusamuneFluddColorsCfg *source) {
    if (!source || source->magic != SUSAMUNE_FLUDD_COLORS_MAGIC ||
        source->version != SUSAMUNE_FLUDD_COLORS_VERSION ||
        (source->enabled & ~SUSAMUNE_FLUDD_COLORS_MASK)) return;
    memcpy(sState.colors, (const void *)source->rgb, sizeof(sState.colors));
    sState.enabled = source->enabled;
    sState.dirty = false;
}

void stageInto(volatile SusamuneFluddColorsCfg *destination) {
    // A prior settings save can finish while this preview is unconfirmed.
    const bool preview = sState.editor.editing();
    memset((void *)destination, 0, sizeof(*destination));
    destination->magic = SUSAMUNE_FLUDD_COLORS_MAGIC;
    destination->version = SUSAMUNE_FLUDD_COLORS_VERSION;
    destination->enabled = (u16)(preview ? sState.enabledBefore : sState.enabled);
    memcpy((void *)destination->rgb, preview ? sState.backup : sState.colors,
           sizeof(sState.colors));
}

void beginEditor() {
    if (editing()) return;
    sState.dirtyBefore = sState.dirty;
    sState.dirty = false;
    sState.enabledBefore = sState.enabled;
    sState.style = kEditorStyle;
    sState.editor.begin(&sState.style, sState.colors, sState.backup,
        PART_COUNT, PART_COUNT, kPartNames, CreationEditor::CAP_TEXT_COLOR |
        CreationEditor::CAP_COLOR_MODE | CreationEditor::CAP_RGB_ENABLES_CUSTOM,
        &sState.enabled);
    sState.input.begin(kPromptButtons);
}

void updateEditor(TMarioGamePad *pad) {
    if (!pad) return;
    if (sState.releaseGuard) {
        if (!(JUTGamePad::mPadStatus[0].mButton & kPromptButtons))
            sState.releaseGuard = false;
        return;
    }
    if (!sState.editor.editing()) return;
    const u32 original = pad->mButtons.mRapidInput;
    pad->mButtons.mRapidInput = (original & ~kPromptButtons) | sState.input.update();
    const u8 result = sState.editor.update(pad, kEditorStyle, kDefaultRgb);
    pad->mButtons.mRapidInput = original;
    if (result & CreationEditor::UPDATE_CHANGED) sState.dirty = true;
    if (result & CreationEditor::UPDATE_CANCELLED) sState.dirty = sState.dirtyBefore;
    else if (result & CreationEditor::UPDATE_FINISHED) sState.dirty |= sState.dirtyBefore;
    // Keep the final confirmation press away from the menu underneath.
    if (result & CreationEditor::UPDATE_FINISHED) sState.releaseGuard = true;
}

void drawEditor(Menu *menu) { sState.editor.draw(menu, "FLUDD colours", ""); }

} // namespace FluddColors
