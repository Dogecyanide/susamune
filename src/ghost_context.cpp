#include "susamune/ghost_context.hxx"
#include "susamune/ghost_stage_context.hxx"
#include "susamune/ghost_simulation.hxx"
#include "susamune/checksum.hxx"
#include "Dolphin/mem.h"
#include "Dolphin/string.h"

namespace GhostContext {
namespace {
struct Runtime { u32 frame; u16 segment; bool seen, restore; };
u32 sFrame;
bool sDetails;
static_assert(SUSAMUNE_GHOST_CONTEXT_BANK_OFFSET + SUSAMUNE_GHOST_CONTEXT_MAX_SIZE +
              sizeof(Runtime) <= 0x695e0u, "context tracker overlaps model storage");
SusamuneGhostContextHeader *header(void *bank) {
    return static_cast<SusamuneGhostContextHeader *>(prefix(bank));
}
SusamuneGhostContextRecord *rows(void *bank) {
    return reinterpret_cast<SusamuneGhostContextRecord *>(header(bank) + 1);
}
Runtime &runtime(void *bank) {
    return *reinterpret_cast<Runtime *>(static_cast<u8 *>(prefix(bank)) + SUSAMUNE_GHOST_CONTEXT_MAX_SIZE);
}
bool sane(const SusamuneGhostContextHeader *h) {
    return h && h->magic == SUSAMUNE_GHOST_CONTEXT_MAGIC && h->version == 1 &&
        h->headerSize == 32 && h->recordSize == 96 && h->settingsSchema == 1 &&
        h->count <= SUSAMUNE_GHOST_CONTEXT_MAX_COUNT;
}
bool append(void *bank, u16 segment, u8 kind, u32 qf, u32 index, bool synthetic = false) {
    auto *h = header(bank);
    if (!sane(h) || segment >= 64) return false;
    // Leave room for one first-observation record in every remaining segment.
    const u32 limit = kind == SUSAMUNE_GHOST_CONTEXT_SEGMENT ?
        SUSAMUNE_GHOST_CONTEXT_MAX_COUNT : SUSAMUNE_GHOST_CONTEXT_MAX_COUNT - (63 - segment);
    if (h->count >= limit) { h->flags |= SUSAMUNE_GHOST_CONTEXT_TRUNCATED; return false; }
    if (h->count && (rows(bank)[h->count-1].captureQf > qf ||
        (rows(bank)[h->count-1].segment == segment &&
         rows(bank)[h->count-1].kind >= SUSAMUNE_GHOST_CONTEXT_HELD_END))) return false;
    SusamuneGhostContextRecord r = {};
    r.captureQf = qf; r.inputIndex = index; r.sourceFrameSerial = sFrame;
    r.segment = segment; r.kind = kind;
    if (synthetic) r.flags |= SUSAMUNE_GHOST_CONTEXT_SYNTHETIC_START;
    if (GhostStageContext::restoredStage()) r.flags |= SUSAMUNE_GHOST_CONTEXT_RESTORED;
    const bool annotation = kind >= SUSAMUNE_GHOST_CONTEXT_HELD_END;
    GhostStageContext::Sample stage;
    if (!annotation && GhostStageContext::sample(&stage)) {
        r.preSetupSeed = stage.seed; r.movementTicks = stage.movementTicks;
        r.directorTicks = stage.directorTicks;
        r.flags |= SUSAMUNE_GHOST_CONTEXT_SEED_KNOWN | SUSAMUNE_GHOST_CONTEXT_AGE_KNOWN;
    }
    GhostSimulation::CameraObservation camera;
    GhostSimulation::readCamera(camera);
    if (!annotation && camera.valid) {
        r.cameraYaw = camera.yaw; r.cameraMode = camera.mode;
        r.flags |= SUSAMUNE_GHOST_CONTEXT_CAMERA_KNOWN;
        if (camera.varied) r.flags |= SUSAMUNE_GHOST_CONTEXT_YAW_VARIED;
    }
    // A synthetic finish may be backdated; do not label today's clocks as its age.
    if (annotation && h->count) memcpy(r.settings, rows(bank)[h->count-1].settings, sizeof(r.settings));
    else {
        GhostSimulation::Snapshot settings;
        GhostSimulation::capture(settings);
        memcpy(r.settings, settings.bytes, sizeof(r.settings));
    }
    rows(bank)[h->count++] = r;
    return true;
}
}
bool detailsEnabled() { return sDetails; }
void toggleDetails() { sDetails = !sDetails; }
void beginFrame() { ++sFrame; }
void *prefix(void *bank) { return bank ? static_cast<u8 *>(bank) + SUSAMUNE_GHOST_CONTEXT_BANK_OFFSET : nullptr; }
const void *prefix(const void *bank) { return prefix(const_cast<void *>(bank)); }
u32 prefixSize(const void *bank) {
    auto *h = header(const_cast<void *>(bank));
    return sane(h) ? 32 + h->count * 96 : 0;
}
void reset(void *bank) {
    if (!bank) return;
    auto *h = header(bank); memset(h, 0, sizeof(*h));
    h->magic = SUSAMUNE_GHOST_CONTEXT_MAGIC; h->version = 1; h->headerSize = 32;
    h->recordSize = 96; h->settingsSchema = 1;
    memset(&runtime(bank), 0, sizeof(Runtime));
}
void clearSegment(void *bank, u16 segment) {
    auto *h = header(bank); if (!sane(h)) return;
    while (h->count && rows(bank)[h->count-1].segment >= segment) --h->count;
    memset(&runtime(bank), 0, sizeof(Runtime));
}
void segment(void *bank, u16 segment, u32 qf, u32 index, bool synthetic) {
    clearSegment(bank, segment);
    append(bank, segment, SUSAMUNE_GHOST_CONTEXT_SEGMENT, qf, index, synthetic);
}
void input(void *bank, u16 segment, u32 qf, u32 index) {
    auto *h = header(bank); if (!sane(h)) return;
    Runtime &state = runtime(bank);
    if (state.restore) {
        append(bank, segment, SUSAMUNE_GHOST_CONTEXT_RESTORE, qf, index);
        state.restore = false;
    } else if (state.seen && state.segment == segment && sFrame - state.frame != 1) {
        append(bank, segment, SUSAMUNE_GHOST_CONTEXT_INPUT_GAP, qf, index);
    }
    GhostSimulation::Snapshot settings;
    GhostSimulation::capture(settings);
    if (h->count && memcmp(settings.bytes, rows(bank)[h->count-1].settings, sizeof(settings)))
        append(bank, segment, SUSAMUNE_GHOST_CONTEXT_SETTINGS, qf, index);
    state.frame = sFrame; state.segment = segment; state.seen = true;
}
void endpoint(void *bank, u16 segment, u32 qf, u32 inputCount, bool held) {
    auto *h = header(bank); if (!sane(h)) return;
    while (h->count && rows(bank)[h->count-1].captureQf > qf) --h->count;
    append(bank, segment, held ? SUSAMUNE_GHOST_CONTEXT_HELD_END :
        SUSAMUNE_GHOST_CONTEXT_INTERPOLATED_END, qf, inputCount);
}
void restored(void *bank) {
    if (!sane(header(bank))) return;
    memset(&runtime(bank), 0, sizeof(Runtime)); runtime(bank).restore = true;
}
u32 exportSize(const void *bank, u32 endQf) {
    auto *h = header(const_cast<void *>(bank)); if (!sane(h)) return 0;
    u32 count = h->count;
    while (count && rows(const_cast<void *>(bank))[count-1].captureQf > endQf) --count;
    return 32 + count * 96;
}
bool exportInto(void *out, const void *bank, u32 endQf, u32 firstInput, u32 inputCount) {
    const u32 size = exportSize(bank, endQf); if (!out || !size) return false;
    memcpy(out, prefix(bank), size);
    auto *h = static_cast<SusamuneGhostContextHeader *>(out); h->count = (size-32)/96;
    auto *data = reinterpret_cast<SusamuneGhostContextRecord *>(h+1);
    for (u32 i = 0; i < h->count; ++i) {
        if (data[i].inputIndex < firstInput) {
            data[i].inputIndex = 0; data[i].flags |= SUSAMUNE_GHOST_CONTEXT_BEFORE_INPUTS;
        } else data[i].inputIndex -= firstInput;
        if (data[i].inputIndex > inputCount) data[i].inputIndex = inputCount;
    }
    h->dataChecksum = Checksum::crc32(data, size-32);
    return true;
}
}
