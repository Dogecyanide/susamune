#include "susamune/loading_trace.hxx"
#include "susamune/ghost_world_runtime.hxx"
#include "susamune/ghost_stage_context.hxx"
#include "susamune/ghost_trace.hxx"
#include "susamune/ghost_recording.hxx"
#include "susamune/addresses.hxx"
#include "susamune/features.hxx"
#include "susamune/retail_input.hxx"
#include "SMS/System/MarDirector.hxx"

extern "C" s32 susamuneGhostStageSetup(TMarDirector *, JDrama::TDisplay *,
                                      TMarioGamePad **, u8, u8);

namespace GhostStageContext {
namespace {
TMarDirector *sDirector;
u32 sSeed, sGeneration;
u8 sArea, sEpisode;
bool sInstalled, sRestored;

const u32 kSetupSite = SUSAMUNE_MEM1_ADDR(0x800f9f70u, 0x802a656cu, 0x8029e4a8u);
const u32 kSetupRetail = SUSAMUNE_MEM1_ADDR(0x4bff03adu, 0x4bff07f5u, 0x4bff0751u);
}

void init() {
    const u32 target = static_cast<u32>(reinterpret_cast<__UINTPTR_TYPE__>(&susamuneGhostStageSetup));
    const s32 distance = static_cast<s32>(target - kSetupSite);
    if ((target & 3u) || distance < -0x02000000 || distance >= 0x02000000) return;
    const u32 branch = 0x48000001u | (static_cast<u32>(distance) & 0x03fffffcu);
    const u32 original = *reinterpret_cast<volatile const u32 *>(kSetupSite);
    if (original == kSetupRetail) writeGameCode(kSetupSite, branch);
    sInstalled = original == kSetupRetail || original == branch;
}

u32 generation() {
    return sInstalled && sDirector && RetailInput::stageDirector() == sDirector ? sGeneration : 0;
}

bool sample(Sample *out) {
    TMarDirector *director = RetailInput::stageDirector();
    if (!out || !sInstalled || !sDirector || director != sDirector ||
        director != gpMarDirector || !director->_260 ||
        director->mAreaID != sArea || director->mEpisodeID != sEpisode) return false;
    // +0x58 excludes paused movement; +0x5c includes every director tick.
    *out = {sSeed, static_cast<u32>(director->unk58),
            static_cast<u32>(director->unk5C), sGeneration, sArea, sEpisode};
    return true;
}

void invalidateAfterRestore() {
    // A restored heap may have been constructed with a different seed.
    sDirector = nullptr;
    sRestored = true;
}

bool restoredStage() { return sRestored; }
} // namespace GhostStageContext

extern "C" s32 susamuneGhostStageSetup(TMarDirector *director, JDrama::TDisplay *display,
                                      TMarioGamePad **pads, u8 area, u8 episode) {
    using namespace GhostStageContext;
    LoadingTrace::mark(MS_LOAD_THREAD_BEGIN,(unsigned(area)<<8)|episode);
    sDirector = director;
    sRestored = false;
    if (!++sGeneration) ++sGeneration;
    sArea = area;
    sEpisode = episode;
    GhostWorldRuntime::stageSetup(area, episode, sGeneration);
    sSeed = *reinterpret_cast<volatile const u32 *>(SUSAMUNE_ADDR_LIBC_RAND_SEED);
    GhostRecording::automaticStageSetup((unsigned(area)<<8)|episode);
    GhostTrace::stageSetup(area, episode, sGeneration);
    const s32 result = director->setup(display, pads, area, episode);
    if (result != 0) sDirector = nullptr;
    return result;
}
