#include "susamune/practice_session.hxx"
#include "susamune/crash_report.hxx"
// =====================================================================
// savestate.cpp
//
// Emulator-style savestates for Super Mario Sunshine running under
// Nintendont. Hooked once per frame from main.cpp::onUpdate; D-pad LEFT
// snapshots, D-pad RIGHT restores.
//
// What gets snapshotted
// ---------------------
// 1. The current "stage" heap: gpApplication.mCurrentHeap is a
//    JKRSolidHeap (created in TApplication::initialize_nlogoAfter) that
//    fills the rest of the root heap. Almost every per-stage allocation
//    lives here -- TMario, every enemy, MapObj, particles, the scene
//    graph, the camera, etc. Each director cycle the game does a
//    freeAll() on this heap, so its high-water layout is stable for the
//    duration of one scenario.
//
// 2. The "game half" of .bss / .sdata / .sbss. Pointers from heap-resident
//    objects into BSS (and back) need to survive a load, so we restore the
//    parts of BSS that hold mutable game state -- the TFlagManager
//    singleton pointer, gpMarDirector, gpMSound, the libc rand() state,
//    every game module's static counters/caches. The boundaries below were
//    derived from the selected maps/<version>.map: the first game-side modules are
//    MarioUtil.a/DrawUtil.cpp in .bss/.sbss and MoveBG.a/MapObjGeneral.cpp
//    in .sdata. Everything below those addresses is JSystem / JAudio /
//    runtime / OS / DVD / VI / PAD / CARD / GX / SI / EXI / THP / debugger
//    state which we DO NOT touch -- restoring OS thread queues, DVD command
//    queues, audio DSP mailboxes, etc. would crash the console.
//
// What is intentionally not snapshotted
// -------------------------------------
// .data    : almost entirely vtables and static const tables. Read-only at
//            runtime, so no need to copy it back.
// stack    : we are running on it.
// system   : everything before the selected game-side range in each section.
// audio    : MSound has internal queues that reference DSP-side state. We
//            stopAllSound() before save AND before restore so the audio
//            engine never sees inconsistent state.
//
// Invariants for a successful load
// --------------------------------
// - Same build (vtable addresses, BSS layout)
// - Same scenario as the snapshot (same area + episode)
// - Heap object ended up at the same address (deterministic boot)
// - No async DVD / archive load in flight (best-effort: gameplay is
//   normally quiescent)
//
// Where the snapshot lives
// ------------------------
// On Wii via Nintendont, MEM2 cached lives at 0x90000000 / uncached at
// 0xD0000000. The custom launcher reserves a dedicated 16 MiB physical
// window and relocates all Nintendont buffers below it; mem2_map.h is the
// shared source of truth for the PPC mod/loader and ARM kernel. On Dolphin
// we just pick a spot in the emulator's larger virtual space.
// =====================================================================

#include "susamune/savestate.hxx"
#include "susamune/addresses.hxx"
#include "susamune/binds.hxx"
#include "susamune/creation_extras.hxx"
#include "susamune/features.hxx"
#include "susamune/ghost.hxx"
#include "susamune/ghost_storage.hxx"
#include "susamune/mem2_map.h"
#include "susamune/qft_timer.hxx"
#include "susamune/split_events.hxx"
#include "susamune/split_stats.hxx"
#include "susamune/iling.hxx"
#include "susamune/records.hxx"
#include "susamune/rng_control.hxx"
#include "susamune/movement_display.hxx"
#include "susamune/warp_wheel.hxx"
#include "susamune/menu.hxx"
#include "susamune/settings.hxx"
#include "susamune/state_codec.hxx"
#include "susamune/state_slot_pool.h"
#include "susamune/state_pool_runtime.hxx"
#include "susamune/state_storage.hxx"
#include "susamune/state_archive_profile.hxx"
#include "Dolphin/CARD.h"
#include "Dolphin/GX.h"
#include "Dolphin/mem.h"
#include "Dolphin/OS.h"
#include "Dolphin/printf.h"
#include "Dolphin/string.h"
#include "JKernel/JKRHeap.hxx"
#include "JUtility/JUTGamePad.hxx"
#include "SMS/GC2D/SmplFader.hxx"
#include "SMS/MSound/MSound.hxx"
#include "SMS/Manager/FlagManager.hxx"
#include "SMS/Manager/RumbleManager.hxx"
#include "SMS/Player/MarioGamePad.hxx"
#include "SMS/System/Application.hxx"
#include "SMS/System/CardManager.hxx"
#include "SMS/System/MarDirector.hxx"


// ---------------------------------------------------------------------
// Build configuration
// ---------------------------------------------------------------------

#if IS_EMULATOR
// Dolphin: a region in the emulator's "free" space.
static const u32 kSnapshotBase = SUSAMUNE_DOLPHIN_SNAPSHOT_PPC_BASE;
static const u32 kStagingBase = SUSAMUNE_DOLPHIN_STATE_STAGING_PPC_BASE;
#else
// Wii: a dedicated 16 MiB window. The custom Nintendont memory map relocates
// all of its former users below this address; the ARM kernel begins exactly at
// the window's exclusive end.
static const u32 kSnapshotBase = SUSAMUNE_MEM2_SNAPSHOT_PPC_BASE;
static const u32 kStagingBase = SUSAMUNE_STATE_STAGING_PPC_BASE;
#endif

// How much MEM2 we promise not to step outside of. The actual snapshot is
// (game-bss + game-sdata + game-sbss + heap), which should be under 16MiB.
static const u32 kSnapshotReservedSize = SUSAMUNE_MEM2_SNAPSHOT_SIZE;


// ---------------------------------------------------------------------
// Static memory regions to snapshot (game-side BSS / sdata / sbss).
// Boundaries come from maps/<version>.map. The first game modules are
// MarioUtil.a/DrawUtil.cpp in BSS/SBSS and MoveBG.a/MapObjGeneral.cpp in
// SDATA; every range stops before the JSystem/runtime portion of that linker
// section. Section ends are unsafe: they include live renderer, DSP, heap,
// and OS state that must not be restored.
//
// gpApplication itself sits at the very top of .bss (main.o) and holds
// pointers and scene-id fields TApplication touches every frame, so we
// pull it in as a one-off range.
// ---------------------------------------------------------------------

namespace {

// A range is captured unconditionally when gate == kNoGate; otherwise it is
// only captured while the named setting is enabled. This lets a menu toggle
// exclude a range from the snapshot (e.g. the libc RNG seed) without touching
// the save/load machinery. Unsigned sentinel deliberately: a -1 in a `char`
// field only reads back as -1 while -fsigned-char is in force.
const u8 kNoGate = 0xFFu;

struct StaticRange {
    u32 start;
    u32 end;
    u8  gate;  // kNoGate, or a SettingId that must be enabled
};

const StaticRange kStaticRanges[] = {
    { SUSAMUNE_ADDR_APPLICATION, SUSAMUNE_ADDR_APPLICATION + sizeof(TApplication), kNoGate },
#if defined(SUSAMUNE_VERSION_JP)
    // The audio and THP blocks hold live thread/JAudio state, so every region
    // snapshots only the game-owned runs around them. Boundaries come directly
    // from each retail link map.
    { SUSAMUNE_ADDR_GAME_BSS_START, 0x803f2c38u, kNoGate }, // .. before MSoundMainSide
    { 0x803f2cf0u,                  0x803f44d0u, kNoGate }, // after MSoundMainSide .. before MSound.a
    { 0x803f57a0u,                  SUSAMUNE_ADDR_GAME_BSS_END, kNoGate }, // after MSound.a ..
#elif defined(SUSAMUNE_VERSION_US)
    { SUSAMUNE_ADDR_GAME_BSS_START, 0x803e9b10u, kNoGate }, // Animal .. before MSound.a
    { 0x803efcb0u, 0x803fd490u, kNoGate }, // after THP .. before MSoundMainSide
#elif defined(SUSAMUNE_VERSION_PAL)
    { SUSAMUNE_ADDR_GAME_BSS_START, 0x803e14d0u, kNoGate }, // Animal .. before MSound.a
    { 0x803e7670u, 0x803f4c30u, kNoGate }, // after THP .. before MSoundMainSide
#endif
#if defined(SUSAMUNE_VERSION_JP)
    { SUSAMUNE_ADDR_GAME_SDATA_START, 0x80408fc0u, kNoGate }, // before MSound.a
    { 0x80408fe8u, SUSAMUNE_ADDR_GAME_SDATA_END, kNoGate },  // after MSound.a

    { SUSAMUNE_ADDR_GAME_SBSS_START, 0x8040a268u, kNoGate }, // before JAL audio lists
    { 0x8040a290u, 0x8040a318u, kNoGate }, // after lists .. before MSoundMainSide
    { 0x8040a348u, 0x8040a4b0u, kNoGate }, // after MSoundMainSide .. before MSound.a
    { 0x8040a4d0u, SUSAMUNE_ADDR_GAME_SBSS_END, kNoGate }, // after MSound.a
#elif defined(SUSAMUNE_VERSION_US)
    { SUSAMUNE_ADDR_GAME_SDATA_START, SUSAMUNE_ADDR_GAME_SDATA_END, kNoGate },

    { SUSAMUNE_ADDR_GAME_SBSS_START, 0x8040cf08u, kNoGate }, // fishoid
    { 0x8040cfd0u, 0x8040d058u, kNoGate }, // Animal after JAL audio lists
    { 0x8040d0a8u, 0x8040e1e8u, kNoGate }, // after THP .. before MSoundMainSide
    { 0x8040e220u, SUSAMUNE_ADDR_GAME_SBSS_END, kNoGate }, // TargetArrow
#elif defined(SUSAMUNE_VERSION_PAL)
    { SUSAMUNE_ADDR_GAME_SDATA_START, SUSAMUNE_ADDR_GAME_SDATA_END, kNoGate },

    { SUSAMUNE_ADDR_GAME_SBSS_START, 0x80404668u, kNoGate }, // fishoid
    { 0x80404730u, 0x804047b8u, kNoGate }, // Animal after JAL audio lists
    { 0x80404808u, 0x804058c0u, kNoGate }, // after THP .. before MSoundMainSide
    { 0x804058f8u, SUSAMUNE_ADDR_GAME_SBSS_END, kNoGate }, // TargetArrow
#endif
    // MSL rand.c `next` -- the seed for libc rand()/srand(), which every
    // gameplay RNG funnels through (MarioUtil MsRandF/MsRandI, so King Boo's
    // fruit pulls, Gooper Blooper / manta patterns, enemy timers). It sits
    // below the game-sdata boundary, so it needs its own row. A plain counter
    // with no hardware linkage, so restoring it is safe. Off leaves the seed
    // advancing across a load instead of rewinding with the state.
    { SUSAMUNE_ADDR_LIBC_RAND_SEED, SUSAMUNE_ADDR_LIBC_RAND_SEED + sizeof(u32),
      SETTING_SAVE_RNG_STATE },
};
const int kNumStaticRanges = sizeof(kStaticRanges) / sizeof(kStaticRanges[0]);

// Pointed-to allocations: globals in BSS that hold a pointer to a
// root-heap-allocated object the game mutates every frame. The static
// ranges above already preserve the *pointer* (it lives in BSS), but the
// pointed-to *bytes* are on the root heap, which is outside our heap
// snapshot. So we follow each pointer at save time and capture its
// target as an additional region.
struct PointedAlloc {
    u32 ptr_addr;     // address of the global pointer (in BSS)
    u32 size;         // bytes to capture from *(*ptr_addr)
};

const PointedAlloc kPointedAllocs[] = {
    // TFlagManager::smInstance -- coin counts, shines, episode flags,
    // life count, etc. Without this, coin pickups are forgotten on load.
    { SUSAMUNE_ADDR_FLAG_MANAGER_INSTANCE, sizeof(TFlagManager) },
    // TTimeRec::_instance -- the input/profiler recorder. Object size is
    // 0x820 bytes; the constructor argument 0xDFC0 is unrelated to it.
    { SUSAMUNE_ADDR_TIME_REC_INSTANCE,     0x820u },
    // SMSRumbleMgr -- rumble channels' active state.
    { SUSAMUNE_ADDR_RUMBLE_MANAGER,        sizeof(RumbleMgr) },
    // gpApplication.mGamePads[0..3] -- the four TMarioGamePad objects on
    // the root heap. The pointers themselves live inside the gpApplication
    // static range, but the per-pad button-meaning state machine
    // (mMeaning, mFrameMeaning, mState.mDisable, mState.mIsTalking, ...)
    // mutates every frame. Without restoring it, reloading while a dialog
    // had disabled the pad leaves the meaning bits stuck.
    // Address = &gpApplication + offsetof(TApplication, mGamePads[i]).
    { SUSAMUNE_ADDR_APPLICATION_GAMEPAD(0), sizeof(TMarioGamePad) },
    { SUSAMUNE_ADDR_APPLICATION_GAMEPAD(1), sizeof(TMarioGamePad) },
    { SUSAMUNE_ADDR_APPLICATION_GAMEPAD(2), sizeof(TMarioGamePad) },
    { SUSAMUNE_ADDR_APPLICATION_GAMEPAD(3), sizeof(TMarioGamePad) },
    // gpApplication.mFader -- the screen fader's animation state lives on
    // the root heap. Without this the fader gets stuck mid-fade when you
    // load from inside a transition (shine-get fadeout, save card screen).
    // Address = &gpApplication + offsetof(TApplication, mFader).
    { SUSAMUNE_ADDR_APPLICATION_FADER, sizeof(TSmplFader) },
};
const int kNumPointedAllocs = sizeof(kPointedAllocs) / sizeof(kPointedAllocs[0]);

// One header lives at the very start of the snapshot buffer; the saved
// bytes follow at kHeaderSize.
const u32 kSnapshotMagic   = 0x53555341u; // 'SUSA'
const u32 kSnapshotVersion = 15u;
const u32 kHeaderSize      = 0x120u;
// One slot per static range, one per pointed alloc, plus one for the heap.
const int kMaxRegions      = kNumStaticRanges + kNumPointedAllocs + 1;
static_assert(kMaxRegions + Ghost::kSavestateSpanCount <= StateCodec::kMaxSpans,
              "game and ghost state spans exceed the codec limit");

struct RegionEntry {
    u32 addr;       // virtual address restored to
    u32 size;       // bytes
    u32 buf_offset; // offset from snapshot buffer base (after header)
};

struct SavestateHeader {
    u32 magic;
    u32 version;
    u32 game_version;
    u32 heap_addr;        // value of gpApplication.mCurrentHeap at save time
    u32 heap_size;        // bytes between heap and heap->mEnd
    u8  area_id;
    u8  episode_id;
    u8  feature_state;
    u8  _pad0;
    u32 region_count;
    // OSGetTime() at save. TMarDirector::mStopwatch (the Piantissimo-chase /
    // blooper-race mission countdown) stores an absolute console-uptime
    // timestamp in mLast; a byte-for-byte restore of that field is not
    // enough; see the mission-timer correction in loadState().
    OSTime save_time;
    RegionEntry regions[kMaxRegions];
};
static_assert(sizeof(SavestateHeader) <= kHeaderSize,
              "savestate header no longer fits in its reserved space");

struct StoredState {
    SavestateHeader header;
    QFTTimer::SavestateData timer;
    ILing::SavestateData attempt;
    Ghost::SavestateData ghost;
    StateArchiveProfile::Data archiveProfile;
    u32 generation;
    u32 rawSize;
    u32 packedSize;
    u32 adler32;
    u32 parentEpisode;
    u32 metadataTag;
};
static_assert(sizeof(StoredState) <= SUSAMUNE_STATE_METADATA_SIZE,
              "state archive metadata exceeds its mailbox");

StateSlotPool sPool;
StatePoolMemory sPoolMemory;
#pragma clang section bss=".foxtrot.bss"
StoredState sSlots[SavestateManager::kSlotCount];
StoredState sCandidate;
#pragma clang section bss=""
u32 sActiveSlot;
u32 sNextGeneration;
u32 sPendingSlot;
u32 sPendingGeneration;
bool sAwaitingLoadApproval;
bool sBusy;
StateArchiveProfile::Data sLiveArchiveProfile;
u32 sDurableSlots;
u32 sDiskSlot, sDiskGeneration, sDiskPoolUsed, sDiskScene;
OSTime sDiskStarted;
bool sDiskActive;
const char *sDiskStatus = "SD states ready";
static_assert(STATE_SLOT_POOL_COUNT == SavestateManager::kSlotCount,
              "state slot counts differ");
static_assert(StateCodec::kWorkspaceLimit <= SUSAMUNE_STATE_CODEC_WORKSPACE_SIZE,
              "state codec workspace overlaps packed states");

u32 poolCapacity() { return StatePoolMemoryCapacity(&sPoolMemory); }

void poolWriteSpans(u32 offset, u32 size, StateCodec::WriteSpan *out) {
    out[0] = out[1] = {nullptr, 0};
    for (u32 i = 0; size && i < 2; ++i) {
        StatePoolMemorySpan span;
        if (!StatePoolMemorySpanAt(&sPoolMemory, offset, size, &span)) __builtin_trap();
        out[i] = {span.data, span.size};
        offset += span.size;
        size -= span.size;
    }
    if (size) __builtin_trap();
}

void poolReadSpans(u32 offset, u32 size, StateCodec::ReadSpan *out) {
    StateCodec::WriteSpan pieces[2];
    poolWriteSpans(offset, size, pieces);
    for (u32 i = 0; i < 2; ++i) out[i] = {pieces[i].data, pieces[i].size};
}

void storePool() {
    StateCodec::WriteSpan spans[2];
    poolWriteSpans(0, sPool.used, spans);
    for (u32 i = 0; i < 2; ++i)
        if (spans[i].size) DCStoreRange(spans[i].data, spans[i].size);
}
void *codecWorkspace() {
    return reinterpret_cast<void *>(kSnapshotBase + SUSAMUNE_STATE_POOL_SIZE);
}

bool commitPackedState(const StateCodec::ReadSpan *source, u32 sourceCount,
                       u32 rawSize, u32 slot, const StateCodec::Result &first) {
    if ((first.status != StateCodec::SUCCESS && first.status != StateCodec::OUTPUT_FULL) ||
        first.rawBytes != rawSize) return false;
    const int plan = StateSlotPoolPlanReplace(&sPool, poolCapacity(),
        slot, first.compressedBytes, SUSAMUNE_STATE_STAGING_SIZE);
    if (plan == STATE_SLOT_REPLACE_STAGED && first.status == StateCodec::SUCCESS)
        return StateSlotPoolCommitBanked(&sPool, &sPoolMemory,
            slot, first.compressedBytes, reinterpret_cast<const u8 *>(kStagingBase),
            SUSAMUNE_STATE_STAGING_SIZE);
    if (plan != STATE_SLOT_REPLACE_RECOMPRESS || first.status != StateCodec::OUTPUT_FULL)
        return false;

    // Interrupts remain off: the complete first pass proved this immutable input fits.
    if (!StateSlotPoolReclaimForReplaceBanked(&sPool, &sPoolMemory,
                                        slot, first.compressedBytes)) __builtin_trap();
    StateCodec::WriteSpan output[2];
    poolWriteSpans(sPool.used, poolCapacity() - sPool.used, output);
    const StateCodec::Result second = StateCodec::compress(codecWorkspace(),
        SUSAMUNE_STATE_CODEC_WORKSPACE_SIZE, source, sourceCount, output);
    if (second.status != StateCodec::SUCCESS || second.rawBytes != first.rawBytes ||
        second.compressedBytes != first.compressedBytes || second.adler32 != first.adler32)
        __builtin_trap();
    if (!StateSlotPoolCommitPreparedBanked(&sPool, &sPoolMemory,
                                     slot, second.compressedBytes)) __builtin_trap();
    return true;
}

u32 metadataTag(const StoredState &slot) {
    const u8 *bytes = reinterpret_cast<const u8 *>(&slot);
    u32 value = 2166136261u;
    for (u32 i = 0; i < __builtin_offsetof(StoredState, metadataTag); ++i)
        value = (value ^ bytes[i]) * 16777619u;
    return value;
}

bool validStore() {
    if (!StateSlotPoolValid(&sPool, poolCapacity())) return false;
    for (u32 i = 0; i < SavestateManager::kSlotCount; ++i) {
        const StoredState &slot = sSlots[i];
        if (!sPool.slots[i].size) {
            if (slot.header.magic) return false;
            continue;
        }
        if (slot.header.magic != kSnapshotMagic || !slot.generation ||
            slot.packedSize != sPool.slots[i].size ||
            slot.metadataTag != metadataTag(slot)) return false;
    }
    return true;
}

u32 nextGeneration() {
    if (++sNextGeneration == 0) ++sNextGeneration;
    return sNextGeneration;
}

u32 parentEpisode() {
    return TFlagManager::smInstance
        ? TFlagManager::smInstance->getFlag(0x40003) : 0;
}

u32 archiveBuildId() {
    const SusamuneCrashReport *report = SUSAMUNE_CRASH_PPC_PTR;
    return report->magic == SUSAMUNE_CRASH_MAGIC && report->version == SUSAMUNE_CRASH_VERSION
        ? report->modFileCrc32 : 0;
}

u32 archiveGameId() {
    return SUSAMUNE_GAME_VERSION == 1 ? 0x474D534Au :
           SUSAMUNE_GAME_VERSION == 2 ? 0x474D5345u : 0x474D5350u;
}

u32 archiveSceneKey() {
    return (static_cast<u32>(gpApplication.mCurrentScene.mAreaID) << 24) |
        (static_cast<u32>(gpApplication.mCurrentScene.mEpisodeID) << 16) |
        (parentEpisode() & 0xFFFFu);
}

void captureArchiveProfile(StateArchiveProfile::Data &out) {
    if (!StateStorage::available() || !archiveBuildId() ||
        !StateArchiveProfile::capture(out, archiveBuildId(), StateStorage::configId()))
        memset(&out, 0, sizeof(out));
}

void rebaseMissionStopwatch(OSTime previousTime) {
    if (!gpMarDirector) return;
    gpMarDirector->mStopwatch.mLast += OSGetTime() - previousTime;
    DCStoreRange(&gpMarDirector->mStopwatch, sizeof(OSStopwatch));
}

__attribute__((noinline)) u32 captureRegion(SavestateHeader *h, u32 offset,
                                            u32 addr, u32 size) {
    RegionEntry &region = h->regions[h->region_count++];
    region.addr         = addr;
    region.size         = size;
    region.buf_offset   = offset;
    return offset + size;
}

bool consumeExpectedRegion(const SavestateHeader *h, u32 *index, u32 *offset,
                           u32 addr, u32 size) {
    if (*index >= h->region_count || size == 0) return false;
    const RegionEntry &region = h->regions[*index];
    const u32 capacity = kSnapshotReservedSize - kHeaderSize;
    if (region.addr != addr || region.size != size ||
        region.buf_offset != *offset || *offset > capacity ||
        size > capacity - *offset || addr > 0xffffffffu - size) {
        return false;
    }
    *offset += size;
    ++*index;
    return true;
}

bool validSnapshotRegions(const SavestateHeader *h, u32 heapStart,
                          u32 heapEnd) {
    if (h->region_count == 0 || h->region_count > (u32)kMaxRegions ||
        heapStart < 0x80000000u || heapEnd > 0x81800000u ||
        heapEnd <= heapStart) {
        return false;
    }

    u32 index = 0;
    u32 offset = 0;
    for (int i = 0; i < kNumStaticRanges; i++) {
        const StaticRange &range = kStaticRanges[i];
        const u32 size = range.end - range.start;
        // A gated range may legitimately be absent if its setting was off at
        // save time. Every present entry still has to match the compiled map.
        if (range.gate != kNoGate &&
            (index >= h->region_count ||
             h->regions[index].addr != range.start)) {
            continue;
        }
        if (!consumeExpectedRegion(h, &index, &offset, range.start, size))
            return false;
    }

    for (int i = 0; i < kNumPointedAllocs; i++) {
        const PointedAlloc &alloc = kPointedAllocs[i];
        const u32 target = *reinterpret_cast<const u32 *>(alloc.ptr_addr);
        if (target == 0) continue;
        const bool inHeap = target >= heapStart && target < heapEnd &&
                            alloc.size <= heapEnd - target;
        if (inHeap) continue;
        // All tracked root-heap allocations must remain inside physical MEM1.
        if (target < 0x80000000u || target >= 0x81800000u ||
            alloc.size > 0x81800000u - target) {
            return false;
        }
        if (!consumeExpectedRegion(h, &index, &offset, target, alloc.size))
            return false;
    }

    const u32 heapSize = heapEnd - heapStart;
    return consumeExpectedRegion(h, &index, &offset, heapStart, heapSize) &&
           index == h->region_count;
}

// ---------------------------------------------------------------------
// Hardware audio mute
// ---------------------------------------------------------------------
// The snapshot copy runs with interrupts disabled (see save/loadState). For
// a multi-megabyte heap that is several ms during which the DSP-driven audio
// DMA never gets its refill interrupt, so the DAC just replays its last block
// -> an unpleasant hiccup/buzz. stopAllSound() only quiets the software mixer;
// it does not stop the DMA that is already feeding the DAC.
//
// The master audio-out DMA enable is bit 0x8000 of DSPRegs[27] (0xCC005000 +
// 27*2). This is exactly the bit AIStartDMA sets / AIStopDMA clears -- SMS's
// own audio interrupt handler toggles it every block. Clearing it silences
// the DAC immediately at the hardware level, which is the only mute that
// survives our interrupts-disabled window; setting it back resumes output.
// (AIStopDMA itself is stripped from the game binary, so we poke the register
// directly. The 0xCC00_xxxx MMIO block is uncached, so no cache handling.)
volatile u16 *const kDspRegs      = reinterpret_cast<volatile u16 *>(0xCC005000u);
const u16           kAiDmaEnable  = 0x8000u;

inline bool muteAudioDma() {
    bool wasOn = (kDspRegs[27] & kAiDmaEnable) != 0;
    kDspRegs[27] = kDspRegs[27] & ~kAiDmaEnable;
    return wasOn;
}
inline void unmuteAudioDma(bool wasOn) {
    if (wasOn) {
        kDspRegs[27] = kDspRegs[27] | kAiDmaEnable;
    }
}

// ---------------------------------------------------------------------
// Load-in-flight / transition gate
// ---------------------------------------------------------------------
// Snapshotting during a stage load or the opening sequence captures (or
// scribbles over) a heap that the async setup thread is still populating ->
// crash. TMarDirector::direct() returns early every frame while _260 == 0,
// which is precisely the window where the setup thread (gSetupThread) has not
// been joined yet -- i.e. the all-black "loading" screen. It flips to 1 only
// after the load completes.
//
// After that, the opening runs: STATE_INTRO_INIT (0) then, on stages with an
// intro, STATE_INTRO_PLAYING (1) -- the demo-camera cutscene, which still
// crashed when snapshotted. We block those two. Once the intro's closing/
// opening wipe fades the stage back in, the director reaches
// STATE_GAME_STARTING (2) / the opening-wipe state (3), where Mario plays his
// materialise-in animation before the "GO": the whole stage is loaded and
// visible by then (SMS loads everything up front -- nothing streams in
// dynamically), so snapshotting is safe. Allow state >= 2.
bool inLoadTransition() {
    if (!gpMarDirector) {
        return true;
    }
    if (gpMarDirector->_260 == 0) {
        return true; // setup thread still loading -- all-black screen
    }
    if (gpMarDirector->mCurState < TMarDirector::STATE_GAME_STARTING) {
        return true; // black init (0) / intro-cutscene (1) still playing
    }
    return false;
}

bool archiveStageReady() {
    return !inLoadTransition() && gpMarDirector->mCurState == TMarDirector::STATE_NORMAL;
}

bool admitArchiveStage() {
    if (archiveStageReady()) return true;
    sDiskStatus = "Return to normal play before using SD states";
    if (gMenu) gMenu->toast(sDiskStatus);
    return false;
}

bool archiveCandidateMatches(const SusamuneStateArchiveHeader &file) {
    const SavestateHeader &h = sCandidate.header;
    if (file.metadataSize != sizeof(sCandidate) || file.buildCrc != archiveBuildId() ||
        file.gameId != archiveGameId() || file.snapshotVersion != kSnapshotVersion ||
        file.sceneKey != archiveSceneKey() || file.packedSize != sCandidate.packedSize ||
        file.rawSize != sCandidate.rawSize || h.magic != kSnapshotMagic ||
        h.version != kSnapshotVersion || h.game_version != SUSAMUNE_GAME_VERSION ||
        sCandidate.metadataTag != metadataTag(sCandidate) || !sCandidate.generation ||
        h.area_id != gpApplication.mCurrentScene.mAreaID ||
        h.episode_id != gpApplication.mCurrentScene.mEpisodeID ||
        sCandidate.parentEpisode != parentEpisode() || inLoadTransition()) return false;
    JKRHeap *heap = gpApplication.mCurrentHeap;
    const u32 begin = reinterpret_cast<u32>(heap);
    if (!heap || begin < 0x80000000u || begin > 0x81800000u - sizeof(JKRHeap)) return false;
    const u32 end = reinterpret_cast<u32>(heap->mEnd);
    if (end <= begin || end > 0x81800000u || h.heap_addr != begin || h.heap_size != end - begin ||
        !validSnapshotRegions(&h, begin, end)) return false;
    StateCodec::WriteSpan ghost[Ghost::kSavestateSpanCount];
    if (!Ghost::savestateRestoreSpans(sCandidate.ghost, ghost)) return false;
    u32 raw = h.regions[h.region_count - 1].buf_offset + h.heap_size;
    for (u32 i = 0; i < Ghost::kSavestateSpanCount; ++i) raw += ghost[i].size;
    if (raw != sCandidate.rawSize) return false;
    captureArchiveProfile(sLiveArchiveProfile);
    return StateArchiveProfile::matches(sCandidate.archiveProfile, sLiveArchiveProfile);
}

const char *archiveStatusText(u32 status) {
    switch (status) {
    case SUSAMUNE_STATE_CANCELLED: return "SD transfer cancelled";
    case SUSAMUNE_STATE_FULL: return "Not enough state memory - clear a slot";
    case SUSAMUNE_STATE_BAD_FILE: return "SD state is damaged or unsupported";
    case SUSAMUNE_STATE_NOT_FOUND: return "SD state was not found";
    case SUSAMUNE_STATE_STALE: return "SD state changed - refresh the list";
    case SUSAMUNE_STATE_WRONG_CONFIG: return "SD state needs the same game setup";
    case SUSAMUNE_STATE_UNAVAILABLE: return "SD states unavailable";
    default: return "SD transfer failed - try again";
    }
}

#if ENABLE_SAVESTATE_DBG
// Kept out of the stage heap so the textbox survives stage transitions.
char sStatusBuf[12];
#endif

} // namespace


// ---------------------------------------------------------------------
// SavestateManager
// ---------------------------------------------------------------------

SavestateManager::SavestateManager() {
    mFeedback[0] = '\0';
    mFeedbackFrames = 0;
    mLoadPending = false;
    mLoadWaitFrames = 0;

#if ENABLE_SAVESTATE_DBG
    setStatus("ready");
#endif

    memset(&sPool, 0, sizeof(sPool));
    sPoolMemory = statePoolMemory();
    memset(sSlots, 0, sizeof(sSlots));
    sActiveSlot = sNextGeneration = 0;
    sPendingSlot = sPendingGeneration = 0;
    sAwaitingLoadApproval = sBusy = false;
    sDurableSlots = 0;
    sDiskActive = false;
}

#if ENABLE_SAVESTATE_DBG
void SavestateManager::setStatus(const char *msg) {
    // Do NOT call J2DTextBox::setString; it reallocates on the stage heap.
    strncpy(sStatusBuf, msg, sizeof(sStatusBuf));
}
#define SET_STATUS(msg) setStatus(msg)
#else
#define SET_STATUS(msg) ((void)0)
#endif

void SavestateManager::feedback(const char *debug, const char *message) {
    SET_STATUS(debug);
    if (!gSettings.getBool(SETTING_SAVESTATE_FEEDBACK)) {
        mFeedbackFrames = 0;
        return;
    }
    strncpy(mFeedback, message, sizeof(mFeedback) - 1);
    mFeedback[sizeof(mFeedback) - 1] = '\0';
    mFeedbackFrames = Menu::kToastFrames;
}

u32 SavestateManager::activeSlot() const { return sActiveSlot; }

SavestateManager::SlotInfo SavestateManager::slotInfo(u32 slot) const {
    SlotInfo info = {};
    if (slot >= kSlotCount || !validStore()) return info;
    const StoredState &saved = sSlots[slot];
    info.valid = saved.header.magic == kSnapshotMagic;
    info.area = saved.header.area_id;
    info.episode = saved.header.episode_id;
    info.generation = saved.generation;
    info.packedBytes = saved.packedSize;
    return info;
}

bool SavestateManager::selectSlot(u32 slot) {
    if (slot >= kSlotCount || sBusy || diskBusy()) return false;
    sActiveSlot = slot;
    char text[48];
    snprintf(text, sizeof(text), "State %lu selected - %s", slot + 1,
             slotInfo(slot).valid ? "saved" : "empty");
    if (gMenu) gMenu->toast(text);
    return true;
}

bool SavestateManager::cycleSlot() { return selectSlot((sActiveSlot + 1) % kSlotCount); }

bool SavestateManager::diskBusy() { return sDiskActive || StateStorage::busy(); }
bool SavestateManager::sdAvailable() const { return StateStorage::available(); }
bool SavestateManager::sdCatalogReady() const { return StateStorage::catalogReady(); }
const SusamuneStateCatalog &SavestateManager::sdCatalog() const { return StateStorage::catalog(); }
const char *SavestateManager::sdStatus() const {
    return sdAvailable() ? sDiskStatus : "SD states need Moonshine Launcher";
}

bool SavestateManager::saveToSD(const char *name) {
    if (sBusy || diskBusy() || mLoadPending || sAwaitingLoadApproval || !validStore()) return false;
    if (!admitArchiveStage()) return false;
    const StoredState &saved = sSlots[sActiveSlot];
    if (!StateArchiveProfile::valid(saved.archiveProfile)) {
        sDiskStatus = "Save a supported stage state first";
        if (gMenu) gMenu->toast(sDiskStatus);
        return false;
    }
    SusamuneStateArchiveHeader h = {};
    h.metadataSize = sizeof(saved);
    h.packedSize = saved.packedSize;
    h.rawSize = saved.rawSize;
    h.gameId = archiveGameId();
    h.buildCrc = archiveBuildId();
    h.snapshotVersion = kSnapshotVersion;
    h.sceneKey = (static_cast<u32>(saved.header.area_id) << 24) |
        (static_cast<u32>(saved.header.episode_id) << 16) | (saved.parentEpisode & 0xFFFFu);
    if (name) strncpy(h.name, name, sizeof(h.name) - 1);
    else snprintf(h.name, sizeof(h.name), "State %lu - area %u episode %u", sActiveSlot + 1,
                  saved.header.area_id, saved.header.episode_id);
    if (!StateStorage::startExport(h, &saved, sPool.slots[sActiveSlot].offset)) return false;
    sDiskStarted = OSGetTime();
    sDiskActive = true;
    sDiskStatus = "Saving state to SD...";
    return true;
}

bool SavestateManager::loadFromSD(u32 id, u32 crc, u32 packed) {
    if (sBusy || diskBusy() || mLoadPending || sAwaitingLoadApproval || !validStore()) return false;
    if (!admitArchiveStage()) return false;
    if (!StateSlotPoolCanCommit(&sPool, poolCapacity(), sActiveSlot, packed, SUSAMUNE_STATE_STAGING_SIZE)) {
        sDiskStatus = "Not enough state memory - clear a slot";
        if (gMenu) gMenu->toast(sDiskStatus);
        return false;
    }
    if (!StateStorage::startImport(id, crc, packed, sPool.used)) return false;
    sDiskSlot = sActiveSlot;
    sDiskGeneration = sSlots[sDiskSlot].generation;
    sDiskPoolUsed = sPool.used;
    sDiskScene = archiveSceneKey();
    sDiskStarted = OSGetTime();
    sDiskActive = true;
    sDiskStatus = "Reading state from SD...";
    return true;
}

bool SavestateManager::refreshSD(u32 afterId) {
    if (sBusy || diskBusy() || mLoadPending || sAwaitingLoadApproval) return false;
    if (!admitArchiveStage()) return false;
    if (!StateStorage::refresh(afterId)) return false;
    sDiskStarted = OSGetTime();
    sDiskActive = true;
    sDiskStatus = "Reading SD states...";
    return true;
}

bool SavestateManager::cancelSD() {
    if (!StateStorage::cancel()) return false;
    sDiskStatus = "Cancelling SD transfer...";
    return true;
}

void SavestateManager::updateDisk() {
    StateStorage::update();
    StateStorage::Result result;
    if (!StateStorage::takeResult(result)) return;
    const bool wasActive = sDiskActive;
    bool imported = false;
    if (result.status == SUSAMUNE_STATE_OK && result.command == SUSAMUNE_STATE_CMD_IMPORT) {
        GXDrawDone();
        const bool ints = OSDisableInterrupts();
        const bool dma = muteAudioDma();
        bool valid = wasActive && validStore() && sDiskSlot < kSlotCount &&
            sPool.used == sDiskPoolUsed && sSlots[sDiskSlot].generation == sDiskGeneration &&
            archiveSceneKey() == sDiskScene && result.header.metadataSize == sizeof(sCandidate) && result.metadata;
        if (valid) {
            memcpy(&sCandidate, result.metadata, sizeof(sCandidate));
            valid = archiveCandidateMatches(result.header);
        }
        if (valid) {
            const u32 first = sCandidate.packedSize < SUSAMUNE_STATE_STAGING_SIZE ?
                sCandidate.packedSize : SUSAMUNE_STATE_STAGING_SIZE;
            StateCodec::ReadSpan spans[3];
            spans[0] = {reinterpret_cast<const void *>(kStagingBase), first};
            poolReadSpans(sDiskPoolUsed, sCandidate.packedSize - first, spans + 1);
            valid = StateCodec::validate(codecWorkspace(), SUSAMUNE_STATE_CODEC_WORKSPACE_SIZE,
                spans, 3, sCandidate.rawSize, sCandidate.adler32) == StateCodec::SUCCESS;
        }
        if (valid) {
            valid = StateSlotPoolCommitBanked(&sPool, &sPoolMemory, sDiskSlot,
                sCandidate.packedSize, reinterpret_cast<const u8 *>(kStagingBase), SUSAMUNE_STATE_STAGING_SIZE);
            if (valid) {
                sCandidate.generation = nextGeneration();
                sCandidate.metadataTag = metadataTag(sCandidate);
                sSlots[sDiskSlot] = sCandidate;
                sDurableSlots |= 1u << sDiskSlot;
                storePool();
                imported = true;
            }
        }
        if (wasActive) rebaseMissionStopwatch(sDiskStarted);
        unmuteAudioDma(dma);
        OSRestoreInterrupts(ints);
        if (!valid) result.status = SUSAMUNE_STATE_BAD_FILE;
    } else if (wasActive) rebaseMissionStopwatch(sDiskStarted);
    sDiskActive = false;
    if (result.status != SUSAMUNE_STATE_OK) sDiskStatus = archiveStatusText(result.status);
    else if (result.command == SUSAMUNE_STATE_CMD_EXPORT) sDiskStatus = "State saved in /moonshine_states";
    else if (result.command == SUSAMUNE_STATE_CMD_CATALOG) sDiskStatus = "SD states ready";
    if (imported) {
        PracticeSession::onSavestateCleared(sDiskSlot, sDiskGeneration);
        sDiskStatus = "SD state ready - press Load";
        char message[48];
        snprintf(message, sizeof(message), "Loaded into state %lu - press Load", sDiskSlot + 1);
        if (gMenu) gMenu->toast(message);
    } else if (wasActive && gMenu) gMenu->toast(sDiskStatus);
}

bool SavestateManager::clearSlot(u32 slot, u32 expectedGeneration) {
    if (sBusy || diskBusy() || mLoadPending || sAwaitingLoadApproval || !validStore() ||
        slot >= kSlotCount || !sSlots[slot].header.magic ||
        sSlots[slot].generation != expectedGeneration) return false;
    sBusy = true;
    if (!StateSlotPoolClearBanked(&sPool, &sPoolMemory, slot)) {
        sBusy = false;
        return false;
    }
    memset(&sSlots[slot], 0, sizeof(sSlots[slot]));
    sDurableSlots &= ~(1u << slot);
    sSlots[slot].generation = nextGeneration();
    sBusy = false;
    PracticeSession::onSavestateCleared(slot, expectedGeneration);
    return true;
}

bool SavestateManager::saveState() {
    if (sBusy || diskBusy() || mLoadPending || sAwaitingLoadApproval) {
        feedback("E:busy", "Wait for the pending state load");
        return false;
    }
    if (!validStore()) {
        feedback("E:store", "State memory damaged - restart game");
        return false;
    }
    // Refuse while a stage load is in flight or the intro sequence is playing;
    // the heap is not yet stable there. See inLoadTransition().
    if (inLoadTransition()) {
        feedback("E:loading", "Can't save during stage loading");
        return false;
    }

    JKRHeap *heap = gpApplication.mCurrentHeap;
    if (!heap) {
        feedback("E:noheap", "Savestate unavailable");
        return false;
    }

    const u32 heapStart = reinterpret_cast<u32>(heap);
    if (heapStart < 0x80000000u ||
        heapStart > 0x81800000u - sizeof(JKRHeap)) {
        feedback("E:badheap", "Savestate unavailable");
        return false;
    }
    const u32 heapEnd = reinterpret_cast<u32>(heap->mEnd);
    if (heapEnd > 0x81800000u ||
        heapEnd <= heapStart) {
        feedback("E:badheap", "Savestate unavailable");
        return false;
    }
    const u32 heapSize  = heapEnd - heapStart;

    // Bounds check before we write a single byte.
    u32 total = 0;
    for (int i = 0; i < kNumStaticRanges; i++) {
        total += kStaticRanges[i].end - kStaticRanges[i].start;
    }
    for (int i = 0; i < kNumPointedAllocs; i++) {
        total += kPointedAllocs[i].size;
    }
    total += heapSize;
    if (total + kHeaderSize > kSnapshotReservedSize) {
        feedback("E:size", "Savestate is too large");
        return false;
    }

    // These globals are trusted in a healthy stage, but validate every target
    // before the first copy so a damaged live pointer cannot turn Save into an
    // arbitrary MEM1 read or wrap the in-heap containment check.
    for (int i = 0; i < kNumPointedAllocs; i++) {
        const PointedAlloc &alloc = kPointedAllocs[i];
        const u32 target = *reinterpret_cast<const u32 *>(alloc.ptr_addr);
        if (target == 0) continue;
        const bool inHeap = target >= heapStart && target < heapEnd &&
                            alloc.size <= heapEnd - target;
        if (!inHeap &&
            (target < 0x80000000u || target >= 0x81800000u ||
             alloc.size > 0x81800000u - target)) {
            feedback("E:rootptr", "Stage layout changed - save again");
            return false;
        }
    }

    // Audio engine has DSP-side state we can't snapshot; quiet it before
    // we touch anything so the current-sounds list won't reference freed
    // tracks after a future restore.
    if (gpMSound) {
        gpMSound->stopAllSound();
    }

    // Compression reads live regions for longer than the old raw copy.
    GXDrawDone();

    // We are called from inside onUpdate, which runs on the main thread
    // between director->direct() and rendering. That is already the most
    // quiescent point in the frame, but disable interrupts anyway so we
    // don't race a VI retrace callback that touches heap objects.
    sBusy = true;
    bool ints = OSDisableInterrupts();
    // Silence the DAC for the whole interrupts-off window so the frozen audio
    // DMA doesn't buzz; restored just before interrupts come back.
    bool dma = muteAudioDma();

    memset(&sCandidate, 0, sizeof(sCandidate));
    SavestateHeader *h = &sCandidate.header;
    h->magic        = 0; // committed at end as a torn-write guard
    h->version      = kSnapshotVersion;
    h->game_version = SUSAMUNE_GAME_VERSION;
    h->heap_addr    = heapStart;
    h->heap_size    = heapSize;
    h->area_id      = gpApplication.mCurrentScene.mAreaID;
    h->episode_id   = gpApplication.mCurrentScene.mEpisodeID;
    h->feature_state = featuresSavestateState();
    h->_pad0        = 0;
    h->region_count = 0;
    h->save_time    = OSGetTime();

    u32 offset = 0;
    for (int i = 0; i < kNumStaticRanges; i++) {
        // Skip a setting-gated range when its setting is disabled (e.g. the RNG
        // seed when "Save RNG state" is Off). It simply won't be in the region
        // list, so a later load leaves that memory untouched.
        if (kStaticRanges[i].gate != kNoGate &&
            !gSettings.getBool((SettingId)kStaticRanges[i].gate)) {
            continue;
        }
        u32 sz = kStaticRanges[i].end - kStaticRanges[i].start;
        offset = captureRegion(h, offset, kStaticRanges[i].start, sz);
    }

    // Follow each tracked pointer and capture its target. These objects
    // live on the root heap, which the JKRSolidHeap snapshot does not
    // cover -- without this, e.g. coin counts (TFlagManager) and shine
    // flags survive *only* because their pointer in BSS is restored, but
    // the bytes it points at are whatever is live at load time.
    for (int i = 0; i < kNumPointedAllocs; i++) {
        const PointedAlloc &pa = kPointedAllocs[i];
        u32 target = *reinterpret_cast<u32 *>(pa.ptr_addr);
        if (target == 0) {
            continue; // not yet initialised
        }
        // If the target happens to live inside the JKRSolidHeap range,
        // skip it -- it'll already be covered by the heap snapshot.
        if (target >= heapStart && target < heapEnd &&
            pa.size <= heapEnd - target) {
            continue;
        }
        offset = captureRegion(h, offset, target, pa.size);
    }

    // Heap last (largest payload).
    offset = captureRegion(h, offset, heapStart, heapSize);

    sCandidate.parentEpisode = parentEpisode();
    gQFTTimer.captureSavestate(sCandidate.timer);
    ILing::captureSavestate(sCandidate.attempt);
    captureArchiveProfile(sCandidate.archiveProfile);
    StateCodec::ReadSpan ghostSource[Ghost::kSavestateSpanCount];
    if (!Ghost::captureSavestate(sCandidate.ghost, ghostSource)) {
        rebaseMissionStopwatch(h->save_time);
        unmuteAudioDma(dma);
        OSRestoreInterrupts(ints);
        sBusy = false;
        feedback("E:ghost", "Ghost recording unavailable - try again");
        return false;
    }
    StateCodec::ReadSpan source[kMaxRegions + Ghost::kSavestateSpanCount];
    for (u32 i = 0; i < h->region_count; ++i)
        source[i] = {reinterpret_cast<const void *>(h->regions[i].addr), h->regions[i].size};
    u32 rawSize = offset;
    for (u32 i = 0; i < Ghost::kSavestateSpanCount; ++i) {
        source[h->region_count + i] = ghostSource[i];
        rawSize += ghostSource[i].size;
    }
    StateCodec::WriteSpan output[3];
    output[0] = {reinterpret_cast<void *>(kStagingBase), SUSAMUNE_STATE_STAGING_SIZE};
    poolWriteSpans(sPool.used, poolCapacity() - sPool.used, output + 1);
    const StateCodec::Result result = StateCodec::compress(codecWorkspace(),
        SUSAMUNE_STATE_CODEC_WORKSPACE_SIZE, source,
        h->region_count + Ghost::kSavestateSpanCount, output, 3);
    const bool fits = commitPackedState(source, h->region_count + Ghost::kSavestateSpanCount,
                                         rawSize, sActiveSlot, result);
    if (!fits) {
        rebaseMissionStopwatch(h->save_time);
        unmuteAudioDma(dma);
        OSRestoreInterrupts(ints);
        sBusy = false;
        feedback("E:space", result.status == StateCodec::SUCCESS ||
            result.status == StateCodec::OUTPUT_FULL ?
            "State won't fit - clear another slot" : "State could not be compressed");
        return false;
    }
    sCandidate.rawSize = rawSize;
    sCandidate.packedSize = result.compressedBytes;
    sCandidate.adler32 = result.adler32;
    sCandidate.generation = nextGeneration();
    h->magic = kSnapshotMagic;
    sCandidate.metadataTag = metadataTag(sCandidate);
    sSlots[sActiveSlot] = sCandidate;
    sDurableSlots &= ~(1u << sActiveSlot);
    storePool();

    // The mission countdown must not charge time spent compressing a state.
    rebaseMissionStopwatch(h->save_time);
    unmuteAudioDma(dma);
    OSRestoreInterrupts(ints);
    sBusy = false;

    PracticeSession::onSavestateSaved(sActiveSlot, sCandidate.generation);
    CrashReport::note(SUSAMUNE_CRASH_EVENT_SAVESTATE, 1, sActiveSlot + 1);
    char text[48];
    snprintf(text, sizeof(text), "State %lu saved", sActiveSlot + 1);
    feedback("saved", text);
    return true;
}

bool SavestateManager::loadState() {
    return loadSlot(sActiveSlot, slotInfo(sActiveSlot).generation);
}

bool SavestateManager::loadSlot(u32 slot, u32 expectedGeneration) {
    if (sBusy || diskBusy() || mLoadPending || sAwaitingLoadApproval) {
        feedback("E:busy", "Wait for the pending state load");
        return false;
    }
    // Refuse while a stage load is in flight or the intro sequence is playing;
    // overwriting a heap the setup thread is still filling crashes. See
    // inLoadTransition().
    if (inLoadTransition()) {
        feedback("E:loading", "Can't load during stage loading");
        return false;
    }

    if (!validStore() || slot >= kSlotCount) {
        feedback("E:store", "State memory damaged - restart game");
        return false;
    }
    StoredState &saved = sSlots[slot];
    SavestateHeader *h = &saved.header;
    if (h->magic != kSnapshotMagic) {
        feedback("E:nosnap", "No savestate yet");
        return false;
    }
    if (!expectedGeneration || saved.generation != expectedGeneration) {
        feedback("E:changed", "That state changed - choose it again");
        return false;
    }
    if (h->version != kSnapshotVersion) {
        feedback("E:version", "Savestate is from another build");
        return false;
    }
    if (h->game_version != SUSAMUNE_GAME_VERSION) {
        feedback("E:region", "Savestate is from another region");
        return false;
    }

    JKRHeap *heap = gpApplication.mCurrentHeap;
    if (!heap) {
        feedback("E:noheap", "Savestate unavailable");
        return false;
    }

    const u32 heapStart = reinterpret_cast<u32>(heap);
    if (heapStart < 0x80000000u ||
        heapStart > 0x81800000u - sizeof(JKRHeap)) {
        feedback("E:badheap", "Savestate unavailable");
        return false;
    }

    // Pointers in the snapshotted heap are absolute. If the heap moved
    // (different scenario, different boot path), restoring would scribble
    // stale pointers all over the place. Refuse the load.
    if (heapStart != h->heap_addr) {
        feedback("E:hpaddr", "Stage layout changed - save again");
        return false;
    }
    const u32 heapEnd = reinterpret_cast<u32>(heap->mEnd);
    if (heapEnd > 0x81800000u || heapEnd <= heapStart) {
        feedback("E:badheap", "Savestate unavailable");
        return false;
    }
    const u32 heapSize = heapEnd - heapStart;
    if (heapSize != h->heap_size) {
        feedback("E:hpsize", "Stage layout changed - save again");
        return false;
    }

    // Same-scenario only. Restoring across a moveStage() is more
    // complicated -- the heap freeAll()s and gets re-populated by the
    // new director's setup -- and not the use case we're after.
    if (h->area_id    != gpApplication.mCurrentScene.mAreaID
     || h->episode_id != gpApplication.mCurrentScene.mEpisodeID
     || saved.parentEpisode != parentEpisode()) {
        feedback("E:scene", "Savestate belongs to another area");
        return false;
    }

    if (!validSnapshotRegions(h, heapStart, heapEnd)) {
        feedback("E:badsnap", "Savestate is damaged - save again");
        return false;
    }
    StateCodec::WriteSpan ghostDestinations[Ghost::kSavestateSpanCount];
    if (!Ghost::savestateRestoreSpans(saved.ghost, ghostDestinations)) {
        feedback("E:ghost", "Ghost recording unavailable - try again");
        return false;
    }
    u32 rawSize = h->regions[h->region_count - 1].buf_offset + heapSize;
    for (u32 i = 0; i < Ghost::kSavestateSpanCount; ++i)
        rawSize += ghostDestinations[i].size;
    if (rawSize != saved.rawSize) {
        feedback("E:badsnap", "Savestate is damaged - save again");
        return false;
    }

    // gpCardManager has its own worker thread, mutex, and cond var on the
    // root heap. Snapshotting/restoring it would trash kernel-side thread
    // bookkeeping, so we don't -- but we also can't safely tear down the
    // rest of the world while the card thread is mid-transaction. Queued
    // loads wait frame-by-frame in processPendingLoad(); keep this guard for
    // direct callers and the tiny race between that check and this one.
    if (gpCardManager && gpCardManager->getLastStatus() == CARD_ERROR_BUSY) {
        feedback("E:cardbsy", "Memory card busy - try again");
        return false;
    }

    // Same reasoning as save().
    if (gpMSound) {
        gpMSound->stopAllSound();
    }

    // Never overwrite heap-resident textures or display-list backing storage
    // while the graphics processor can still be reading the current frame.
    // D-pad loads normally arrive from processPendingLoad(), immediately after
    // THPPlayerDrawDone() has already issued this barrier. Keep it here too so
    // direct callers of loadState() receive the same safety guarantee.
    GXDrawDone();

    sBusy = true;
    bool ints = OSDisableInterrupts();
    // Silence the DAC across the interrupts-off restore so the frozen audio
    // DMA doesn't buzz; restored just before interrupts come back.
    bool dma = muteAudioDma();

    const OSTime restoreStarted = OSGetTime();
    const bool durable = (sDurableSlots & (1u << slot)) != 0;
    if (durable) {
        captureArchiveProfile(sLiveArchiveProfile);
        if (!StateArchiveProfile::matches(saved.archiveProfile, sLiveArchiveProfile)) {
            rebaseMissionStopwatch(restoreStarted);
            unmuteAudioDma(dma);
            OSRestoreInterrupts(ints);
            sBusy = false;
            feedback("E:owners", "SD state needs the same stage setup");
            return false;
        }
    }
    StateCodec::ReadSpan compressed[2];
    poolReadSpans(sPool.slots[slot].offset, saved.packedSize, compressed);
    StateCodec::WriteSpan destinations[kMaxRegions + Ghost::kSavestateSpanCount];
    for (u32 i = 0; i < h->region_count; ++i)
        destinations[i] = {reinterpret_cast<void *>(h->regions[i].addr), h->regions[i].size};
    for (u32 i = 0; i < Ghost::kSavestateSpanCount; ++i)
        destinations[h->region_count + i] = ghostDestinations[i];
    const StateCodec::Status restored = StateCodec::decompress(codecWorkspace(),
        SUSAMUNE_STATE_CODEC_WORKSPACE_SIZE, compressed, 2, destinations,
        h->region_count + Ghost::kSavestateSpanCount, saved.rawSize, saved.adler32,
        durable ? StateArchiveProfile::copyGameBytes : nullptr,
        durable ? &sLiveArchiveProfile : nullptr);
    if (restored == StateCodec::COMMIT_FAILED) __builtin_trap();
    if (restored != StateCodec::SUCCESS) {
        rebaseMissionStopwatch(restoreStarted);
        unmuteAudioDma(dma);
        OSRestoreInterrupts(ints);
        sBusy = false;
        feedback("E:badsnap", "State is damaged - save again");
        return false;
    }
    for (u32 i = 0; i < h->region_count; i++) {
        const RegionEntry &r = h->regions[i];
        // Decompression has placed the restored bytes in D-cache, so the
        // CPU can use them immediately. Store them for GX/DMA visibility, but
        // do not flush-and-invalidate the whole stage heap: doing so makes the
        // next frame fault every restored line back in from RAM.
        DCStoreRange(reinterpret_cast<void *>(r.addr), r.size);
        // No instruction-cache invalidation: we never restore .text.
    }

    // The restored heap contains texture/image bytes from the saved frame.
    // Invalidate the GP texture cache before any subsequent draw so it cannot
    // keep sampling lines cached from the pre-load state.
    GXInvalidateTexAll();

    // TMarDirector::mStopwatch (the Piantissimo-chase / blooper-race mission
    // countdown, restored above as part of the heap region) stores an
    // absolute OSGetTime() timestamp in mLast rather than an elapsed
    // duration -- OSCheckStopwatch() computes `total + (now - mLast)`. A
    // byte-for-byte restore puts back the OLD mLast, so on the very next
    // check the timer would read as if it had kept running in real time
    // across the save/load gap instead of rewinding. Shift mLast forward by
    // exactly that real-time gap so OSCheckStopwatch() reproduces the same
    // value it had at save time.
    rebaseMissionStopwatch(h->save_time);

    unmuteAudioDma(dma);
    OSRestoreInterrupts(ints);
    sBusy = false;

    featuresOnSavestateLoaded(h->feature_state);
    gQFTTimer.restoreSavestate(saved.timer);
    SplitEvents::onSavestateLoaded();
    SplitStats::onSavestateLoaded();
    Ghost::restoreSavestate(saved.ghost);
    GhostStorage::onSavestateLoaded();
    rngControlOnSavestateLoaded();
    MovementDisplay::onSavestateLoaded();
    gCreationExtras.onSavestateLoaded();
    // An armed warp lives in mod BSS, outside the restored game snapshot.
    // Cancel it before ILing adopts the save-time attempt state.
    LevelWarp::cancelPending();
    ILing::restoreSavestate(saved.attempt);
    Records::onSavestateLoaded();
    PracticeSession::onSavestateLoaded();
    CrashReport::note(SUSAMUNE_CRASH_EVENT_SAVESTATE, 2, slot + 1);
    char text[48];
    snprintf(text, sizeof(text), "State %lu loaded", slot + 1);
    feedback("loaded", text);
    return true;
}

void SavestateManager::updateHook() {
    if (diskBusy()) return;
    // The original optional in-stage counter uses bare D-pad Left/Right, the
    // same defaults as full savestates. When that option is explicitly on and
    // the live binds actually collide, the counter owns those two presses;
    // rebinding either action removes the suppression automatically.
    const bool counterControls =
        gSettings.getBool(SETTING_ATTEMPT_COUNTER) &&
        gSettings.getBool(SETTING_ATTEMPT_IN_STAGE_CONTROLS);
    const bool counterOwnsSave =
        counterControls && gBinds.get(BIND_ATTEMPT_SHOW) != 0 &&
        gBinds.get(BIND_ATTEMPT_SHOW) == gBinds.get(BIND_SAVESTATE_SAVE);
    const bool counterOwnsLoad =
        counterControls && gBinds.get(BIND_ATTEMPT_ADD) != 0 &&
        gBinds.get(BIND_ATTEMPT_ADD) == gBinds.get(BIND_SAVESTATE_LOAD);

    const bool approvedLoad = WarpWheel::takeSavestateLoadApproval();
    if (sAwaitingLoadApproval && !approvedLoad && !WarpWheel::promptPending())
        sAwaitingLoadApproval = false;
    if (mLoadPending) return;
    if (approvedLoad && sAwaitingLoadApproval) {
        sAwaitingLoadApproval = false;
        mLoadPending = true;
        mLoadWaitFrames = 0;
        SET_STATUS("loading");
    } else if (sAwaitingLoadApproval) {
        return;
    } else if (!counterOwnsSave &&
               gBinds.wasPressed(BIND_SAVESTATE_SAVE)) {
        saveState();
    } else if (!counterOwnsLoad &&
               gBinds.wasPressed(BIND_SAVESTATE_LOAD)) {
        // Pin before the unsaved-ghost prompt; changing selection cannot
        // redirect a confirmation or a card-busy load to another state.
        sPendingSlot = sActiveSlot;
        sPendingGeneration = slotInfo(sPendingSlot).generation;
        if (!WarpWheel::requestSavestateLoad()) {
            sAwaitingLoadApproval = true;
            return;
        }
        // TApplication still runs the fader and gpMSound->mainLoop(), then
        // submits the rest of the frame after this hook returns. Restoring here
        // made those systems consume half-live/half-restored state. Defer the
        // operation until after the post-render GXDrawDone barrier instead.
        mLoadPending = true;
        mLoadWaitFrames = 0;
        SET_STATUS("loading");
    } else if (gBinds.wasPressed(BIND_SAVESTATE_CYCLE)) {
        cycleSlot();
    }
}

void SavestateManager::processPendingLoad() {
    if (diskBusy()) return;
    if (!mLoadPending) {
        return;
    }

    // The card worker can remain busy across many scheduler yields. Wait in
    // actual rendered frames so an ordinary save finishes without dropping
    // the user's one-shot load request.
    if (gpCardManager && gpCardManager->getLastStatus() == CARD_ERROR_BUSY) {
        if (++mLoadWaitFrames < 600) return;
        mLoadPending = false;
        mLoadWaitFrames = 0;
        feedback("E:cardbsy", "Memory card busy - try again");
        return;
    }

    // Clear first so a rejected snapshot is not retried every frame.
    mLoadPending = false;
    mLoadWaitFrames = 0;
    loadSlot(sPendingSlot, sPendingGeneration);
}

void SavestateManager::draw(Menu *menu) {
    if (mFeedbackFrames > 0) mFeedbackFrames--;
#if ENABLE_SAVESTATE_DBG
    if (menu)
        menu->drawTextBaseline(sStatusBuf, 20, 60, 18, 18,
                               JUtility::TColor(255, 200, 0, 255));
#endif
    if (!menu || menu->shown() || mFeedbackFrames <= 0 ||
        !gSettings.getBool(SETTING_SAVESTATE_FEEDBACK)) return;
    gCreationExtras.drawSavestateFeedback(menu, mFeedback);
}
