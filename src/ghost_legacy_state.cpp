#include "susamune/ghost_legacy_state.hxx"
#include "susamune/ghost_format.h"
#include "susamune/ghost_camera.hxx"
#include "susamune/ghost_context.hxx"
#include "susamune/iling.hxx"
namespace GhostLegacyState {
namespace {
const u32 kSavedPrefixMagic=0x53475046u;
const u16 kMaxSegments=SUSAMUNE_GHOST_V4_MAX_SEGMENTS;
enum { CLOCK_WAIT_STAGE=4, RECORD_FAILURE_NONE=0, PREFIX_RECORDING=1, PREFIX_CONTINUE=8, PREFIX_BOUNDARY=16 };
struct LegacyClock {u32 serial;s32 liveQf;u32 omittedQf;u8 ready;u8 padding[3];};
s32 mappedQf(const LegacyClock *clock,s32 live) {
    if(!clock->ready||live<0)return live;
    return static_cast<u32>(live)<clock->omittedQf?0:live-static_cast<s32>(clock->omittedQf);
}
struct Track {
    u32 samples;
    u32 segments;
    u32 inputs;
    u32 inputCount;
    SusamuneGhostSplitSample splits[SUSAMUNE_GHOST_SPLIT_MAX_COUNT];
    u8 splitCount;
    u8 sourceRegion;
    u8 teachingFlags;
    u8 sourceProfile;
    u32 count;
    u32 startQf;
    u32 endQf;
    u32 resultQf;
    u32 runFlags;
    u32 pbToken;
    s32 parentEpisode;
    u8 area;
    u8 episode;
    u8 routeParentArea;
    u8 routeFlags;
    u16 segmentCount;
    u16 formatVersion;
    u16 attachmentFlags;
    u8 attachmentCount;
    SusamuneGhostAttachmentDescriptor
        attachments[SUSAMUNE_GHOST_V4_ATTACHMENT_DESCRIPTOR_COUNT];
    u8 valid;
    u8 completed;
    u8 saved;
    u8 pb;
    u8 failure;
};
struct SavedPrefix {
    u32 magic;
    u32 capturedQf;
    Track track;
    LegacyClock clock;
    u32 serial;
    s32 lastSampleQf;
    s32 clockLastQf;
    s32 clockEpochStartQf;
    s32 pendingPreviousClockQf;
    s32 boundaryPriorQf;
    s32 liveParentEpisode;
    u16 clockObservations;
    u16 boundaryBaseSegmentCount;
    u8 phase;
    u8 flags;
    u8 liveArea;
    u8 liveEpisode;
    u8 liveRouteParentArea;
    u8 liveRouteFlags;
    u8 endpoint;
};
static_assert(sizeof(Track)==204&&sizeof(SavedPrefix)==268,"legacy state metadata must match the PPC wire layout");
bool validRouteTuple(u8 area, u8 episode, u8 parentArea, u8 flags,
                     s32 variant) {
    return area <= SUSAMUNE_GHOST_ROUTE_AREA_MAX &&
           episode <= SUSAMUNE_GHOST_ROUTE_EPISODE_MAX &&
           (parentArea == SUSAMUNE_GHOST_ROUTE_PARENT_NONE ||
            parentArea <= SUSAMUNE_GHOST_ROUTE_AREA_MAX) &&
           !(flags & ~SUSAMUNE_GHOST_ROUTE_FLAGS_V1) &&
           (!!(flags & SUSAMUNE_GHOST_ROUTE_INTERNAL_SCENE) ==
            (parentArea != SUSAMUNE_GHOST_ROUTE_PARENT_NONE)) &&
           (!(flags & SUSAMUNE_GHOST_ROUTE_PARENT_START) ||
            parentArea != SUSAMUNE_GHOST_ROUTE_PARENT_NONE) &&
           variant >= SUSAMUNE_GHOST_ROUTE_VARIANT_NONE &&
           variant <= SUSAMUNE_GHOST_ROUTE_VARIANT_MAX;
}
bool decodeSavedPrefix(const Ghost::SavestateData &data, SavedPrefix *saved) {
    __builtin_memcpy(saved, &data, sizeof(*saved));
    if (!saved->magic) {
        for (u32 i = 0; i < sizeof(data.words) / sizeof(data.words[0]); ++i)
            if (data.words[i]) return false;
        return true;
    }
    const Track &track = saved->track;
    if (saved->magic != kSavedPrefixMagic ||
        !SusamuneGhostPersonalProfile(track.sourceProfile) ||
        track.valid>1||track.saved>1||track.pb>1||saved->clock.ready>1||
        track.samples || track.segments || track.inputs ||
        !track.count || track.count > SusamuneGhostPoseLimit(track.formatVersion) ||
        !track.segmentCount || track.segmentCount > kMaxSegments ||
        track.inputCount > SusamuneGhostInputLimit(track.formatVersion) ||
        track.splitCount > SUSAMUNE_GHOST_SPLIT_MAX_COUNT ||
        track.attachmentCount > SUSAMUNE_GHOST_V4_ATTACHMENT_DESCRIPTOR_COUNT ||
        (track.attachmentFlags & ~SUSAMUNE_GHOST_V4_ATTACHMENT_FLAGS) ||
        (track.teachingFlags & ~SUSAMUNE_GHOST_TEACHING_INPUT_TRUNCATED) ||
        (track.formatVersion != SUSAMUNE_GHOST_FILE_VERSION_V4 &&
         track.formatVersion != SUSAMUNE_GHOST_FILE_VERSION_V5 &&
         track.formatVersion != SUSAMUNE_GHOST_FILE_VERSION_V6 &&
         track.formatVersion != SUSAMUNE_GHOST_FILE_VERSION_V7 &&
         track.formatVersion != SUSAMUNE_GHOST_FILE_VERSION_V8 &&
         track.formatVersion != SUSAMUNE_GHOST_FILE_VERSION_V9 &&
         track.formatVersion != SUSAMUNE_GHOST_FILE_VERSION_V10) ||
        !validRouteTuple(track.area, track.episode, track.routeParentArea,
                         track.routeFlags, track.parentEpisode) ||
        track.endQf < track.startQf || track.endQf > 0x7fffffffu ||
        track.endQf - track.startQf > SusamuneGhostDurationLimit(track.formatVersion) ||
        saved->lastSampleQf != static_cast<s32>(track.endQf) ||
        saved->capturedQf > 0x7fffffffu ||
        saved->phase > CLOCK_WAIT_STAGE ||
        saved->endpoint > ILing::SAVED_GHOST_END_DEATH ||
        (saved->flags & ~63u) ||
        !(saved->flags & (PREFIX_RECORDING | PREFIX_CONTINUE)) ||
        ((saved->flags & PREFIX_BOUNDARY) &&
         saved->boundaryBaseSegmentCount > track.segmentCount) ||
        track.failure != RECORD_FAILURE_NONE || track.completed ||
        (saved->clock.ready && (saved->clock.serial != saved->serial ||
             saved->clock.liveQf < 0 ||
             saved->clock.omittedQf > static_cast<u32>(saved->clock.liveQf) ||
             saved->clock.liveQf > static_cast<s32>(saved->capturedQf))) ||
        track.endQf > static_cast<u32>(mappedQf(
            &saved->clock, static_cast<s32>(saved->capturedQf)))) return false;
    static_assert(sizeof(SavedPrefix) <= 124 * sizeof(u32), "camera metadata overlaps saved prefix");
    if (track.formatVersion >= SUSAMUNE_GHOST_FILE_VERSION_V8) {
        const u32 size = data.words[126];
        if (data.words[127] != SUSAMUNE_GHOST_CAMERA_MAGIC || size < 32 ||
            size > SUSAMUNE_GHOST_CAMERA_MAX_SIZE || (size - 32) % 24) return false;
    } else if (data.words[126] || data.words[127]) return false;
    if (track.formatVersion >= SUSAMUNE_GHOST_FILE_VERSION_V10) {
        const u32 size = data.words[124];
        if (data.words[125] != SUSAMUNE_GHOST_CONTEXT_MAGIC || size < 32 ||
            size > SUSAMUNE_GHOST_CONTEXT_MAX_SIZE || (size - 32) % 96) return false;
    } else if (data.words[124] || data.words[125]) return false;
    return true;
}
}
bool restoreSpans(const Ghost::SavestateData &data,
                  StateCodec::WriteSpan (&spans)[Ghost::kSavestateSpanCount]) {
    __builtin_memset(spans,0,sizeof(spans));
    SavedPrefix saved;
    if(!decodeSavedPrefix(data,&saved))return false;
    if(!saved.magic)return true;
    spans[0]=StateCodec::discardSpan(saved.track.count*SUSAMUNE_GHOST_POSE_SAMPLE_SIZE);
    spans[1]=StateCodec::discardSpan(saved.track.segmentCount*32u);
    spans[2]=StateCodec::discardSpan(saved.track.inputCount*SusamuneGhostInputStride(saved.track.formatVersion));
    spans[3]=StateCodec::discardSpan(data.words[126]);
    spans[4]=StateCodec::discardSpan(data.words[124]);
    return true;
}
}
