#include "susamune/ghost_world_runtime.hxx"
#include "susamune/replay_session.hxx"
#include "susamune/ghost_recording_native.hxx"
#include "susamune/ghost.hxx"
#include "susamune/rng_control.hxx"
#include "susamune/ghost_recording.hxx"
#include "susamune/ghost_visual_provider.hxx"

#include "Dolphin/MTX.h"
#include "Dolphin/OS.h"
#include "Dolphin/math.h"
#include "Dolphin/mem.h"
#include "Dolphin/printf.h"
#include "Dolphin/string.h"
#include "SMS/Camera/PolarSubCamera.hxx"
#include "SMS/Manager/FlagManager.hxx"
#include "SMS/Map/Map.hxx"
#include "SMS/Player/Mario.hxx"
#include "SMS/Player/MarioDraw.hxx"
#include "SMS/System/Application.hxx"
#include "SMS/System/MarDirector.hxx"
#include "SMS/System/MovieDirector.hxx"
#include "susamune/addresses.hxx"
#include "susamune/actions.hxx"
#include "susamune/binds.hxx"
#include "susamune/checksum.hxx"
#include "susamune/ghost_format.h"
#include "susamune/ghost_clock.h"
#include "susamune/ghost_model.hxx"
#include "susamune/ghost_fludd.hxx"
#include "susamune/ghost_camera.hxx"
#include "susamune/ghost_context.hxx"
#include "susamune/ghost_stage_context.hxx"
#include "susamune/ghost_simulation.hxx"
#include "susamune/ghost_scrub.hxx"
#include "susamune/ghost_path.hxx"
#if TIMEWARP_LIVE_RACING
#include "susamune/live_ghost.hxx"
#include "susamune/live_race.hxx"
#endif
#include "susamune/ghost_storage.h"
#include "susamune/iling.hxx"
#include "susamune/input_display.hxx"
#include "susamune/mem2_map.h"
#include "susamune/menu.hxx"
#include "susamune/features.hxx"
#include "susamune/qft_timer.hxx"
#include "susamune/records.hxx"
#include "susamune/practice_session.hxx"
#include "susamune/retail_input.hxx"
#include "susamune/settings.hxx"
#include "susamune/stage_loader.hxx"
#include "susamune/warp_wheel.hxx"

namespace Ghost {

namespace {

const s32 kPositionScale = SUSAMUNE_GHOST_POSITION_SCALE;
const s32 kMaxPosition = 1000000;
// Legacy imports and savestate prefixes keep their fifteen-minute bounds.
const s32 kMaxDurationQf = SUSAMUNE_GHOST_MAX_DURATION_QF;
const u16 kClockSettleObservations = 30;
const u16 kMaxSegments = SUSAMUNE_GHOST_V4_MAX_SEGMENTS;
const u32 kPlaybackTokenBit = 0x80000000u;
const u16 kCueMove = 0x0001u;
const u16 kCueEntry = 0x0200u;
u8 runningRegion();
static_assert(SUSAMUNE_GHOST_INPUT_MAX_COUNT *
                  sizeof(SusamuneGhostInputSample) <=
              SUSAMUNE_GHOST_INPUT_BANK_SIZE, "ghost input bank too small");

enum RecordFailure {
    RECORD_FAILURE_NONE,
    RECORD_FAILURE_MARIO,
    RECORD_FAILURE_CLOCK_REGRESSION,
    RECORD_FAILURE_CLOCK_GAP,
    RECORD_FAILURE_POSITION,
    RECORD_FAILURE_ANIMATION,
    RECORD_FAILURE_ASSIST,
    RECORD_FAILURE_SEGMENTS,
};

enum ClockPhase {
    CLOCK_UNAVAILABLE,
    CLOCK_PROVISIONAL,
    CLOCK_ACTIVE,
    CLOCK_FINISHED,
    CLOCK_WAIT_STAGE,
};

enum ObserverPhase {
    OBSERVER_OFF,
    OBSERVER_PREPARING_ONE,
    OBSERVER_PREPARING_TWO,
    OBSERVER_WARPING_ONE,
    OBSERVER_WARPING_TWO,
    OBSERVER_ACTIVE_ONE,
    OBSERVER_ACTIVE_TWO,
};

typedef SusamuneGhostPoseSample Sample;
static_assert(sizeof(Sample) == SUSAMUNE_GHOST_POSE_SAMPLE_SIZE,
              "ghost sample layout changed");

struct Segment {
    u32 firstSample;
    u32 sampleCount;
    u32 startQf;
    u32 endQf;
    s32 routeVariant;
    u8 routeArea;
    u8 routeEpisode;
    u8 routeParentArea;
    u8 routeFlags;
    u32 reserved0;
    u32 reserved1;
};
static_assert(sizeof(Segment) == 32, "ghost segment layout changed");
static_assert(sizeof(Segment) == sizeof(SusamuneGhostSegment),
              "runtime and canonical ghost segments differ");

const u32 kMaxSamples = SUSAMUNE_GHOST_MAX_SAMPLE_COUNT;
const u32 kSegmentTableOffset =
    SUSAMUNE_GHOST_SLOT_SIZE - kMaxSegments * sizeof(Segment);
static_assert(kMaxSamples * sizeof(Sample) <= SUSAMUNE_GHOST_SLOT_SIZE,
              "ghost samples do not fit their MEM2 slot");
static_assert(kMaxSamples * sizeof(Sample) <= kSegmentTableOffset,
              "ghost samples overlap their segment table");
static_assert(kSegmentTableOffset + kMaxSegments * sizeof(Segment) <=
                  SUSAMUNE_GHOST_SLOT_SIZE,
              "ghost segments do not fit their MEM2 slot");

struct Track {
    Sample *samples;
    Segment *segments;
    SusamuneGhostInputSample *inputs;
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
    bool valid;
    bool completed;
    bool saved;
    bool pb;
    u8 failure;
};

#pragma clang section text=".foxtrot.text"
SusamuneGhostInputSample &inputAt(const Track &track, u32 index) {
    return *reinterpret_cast<SusamuneGhostInputSample *>(
        reinterpret_cast<u8 *>(track.inputs) +
        index * SusamuneGhostInputStride(track.formatVersion));
}

#pragma clang section text=""
u32 inputQf(const Track &track, u32 index) {
    if (track.formatVersion < SUSAMUNE_GHOST_FILE_VERSION_V10) return inputAt(track, index).qf;
    return SusamuneGhostTeachingInputQf(reinterpret_cast<const u8 *>(&inputAt(track, index)),
                                       track.startQf, track.formatVersion);
}

Track &sRecord = *reinterpret_cast<Track *>(SUSAMUNE_GHOST_TRACKS_PPC_BASE);
Track &sPlayback = *reinterpret_cast<Track *>(SUSAMUNE_GHOST_TRACKS_PPC_BASE + sizeof(Track));
// Watch 2 borrows the record slot's MEM2 payload, but its metadata must not
// participate in recording, PB, or storage-ack ownership.
Track &sObserverSecondary = *reinterpret_cast<Track *>(SUSAMUNE_GHOST_TRACKS_PPC_BASE + 2 * sizeof(Track));
static_assert(3 * sizeof(Track) <= SUSAMUNE_GHOST_TRACKS_SIZE, "ghost track metadata allocation");
const u32 kSavedRngWord = 124 - RNG_CONTROL_SAVESTATE_DATA_WORDS;
const u32 kSavedPrefixMagic = 0x53475046u; // SGPF
struct SavedPrefix {
    u32 magic;
    u32 capturedQf;
    Track track;
    SusamuneGhostClock clock;
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
enum SavedPrefixFlags {
    PREFIX_RECORDING = 1,
    PREFIX_STAGE_PENDING = 2,
    PREFIX_HAD_ROUTE = 4,
    PREFIX_CONTINUE = 8,
    PREFIX_BOUNDARY = 16,
    PREFIX_LIVE_ROUTE = 32,
};
static_assert(sizeof(SavedPrefix) <= sizeof(SavestateData),
              "ghost prefix metadata exceeded its snapshot sidecar");
u32 sAttemptSerial;
s32 sLastSampleQf;
SusamuneGhostClock sRecordClock;
bool sFrameFrozen;
bool sFrameAssisted;
u32 sPlaybackCursor;
s32 sPlaybackCursorQf;
u16 sPlaybackSegment;
bool sRecording;
bool sRestoredPrefix;
u8 sRestoredEndpoint;
bool sGhostVisible;
bool sStageRoutePending;
bool sPendingHadLiveRoute;
bool sPendingContinueRecording;
bool sBoundaryPending;
bool sLiveRouteValid;
bool sPlaybackPinned;
bool sPinRouteCheckPending;
bool sChallengerNotified;
RaceSource sPlaybackRaceSource;
u32 sPlaybackRaceToken;
RaceContext sRaceContext;
u32 sRaceContextPlaybackToken;
bool sRaceContextValid;
SusamuneGhostSplitSample sRaceSplits[SUSAMUNE_GHOST_SPLIT_MAX_COUNT];
u8 sRaceSplitCount;
u32 sRaceSplitSerial;
u32 sRaceSplitPlaybackToken;
s32 sVisualQf;
ClockPhase sClockPhase;
u16 sClockObservations;
u8 sLiveArea;
u8 sLiveEpisode;
u8 sLiveRouteParentArea;
u8 sLiveRouteFlags;
s32 sClockLastQf;
s32 sClockEpochStartQf;
s32 sLiveParentEpisode;
s32 sPendingPreviousClockQf;
s32 sBoundaryPriorQf;
u16 sBoundaryBaseSegmentCount;
TVec3f sGhostPosition;
s16 sGhostYaw;
u16 sGhostAnimationId;
u16 sGhostAnimationPhase;
u32 sGhostHeldObjectId;
u16 sGhostHeldNameKey;
u8 sGhostYoshi;
u32 sGhostIdSerial;
u32 sRecordToken;
u32 sRecordIdentityToken;
u32 sPlaybackToken;
u32 sPlaybackOriginRecordToken;
u32 sPBTokenSerial;
ObserverPhase sObserverPhase;
bool sObserverPrimaryReady;
bool sObserverSecondaryReady;
u16 sObserverPrimarySegment;
u16 sObserverSecondarySegment;
u32 sObserverSecondaryCursor;
s32 sObserverSecondaryCursorQf;
s32 sObserverBaseQf;
s32 sObserverEndQf;
s32 sObserverLastQf;
s32 sObserverLastLiveQf;
s32 sObserverQfOffset;
s32 sObserverStageAnchorQf;
bool sObserverClockReady;
TVec3f sSecondaryGhostPosition;
s16 sSecondaryGhostYaw;
u16 sSecondaryGhostAnimationId;
u16 sSecondaryGhostAnimationPhase;
u32 sSecondaryGhostHeldObjectId;
u16 sSecondaryGhostHeldNameKey;
u8 sSecondaryGhostYoshi;
bool sSecondaryGhostVisible;
TMario *sObserverMario;
CPolarSubCamera *sObserverCamera;
f32 sObserverCameraYOffset;
u16 sObserverMarioPerformFlags;
bool sObserverMarioVisible;
bool sObserverMarioPrevVisible;
bool sObserverMarioOwned;
bool sObserverMarioBaselineFinalized;
TVec3f sObserverMarioTranslation;
TVec3f sObserverMarioLastPosition;
TVec3f sObserverMarioLastPos;
TVec3f sObserverMarioLastGroundedPos;
TVec3f sObserverMarioSpeed;
TVec3f sObserverMarioPrevSpeed;
f32 sObserverMarioForwardSpeed;
TVec3s sObserverMarioAngle;
s16 sObserverMarioModelAngleY;
const TBGCheckData *sObserverMarioFloor;
f32 sObserverMarioFloorBelow;
u32 sObserverMarioState;
bool sObserverStageReady;
bool sObserverPastEnd;
bool sObserverRouteValidated;
bool sObserverContinuousClock;
bool sObserverCleanupWarp;
bool sObserverExitArmed;
bool sObserverScrubClock;
bool sObserverPaused;
s32 sObserverSeekQf = -1;
s32 sObserverSecondaryOffset;
s32 sObserverRawQf;
s8 sObserverAlignedSplit = -1;
u32 sObserverVisualToken;

s32 parentEpisode() {
    return TFlagManager::smInstance
        ? TFlagManager::smInstance->getFlag(0x40003u)
        : -1;
}

const Segment *lastSegment(const Track &track) {
    return track.segmentCount == 0
        ? nullptr
        : &track.segments[track.segmentCount - 1];
}

Segment *lastSegment(Track &track) {
    return track.segmentCount == 0
        ? nullptr
        : &track.segments[track.segmentCount - 1];
}

bool segmentRouteEquals(const Segment &segment, u8 area, u8 episode,
                        s32 parent, u8 parentArea, u8 flags) {
    return segment.routeArea == area && segment.routeEpisode == episode &&
           segment.routeVariant == parent &&
           segment.routeParentArea == parentArea &&
           segment.routeFlags == flags;
}

__attribute__((always_inline)) constexpr bool routeCourseEquals(
    u8 lhsArea, u8 lhsEpisode, s32 lhsParent, u8 lhsParentArea, u8 rhsArea,
    u8 rhsEpisode, s32 rhsParent, u8 rhsParentArea) {
    const bool lhsInternal =
        lhsParentArea != SUSAMUNE_GHOST_ROUTE_PARENT_NONE;
    const bool rhsInternal =
        rhsParentArea != SUSAMUNE_GHOST_ROUTE_PARENT_NONE;
    const u8 lhsCourse = lhsInternal ? lhsParentArea : lhsArea;
    const u8 rhsCourse = rhsInternal ? rhsParentArea : rhsArea;
    const s32 lhsCourseEpisode = lhsInternal ? lhsParent : lhsEpisode;
    const s32 rhsCourseEpisode = rhsInternal ? rhsParent : rhsEpisode;
    return lhsCourse == rhsCourse && lhsCourseEpisode == rhsCourseEpisode;
}

static_assert(routeCourseEquals(6, 3, 3, SUSAMUNE_GHOST_ROUTE_PARENT_NONE,
                                7, 0, 3, 6),
              "parent and child must share a logical course");
static_assert(routeCourseEquals(7, 0, 3, 6, 6, 3, 3,
                                SUSAMUNE_GHOST_ROUTE_PARENT_NONE),
              "child-start ghosts must match their parent course");
static_assert(!routeCourseEquals(6, 3, 3, SUSAMUNE_GHOST_ROUTE_PARENT_NONE,
                                 6, 4, 4,
                                 SUSAMUNE_GHOST_ROUTE_PARENT_NONE),
              "episodes must remain distinct logical courses");
static_assert(!routeCourseEquals(6, 3, 3, SUSAMUNE_GHOST_ROUTE_PARENT_NONE,
                                 4, 3, 3,
                                 SUSAMUNE_GHOST_ROUTE_PARENT_NONE),
              "stage families must remain distinct logical courses");

bool segmentCourseEquals(const Segment &segment, u8 area, u8 episode,
                         s32 parent, u8 parentArea) {
    return routeCourseEquals(segment.routeArea, segment.routeEpisode,
                             segment.routeVariant,
                             segment.routeParentArea, area, episode, parent,
                             parentArea);
}

bool playbackOwnsCourse(u8 area, u8 episode, s32 parent, u8 parentArea) {
    if (!sPlayback.valid) return false;
    for (u16 i = 0; i < sPlayback.segmentCount; i++) {
        if (segmentCourseEquals(sPlayback.segments[i], area, episode,
                                parent, parentArea)) {
            return true;
        }
    }
    return false;
}

bool neutralHub(u8 area) {
    return area == TGameSequence::AREA_DOLPIC;
}

bool recordRouteMatches(u8 area, u8 episode, s32 parent, u8 parentArea,
                        u8 routeFlags) {
    const Segment *segment = lastSegment(sRecord);
    return sRecord.valid && segment &&
           segmentRouteEquals(*segment, area, episode, parent, parentArea,
                              routeFlags);
}

bool pinSurvivesRoute(u8 area, u8 episode, s32 parent, u8 parentArea) {
    return sPlaybackPinned &&
           (neutralHub(area) ||
            playbackOwnsCourse(area, episode, parent, parentArea));
}

void clearRaceContext() {
    sRaceContextValid = false;
    sRaceContext.source = RACE_SOURCE_NONE;
    if (sRaceSplitSerial != gQFTTimer.attemptSerial()) sRaceSplitCount = 0;
}

void captureComparisonSplits() {
    sRaceSplitCount = 0;
    sRaceSplitSerial = sAttemptSerial;
    sRaceSplitPlaybackToken = sPlaybackToken;
    if (!sPlayback.valid ||
        sPlayback.splitCount > SUSAMUNE_GHOST_SPLIT_MAX_COUNT ||
        !playbackOwnsCourse(sLiveArea, sLiveEpisode, sLiveParentEpisode,
                            sLiveRouteParentArea)) return;
    sRaceSplitCount = sPlayback.splitCount;
    memcpy(sRaceSplits, sPlayback.splits,
           sRaceSplitCount * sizeof(sRaceSplits[0]));
}

void captureRaceContext() {
    // Automatic last-run ghosts also supply checkpoints, without race awards.
    captureComparisonSplits();
    if (!sPlaybackPinned || !sPlayback.valid || !sPlayback.completed ||
        sPlaybackRaceSource == RACE_SOURCE_NONE ||
        sPlaybackRaceToken != sPlaybackToken ||
        !playbackOwnsCourse(sLiveArea, sLiveEpisode, sLiveParentEpisode,
                            sLiveRouteParentArea)) {
        return;
    }
    sRaceContext.attemptSerial = sAttemptSerial;
    sRaceContext.targetQf = sPlayback.resultQf;
    sRaceContext.startingPbQf = -1;
    sRaceContext.routeVariant = sPlayback.parentEpisode;
    sRaceContext.ilEntry = -1;
    sRaceContext.area = sPlayback.area;
    sRaceContext.episode = sPlayback.episode;
    sRaceContext.routeParentArea = sPlayback.routeParentArea;
    sRaceContext.routeFlags = sPlayback.routeFlags;
    sRaceContext.source = sPlaybackRaceSource;
    sRaceContextPlaybackToken = sPlaybackToken;
    sRaceContextValid = true;
}

void settlePlaybackPin() {
    if (!sPinRouteCheckPending) return;
    sPinRouteCheckPending = false;
    if (sPlaybackPinned &&
        !pinSurvivesRoute(sLiveArea, sLiveEpisode, sLiveParentEpisode,
                          sLiveRouteParentArea)) {
        sPlaybackPinned = false;
    }
}

bool recordPromotableForRoute(bool routeMatches, bool boundaryReset) {
    return sRecord.valid &&
           (sRecord.completed ||
            (!gSettings.getBool(SETTING_GHOST_LAST_SUCCESS) &&
             (routeMatches || boundaryReset)));
}

u8 routeParentArea(u8 area) {
    return LevelWarp::parentArea(area);
}

void captureLiveRoute() {
    sLiveArea = gpApplication.mCurrentScene.mAreaID;
    sLiveEpisode = gpApplication.mCurrentScene.mEpisodeID;
    sLiveParentEpisode = parentEpisode();
    sLiveRouteParentArea = routeParentArea(sLiveArea);
    sLiveRouteFlags = sLiveRouteParentArea == SUSAMUNE_GHOST_ROUTE_PARENT_NONE
        ? 0
        : SUSAMUNE_GHOST_ROUTE_INTERNAL_SCENE;
    sLiveRouteValid = true;
}

void refreshProvisionalRoute() {
    const u8 priorArea = sLiveArea;
    const u8 priorEpisode = sLiveEpisode;
    const u8 priorParentArea = sLiveRouteParentArea;
    const u8 priorFlags = sLiveRouteFlags;
    const s32 priorParentEpisode = sLiveParentEpisode;
    captureLiveRoute();
    if (priorArea == sLiveArea && priorEpisode == sLiveEpisode &&
        priorParentArea == sLiveRouteParentArea &&
        priorFlags == sLiveRouteFlags &&
        priorParentEpisode == sLiveParentEpisode) {
        return;
    }

    // Scene and parent-episode fields can still settle after setupObjects().
    // Require a fresh stable window before trusting them for a race or file.
    sClockObservations = 1;
    if (!sRecording) return;
    Segment *segment = lastSegment(sRecord);
    if (!segment) return;
    segment->routeArea = sLiveArea;
    segment->routeEpisode = sLiveEpisode;
    segment->routeVariant = sLiveParentEpisode;
    segment->routeParentArea = sLiveRouteParentArea;
    segment->routeFlags = sLiveRouteFlags;
    if (sRecord.segmentCount == 1) {
        sRecord.area = sLiveArea;
        sRecord.episode = sLiveEpisode;
        sRecord.parentEpisode = sLiveParentEpisode;
        sRecord.routeParentArea = sLiveRouteParentArea;
        sRecord.routeFlags = sLiveRouteFlags;
    }
}

bool liveRouteStorable() {
    return sLiveRouteValid &&
           sLiveArea <= SUSAMUNE_GHOST_ROUTE_AREA_MAX &&
           sLiveEpisode <= SUSAMUNE_GHOST_ROUTE_EPISODE_MAX &&
           sLiveParentEpisode >= SUSAMUNE_GHOST_ROUTE_VARIANT_NONE &&
           sLiveParentEpisode <= SUSAMUNE_GHOST_ROUTE_VARIANT_MAX &&
           (sLiveRouteParentArea == SUSAMUNE_GHOST_ROUTE_PARENT_NONE ||
            sLiveRouteParentArea <= SUSAMUNE_GHOST_ROUTE_AREA_MAX) &&
           (!(sLiveRouteFlags & SUSAMUNE_GHOST_ROUTE_INTERNAL_SCENE) ==
            (sLiveRouteParentArea == SUSAMUNE_GHOST_ROUTE_PARENT_NONE));
}

void clearTrack(Track &track) {
    track.inputCount = 0;
    track.splitCount = 0;
    track.teachingFlags = 0;
    track.sourceProfile = ILing::pbProfile() == 4 ? SUSAMUNE_GHOST_HOVERLESS_PROFILE : ILing::pbProfile();
    track.sourceRegion = runningRegion();
    track.count = 0;
    track.startQf = 0;
    track.endQf = 0;
    track.resultQf = SUSAMUNE_GHOST_RESULT_QF_NONE;
    track.runFlags = SUSAMUNE_GHOST_RUN_INCOMPLETE;
    track.pbToken = 0;
    track.parentEpisode = -1;
    track.area = 0xff;
    track.episode = 0xff;
    track.routeParentArea = SUSAMUNE_GHOST_ROUTE_PARENT_NONE;
    track.routeFlags = 0;
    track.segmentCount = 0;
    track.formatVersion = GhostContext::detailsEnabled() ?
        SUSAMUNE_GHOST_FILE_VERSION_V10 : SUSAMUNE_GHOST_FILE_VERSION_V9;
    track.attachmentFlags = 0;
    track.attachmentCount = 0;
    memset(track.attachments, 0, sizeof(track.attachments));
    track.valid = false;
    track.completed = false;
    track.saved = false;
    track.pb = false;
    track.failure = RECORD_FAILURE_NONE;
}

void bumpRecordToken() {
    sRecord.saved = false;
    sChallengerNotified = false;
    sRecordToken = (sRecordToken + 1) & ~kPlaybackTokenBit;
    if (sRecordToken == 0) sRecordToken++;
}

void bumpPlaybackToken() {
    sPlaybackOriginRecordToken = 0;
    sPlaybackToken = (sPlaybackToken + 1) & ~kPlaybackTokenBit;
    if (sPlaybackToken == 0) sPlaybackToken++;
}

u32 nextPBToken() {
    sPBTokenSerial++;
    if (sPBTokenSerial == 0) sPBTokenSerial++;
    return sPBTokenSerial;
}

void clearRecord() {
    clearTrack(sRecord);
    sRestoredPrefix = false;
    sRestoredEndpoint = ILing::SAVED_GHOST_END_NONE;
    bumpRecordToken();
    sRecordIdentityToken = sRecordToken;
}

bool observerHasTwo() {
    return sObserverPhase == OBSERVER_PREPARING_TWO ||
           sObserverPhase == OBSERVER_WARPING_TWO ||
           sObserverPhase == OBSERVER_ACTIVE_TWO;
}

bool observerRunning() {
    return sObserverPhase == OBSERVER_WARPING_ONE ||
           sObserverPhase == OBSERVER_WARPING_TWO ||
           sObserverPhase == OBSERVER_ACTIVE_ONE ||
           sObserverPhase == OBSERVER_ACTIVE_TWO;
}

s32 recordQf(s32 liveQf) {
    const bool tas = sFrameAssisted ||
        (sAttemptSerial == gQFTTimer.attemptSerial() &&
         (sRecord.runFlags & SUSAMUNE_GHOST_RUN_TAS));
    SusamuneGhostClockObserve(&sRecordClock, gQFTTimer.attemptSerial(),
                             liveQf, sFrameFrozen && tas);
    return SusamuneGhostClockMap(&sRecordClock, liveQf);
}

void updateRestoredRecorder() {
    // The departing prefix may still belong to an attempt being restarted.
    if (sStageRoutePending || sBoundaryPending ||
        sAttemptSerial != gQFTTimer.attemptSerial() ||
        (!sRecording && !sPendingContinueRecording)) return;
    if (sRestoredPrefix) ILing::updateSavestateGhostEndpoint(sRestoredEndpoint);
    // A child scene can arm a new IL while this assisted full-route prefix carries on.
    if (sRecord.runFlags & SUSAMUNE_GHOST_RUN_TAS)
        ILing::invalidateForAssist();
}

void releaseObserverMario(bool restore) {
    if (restore && sObserverMarioOwned && sObserverMario &&
        sObserverMario == gpMarioOriginal) {
        if (sObserverCamera && sObserverCamera == gpCamera &&
            gpMarDirector &&
            gpMarDirector->mCurState == TMarDirector::STATE_NORMAL &&
            sObserverCameraYOffset != 0.0f) {
            Vec cameraMove = {0.0f, -sObserverCameraYOffset, 0.0f};
            sObserverCamera->addMoveCameraAndMario(cameraMove);
        }
        sObserverMario->mPerformFlags = sObserverMarioPerformFlags;
        // A pre-normal abort must not preserve the visibility bit we cleared.
        const bool visible = sObserverMarioBaselineFinalized
            ? sObserverMarioVisible : true;
        const bool prevVisible = sObserverMarioBaselineFinalized
            ? sObserverMarioPrevVisible : true;
        sObserverMario->mAttributes.mIsVisible = visible;
        sObserverMario->mPrevAttributes.mIsVisible =
            prevVisible;
        sObserverMario->mTranslation = sObserverMarioTranslation;
        sObserverMario->mLastPosition = sObserverMarioLastPosition;
        sObserverMario->mLastPos = sObserverMarioLastPos;
        sObserverMario->mLastGroundedPos = sObserverMarioLastGroundedPos;
        sObserverMario->mSpeed = sObserverMarioSpeed;
        sObserverMario->mPrevSpeed = sObserverMarioPrevSpeed;
        sObserverMario->mForwardSpeed = sObserverMarioForwardSpeed;
        sObserverMario->mAngle = sObserverMarioAngle;
        sObserverMario->mModelAngleY = sObserverMarioModelAngleY;
        sObserverMario->mFloorTriangle = sObserverMarioFloor;
        sObserverMario->mFloorBelow = sObserverMarioFloorBelow;
        sObserverMario->mState = sObserverMarioState;
    }
    sObserverMario = nullptr;
    sObserverCamera = nullptr;
    sObserverCameraYOffset = 0.0f;
    sObserverMarioOwned = false;
}

__attribute__((noinline)) void captureObserverMarioPose() {
    sObserverMarioTranslation = sObserverMario->mTranslation;
    sObserverMarioLastPosition = sObserverMario->mLastPosition;
    sObserverMarioLastPos = sObserverMario->mLastPos;
    sObserverMarioLastGroundedPos = sObserverMario->mLastGroundedPos;
    sObserverMarioSpeed = sObserverMario->mSpeed;
    sObserverMarioPrevSpeed = sObserverMario->mPrevSpeed;
    sObserverMarioForwardSpeed = sObserverMario->mForwardSpeed;
    sObserverMarioAngle = sObserverMario->mAngle;
    sObserverMarioModelAngleY = sObserverMario->mModelAngleY;
    sObserverMarioFloor = sObserverMario->mFloorTriangle;
    sObserverMarioFloorBelow = sObserverMario->mFloorBelow;
    sObserverMarioState = sObserverMario->mState;
}

void bindObserverMario() {
    if (!gpMarioOriginal) return;
    if (sObserverMarioOwned && sObserverMario == gpMarioOriginal) return;
    releaseObserverMario(false);
    sObserverMario = gpMarioOriginal;
    sObserverCamera = gpCamera;
    sObserverCameraYOffset = 0.0f;
    sObserverMarioPerformFlags = sObserverMario->mPerformFlags;
    sObserverMarioVisible = sObserverMario->mAttributes.mIsVisible;
    sObserverMarioPrevVisible = sObserverMario->mPrevAttributes.mIsVisible;
    captureObserverMarioPose();
    sObserverMarioOwned = true;
    sObserverMarioBaselineFinalized = false;
    sObserverMario->mPerformFlags |= kCueEntry;
    sObserverMario->mAttributes.mIsVisible = false;
    sObserverMario->mPrevAttributes.mIsVisible = false;
}

void finalizeObserverMarioBaseline() {
    if (!sObserverMarioOwned || !sObserverMario ||
        sObserverMarioBaselineFinalized) return;
    // bindObserverMario already hid these bits during the intro. Once normal
    // gameplay begins, the state we must restore is Sunshine's visible Mario.
    sObserverMarioVisible = true;
    sObserverMarioPrevVisible = true;
    captureObserverMarioPose();
    sObserverMarioBaselineFinalized = true;
    sObserverMario->mAttributes.mIsVisible = false;
    sObserverMario->mPrevAttributes.mIsVisible = false;
}

void resetObserverRuntime() {
    releaseObserverMario(true);
    clearTrack(sObserverSecondary);
    sObserverPhase = OBSERVER_OFF;
    sObserverPrimaryReady = false;
    sObserverSecondaryReady = false;
    sObserverPrimarySegment = 0xffff;
    sObserverSecondarySegment = 0xffff;
    sObserverSecondaryCursor = 0;
    sObserverSecondaryCursorQf = 0;
    sObserverBaseQf = 0;
    sObserverEndQf = 0;
    sObserverLastQf = 0;
    sObserverQfOffset = 0;
    sObserverStageAnchorQf = -1;
    sObserverClockReady = false;
    sSecondaryGhostYaw = 0;
    sSecondaryGhostAnimationId = 0;
    sSecondaryGhostAnimationPhase = 0;
    sSecondaryGhostHeldObjectId = 0;
    sSecondaryGhostHeldNameKey = 0;
    sSecondaryGhostYoshi = SUSAMUNE_GHOST_V4_YOSHI_NONE;
    sSecondaryGhostVisible = false;
    sObserverStageReady = false;
    sObserverPastEnd = false;
    sObserverRouteValidated = false;
    sObserverContinuousClock = false;
    sObserverCleanupWarp = false;
    sObserverExitArmed = false;
    sObserverScrubClock = false;
    sObserverPaused = false;
    sObserverSeekQf = -1;
    sObserverSecondaryOffset = 0;
    sObserverAlignedSplit = -1;
}

void failRecording(RecordFailure failure, const char *message) {
    sRecording = false;
    sRecord.valid = false;
    sRecord.failure = static_cast<u8>(failure);
    bumpRecordToken();
    if (gMenu) gMenu->toast(message);
}

void stopAll() {
    GhostRecording::cancelActive();
    GhostVisualProvider::stopActive();
    clearRecord();
    clearTrack(sPlayback);
    bumpPlaybackToken();
    sPlaybackPinned = false;
    sPinRouteCheckPending = false;
    sRecording = false;
    sGhostVisible = false;
    sStageRoutePending = false;
    sPendingHadLiveRoute = false;
    sPendingContinueRecording = false;
    sBoundaryPending = false;
    sLiveRouteValid = false;
    sClockPhase = CLOCK_UNAVAILABLE;
    clearRaceContext();
    resetObserverRuntime();
}

bool fixedPosition(f32 value, s32 *fixed) {
    if (!fixed) return false;
    if (value != value || value < -static_cast<f32>(kMaxPosition) ||
        value > static_cast<f32>(kMaxPosition)) {
        return false;
    }
    *fixed = static_cast<s32>(value * static_cast<f32>(kPositionScale));
    return true;
}

u32 readU24(const u8 bytes[3]) {
    return (static_cast<u32>(bytes[0]) << 16) |
           (static_cast<u32>(bytes[1]) << 8) |
           static_cast<u32>(bytes[2]);
}

s32 readS24(const u8 bytes[3]) {
    const u32 raw = readU24(bytes);
    return static_cast<s32>((raw & 0x800000u) ? raw | 0xff000000u : raw);
}

void writeU24(u8 bytes[3], u32 value) {
    bytes[0] = static_cast<u8>(value >> 16);
    bytes[1] = static_cast<u8>(value >> 8);
    bytes[2] = static_cast<u8>(value);
}

void writeS24(u8 bytes[3], s32 value) {
    writeU24(bytes, static_cast<u32>(value) & 0xffffffu);
}

s32 sampleX(const Sample &sample) { return readS24(sample.x); }
s32 sampleY(const Sample &sample) { return readS24(sample.y); }
s32 sampleZ(const Sample &sample) { return readS24(sample.z); }

u16 sampleAnimationId(const Sample &sample) {
    return static_cast<u16>(readU24(sample.animation) >> 15);
}

u16 sampleAnimationPhase(const Sample &sample, u16 version) {
    const u32 packed = readU24(sample.animation);
    if (version >= SUSAMUNE_GHOST_FILE_VERSION_V4) {
        const u32 phase = (packed >> SUSAMUNE_GHOST_V4_ANIMATION_PHASE_SHIFT) &
                          SUSAMUNE_GHOST_V4_ANIMATION_PHASE_MAX;
        return static_cast<u16>(phase * SUSAMUNE_GHOST_ANIMATION_PHASE_MAX /
                                SUSAMUNE_GHOST_V4_ANIMATION_PHASE_MAX);
    }
    return static_cast<u16>((packed >> 3) &
                            SUSAMUNE_GHOST_ANIMATION_PHASE_MAX);
}

u8 sampleYoshi(const Sample &sample, u16 version) {
    return version >= SUSAMUNE_GHOST_FILE_VERSION_V4
        ? static_cast<u8>((readU24(sample.animation) >>
                           SUSAMUNE_GHOST_V4_YOSHI_SHIFT) &
                          SUSAMUNE_GHOST_V4_YOSHI_MASK)
        : SUSAMUNE_GHOST_V4_YOSHI_NONE;
}

u8 sampleHeld(const Sample &sample, u16 version) {
    return version >= SUSAMUNE_GHOST_FILE_VERSION_V4
        ? static_cast<u8>(readU24(sample.animation) &
                          SUSAMUNE_GHOST_V4_HELD_INDEX_MASK)
        : 0;
}

void sampleAttachments(const Track &track, const Sample &sample, u8 *yoshi,
                       u32 *objectId, u16 *nameKey) {
    if (yoshi) *yoshi = sampleYoshi(sample, track.formatVersion);
    if (objectId) *objectId = 0;
    if (nameKey) *nameKey = 0;
    const u8 held = sampleHeld(sample, track.formatVersion);
    if (held == 0 || held == SUSAMUNE_GHOST_V4_HELD_UNKNOWN ||
        held > track.attachmentCount) {
        return;
    }
    const SusamuneGhostAttachmentDescriptor &descriptor =
        track.attachments[held - 1];
    if (objectId) {
        *objectId = (static_cast<u32>(descriptor.objectId[0]) << 24) |
                    (static_cast<u32>(descriptor.objectId[1]) << 16) |
                    (static_cast<u32>(descriptor.objectId[2]) << 8) |
                    static_cast<u32>(descriptor.objectId[3]);
    }
    if (nameKey) {
        *nameKey = static_cast<u16>(
            (static_cast<u16>(descriptor.nameKey[0]) << 8) |
            descriptor.nameKey[1]);
    }
}

void setSampleAnimation(Sample &sample, u16 id, u16 phase) {
    const u32 attachments = readU24(sample.animation) & 0x7fu;
    const u32 phaseV4 =
        (static_cast<u32>(phase) * SUSAMUNE_GHOST_V4_ANIMATION_PHASE_MAX +
         SUSAMUNE_GHOST_ANIMATION_PHASE_MAX / 2) /
        SUSAMUNE_GHOST_ANIMATION_PHASE_MAX;
    writeU24(sample.animation,
             (static_cast<u32>(id) << 15) |
             (phaseV4 << SUSAMUNE_GHOST_V4_ANIMATION_PHASE_SHIFT) |
             attachments);
}

void setSampleAttachments(Sample &sample, u8 yoshi, u8 held) {
    const u32 animation = readU24(sample.animation) & ~0x7fu;
    writeU24(sample.animation,
             animation |
             (static_cast<u32>(yoshi) << SUSAMUNE_GHOST_V4_YOSHI_SHIFT) |
             held);
}

bool attachmentDescriptorEquals(
    const SusamuneGhostAttachmentDescriptor &descriptor, u32 objectId,
    u16 nameKey) {
    return descriptor.objectId[0] == static_cast<u8>(objectId >> 24) &&
           descriptor.objectId[1] == static_cast<u8>(objectId >> 16) &&
           descriptor.objectId[2] == static_cast<u8>(objectId >> 8) &&
           descriptor.objectId[3] == static_cast<u8>(objectId) &&
           descriptor.nameKey[0] == static_cast<u8>(nameKey >> 8) &&
           descriptor.nameKey[1] == static_cast<u8>(nameKey);
}

void setAttachmentDescriptor(SusamuneGhostAttachmentDescriptor &descriptor,
                             u32 objectId, u16 nameKey) {
    descriptor.objectId[0] = static_cast<u8>(objectId >> 24);
    descriptor.objectId[1] = static_cast<u8>(objectId >> 16);
    descriptor.objectId[2] = static_cast<u8>(objectId >> 8);
    descriptor.objectId[3] = static_cast<u8>(objectId);
    descriptor.nameKey[0] = static_cast<u8>(nameKey >> 8);
    descriptor.nameKey[1] = static_cast<u8>(nameKey);
}

u8 captureYoshiState() {
    if (!gpMarioOriginal || !gpMarioOriginal->mYoshi ||
        gpMarioOriginal->mYoshi->mState != TYoshi::MOUNTED) {
        return SUSAMUNE_GHOST_V4_YOSHI_NONE;
    }
    const s8 color = gpMarioOriginal->mYoshi->mType;
    return color >= TYoshi::GREEN && color <= TYoshi::PINK
        ? static_cast<u8>(color + 1)
        : SUSAMUNE_GHOST_V4_YOSHI_UNKNOWN;
}

u8 captureHeldObject(Track &track) {
    if (!gpMarioOriginal || !gpMarioOriginal->mHeldObject) return 0;
    const TTakeActor *held = gpMarioOriginal->mHeldObject;
    if (held->mObjectID == 0 && held->mKeyCode == 0) {
        track.attachmentFlags |=
            SUSAMUNE_GHOST_V4_ATTACHMENT_HELD_OVERFLOW;
        return SUSAMUNE_GHOST_V4_HELD_UNKNOWN;
    }
    for (u8 i = 0; i < track.attachmentCount; i++) {
        if (attachmentDescriptorEquals(track.attachments[i], held->mObjectID,
                                       held->mKeyCode)) {
            return static_cast<u8>(i + 1);
        }
    }
    if (track.attachmentCount <
        SUSAMUNE_GHOST_V4_ATTACHMENT_DESCRIPTOR_COUNT) {
        setAttachmentDescriptor(track.attachments[track.attachmentCount],
                                held->mObjectID, held->mKeyCode);
        return static_cast<u8>(++track.attachmentCount);
    }
    track.attachmentFlags |=
        SUSAMUNE_GHOST_V4_ATTACHMENT_HELD_OVERFLOW;
    return SUSAMUNE_GHOST_V4_HELD_UNKNOWN;
}

bool captureAnimation(u16 *idOut, u16 *phaseOut) {
    if (!idOut || !phaseOut || !gpMarioOriginal ||
        gpMarioOriginal->mAnimationID > SUSAMUNE_GHOST_ANIMATION_ID_MAX) {
        return false;
    }
    J3DFrameCtrl *frame = gpMarioOriginal->getMotionFrameCtrl();
    if (!frame || frame->mNumFrames <= 0 ||
        frame->mCurFrame != frame->mCurFrame) {
        return false;
    }

    f32 current = frame->mCurFrame;
    const f32 end = static_cast<f32>(frame->mNumFrames);
    if (current < 0.0f) current = 0.0f;
    if (current > end) current = end;
    u32 phase = static_cast<u32>(
        current * static_cast<f32>(
                      SUSAMUNE_GHOST_ANIMATION_PHASE_MAX + 1u) /
        end + 0.5f);
    if (phase > SUSAMUNE_GHOST_ANIMATION_PHASE_MAX) {
        phase = SUSAMUNE_GHOST_ANIMATION_PHASE_MAX;
    }
    *idOut = gpMarioOriginal->mAnimationID;
    *phaseOut = static_cast<u16>(phase);
    return true;
}

u16 interpolateAnimationPhase(u16 before, u16 after, s32 numerator,
                              s32 denominator) {
    const s32 period = SUSAMUNE_GHOST_ANIMATION_PHASE_MAX + 1;
    s32 delta = (static_cast<s32>(after) - before + period / 2) &
                (period - 1);
    delta -= period / 2;
    return static_cast<u16>((before +
        static_cast<s32>(static_cast<s64>(delta) * numerator / denominator)) &
        (period - 1));
}

bool appendSegment() {
    if (sRecord.segmentCount >= kMaxSegments) {
        sRecording = false;
        sRecord.failure = RECORD_FAILURE_SEGMENTS;
        if (gMenu) gMenu->toast("Ghost: segment capacity reached");
        return false;
    }
    Segment &segment = sRecord.segments[sRecord.segmentCount++];
    memset(&segment, 0, sizeof(segment));
    segment.firstSample = sRecord.count;
    segment.routeVariant = sLiveParentEpisode;
    segment.routeArea = sLiveArea;
    segment.routeEpisode = sLiveEpisode;
    segment.routeParentArea = sLiveRouteParentArea;
    segment.routeFlags = sLiveRouteFlags;
    if (sRecord.segmentCount == 1) {
        sRecord.area = sLiveArea;
        sRecord.episode = sLiveEpisode;
        sRecord.parentEpisode = sLiveParentEpisode;
        sRecord.routeParentArea = sLiveRouteParentArea;
        sRecord.routeFlags = sLiveRouteFlags;
    } else {
        sRecord.runFlags |= SUSAMUNE_GHOST_RUN_CUSTOM_ROUTE;
    }
    bumpRecordToken();
    return true;
}

void rollbackBoundarySegment() {
    if (sRecord.segmentCount <= sBoundaryBaseSegmentCount) return;
    if (sRecord.formatVersion >= SUSAMUNE_GHOST_FILE_VERSION_V10)
        GhostContext::clearSegment(sRecord.samples, sBoundaryBaseSegmentCount);
    while (sRecord.segmentCount > sBoundaryBaseSegmentCount) {
        memset(&sRecord.segments[--sRecord.segmentCount], 0,
               sizeof(Segment));
    }
    if (sRecord.segmentCount == 0) {
        sRecord.count = 0;
        sRecord.startQf = 0;
        sRecord.endQf = 0;
        sRecord.valid = false;
        sRecord.runFlags &= ~SUSAMUNE_GHOST_RUN_CUSTOM_ROUTE;
    } else {
        const Segment &last = sRecord.segments[sRecord.segmentCount - 1];
        sRecord.count = last.firstSample + last.sampleCount;
        sRecord.endQf = last.endQf;
        if (sRecord.segmentCount == 1) {
            sRecord.runFlags &= ~SUSAMUNE_GHOST_RUN_CUSTOM_ROUTE;
        }
    }
    sLastSampleQf = sRecord.segmentCount == 0
        ? 0
        : static_cast<s32>(sRecord.endQf);
    if (sRecord.formatVersion >= SUSAMUNE_GHOST_FILE_VERSION_V8)
        GhostCamera::trim(sRecord.samples, sRecord.endQf, sRecord.segmentCount);
    bumpRecordToken();
}

void dropLastEmptySegment() {
    Segment *segment = lastSegment(sRecord);
    if (!segment || segment->sampleCount != 0) return;
    memset(segment, 0, sizeof(*segment));
    sRecord.segmentCount--;
    if (sRecord.segmentCount <= 1) {
        sRecord.runFlags &= ~SUSAMUNE_GHOST_RUN_CUSTOM_ROUTE;
    }
    bumpRecordToken();
}

bool appendSample(s32 qf) {
    qf = SusamuneGhostClockMap(&sRecordClock, qf);
    if (!gpMarioOriginal) {
        failRecording(RECORD_FAILURE_MARIO,
                      "Ghost: Mario disappeared");
        return false;
    }
    if (qf < 0) {
        failRecording(RECORD_FAILURE_CLOCK_REGRESSION,
                      "Ghost: negative QFT");
        return false;
    }

    Segment *segment = lastSegment(sRecord);
    if (!segment) {
        failRecording(RECORD_FAILURE_SEGMENTS,
                      "Ghost: missing route segment");
        return false;
    }

    if (sRecord.count != 0 &&
        qf - static_cast<s32>(sRecord.startQf) >
            static_cast<s32>(SusamuneGhostDurationLimit(sRecord.formatVersion))) {
        dropLastEmptySegment();
        sRecording = false;
        sClockPhase = CLOCK_FINISHED;
        if (gMenu) gMenu->toast("Ghost: recording limit reached");
        return false;
    }
    if (sRecord.count >= SusamuneGhostPoseLimit(sRecord.formatVersion)) {
        dropLastEmptySegment();
        sRecording = false;
        sClockPhase = CLOCK_FINISHED;
        if (gMenu) gMenu->toast("Ghost: sample capacity reached");
        return false;
    }

    const s32 delta = segment->sampleCount == 0 ? 0 : qf - sLastSampleQf;
    if (delta < 0) {
        failRecording(RECORD_FAILURE_CLOCK_REGRESSION,
                      "Ghost: sample clock regressed");
        return false;
    }
    if (delta > 0xffff) {
        failRecording(RECORD_FAILURE_CLOCK_GAP,
                      "Ghost: sample clock gap");
        return false;
    }
    if (segment->sampleCount != 0 && delta < 4) return true;

    s32 x;
    s32 y;
    s32 z;
    if (!fixedPosition(gpMarioOriginal->mTranslation.x, &x) ||
        !fixedPosition(gpMarioOriginal->mTranslation.y, &y) ||
        !fixedPosition(gpMarioOriginal->mTranslation.z, &z)) {
        failRecording(RECORD_FAILURE_POSITION,
                      "Ghost: invalid Mario position");
        return false;
    }
    u16 animationId;
    u16 animationPhase;
    if (!captureAnimation(&animationId, &animationPhase)) {
        failRecording(RECORD_FAILURE_ANIMATION,
                      "Ghost: invalid Mario animation");
        return false;
    }

    Sample &sample = sRecord.samples[sRecord.count];
    memset(&sample, 0, sizeof(sample));
    writeS24(sample.x, x);
    writeS24(sample.y, y);
    writeS24(sample.z, z);
    sample.yaw = gpMarioOriginal->mModelAngleY;
    sample.deltaQf = static_cast<u16>(delta);
    setSampleAnimation(sample, animationId, animationPhase);
    setSampleAttachments(sample, captureYoshiState(),
                         captureHeldObject(sRecord));
    if (segment->sampleCount == 0) {
        segment->startQf = static_cast<u32>(qf);
        if (sRecord.count == 0) {
            sRecord.startQf = static_cast<u32>(qf);
            if (sRecord.formatVersion >= SUSAMUNE_GHOST_FILE_VERSION_V9) {
                // Observation only: this is the first retained pose, not stage init.
                segment->reserved0 = *reinterpret_cast<volatile const u32 *>(
                    SUSAMUNE_ADDR_LIBC_RAND_SEED);
                segment->reserved1 = SUSAMUNE_GHOST_RNG_FIRST_POSE;
            }
        }
    }
    sRecord.count++;
    segment->sampleCount++;
    sLastSampleQf = qf;
    sRecord.endQf = static_cast<u32>(qf);
    segment->endQf = static_cast<u32>(qf);
    if (sClockPhase == CLOCK_ACTIVE && sRecord.count >= 2) {
        sRecord.valid = true;
    }
    bumpRecordToken();
    return true;
}

void clearEpochSamples() {
    Segment *segment = lastSegment(sRecord);
    if (!segment) return;
    if (sRecord.formatVersion >= SUSAMUNE_GHOST_FILE_VERSION_V10)
        GhostContext::clearSegment(sRecord.samples, sRecord.segmentCount - 1);
    sRecord.count = segment->firstSample;
    segment->sampleCount = 0;
    segment->reserved0 = segment->reserved1 = 0;
    segment->startQf = 0;
    segment->endQf = 0;
    if (sRecord.segmentCount == 1) {
        if (sRecord.formatVersion >= SUSAMUNE_GHOST_FILE_VERSION_V8)
            GhostCamera::reset(sRecord.samples);
        sRecord.inputCount = 0;
        sRecord.splitCount = 0;
        sRecord.teachingFlags = 0;
        sRecord.startQf = 0;
        sRecord.endQf = 0;
        sRecord.valid = false;
    } else {
        sRecord.endQf = sRecord.segments[sRecord.segmentCount - 2].endQf;
        if (sRecord.formatVersion >= SUSAMUNE_GHOST_FILE_VERSION_V8)
            GhostCamera::trim(sRecord.samples, sRecord.endQf, sRecord.segmentCount - 1);
    }
    sRecord.resultQf = SUSAMUNE_GHOST_RESULT_QF_NONE;
    sRecord.completed = false;
    sRecord.failure = RECORD_FAILURE_NONE;
    sLastSampleQf = 0;
    bumpRecordToken();
}

bool startEpochSamples(s32 qf) {
    if (sRecord.formatVersion >= SUSAMUNE_GHOST_FILE_VERSION_V10 && sRecord.segmentCount == 1)
        GhostContext::reset(sRecord.samples);
    clearEpochSamples();
    // QFT can first become readable partway through the materialise-in. Keep
    // that elapsed time by holding Mario's first observable pose from QF zero.
    const s32 anchor = sRecord.segmentCount == 1 ? 0 : qf;
    if (!appendSample(anchor)) return false;
    if (sRecord.formatVersion >= SUSAMUNE_GHOST_FILE_VERSION_V10)
        GhostContext::segment(sRecord.samples, sRecord.segmentCount - 1, qf, sRecord.inputCount, anchor != qf);
    if (GhostStageContext::restoredStage())
        sRecord.runFlags |= SUSAMUNE_GHOST_RUN_SAVESTATE_USED | SUSAMUNE_GHOST_RUN_ASSISTED | SUSAMUNE_GHOST_RUN_TAS;
    if (qf - anchor >=
        static_cast<s32>(SUSAMUNE_GHOST_TRANSFORM_INTERVAL_QF)) {
        return appendSample(qf);
    }
    return true;
}

void rewindPlayback() {
    sPlaybackCursor = 0;
    sPlaybackCursorQf = 0;
    sPlaybackSegment = 0xffff;
}

void rebaseClock(s32 qf) {
    if (sRecording) {
        if (sRecord.segmentCount > 1) {
            failRecording(RECORD_FAILURE_CLOCK_REGRESSION,
                          "Ghost: cross-stage QFT regression");
        } else {
            startEpochSamples(qf);
        }
    }
    rewindPlayback();
    sClockPhase = CLOCK_PROVISIONAL;
    sClockObservations = 1;
    sClockLastQf = qf;
    sClockEpochStartQf = qf;
}

s32 interpolateFixed(s32 a, s32 b, s32 numerator, s32 denominator) {
    return a + static_cast<s32>(
        static_cast<s64>(b - a) * numerator / denominator);
}

bool finishTrackAt(s32 qf) {
    Segment *segment = lastSegment(sRecord);
    if (!segment || segment->sampleCount == 0 ||
        qf < static_cast<s32>(segment->startQf) ||
        qf - static_cast<s32>(sRecord.startQf) >
            static_cast<s32>(SusamuneGhostDurationLimit(sRecord.formatVersion))) {
        return false;
    }

    u32 index = segment->firstSample;
    const u32 segmentEnd = segment->firstSample + segment->sampleCount;
    s32 sampleQf = static_cast<s32>(segment->startQf);
    while (index + 1 < segmentEnd) {
        const s32 nextQf = sampleQf + sRecord.samples[index + 1].deltaQf;
        if (nextQf == qf) {
            sRecord.count = index + 2;
            segment->sampleCount = sRecord.count - segment->firstSample;
            segment->endQf = static_cast<u32>(qf);
            sRecord.endQf = static_cast<u32>(qf);
            sLastSampleQf = qf;
            return true;
        }
        if (nextQf > qf) {
            const s32 numerator = qf - sampleQf;
            const s32 denominator = nextQf - sampleQf;
            if (numerator == 0) {
                sRecord.count = index + 1;
            } else {
                const Sample before = sRecord.samples[index];
                const Sample after = sRecord.samples[index + 1];
                Sample &terminal = sRecord.samples[index + 1];
                writeS24(terminal.x,
                         interpolateFixed(sampleX(before), sampleX(after),
                                          numerator, denominator));
                writeS24(terminal.y,
                         interpolateFixed(sampleY(before), sampleY(after),
                                          numerator, denominator));
                writeS24(terminal.z,
                         interpolateFixed(sampleZ(before), sampleZ(after),
                                          numerator, denominator));
                const s32 yawDelta = static_cast<s16>(
                    static_cast<u16>(after.yaw - before.yaw));
                terminal.yaw = static_cast<s16>(
                    before.yaw + yawDelta * numerator / denominator);
                const u16 beforeAnimation = sampleAnimationId(before);
                const u16 afterAnimation = sampleAnimationId(after);
                setSampleAnimation(
                    terminal, beforeAnimation,
                    beforeAnimation == afterAnimation
                        ? interpolateAnimationPhase(
                              sampleAnimationPhase(before, sRecord.formatVersion),
                              sampleAnimationPhase(after, sRecord.formatVersion), numerator,
                              denominator)
                        : sampleAnimationPhase(before, sRecord.formatVersion));
                terminal.deltaQf = static_cast<u16>(numerator);
                sRecord.count = index + 2;
                if (sRecord.formatVersion >= SUSAMUNE_GHOST_FILE_VERSION_V10)
                    GhostContext::endpoint(sRecord.samples, sRecord.segmentCount - 1, qf, sRecord.inputCount, false);
            }
            segment->sampleCount = sRecord.count - segment->firstSample;
            segment->endQf = static_cast<u32>(qf);
            sRecord.endQf = static_cast<u32>(qf);
            sLastSampleQf = qf;
            return true;
        }
        sampleQf = nextQf;
        index++;
    }

    if (qf == sampleQf) {
        sRecord.count = index + 1;
        segment->sampleCount = sRecord.count - segment->firstSample;
        segment->endQf = static_cast<u32>(qf);
        sRecord.endQf = static_cast<u32>(qf);
        sLastSampleQf = qf;
        return true;
    }

    const s32 delta = qf - sampleQf;
    if (delta <= 0 || delta > 0xffff || sRecord.count >= SusamuneGhostPoseLimit(sRecord.formatVersion)) {
        return false;
    }
    if (sRecord.formatVersion >= SUSAMUNE_GHOST_FILE_VERSION_V10)
        GhostContext::endpoint(sRecord.samples, sRecord.segmentCount - 1, qf, sRecord.inputCount, true);
    Sample terminal = sRecord.samples[sRecord.count - 1];
    terminal.deltaQf = static_cast<u16>(delta);
    sRecord.samples[sRecord.count++] = terminal;
    segment->sampleCount++;
    segment->endQf = static_cast<u32>(qf);
    sRecord.endQf = static_cast<u32>(qf);
    sLastSampleQf = qf;
    return true;
}

void finishStreamRecord(const Track &track);

void finishRecording(s32 qf, bool completed) {
    const s32 storedQf = SusamuneGhostClockMap(&sRecordClock, qf);
    const bool clockWasActive = sClockPhase == CLOCK_ACTIVE;
    if (sRecording && sRecord.count != 0) {
        bool bounded = clockWasActive;
        if (bounded && completed) bounded = finishTrackAt(storedQf);
        sRecord.valid = bounded && sRecord.count >= 2;
        sRecord.completed = completed && sRecord.valid;
        if (sRecord.completed) {
            sRecord.resultQf = static_cast<u32>(storedQf);
            sRecord.runFlags &= ~SUSAMUNE_GHOST_RUN_INCOMPLETE;
        } else {
            sRecord.resultQf = SUSAMUNE_GHOST_RESULT_QF_NONE;
            sRecord.runFlags |= SUSAMUNE_GHOST_RUN_INCOMPLETE;
        }
        bumpRecordToken();
    }
    sRecording = false;
    sClockLastQf = qf;
    sClockPhase = CLOCK_FINISHED;
    if (sRecord.valid) finishStreamRecord(sRecord);
}

void prepareClock(s32 qf) {
    sGhostVisible = false;
    sStageRoutePending = false;
    sClockPhase = CLOCK_PROVISIONAL;
    sClockObservations = 1;
    sClockLastQf = qf;
    sClockEpochStartQf = qf;
}

void beginAttempt(s32 qf, bool boundaryReset = false) {
    if (!gpMarDirector) return;

    clearRaceContext();
    captureLiveRoute();
    const u8 area = sLiveArea;
    const u8 episode = sLiveEpisode;
    const s32 parent = sLiveParentEpisode;
    const bool recordReady = sRecord.valid;
    const bool routeMatches = recordRouteMatches(
        area, episode, parent, sLiveRouteParentArea, sLiveRouteFlags);
    // Plaza is a neutral handoff between races. Outside it, reaching another
    // logical course retires the pinned target so its challenger can take the
    // playback slot and the old target buffer can record the next attempt.
    if (sPlaybackPinned) {
        if (boundaryReset) {
            // setupObjects can briefly expose the departed route. Keep the
            // selected opponent until the new route has settled.
            sPinRouteCheckPending = true;
        } else if (!pinSurvivesRoute(area, episode, parent,
                                     sLiveRouteParentArea)) {
            sPlaybackPinned = false;
            sPinRouteCheckPending = false;
        }
    } else {
        sPinRouteCheckPending = false;
    }
    if (!sPlaybackPinned &&
        gSettings.getBool(SETTING_GHOST_LAST_SUCCESS) &&
        sPlayback.valid && !sPlayback.completed) {
        // Two buffers cannot recover an older success once a partial replaced
        // it. Do not misrepresent that stale partial as the selected policy.
        clearTrack(sPlayback);
        bumpPlaybackToken();
    }
    // Completed runs remain exportable across scenes. An interrupted attempt
    // is useful only when restarting that exact route; never let a plaza/hub
    // segment evict the last course ghost.
    const bool recordPromotable = recordReady &&
        recordPromotableForRoute(routeMatches, boundaryReset);
    const bool keepChallenger =
        recordReady && sRecord.completed &&
        sPlaybackPinned && !sRecord.saved;

    if (recordPromotable && !sPlaybackPinned) {
        // Keep the newest completed track even when the next attempt changes
        // route. Route matching controls racing, not ownership/exportability.
        Sample *oldPlayback = sPlayback.samples;
        Segment *oldPlaybackSegments = sPlayback.segments;
        SusamuneGhostInputSample *oldInputs = sPlayback.inputs;
        sPlayback = sRecord;
        sRecord.samples = oldPlayback;
        sRecord.segments = oldPlaybackSegments;
        sRecord.inputs = oldInputs;
        bumpPlaybackToken();
        sPlaybackOriginRecordToken = sRecordToken;
    }
    captureRaceContext();
    rewindPlayback();

    if (!keepChallenger) {
        clearRecord();
    }
    sLastSampleQf = 0;
    // A pinned library target stays in the playback slot while this independent
    // record slot captures a challenger. Once complete, preserve that challenger
    // across restarts until storage acknowledges it or the pin is released.
    sRecording = !keepChallenger;
    prepareClock(qf);
    if (sRecording && appendSegment()) startEpochSamples(qf);
    if (keepChallenger && !sChallengerNotified && gMenu) {
        gMenu->toast("Ghost challenger ready: save or unpin");
        sChallengerNotified = true;
    }

}

f32 samplePosition(s32 value) {
    return static_cast<f32>(value) / static_cast<f32>(kPositionScale);
}

int playbackSegmentAt(s32 qf) {
    if (!gpMarDirector || !sLiveRouteValid || !sPlayback.valid) return -1;
    // Later segments own an equal end/start boundary. This keeps a movie
    // return on its new entry pose instead of the departed director's pose.
    for (int i = static_cast<int>(sPlayback.segmentCount) - 1; i >= 0; i--) {
        const Segment &segment = sPlayback.segments[i];
        if (segmentRouteEquals(segment, sLiveArea, sLiveEpisode,
                               sLiveParentEpisode, sLiveRouteParentArea,
                               sLiveRouteFlags) &&
            qf >= static_cast<s32>(segment.startQf) &&
            qf <= static_cast<s32>(segment.endQf)) {
            return i;
        }
    }
    return -1;
}

void selectPlaybackSegment(u16 index) {
    if (index >= sPlayback.segmentCount || sPlaybackSegment == index) return;
    const Segment &segment = sPlayback.segments[index];
    sPlaybackSegment = index;
    sPlaybackCursor = segment.firstSample;
    sPlaybackCursorQf = static_cast<s32>(segment.startQf);
}

GhostVisualProvider::Query providerQuery(unsigned runner, s32 qf, bool watch, bool history = false) {
    const u32 scene = (u32(gpApplication.mCurrentScene.mAreaID) << 8) |
                     gpApplication.mCurrentScene.mEpisodeID;
    const unsigned segment = watch
        ? (runner ? sObserverSecondarySegment : sObserverPrimarySegment) : ~0u;
    const Track &track = runner ? sObserverSecondary : sPlayback;
    const Segment *route = watch && segment < track.segmentCount ? track.segments + segment : nullptr;
    return {runner, segment, scene, static_cast<unsigned>(gQFTTimer.attemptSerial()),
            watch ? static_cast<unsigned>(0x40000000u | sObserverVisualToken) : 0u,
            static_cast<int>(qf), (watch ? GhostVisualProvider::WATCH : 0u) |
                                  (history ? GhostVisualProvider::HISTORY : 0u),
            static_cast<int>(route ? route->routeVariant : sLiveParentEpisode),
            route ? route->routeParentArea : sLiveRouteParentArea,
            route ? route->routeFlags : sLiveRouteFlags};
}

void refreshProvidedVisual(s32 qf, bool watch) {
    sGhostVisible = sSecondaryGhostVisible = false;
    // setupObjects also reaches the observer helper from its resource worker.
    if (!gpMarDirector || !gpMarDirector->_260 || !OSIsThreadTerminated(&gSetupThread)) return;
    if (!watch && (sStageRoutePending || !sLiveRouteValid)) {
        GhostVisualProvider::suspend();
        return;
    }
#if TIMEWARP_LIVE_RACING
    if (!watch && LiveRace::groupState()) { GhostVisualProvider::suspend(); return; }
#endif
    const unsigned count = watch ? (observerHasTwo() ? 2u : 1u) : GhostVisualProvider::runners();
    const s64 secondary = static_cast<s64>(qf) + (watch ? sObserverSecondaryOffset : 0);
    if (qf < 0 || secondary < 0 || secondary > 0x7fffffff) {
        GhostVisualProvider::suspend();
        return;
    }
    GhostVisualProvider::Query queries[2] = {
        providerQuery(0, qf, watch), providerQuery(1, static_cast<s32>(secondary), watch)};
    GhostVisualProvider::refresh(queries, count, watch && count == 2);
    for (unsigned runner = 0; runner < 2; ++runner) {
#if TIMEWARP_LIVE_RACING
        if (runner && !watch && LiveRace::opponentModel() >= 0) continue;
#endif
        GhostVisualProvider::Frame frame;
        if (!GhostVisualProvider::read(runner, frame)) continue;
        const VisualState &v = frame.visual;
        if (!runner) {
            sGhostPosition.set(v.x, v.y, v.z); sGhostYaw = v.yaw;
            sGhostAnimationId = v.animationId; sGhostAnimationPhase = v.animationPhase;
            sGhostHeldObjectId = v.heldObjectId; sGhostHeldNameKey = v.heldNameKey;
            sGhostYoshi = v.yoshi; sGhostVisible = v.visible;
        } else {
            sSecondaryGhostPosition.set(v.x, v.y, v.z); sSecondaryGhostYaw = v.yaw;
            sSecondaryGhostAnimationId = v.animationId; sSecondaryGhostAnimationPhase = v.animationPhase;
            sSecondaryGhostHeldObjectId = v.heldObjectId; sSecondaryGhostHeldNameKey = v.heldNameKey;
            sSecondaryGhostYoshi = v.yoshi; sSecondaryGhostVisible = v.visible;
        }
    }
}

void updatePlayback(s32 qf) {
    qf = recordQf(qf);
    sVisualQf = qf;
    if (GhostVisualProvider::active()) { refreshProvidedVisual(qf, false); return; }
    sGhostVisible = false;
    sGhostHeldObjectId = 0;
    sGhostHeldNameKey = 0;
    sGhostYoshi = SUSAMUNE_GHOST_V4_YOSHI_NONE;
    const int segmentIndex = playbackSegmentAt(qf);
    if (segmentIndex < 0) return;
    const Segment &segment = sPlayback.segments[segmentIndex];
    if (segment.sampleCount == 0) return;
    selectPlaybackSegment(static_cast<u16>(segmentIndex));
    if (qf < sPlaybackCursorQf) {
        sPlaybackSegment = 0xffff;
        selectPlaybackSegment(static_cast<u16>(segmentIndex));
    }

    const u32 segmentEnd = segment.firstSample + segment.sampleCount;

    while (sPlaybackCursor + 1 < segmentEnd) {
        const s32 nextQf = sPlaybackCursorQf +
            sPlayback.samples[sPlaybackCursor + 1].deltaQf;
        if (nextQf > qf) break;
        sPlaybackCursor++;
        sPlaybackCursorQf = nextQf;
    }

    const Sample &a = sPlayback.samples[sPlaybackCursor];
    if (sPlaybackCursor + 1 >= segmentEnd) {
        sGhostPosition.set(samplePosition(sampleX(a)),
                           samplePosition(sampleY(a)),
                           samplePosition(sampleZ(a)));
        sGhostYaw = a.yaw;
        sGhostAnimationId = sampleAnimationId(a);
        sGhostAnimationPhase = sampleAnimationPhase(a, sPlayback.formatVersion);
        sampleAttachments(sPlayback, a, &sGhostYoshi,
                          &sGhostHeldObjectId, &sGhostHeldNameKey);
        sGhostVisible = true;
        return;
    }

    const Sample &b = sPlayback.samples[sPlaybackCursor + 1];
    const s32 nextQf = sPlaybackCursorQf + b.deltaQf;
    f32 t = 0.0f;
    if (nextQf > sPlaybackCursorQf) {
        t = static_cast<f32>(qf - sPlaybackCursorQf) /
            static_cast<f32>(nextQf - sPlaybackCursorQf);
        if (t < 0.0f) t = 0.0f;
        if (t > 1.0f) t = 1.0f;
    }

    sGhostPosition.x = samplePosition(sampleX(a)) +
        (samplePosition(sampleX(b)) - samplePosition(sampleX(a))) * t;
    sGhostPosition.y = samplePosition(sampleY(a)) +
        (samplePosition(sampleY(b)) - samplePosition(sampleY(a))) * t;
    sGhostPosition.z = samplePosition(sampleZ(a)) +
        (samplePosition(sampleZ(b)) - samplePosition(sampleZ(a))) * t;
    const s32 yawDelta = static_cast<s16>(
        static_cast<u16>(b.yaw - a.yaw));
    sGhostYaw = static_cast<s16>(a.yaw + yawDelta *
        (qf - sPlaybackCursorQf) / (nextQf - sPlaybackCursorQf));
    sGhostAnimationId = sampleAnimationId(a);
    sGhostAnimationPhase = sampleAnimationId(a) == sampleAnimationId(b)
        ? interpolateAnimationPhase(
              sampleAnimationPhase(a, sPlayback.formatVersion),
              sampleAnimationPhase(b, sPlayback.formatVersion),
              qf - sPlaybackCursorQf, nextQf - sPlaybackCursorQf)
        : sampleAnimationPhase(a, sPlayback.formatVersion);
    sampleAttachments(sPlayback, a, &sGhostYoshi,
                      &sGhostHeldObjectId, &sGhostHeldNameKey);
    sGhostVisible = true;
}

void updateProvisionalPlayback(s32 qf) {
    // Recording still waits for a settled clock. Playback can seek the live
    // observation now; a later regression rewinds its cursor in rebaseClock().
    updatePlayback(qf);
}

bool sampleObserverTrack(const Track &track, u16 segmentIndex, s32 qf,
                         u32 *cursor, s32 *cursorQf, TVec3f *position,
                         s16 *yaw, u16 *animationId, u16 *animationPhase,
                         u8 *yoshi, u32 *heldObjectId, u16 *heldNameKey) {
    if (!cursor || !cursorQf || !position || !yaw || !animationId ||
        !animationPhase || !yoshi || !heldObjectId || !heldNameKey ||
        segmentIndex >= track.segmentCount) {
        return false;
    }
    const Segment &segment = track.segments[segmentIndex];
    if (segment.sampleCount == 0 || qf < static_cast<s32>(segment.startQf) ||
        qf > static_cast<s32>(segment.endQf)) {
        return false;
    }

    const u32 segmentEnd = segment.firstSample + segment.sampleCount;
    if (*cursor < segment.firstSample || *cursor >= segmentEnd ||
        qf < *cursorQf) {
        *cursor = segment.firstSample;
        *cursorQf = static_cast<s32>(segment.startQf);
    }
    while (*cursor + 1 < segmentEnd) {
        const s32 nextQf = *cursorQf + track.samples[*cursor + 1].deltaQf;
        if (nextQf > qf) break;
        (*cursor)++;
        *cursorQf = nextQf;
    }

    const Sample &a = track.samples[*cursor];
    if (*cursor + 1 >= segmentEnd) {
        position->set(samplePosition(sampleX(a)), samplePosition(sampleY(a)),
                      samplePosition(sampleZ(a)));
        *yaw = a.yaw;
        *animationId = sampleAnimationId(a);
        *animationPhase = sampleAnimationPhase(a, track.formatVersion);
        sampleAttachments(track, a, yoshi, heldObjectId, heldNameKey);
        return true;
    }

    const Sample &b = track.samples[*cursor + 1];
    const s32 nextQf = *cursorQf + b.deltaQf;
    const s32 span = nextQf - *cursorQf;
    if (span <= 0) return false;
    const s32 elapsed = qf - *cursorQf;
    const f32 t = static_cast<f32>(elapsed) / static_cast<f32>(span);
    position->x = samplePosition(sampleX(a)) +
        (samplePosition(sampleX(b)) - samplePosition(sampleX(a))) * t;
    position->y = samplePosition(sampleY(a)) +
        (samplePosition(sampleY(b)) - samplePosition(sampleY(a))) * t;
    position->z = samplePosition(sampleZ(a)) +
        (samplePosition(sampleZ(b)) - samplePosition(sampleZ(a))) * t;
    const s32 yawDelta = static_cast<s16>(
        static_cast<u16>(b.yaw - a.yaw));
    *yaw = static_cast<s16>(a.yaw + yawDelta * elapsed / span);
    *animationId = sampleAnimationId(a);
    *animationPhase = sampleAnimationId(a) == sampleAnimationId(b)
        ? interpolateAnimationPhase(sampleAnimationPhase(a, track.formatVersion),
                                    sampleAnimationPhase(b, track.formatVersion),
                                    elapsed, span)
        : sampleAnimationPhase(a, track.formatVersion);
    sampleAttachments(track, a, yoshi, heldObjectId, heldNameKey);
    return true;
}

s32 observerQf(bool *pastEnd = nullptr) {
    if (pastEnd) *pastEnd = false;
    if (sObserverPhase != OBSERVER_ACTIVE_ONE &&
        sObserverPhase != OBSERVER_ACTIVE_TWO) {
        return sObserverBaseQf;
    }

    if (sObserverScrubClock) {
        // The director counter still runs after a shine stops the race QFT.
        const s32 raw = gpMarDirector ? gpMarDirector->unk5C : sObserverRawQf;
        const s32 delta = raw >= sObserverRawQf ? raw - sObserverRawQf : 0;
        sObserverRawQf = raw;
        if (!sFrameFrozen && !sObserverPaused) sObserverLastQf += delta;
        if (pastEnd) *pastEnd = !sObserverPaused && sObserverLastQf > sObserverEndQf;
        if (sObserverLastQf > sObserverEndQf) sObserverLastQf = sObserverEndQf;
        return sObserverLastQf;
    }

    s32 liveQf;
    bool stopped;
    if (!sObserverClockReady ||
        !gQFTTimer.currentQf(&liveQf, &stopped)) {
        return sObserverLastQf;
    }

    if (liveQf >= sObserverLastLiveQf && sFrameFrozen)
        sObserverQfOffset -= liveQf - sObserverLastLiveQf;
    sObserverLastLiveQf = liveQf;
    s64 absoluteQf = static_cast<s64>(liveQf) + sObserverQfOffset;
    if (pastEnd) {
        // A stopped shared clock cannot reach a later Watch 2 endpoint.
        *pastEnd = stopped || absoluteQf > sObserverEndQf;
    }
    if (absoluteQf < sObserverBaseQf) absoluteQf = sObserverBaseQf;
    if (absoluteQf > sObserverEndQf) absoluteQf = sObserverEndQf;
    sObserverLastQf = static_cast<s32>(absoluteQf);
    return sObserverLastQf;
}

void updateObserverVisual(s32 qf) {
    sVisualQf = qf;
    if (GhostVisualProvider::active()) { refreshProvidedVisual(qf, true); return; }
    sGhostVisible = sampleObserverTrack(
        sPlayback, sObserverPrimarySegment, qf, &sPlaybackCursor,
        &sPlaybackCursorQf, &sGhostPosition, &sGhostYaw,
        &sGhostAnimationId, &sGhostAnimationPhase, &sGhostYoshi,
        &sGhostHeldObjectId, &sGhostHeldNameKey);
    sSecondaryGhostVisible = observerHasTwo() &&
        sampleObserverTrack(
            sObserverSecondary, sObserverSecondarySegment,
            qf + sObserverSecondaryOffset,
            &sObserverSecondaryCursor, &sObserverSecondaryCursorQf,
            &sSecondaryGhostPosition, &sSecondaryGhostYaw,
            &sSecondaryGhostAnimationId, &sSecondaryGhostAnimationPhase,
            &sSecondaryGhostYoshi, &sSecondaryGhostHeldObjectId,
            &sSecondaryGhostHeldNameKey);
}

bool observerRoutesCompatible() {
    if (!sPlayback.valid || sPlayback.segmentCount == 0) return false;
    if (!observerHasTwo()) return true;
    if (!sObserverSecondary.valid ||
        sObserverSecondary.segmentCount != sPlayback.segmentCount)
        return false;
    for (u16 i = 0; i < sPlayback.segmentCount; ++i) {
        const Segment &a = sPlayback.segments[i];
        const Segment &b = sObserverSecondary.segments[i];
        if (!segmentRouteEquals(b, a.routeArea, a.routeEpisode,
                                a.routeVariant, a.routeParentArea,
                                a.routeFlags)) {
            return false;
        }
    }
    return true;
}

bool observerSegmentRange(u16 index, s32 secondaryOffset, u32 *base, u32 *end) {
    if (index >= sPlayback.segmentCount) return false;
    const Segment &primary = sPlayback.segments[index];
    u32 baseQf = primary.startQf;
    u32 endQf = primary.endQf;
    if (primary.sampleCount == 0) return false;
    if (observerHasTwo()) {
        if (index >= sObserverSecondary.segmentCount) return false;
        const Segment &secondary = sObserverSecondary.segments[index];
        if (secondary.sampleCount == 0) return false;
        const s64 start = static_cast<s64>(secondary.startQf) - secondaryOffset;
        const s64 end = static_cast<s64>(secondary.endQf) - secondaryOffset;
        if (end > 0x7fffffff) return false;
        if (start >= 0 && static_cast<u32>(start) < baseQf) baseQf = start;
        if (end >= 0 && static_cast<u32>(end) > endQf) endQf = end;
    }
    if (endQf < baseQf || endQf - baseQf >
            static_cast<u32>(kMaxDurationQf)) {
        return false;
    }
    *base = baseQf;
    *end = endQf;
    return true;
}

bool configureObserverSegment() {
    u32 baseQf, endQf;
    if (!observerSegmentRange(sObserverPrimarySegment, sObserverSecondaryOffset,
                             &baseQf, &endQf)) return false;
    const Segment &primary = sPlayback.segments[sObserverPrimarySegment];
    sObserverSecondarySegment = 0xffff;
    if (observerHasTwo()) {
        sObserverSecondarySegment = sObserverPrimarySegment;
        const Segment &secondary = sObserverSecondary.segments[sObserverSecondarySegment];
        sObserverSecondaryCursor = secondary.firstSample;
        sObserverSecondaryCursorQf = static_cast<s32>(secondary.startQf);
    }
    sObserverBaseQf = static_cast<s32>(baseQf);
    sObserverEndQf = static_cast<s32>(endQf);
    sObserverLastQf = sObserverBaseQf;
    sObserverQfOffset = 0;
    sObserverStageAnchorQf = -1;
    sObserverClockReady = false;
    sPlaybackSegment = sObserverPrimarySegment;
    sPlaybackCursor = primary.firstSample;
    sPlaybackCursorQf = static_cast<s32>(primary.startQf);
    updateObserverVisual(sObserverBaseQf);
    return true;
}

LevelWarp::Dest observerSegmentDest() {
    const Segment &segment = sPlayback.segments[sObserverPrimarySegment];
    const u8 variant = segment.routeVariant >= 0
        ? static_cast<u8>(segment.routeVariant)
        : segment.routeEpisode;
    const LevelWarp::Dest dest = {
        segment.routeArea, segment.routeEpisode, variant
    };
    return dest;
}

LevelWarp::Dest observerSegmentSource() {
    const Segment &segment = sPlayback.segments[sObserverPrimarySegment];
    if (segment.routeParentArea == SUSAMUNE_GHOST_ROUTE_PARENT_NONE) {
        return observerSegmentDest();
    }
    const u8 episode = segment.routeVariant >= 0
        ? static_cast<u8>(segment.routeVariant)
        : segment.routeEpisode;
    const LevelWarp::Dest source = {
        segment.routeParentArea, episode, episode
    };
    return source;
}

void armObserverSegment() {
    const bool two = observerHasTwo();
    const LevelWarp::Dest dest = observerSegmentDest();
    const LevelWarp::Dest source = observerSegmentSource();
    // The guarded warp can wait on CARD or be canceled by settings. Restore
    // the current actor now; the loaded-stage callback drops stale ownership.
    releaseObserverMario(true);
    sObserverStageReady = false;
    sObserverPastEnd = false;
    sObserverRouteValidated = false;
    sObserverContinuousClock = false;
    sObserverExitArmed = false;
    sGhostVisible = false;
    sSecondaryGhostVisible = false;
    sObserverPhase = two ? OBSERVER_WARPING_TWO : OBSERVER_WARPING_ONE;
    LevelWarp::warpFrom(source, dest);
}

bool observerRouteLoaded() {
    captureLiveRoute();
    if (!sLiveRouteValid ||
        sObserverPrimarySegment >= sPlayback.segmentCount) {
        return false;
    }
    const Segment &segment = sPlayback.segments[sObserverPrimarySegment];
    if (!segmentRouteEquals(segment, sLiveArea, sLiveEpisode,
                            sLiveParentEpisode, sLiveRouteParentArea,
                            sLiveRouteFlags)) {
        return false;
    }
    if (!observerHasTwo()) return true;
    if (sObserverSecondarySegment >=
        sObserverSecondary.segmentCount) return false;
    return segmentRouteEquals(
        sObserverSecondary.segments[sObserverSecondarySegment],
        sLiveArea, sLiveEpisode, sLiveParentEpisode,
        sLiveRouteParentArea, sLiveRouteFlags);
}

void startObserverClock(s32 liveQf) {
    const bool two = observerHasTwo();
    // A direct observer warp resets QFT and needs a stage-local translation.
    // Retail loading zones carry the existing absolute timeline instead.
    const s32 stageAnchor = sObserverStageAnchorQf >= 0
        ? sObserverStageAnchorQf : liveQf;
    if (!sObserverContinuousClock) {
        sObserverQfOffset = sObserverPrimarySegment == 0
            ? 0 : sObserverBaseQf - stageAnchor;
    }
    sObserverContinuousClock = false;
    sObserverClockReady = true;
    sObserverLastLiveQf = liveQf;
    sObserverPastEnd = false;
    // Intro-skip presses are viewer input, not exit requests. An active-state
    // release must be observed before B or Start can end this segment.
    sObserverExitArmed = false;
    sObserverPhase = two ? OBSERVER_ACTIVE_TWO : OBSERVER_ACTIVE_ONE;
    if (sObserverScrubClock) {
        sObserverLastQf = sObserverSeekQf >= 0 ? sObserverSeekQf : sObserverBaseQf;
        sObserverSeekQf = -1;
        sObserverRawQf = gpMarDirector->unk5C;
    }
    updateObserverVisual(observerQf(&sObserverPastEnd));
}

void updateObserverGround() {
    // Watch 2 uses Mario as its camera midpoint, not either runner's contact
    // position. It must not press a platform between the two recorded paths.
    const TBGCheckData *floor = gpMap ? gpMap->getIllegalCheckData()
                                    : sObserverMarioFloor;
    f32 height = -32768.0f;
    bool standing = false;
    if (!observerHasTwo() && gpMap && sGhostVisible) {
        height = gpMap->checkGround(sGhostPosition.x, sGhostPosition.y + 25.0f,
                                    sGhostPosition.z, &floor);
        const f32 dx = sGhostPosition.x - sObserverMario->mTranslation.x;
        const f32 dz = sGhostPosition.z - sObserverMario->mTranslation.z;
        // Retail wait/landing/ledge-hang states can ride while still moving
        // in world space. A hanging root stays at the top of its ledge;
        // animation lowers the body. Keep the same real floor-contact gate.
        const bool landed = sGhostAnimationId == TMario::ANIMATION_IDLE ||
                            sGhostAnimationId == TMario::ANIMATION_WALLHANG ||
                            sGhostAnimationId == 0xd7u || // ANIM_HMOV_L
                            sGhostAnimationId == 0xd8u || // ANIM_HMOV_R
                            sGhostAnimationId == 0x4bu || // ANIM_2JMED
                            sGhostAnimationId == 0x4eu || // ANIM_JMPED
                            sGhostAnimationId == 0x57u;   // ANIM_LAEND
        standing = sGhostPosition.y <= height + 4.0f &&
                   (landed || dx * dx + dz * dz <= 0.0625f);
    }
    // Retail rail/tilt blocks read these even while Mario's own movement is
    // suppressed. Use the recorded contact; never integrate Mario physics.
    sObserverMario->mFloorTriangle = floor;
    sObserverMario->mFloorBelow = height;
    sObserverMario->mState = standing ? TMario::STATE_IDLE
                                    : sObserverMarioState & ~0x200u;
}

void anchorObserverMario() {
    if (!sObserverStageReady || !gpMarDirector ||
        (gpMarDirector->mCurState != TMarDirector::STATE_NORMAL &&
         !(sFrameFrozen && sObserverPaused &&
           gpMarDirector->mCurState == TMarDirector::STATE_STAGE_EXIT_2))) return;
    bindObserverMario();
    if (!sObserverMarioOwned || !sObserverMario) return;
    finalizeObserverMarioBaseline();

    // Suppress the actor even during a route gap where neither runner has a
    // sample yet. Otherwise the hidden Mario remains player-controllable.
    sObserverMario->mPerformFlags |= kCueMove | kCueEntry;
    sObserverMario->mAttributes.mIsVisible = false;
    sObserverMario->mPrevAttributes.mIsVisible = false;
    sObserverMario->mSpeed.set(0.0f, 0.0f, 0.0f);
    sObserverMario->mPrevSpeed.set(0.0f, 0.0f, 0.0f);
    sObserverMario->mForwardSpeed = 0.0f;
    updateObserverGround();
    if (!sGhostVisible && !sSecondaryGhostVisible) return;

    TVec3f target;
    s16 yaw;
    if (sGhostVisible && sSecondaryGhostVisible) {
        target.set((sGhostPosition.x + sSecondaryGhostPosition.x) * 0.5f,
                   (sGhostPosition.y + sSecondaryGhostPosition.y) * 0.5f,
                   (sGhostPosition.z + sSecondaryGhostPosition.z) * 0.5f);
        yaw = sGhostYaw;
    } else if (sGhostVisible) {
        target = sGhostPosition;
        yaw = sGhostYaw;
    } else {
        target = sSecondaryGhostPosition;
        yaw = sSecondaryGhostYaw;
    }

    // Moving Mario externally must carry the camera's smoothed Y anchors too.
    if (gpCamera && gpCamera == sObserverCamera) {
        Vec cameraMove = {
            0.0f, target.y - sObserverMario->mTranslation.y, 0.0f
        };
        if (cameraMove.y != 0.0f) {
            gpCamera->addMoveCameraAndMario(cameraMove);
            sObserverCameraYOffset += cameraMove.y;
        }
    }

    // TViewObj::testPerform subtracts this mask from each incoming cue.
    sObserverMario->mTranslation = target;
    sObserverMario->mLastPosition = target;
    sObserverMario->mLastPos = target;
    sObserverMario->mLastGroundedPos = target;
    sObserverMario->mAngle.y = yaw;
    sObserverMario->mModelAngleY = yaw;
}

void endObserver(bool reload, const char *message) {
    GhostCamera::restore();
    if (sObserverPhase == OBSERVER_OFF) return;
    const bool wasRunning = observerRunning();
    const bool canReload = reload && wasRunning &&
        sObserverPrimarySegment < sPlayback.segmentCount &&
        !gSettings.getBool(SETTING_DISABLE_WARPS);
    LevelWarp::Dest dest = {0, 0, 0};
    LevelWarp::Dest source = {0, 0, 0};
    if (canReload) {
        dest = observerSegmentDest();
        source = observerSegmentSource();
    }
    if (canReload) releaseObserverMario(true);
    if (wasRunning) {
        ILing::invalidateForAssist();
        Records::invalidateAttempt();
    }
    stopAll();
    sObserverCleanupWarp = canReload;
    sAttemptSerial = gQFTTimer.attemptSerial();
    if (canReload) LevelWarp::warpFrom(source, dest);
    if (message && gMenu) gMenu->toast(message);
}

bool advanceObserverSegment() {
    if (sObserverPrimarySegment + 1 >= sPlayback.segmentCount) return false;
    ++sObserverPrimarySegment;
    if (!configureObserverSegment()) return false;
    armObserverSegment();
    return true;
}

u32 runningGameId() {
#if defined(SUSAMUNE_VERSION_JP)
    return SUSAMUNE_GHOST_GAME_ID_JP;
#elif defined(SUSAMUNE_VERSION_US)
    return SUSAMUNE_GHOST_GAME_ID_US;
#else
    return SUSAMUNE_GHOST_GAME_ID_PAL;
#endif
}

u8 runningRegion() {
#if defined(SUSAMUNE_VERSION_JP)
    return SUSAMUNE_GHOST_REGION_JP;
#elif defined(SUSAMUNE_VERSION_US)
    return SUSAMUNE_GHOST_REGION_US;
#else
    return SUSAMUNE_GHOST_REGION_PAL;
#endif
}

bool validText(const char *text, u32 capacity, u8 length, bool required) {
    if (!text || length > capacity || (required && length == 0)) return false;
    for (u32 i = 0; i < capacity; i++) {
        const u8 c = static_cast<u8>(text[i]);
        if (i < length) {
            if (c < SUSAMUNE_GHOST_TEXT_MIN || c > SUSAMUNE_GHOST_TEXT_MAX ||
                c == '/' || c == '\\') {
                return false;
            }
        } else if (c != 0) {
            return false;
        }
    }
    return true;
}

u8 copyText(char *out, u32 capacity, const char *text) {
    if (!out || capacity == 0) return 0;
    memset(out, 0, capacity);
    if (!text) return 0;
    u8 length = 0;
    while (length < capacity && text[length]) {
        const u8 c = static_cast<u8>(text[length]);
        if (c >= SUSAMUNE_GHOST_TEXT_MIN && c <= SUSAMUNE_GHOST_TEXT_MAX &&
            c != '/' && c != '\\') {
            out[length] = static_cast<char>(c);
            length++;
        } else {
            break;
        }
    }
    return length;
}

const char *courseName(u8 area) {
    switch (area) {
    case TGameSequence::AREA_BIANCO: return "Bianco Hills";
    case TGameSequence::AREA_RICCO: return "Ricco Harbor";
    case TGameSequence::AREA_MAMMA: return "Gelato Beach";
    case TGameSequence::AREA_PINNABEACH: return "Pinna Park";
    case TGameSequence::AREA_SIRENA: return "Sirena Beach";
    case TGameSequence::AREA_MONTE: return "Pianta Village";
    case TGameSequence::AREA_MARE: return "Noki Bay";
    default: return nullptr;
    }
}

const char *internalRouteSuffix(u8 area, u8 episode, s32 variant) {
    switch (area) {
    case TGameSequence::AREA_BIANCOBOSS:
        return episode == 0 ? "Windmill" : nullptr;
    case TGameSequence::AREA_RICOEX0:
        return episode == 0 ? "Blooper Race" : nullptr;
    case TGameSequence::AREA_RICCOBOSS:
        return episode == 0 ? "Blooper" : nullptr;
    case TGameSequence::AREA_MAMMAEX1:
        return episode == 0 ? "Sand Bird" : nullptr;
    case TGameSequence::AREA_MAMMAEX0:
    case TGameSequence::AREA_SIRENAEX0:
    case TGameSequence::AREA_SIRENAEX1:
    case TGameSequence::AREA_COROEX0:
    case TGameSequence::AREA_COROEX1:
    case TGameSequence::AREA_COROEX2:
    case TGameSequence::AREA_COROEX4:
    case TGameSequence::AREA_COROEX5:
    case TGameSequence::AREA_MONTEEX0:
    case TGameSequence::AREA_RICOEX1:
        return episode == 0 ? "Secret" : nullptr;
    case TGameSequence::AREA_PINNABOSS:
        if (episode == 1 && variant == 0) return "Mecha-Bowser";
        return episode == 0 && variant == 7 ? "Balloons" : nullptr;
    case TGameSequence::AREA_DELFINO:
        if ((episode == 0 && variant == 1) ||
            (episode == 1 && variant == 2) ||
            (episode == 2 && (variant == 3 || variant == 4)) ||
            (episode == 3 && variant == 6) ||
            (episode == 4 && variant == 7)) {
            return "Hotel";
        }
        return nullptr;
    case TGameSequence::AREA_CASINO:
        return ((episode == 0 && variant == 3) ||
                (episode == 1 && variant == 4)) ? "Casino" : nullptr;
    case TGameSequence::AREA_DELFINOBOSS:
        return episode == 0 ? "King Boo" : nullptr;
    case TGameSequence::AREA_MAREEX0:
        return episode == 0 ? "Bottle" : nullptr;
    case TGameSequence::AREA_MAREBOSS:
        return episode == 0 ? "Eel Only" : nullptr;
    case TGameSequence::AREA_MAREUNDERSEA:
        return episode == 0 ? "Red Fish" : nullptr;
    default: return nullptr;
    }
}

bool isPinnaParkRoute(u8 episode, s32 variant) {
    return (episode == 0 && variant == 0) ||
           (episode == 1 && variant == 2) ||
           (episode == 2 && variant == 4) ||
           (episode == 3 && variant == 5) ||
           (episode == 4 && variant == 6) ||
           (episode == 5 && variant == 7);
}

const char *standaloneRouteName(u8 area) {
    switch (area) {
    case TGameSequence::AREA_AIRPORT: return "Airstrip 1";
    case TGameSequence::AREA_DOLPIC: return "Delfino Plaza";
    case TGameSequence::AREA_DOLPICEX0: return "Airstrip Reds";
    case TGameSequence::AREA_DOLPICEX1: return "Delfino Slide";
    case TGameSequence::AREA_DOLPICEX2: return "Pachinko";
    case TGameSequence::AREA_DOLPICEX3: return "Grass Secret";
    case TGameSequence::AREA_DOLPICEX4: return "Lily Pad";
    case TGameSequence::AREA_BIANCOEX1: return "Delfino Cop Secret";
    case TGameSequence::AREA_COROEX6: return "Corona Mountain";
    case TGameSequence::AREA_CORONABOSS: return "Bowser";
    default: return nullptr;
    }
}

void formatTrackName(const Track &track, char *out, u32 size) {
    if (!out || size == 0) return;
    out[0] = '\0';
    const u32 duration = track.endQf - track.startQf;
    const u32 millis = (duration * 1001u) / 120u;
    char route[32];
    route[0] = '\0';

    if (track.routeParentArea != SUSAMUNE_GHOST_ROUTE_PARENT_NONE &&
        (track.routeFlags & SUSAMUNE_GHOST_ROUTE_INTERNAL_SCENE) &&
        track.routeParentArea == routeParentArea(track.area)) {
        const char *parent = courseName(track.routeParentArea);
        if (parent && track.parentEpisode >= 0 &&
            track.parentEpisode < 8) {
            const char *suffix = internalRouteSuffix(
                track.area, track.episode, track.parentEpisode);
            if (suffix) {
                snprintf(route, sizeof(route), "%s %ld %s", parent,
                         track.parentEpisode + 1, suffix);
            } else if (track.area == TGameSequence::AREA_PINNAPARCO &&
                       isPinnaParkRoute(track.episode,
                                        track.parentEpisode)) {
                snprintf(route, sizeof(route), "%s %ld", parent,
                         track.parentEpisode + 1);
            } else {
                snprintf(route, sizeof(route), "%s %ld Route", parent,
                         track.parentEpisode + 1);
            }
        }
    } else if (track.routeParentArea == SUSAMUNE_GHOST_ROUTE_PARENT_NONE &&
               track.routeFlags == 0) {
        const char *course = courseName(track.area);
        if (course && track.episode < 8) {
            snprintf(route, sizeof(route), "%s %u", course,
                     static_cast<unsigned>(track.episode) + 1u);
        } else {
            const char *standalone = standaloneRouteName(track.area);
            if (standalone) snprintf(route, sizeof(route), "%s", standalone);
        }
    }

    if (route[0]) {
        snprintf(out, size, "%s%s - %lu:%02lu.%03lu",
                 (track.runFlags & SUSAMUNE_GHOST_RUN_TAS) ? "TAS " : "", route,
                 millis / 60000u, (millis / 1000u) % 60u,
                 millis % 1000u);
    } else {
        snprintf(out, size, "%sArea %u Episode %u - %lu:%02lu.%03lu",
                 (track.runFlags & SUSAMUNE_GHOST_RUN_TAS) ? "TAS " : "",
                 static_cast<unsigned>(track.area),
                 static_cast<unsigned>(track.episode) + 1u,
                 millis / 60000u, (millis / 1000u) % 60u,
                 millis % 1000u);
    }
}

void finishStreamRecord(const Track &track) {
    if (!GhostRecording::capturing() || !track.valid || track.count < 2) return;
    GhostRecording::Info info = {};
    info.ownerToken=sRecordToken;info.startQf=track.startQf;info.endQf=track.endQf;info.resultQf=track.resultQf;info.runFlags=track.runFlags;
    info.routeVariant=track.parentEpisode;info.area=track.area;info.episode=track.episode;info.parent=track.routeParentArea;info.routeFlags=track.routeFlags;
    info.sourceProfile=track.sourceProfile;info.splitCount=track.splitCount;memcpy(info.splits,track.splits,sizeof(info.splits));formatTrackName(track,info.name,sizeof(info.name));
    GhostRecording::finish(info);
}

enum SaveSource {
    SAVE_SOURCE_NONE,
    SAVE_SOURCE_RECORD,
    SAVE_SOURCE_PLAYBACK,
};

struct SaveSelection {
    const Track *track;
    u32 token;
    u32 identityToken;
    SaveSource source;
};

SaveSelection latestSaveableTrack() {
    if (sObserverPhase != OBSERVER_OFF) {
        return {nullptr, 0, 0, SAVE_SOURCE_NONE};
    }
    // Once Records accepts a PB, Save owns that immutable completed run until
    // storage acknowledges it or the user explicitly discards its PB token.
    // An unrelated live recording must never mask it.
    if (sRecord.valid && sRecord.pb && !sRecord.saved &&
        sRecord.pbToken != 0) {
        return {&sRecord, sRecordToken, sRecord.pbToken,
                SAVE_SOURCE_RECORD};
    }
    if (sPlayback.valid && sPlayback.pb && !sPlayback.saved &&
        sPlayback.pbToken != 0) {
        return {&sPlayback, kPlaybackTokenBit | sPlaybackToken,
                sPlayback.pbToken, SAVE_SOURCE_PLAYBACK};
    }
    // The current attempt owns Save once its clock/route have settled. A
    // loaded race target must never mask a challenger.
    if (sRecord.valid &&
        (!sRecording ||
         (sClockPhase == CLOCK_ACTIVE && !sBoundaryPending))) {
        return {&sRecord, sRecordToken, sRecordIdentityToken,
                SAVE_SOURCE_RECORD};
    }
    // A pinned library target is playback-only while the race is active.
    if (sPlayback.valid && !sPlaybackPinned) {
        return {&sPlayback, kPlaybackTokenBit | sPlaybackToken,
                kPlaybackTokenBit | sPlaybackToken, SAVE_SOURCE_PLAYBACK};
    }
    return {nullptr, 0, 0, SAVE_SOURCE_NONE};
}

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

bool validGameRegionPair(u32 gameId, u8 region) {
    switch (region) {
    case SUSAMUNE_GHOST_REGION_JP:
        return gameId == SUSAMUNE_GHOST_GAME_ID_JP;
    case SUSAMUNE_GHOST_REGION_US:
        return gameId == SUSAMUNE_GHOST_GAME_ID_US;
    case SUSAMUNE_GHOST_REGION_PAL:
        return gameId == SUSAMUNE_GHOST_GAME_ID_PAL;
    default:
        return false;
    }
}

s32 portableRouteParent(u8 area) {
    switch (area) {
#define PORTABLE_ROUTE_PARENT(routeArea, parentArea) \
    case routeArea: return parentArea;
        SUSAMUNE_GHOST_PORTABLE_ROUTE_LIST(PORTABLE_ROUTE_PARENT)
#undef PORTABLE_ROUTE_PARENT
    default:
        return -1;
    }
}

bool validPortableRouteTuple(u8 area, u8 episode, u8 parentArea, u8 flags,
                             s32 variant) {
    if (!validRouteTuple(area, episode, parentArea, flags, variant)) {
        return false;
    }
    const s32 requiredParent = portableRouteParent(area);
    if (requiredParent < 0) return false;
    if (requiredParent == SUSAMUNE_GHOST_ROUTE_PARENT_NONE) {
        return parentArea == SUSAMUNE_GHOST_ROUTE_PARENT_NONE && flags == 0;
    }
    return parentArea == static_cast<u8>(requiredParent) &&
           (flags == SUSAMUNE_GHOST_ROUTE_INTERNAL_SCENE ||
            flags == (SUSAMUNE_GHOST_ROUTE_INTERNAL_SCENE |
                      SUSAMUNE_GHOST_ROUTE_PARENT_START));
}

bool validSamplePosition(const Sample &sample) {
    return sampleX(sample) >= -SUSAMUNE_GHOST_MAX_POSITION_FIXED &&
           sampleX(sample) <= SUSAMUNE_GHOST_MAX_POSITION_FIXED &&
           sampleY(sample) >= -SUSAMUNE_GHOST_MAX_POSITION_FIXED &&
           sampleY(sample) <= SUSAMUNE_GHOST_MAX_POSITION_FIXED &&
           sampleZ(sample) >= -SUSAMUNE_GHOST_MAX_POSITION_FIXED &&
           sampleZ(sample) <= SUSAMUNE_GHOST_MAX_POSITION_FIXED;
}

bool validSampleAnimation(const Sample &sample, u16 version,
                          u8 attachmentCount, u16 attachmentFlags) {
    const u32 packed = readU24(sample.animation);
    if (sampleAnimationId(sample) > SUSAMUNE_GHOST_ANIMATION_ID_MAX) {
        return false;
    }
    if (version == SUSAMUNE_GHOST_FILE_VERSION_V3) {
        return !(packed & SUSAMUNE_GHOST_ANIMATION_RESERVED_MASK);
    }
    if (version != SUSAMUNE_GHOST_FILE_VERSION_V4 &&
        version != SUSAMUNE_GHOST_FILE_VERSION_V5 &&
        version != SUSAMUNE_GHOST_FILE_VERSION_V6 &&
        version != SUSAMUNE_GHOST_FILE_VERSION_V7 &&
        version != SUSAMUNE_GHOST_FILE_VERSION_V8 &&
        version != SUSAMUNE_GHOST_FILE_VERSION_V9 &&
         version != SUSAMUNE_GHOST_FILE_VERSION_V10) return false;
    const u8 yoshi = static_cast<u8>(
        (packed >> SUSAMUNE_GHOST_V4_YOSHI_SHIFT) &
        SUSAMUNE_GHOST_V4_YOSHI_MASK);
    const u8 held = static_cast<u8>(
        packed & SUSAMUNE_GHOST_V4_HELD_INDEX_MASK);
    return yoshi <= SUSAMUNE_GHOST_V4_YOSHI_UNKNOWN &&
           (held == 0 || (held <= attachmentCount) ||
            (held == SUSAMUNE_GHOST_V4_HELD_UNKNOWN &&
             (attachmentFlags &
              SUSAMUNE_GHOST_V4_ATTACHMENT_HELD_OVERFLOW)));
}

#pragma clang section text=".foxtrot.text"


#pragma clang section text=""


bool project(const TVec3f &world, int *screenX, int *screenY, int *radius) {
    if (!gpCamera || !screenX || !screenY || !radius) return false;

    Vec cameraPos = {gpCamera->mTranslation.x, gpCamera->mTranslation.y,
                     gpCamera->mTranslation.z};
    Vec cameraUp = {gpCamera->mUpVector.x, gpCamera->mUpVector.y,
                    gpCamera->mUpVector.z};
    Vec cameraTarget = {gpCamera->mTargetPos.x, gpCamera->mTargetPos.y,
                        gpCamera->mTargetPos.z};
    Vec source = {world.x, world.y + 70.0f, world.z};
    Vec viewPosition;
    Mtx view;
    C_MTXLookAt(view, &cameraPos, &cameraUp, &cameraTarget);
    PSMTXMultVec(view, &source, &viewPosition);

    const f32 depth = -viewPosition.z;
    const f32 fovy = gpCamera->mProjectionFovy;
    const f32 aspect = gpCamera->mProjectionAspect;
    if (depth < gpCamera->mProjectionNear || depth > gpCamera->mProjectionFar ||
        fovy < 1.0f || fovy > 170.0f ||
        aspect < 0.5f || aspect > 2.0f) {
        return false;
    }

    const f32 cot = 1.0f / tanf(fovy * 0.00872664626f);
    const f32 ndcX = viewPosition.x * cot / (aspect * depth);
    const f32 ndcY = viewPosition.y * cot / depth;
    if (ndcX < -1.1f || ndcX > 1.1f || ndcY < -1.1f || ndcY > 1.1f) {
        return false;
    }

    *screenX = static_cast<int>((ndcX * 0.5f + 0.5f) * 640.0f);
    *screenY = static_cast<int>((0.5f - ndcY * 0.5f) * 480.0f);
    int r = static_cast<int>(45.0f * cot * 240.0f / depth);
    if (r < 6) r = 6;
    if (r > 22) r = 22;
    *radius = r;
    return true;
}

void drawMarker(Menu *menu, const TVec3f &position, bool secondary,
                u8 alpha) {
    int x;
    int y;
    int r;
    if (!project(position, &x, &y, &r)) return;

    static const s16 octagon[16] = {
         0, -10,  7, -7, 10,  0,  7,  7,
         0,  10, -7,  7,-10,  0, -7, -7,
    };
    static const s16 diamond[8] = {0, -10, 10, 0, 0, 10, -10, 0};
    const s16 *unit = secondary ? diamond : octagon;
    const int count = secondary ? 4 : 8;
    s16 xy[16];
    for (int i = 0; i < count; i++) {
        xy[i * 2] = static_cast<s16>(x + unit[i * 2] * r / 10);
        xy[i * 2 + 1] = static_cast<s16>(
            y + unit[i * 2 + 1] * r / 10);
    }

    const u8 fillAlpha = alpha == 255
        ? 255 : static_cast<u8>(alpha >> (secondary ? 3 : 2));
    const JUtility::TColor fill = secondary
        ? JUtility::TColor(30, 155, 205, fillAlpha)
        : JUtility::TColor(70, 210, 255, fillAlpha);
    const JUtility::TColor line = secondary
        ? JUtility::TColor(190, 250, 255, alpha)
        : JUtility::TColor(110, 235, 255, alpha);
    menu->fillPoly(xy, count, fill);
    menu->strokePoly(xy, count, line);
    if (secondary) {
        menu->drawText("2", x - 4, y - 7, 12, 12,
                       JUtility::TColor(230, 255, 255, alpha));
    }
}

void drawObserverPath(Menu *menu, const Track &track, u16 index, bool secondary) {
    if (!track.valid || index >= track.segmentCount || !sLiveRouteValid) return;
    const Segment &segment = track.segments[index];
    if (!segmentRouteEquals(segment, sLiveArea, sLiveEpisode, sLiveParentEpisode,
                            sLiveRouteParentArea, sLiveRouteFlags) ||
        segment.firstSample >= track.count ||
        segment.sampleCount > track.count - segment.firstSample) return;
    GhostPath::draw(menu, track.samples + segment.firstSample,
                    segment.sampleCount, secondary);
}

}  // namespace

void init() {
    GhostVisualProvider::stopActive();
    memset(reinterpret_cast<void *>(SUSAMUNE_GHOST_TRACKS_PPC_BASE), 0, 3 * sizeof(Track));
    sRecord.samples = reinterpret_cast<Sample *>(SUSAMUNE_GHOST_RECORD_PPC_BASE);
    sPlayback.samples = reinterpret_cast<Sample *>(SUSAMUNE_GHOST_PLAY_PPC_BASE);
    sObserverSecondary.samples = sRecord.samples;
    sRecord.segments = reinterpret_cast<Segment *>(
        SUSAMUNE_GHOST_RECORD_PPC_BASE + kSegmentTableOffset);
    sPlayback.segments = reinterpret_cast<Segment *>(
        SUSAMUNE_GHOST_PLAY_PPC_BASE + kSegmentTableOffset);
    sObserverSecondary.segments = sRecord.segments;
#if IS_EMULATOR
    sRecord.inputs = reinterpret_cast<SusamuneGhostInputSample *>(
        SUSAMUNE_DOLPHIN_GHOST_INPUT_RECORD_PPC_BASE);
    sPlayback.inputs = reinterpret_cast<SusamuneGhostInputSample *>(
        SUSAMUNE_DOLPHIN_GHOST_INPUT_PLAY_PPC_BASE);
#else
    sRecord.inputs = reinterpret_cast<SusamuneGhostInputSample *>(
        SUSAMUNE_GHOST_INPUT_RECORD_PPC_BASE);
    sPlayback.inputs = reinterpret_cast<SusamuneGhostInputSample *>(
        SUSAMUNE_GHOST_INPUT_PLAY_PPC_BASE);
#endif
    sObserverSecondary.inputs = sRecord.inputs;
#if !IS_EMULATOR
    volatile SusamuneGhostStorageMailbox *mailbox =
        SUSAMUNE_GHOST_STORAGE_PPC_PTR;
    DCInvalidateRange((void *)&mailbox->response, 32);
    if (mailbox->response.responseMagic != SUSAMUNE_GHOST_STORAGE_MAGIC ||
        mailbox->response.protocolVersion != SUSAMUNE_GHOST_STORAGE_VERSION) {
        sRecord.inputs = nullptr;
        sPlayback.inputs = nullptr;
        sObserverSecondary.inputs = nullptr;
    }
#endif
    sRecordToken = 0;
    sRecordIdentityToken = 0;
    sPlaybackToken = 0;
    sPlaybackOriginRecordToken = 0;
    sPBTokenSerial = 0;
    clearRecord();
    clearTrack(sPlayback);
    clearTrack(sObserverSecondary);
    bumpPlaybackToken();
    sAttemptSerial = gQFTTimer.attemptSerial();
    sLastSampleQf = 0;
    memset(&sRecordClock, 0, sizeof(sRecordClock));
    sFrameFrozen = false;
    sFrameAssisted = false;
    sPlaybackCursor = 0;
    sPlaybackCursorQf = 0;
    sPlaybackSegment = 0xffff;
    sRecording = false;
    sGhostVisible = false;
    sStageRoutePending = false;
    sPendingHadLiveRoute = false;
    sPendingContinueRecording = false;
    sBoundaryPending = false;
    sLiveRouteValid = false;
    sPlaybackPinned = false;
    sPinRouteCheckPending = false;
    sPlaybackRaceSource = RACE_SOURCE_NONE;
    sPlaybackRaceToken = 0;
    clearRaceContext();
    sClockPhase = CLOCK_UNAVAILABLE;
    sClockObservations = 0;
    sClockLastQf = 0;
    sClockEpochStartQf = 0;
    sPendingPreviousClockQf = 0;
    sGhostYaw = 0;
    sGhostAnimationId = 0;
    sGhostAnimationPhase = 0;
    sGhostHeldObjectId = 0;
    sGhostHeldNameKey = 0;
    sGhostYoshi = SUSAMUNE_GHOST_V4_YOSHI_NONE;
    sGhostIdSerial = 0;
    resetObserverRuntime();
}

void onStageSetup(TMarDirector *director) {
    GhostCamera::onStageSetup();
    sObserverCleanupWarp = false;
    if (sObserverPhase == OBSERVER_WARPING_ONE ||
        sObserverPhase == OBSERVER_WARPING_TWO) {
        // The old actor lived in the stage heap that setupObjects just freed.
        releaseObserverMario(false);
        sObserverStageReady = director != nullptr;
        sObserverStageAnchorQf = -1;
        sObserverClockReady = false;
        sAttemptSerial = gQFTTimer.attemptSerial();
        sRecording = false;
        sStageRoutePending = false;
        sLiveRouteValid = false;
        sClockPhase = CLOCK_UNAVAILABLE;
        sGhostVisible = false;
        sSecondaryGhostVisible = false;
        if (director) {
            updateObserverVisual(sObserverBaseQf);
            bindObserverMario();
        }
        return;
    }
    if (sObserverPhase == OBSERVER_ACTIVE_ONE ||
        sObserverPhase == OBSERVER_ACTIVE_TWO) {
        const bool two = observerHasTwo();
        releaseObserverMario(false);
        const u16 next = static_cast<u16>(sObserverPrimarySegment + 1);
        const Segment *expectedSegment = director &&
                next < sPlayback.segmentCount
            ? &sPlayback.segments[next] : nullptr;
        // The parent-episode flag can settle after setupObjects(). Match only
        // stable scene identity here; WARPING validates the exact tuple at QFT.
        const bool expected = expectedSegment &&
            director->mAreaID == expectedSegment->routeArea &&
            director->mEpisodeID == expectedSegment->routeEpisode &&
            routeParentArea(director->mAreaID) ==
                expectedSegment->routeParentArea;
        if (expected) {
            const s32 continuedOffset = sObserverQfOffset;
            sObserverPrimarySegment = next;
            if (configureObserverSegment()) {
                sObserverQfOffset = continuedOffset;
                sObserverContinuousClock = true;
                sObserverPhase = two ? OBSERVER_WARPING_TWO
                                     : OBSERVER_WARPING_ONE;
                sObserverStageReady = true;
                sObserverRouteValidated = false;
                sAttemptSerial = gQFTTimer.attemptSerial();
                sRecording = false;
                sStageRoutePending = false;
                sLiveRouteValid = false;
                sClockPhase = CLOCK_UNAVAILABLE;
                sObserverExitArmed = false;
                bindObserverMario();
                return;
            }
        }
        stopAll();
        sAttemptSerial = gQFTTimer.attemptSerial();
        if (gMenu) gMenu->toast("Observer stopped: unexpected stage change");
    }
    if (!director) {
        clearRecord();
        if (!sPlaybackPinned) {
            clearTrack(sPlayback);
            bumpPlaybackToken();
        }
        sRecording = false;
        sGhostVisible = false;
        sStageRoutePending = false;
        sPendingHadLiveRoute = false;
        sPendingContinueRecording = false;
        sLiveRouteValid = false;
        sClockPhase = CLOCK_UNAVAILABLE;
        return;
    }
    const bool continueUnsettledBoundary =
        sBoundaryPending && sRecording && sRecord.valid;
    if (sBoundaryPending) {
        rollbackBoundarySegment();
        sBoundaryPending = false;
        sRecording = continueUnsettledBoundary;
    }
    sPendingHadLiveRoute = sLiveRouteValid;
    sPendingPreviousClockQf = sClockLastQf;
    // Preserve the settled prefix while the next director reveals whether
    // this is a restart or another segment on the same absolute QFT timeline.
    sPendingContinueRecording = continueUnsettledBoundary ||
        (sRecording && sRecord.valid && sClockPhase == CLOCK_ACTIVE);
    sRecording = false;
    // Route flags can still be rewritten while setupObjects() is finishing.
    // Defer compatibility until QFT makes the loaded stage live: a reset then
    // gets first chance to promote the completed recording.
    sStageRoutePending = true;
    sLiveRouteValid = false;
    sGhostVisible = false;
    sClockPhase = CLOCK_WAIT_STAGE;
}

void frameControl(bool frozen, bool assisted) {
    sFrameFrozen = frozen;
    sFrameAssisted = assisted;
    s32 qf;
    if (!observerRunning() && gQFTTimer.currentQf(&qf)) recordQf(qf);
}

void beforeDirect() {
    if (TMovieDirector *movie = RetailInput::movieDirector()) {
        // Watch is pose playback. Skip movies without feeding its raw exit bind
        // or accepting the movie's later dialogs.
        if (observerRunning() && (movie->mFlags & 1) &&
            movie->mState >= 0 && movie->mState <= 1 &&
            movie->mGamePad == gpApplication.mGamePads[0] && movie->mGamePad)
            movie->mGamePad->mFrameMeaning |= 0x20;
        return;
    }
    TMarDirector *const stage = RetailInput::stageDirector();
    if (!stage || !stage->_260) return;
    if (!observerRunning() || !sObserverStageReady) return;
    if (!sFrameFrozen && sObserverMarioBaselineFinalized && gpMarDirector &&
        gpMarDirector->mCurState != TMarDirector::STATE_NORMAL) {
        // Restore the actor while its stage heap is still alive. A replacement
        // Mario can reuse the same address without reinitialising every flag.
        releaseObserverMario(true);
        return;
    }
    if (sObserverPhase == OBSERVER_ACTIVE_ONE ||
        sObserverPhase == OBSERVER_ACTIVE_TWO) {
        const s32 qf = observerQf(&sObserverPastEnd);
        updateObserverVisual(qf);
    }
    anchorObserverMario();
}

void afterDirect(s32 appState) {
    if (!observerRunning() ||
        !sObserverMarioBaselineFinalized || !sObserverMarioOwned) {
        return;
    }
    // Attribute a Step's elapsed time before the next held frame begins.
    if (appState <= TApplication::CONTEXT_DIRECT_MAIN_LOOP && gpMarDirector &&
        (sFrameFrozen || gpMarDirector->mCurState == TMarDirector::STATE_NORMAL))
        observerQf();
    if (appState > TApplication::CONTEXT_DIRECT_MAIN_LOOP || !gpMarDirector ||
        (!sFrameFrozen &&
         gpMarDirector->mCurState != TMarDirector::STATE_NORMAL)) {
        // direct() can begin teardown on the same frame as the loading-zone
        // hit. Restore before the next director reuses this stage heap.
        releaseObserverMario(true);
    }
}

void update() {
    if (ReplaySession::blocksResults()) {
        sRecording = false;
        sGhostVisible = sSecondaryGhostVisible = false;
        return;
    }
    if (sObserverPhase == OBSERVER_OFF && sObserverCleanupWarp &&
        gSettings.getBool(SETTING_DISABLE_WARPS)) {
        sObserverCleanupWarp = false;
    }
    // A freshly allocated director can reuse the previous director's address
    // before setupObjects() replaces the stage-owned Mario and camera globals.
    if (!RetailInput::stageDirector() || gpMarDirector->_260 == 0) {
        sGhostVisible = false;
        sSecondaryGhostVisible = false;
        return;
    }

    if (sObserverPhase == OBSERVER_PREPARING_ONE ||
        sObserverPhase == OBSERVER_PREPARING_TWO) {
        if (!gMenu || !gMenu->shown()) {
            stopObserver();
            if (gMenu) gMenu->toast("Ghost watch canceled");
            return;
        }
        sGhostVisible = false;
        sSecondaryGhostVisible = false;
        return;
    }
    if (sObserverPhase == OBSERVER_WARPING_ONE ||
        sObserverPhase == OBSERVER_WARPING_TWO) {
        sObserverExitArmed = false;
        gBinds.suppressUntilRelease();
        if (gSettings.getBool(SETTING_DISABLE_WARPS)) {
            endObserver(false, "Ghost watch ended");
            return;
        }
        if (!sObserverStageReady) return;
        if (actionsFastForwardActive()) {
            endObserver(true, "Observer stopped: fast-forward");
            return;
        }
        // QFT becomes readable during GAME_STARTING, before Mario materialises.
        // The file's leading hold defines its first pose through that interval.
        if (!sObserverClockReady) updateObserverVisual(sObserverBaseQf);
        s32 liveQf;
        if (!gQFTTimer.currentQf(&liveQf)) {
            return;
        }
        if (sObserverStageAnchorQf < 0) sObserverStageAnchorQf = liveQf;
        if (!sObserverRouteValidated) {
            if (!observerRouteLoaded()) {
                endObserver(false, "Observer stopped: route load failed");
                return;
            }
            ILing::invalidateForAssist();
            Records::invalidateAttempt();
            sObserverRouteValidated = true;
            return;
        }
        startObserverClock(liveQf);
        return;
    }
    if (sObserverPhase == OBSERVER_ACTIVE_ONE ||
        sObserverPhase == OBSERVER_ACTIVE_TWO) {
        if (gSettings.getBool(SETTING_DISABLE_WARPS)) {
            endObserver(false, "Ghost watch ended");
            return;
        }
        const bool menuOwnsExit = gMenu && (gMenu->shown() ||
            gBinds.wasPressedRaw(BIND_MENU_TOGGLE));
        const u16 exitHeld = static_cast<u16>(
            JUTGamePad::mPadStatus[0].mButton &
            (JUTGamePad::B | JUTGamePad::START));
        if (menuOwnsExit) {
            sObserverExitArmed = false;
        } else if (!sObserverExitArmed) {
            sObserverExitArmed = exitHeld == 0;
        } else if (exitHeld != 0) {
            endObserver(true, "Ghost watch ended");
            gBinds.suppressUntilRelease();
            return;
        }
        if (actionsFastForwardActive()) {
            endObserver(true, "Observer stopped: fast-forward");
            return;
        }
        if (sObserverPastEnd) {
            // A retail loading zone may already own the departure. Let its
            // setup select the next segment instead of replacing that warp.
            const bool hasNext =
                sObserverPrimarySegment + 1 < sPlayback.segmentCount;
            if (!hasNext && sObserverScrubClock) {
                sObserverPaused = true;
                sObserverPastEnd = false;
                return;
            }
            if (hasNext &&
                gpMarDirector->mCurState != TMarDirector::STATE_NORMAL) return;
            if (!advanceObserverSegment()) {
                endObserver(true, "Ghost observer finished");
            }
            return;
        }
        return;
    }

    updateRestoredRecorder();
    s32 qf;
    bool stopped;
    if (!gQFTTimer.currentQf(&qf, &stopped) || !gpMarDirector) {
        sGhostVisible = false;
        return;
    }

    recordQf(qf);

    const u32 serial = gQFTTimer.attemptSerial();
    if (serial != sAttemptSerial) {
        sAttemptSerial = serial;
        if (sBoundaryPending) rollbackBoundarySegment();
        sBoundaryPending = false;
        sRecording = false;
        sPendingContinueRecording = false;
        beginAttempt(qf, true);
    } else if (sStageRoutePending) {
        captureLiveRoute();
        sStageRoutePending = false;
        const bool hadLiveRoute = sPendingHadLiveRoute;
        sPendingHadLiveRoute = false;
        if (!liveRouteStorable()) {
            sPendingContinueRecording = false;
            sClockPhase = CLOCK_UNAVAILABLE;
            rewindPlayback();
            sGhostVisible = false;
            if (gMenu) gMenu->toast("Ghost: route ended");
            return;
        }
        if (!hadLiveRoute) {
            sPendingContinueRecording = false;
            beginAttempt(qf);
            return;
        }
        // Any no-serial director replacement can be a restart or a route
        // continuation. Keep a tentative segment until QFT proves which.
        sBoundaryPending = true;
        sBoundaryPriorQf = sPendingPreviousClockQf;
        sBoundaryBaseSegmentCount = sRecord.segmentCount;
        if (sPendingContinueRecording && sRecord.segmentCount != 0 &&
            sBoundaryPriorQf < static_cast<s32>(sRecord.endQf)) {
            sBoundaryPriorQf = static_cast<s32>(sRecord.endQf);
        }
        prepareClock(qf);
        rewindPlayback();
        if (sPendingContinueRecording) {
            sRecording = true;
            if (!appendSegment() || !startEpochSamples(qf)) {
                // Capacity stops preserve the last valid prefix. Hard sample
                // failures have already invalidated it in appendSample().
                rollbackBoundarySegment();
                sBoundaryPending = false;
                sClockPhase = CLOCK_FINISHED;
            }
        }
        sPendingContinueRecording = false;
        return;
    }

    if (!gpMarioOriginal) {
        if (sRecording) {
            failRecording(RECORD_FAILURE_MARIO,
                          "Ghost: Mario disappeared");
        }
        sGhostVisible = false;
        return;
    }

    if (sRecording && sRecord.sourceProfile == SUSAMUNE_GHOST_HOVERLESS_PROFILE && GhostFludd::hoverEmitted())
        sRecord.runFlags |= SUSAMUNE_GHOST_RUN_ASSISTED;

    if (actionsFastForwardActive()) {
        if (sRecording) {
            sRecording = false;
            sRecord.valid = false;
            sRecord.runFlags |= SUSAMUNE_GHOST_RUN_ASSISTED |
                                SUSAMUNE_GHOST_RUN_FAST_FORWARD_USED;
            sRecord.failure = RECORD_FAILURE_ASSIST;
            bumpRecordToken();
            if (gMenu) gMenu->toast("Ghost recording disabled: fast-forward");
        }
        // A saved race target remains intact, but is hidden while time is
        // advancing faster than the visual reference.
        sGhostVisible = false;
        return;
    }

    if (sClockPhase == CLOCK_UNAVAILABLE || sClockPhase == CLOCK_WAIT_STAGE) {
        sGhostVisible = false;
        return;
    }

    if (sClockPhase == CLOCK_PROVISIONAL) refreshProvisionalRoute();

    if (sBoundaryPending) {
        if (qf < sClockLastQf || qf < sBoundaryPriorQf) {
            rollbackBoundarySegment();
            sBoundaryPending = false;
            sRecording = false;
            beginAttempt(qf, true);
            return;
        }
        sClockLastQf = qf;
        if (sClockObservations != 0xffff) sClockObservations++;
        if (sRecording && !appendSample(qf)) {
            rollbackBoundarySegment();
            sBoundaryPending = false;
            sClockPhase = CLOCK_FINISHED;
            updatePlayback(qf);
            return;
        }

        bool ordered = true;
        if (sRecording && sBoundaryBaseSegmentCount != 0) {
            const Segment *segment = lastSegment(sRecord);
            const Segment &prior =
                sRecord.segments[sBoundaryBaseSegmentCount - 1];
            ordered = segment && segment->sampleCount != 0 &&
                      segment->startQf >= prior.endQf;
        }
        if (stopped && sRecording && !ordered) {
            rollbackBoundarySegment();
            sBoundaryPending = false;
            sRecording = false;
            sClockPhase = CLOCK_FINISHED;
            updatePlayback(qf);
        } else if (stopped) {
            // A stopped QFT is an authoritative attempt end. Do not lose a
            // short final segment merely because its director never settled.
            sBoundaryPending = false;
            sClockPhase = CLOCK_ACTIVE;
            settlePlaybackPin();
            finishRecording(qf, true);
            updatePlayback(qf);
        } else if (ordered &&
                   gpMarDirector->mCurState == TMarDirector::STATE_NORMAL &&
            sClockObservations >= kClockSettleObservations &&
            qf - sClockEpochStartQf >= 8) {
            sBoundaryPending = false;
            sClockPhase = CLOCK_ACTIVE;
            settlePlaybackPin();
            if (sRecording && sRecord.count >= 2) sRecord.valid = true;
            updatePlayback(qf);
        } else {
            updateProvisionalPlayback(qf);
        }
        return;
    }

    if (stopped &&
        (sClockPhase == CLOCK_PROVISIONAL || sClockPhase == CLOCK_ACTIVE)) {
        finishRecording(qf, true);
        updatePlayback(qf);
        return;
    }

    if (qf < sClockLastQf) {
        if (sRecording && sRecord.segmentCount > 1 &&
            sBoundaryBaseSegmentCount > 0 &&
            sBoundaryBaseSegmentCount < sRecord.segmentCount) {
            // A reset can surface after the boundary settle window. Promote
            // only the proven prefix; never rebase it onto the lower clock.
            rollbackBoundarySegment();
            sBoundaryPending = false;
            sRecording = false;
            beginAttempt(qf, true);
            return;
        }
        rebaseClock(qf);
    } else {
        sClockLastQf = qf;
        if (sClockObservations != 0xffff) sClockObservations++;
        if (sRecording) appendSample(qf);
    }

    if (sClockPhase == CLOCK_PROVISIONAL) {
        const bool enoughSamples = !sRecording || sRecord.count >= 2;
        if (gpMarDirector->mCurState == TMarDirector::STATE_NORMAL &&
            sClockObservations >= kClockSettleObservations &&
            qf - sClockEpochStartQf >= 8 &&
            enoughSamples) {
            sClockPhase = CLOCK_ACTIVE;
            settlePlaybackPin();
            if (sRecording) sRecord.valid = true;
        } else {
            // Playback follows the observed QFT while recording keeps its
            // conservative settle window.
            updateProvisionalPlayback(qf);
            return;
        }
    }

    updatePlayback(qf);
}

void draw(Menu *menu) {
    if (!menu || menu->shown() ||
        !displayEnabled()) {
        return;
    }
    if (observerRunning() && sObserverStageReady && !observerLoading() &&
        gSettings.getBool(SETTING_GHOST_PATH)) {
        if (GhostVisualProvider::active()) {
            for (unsigned runner = 0; runner < (observerHasTwo() ? 2u : 1u); ++runner) {
                const SusamuneGhostPoseSample *points;
                unsigned count;
                if (GhostVisualProvider::path(providerQuery(runner, sVisualQf, true), points, count))
                    GhostPath::draw(menu, points, count, runner != 0);
            }
        } else {
            drawObserverPath(menu, sPlayback, sObserverPrimarySegment, false);
            if (observerHasTwo())
                drawObserverPath(menu, sObserverSecondary, sObserverSecondarySegment, true);
        }
    }
    GhostScrub::drawStatus(menu);

    static const u8 opacity[] = {64, 128, 192, 255};
    u8 choice = gSettings.get(SETTING_GHOST_OPACITY);
    if (choice >= sizeof(opacity)) choice = 1;
    const u8 alpha = opacity[choice];
    if (sGhostVisible && !GhostModel::submitted(false)) {
        drawMarker(menu, sGhostPosition, false, alpha);
    }
    if (sSecondaryGhostVisible && !GhostModel::submitted(true)) {
        drawMarker(menu, sSecondaryGhostPosition, true, alpha);
    }
    if ((sGhostVisible && playbackIsTas()) ||
        (sSecondaryGhostVisible && playbackIsTas(true))) {
        menu->drawText("TAS ghost", 460, 198, 12, 12,
                       JUtility::TColor(255, 210, 120, 255));
    }
}

void invalidateForAssist() {
    if (!sRecording || sAttemptSerial != gQFTTimer.attemptSerial() ||
        (sRecord.runFlags & SUSAMUNE_GHOST_RUN_TAS)) return;
    sRecord.runFlags |= SUSAMUNE_GHOST_RUN_ASSISTED | SUSAMUNE_GHOST_RUN_TAS;
    bumpRecordToken();
}

void captureInput(const SusamunePracticeInput &input) {
    if (ReplaySession::blocksResults()) return;
    if (sRecord.sourceProfile == SUSAMUNE_GHOST_HOVERLESS_PROFILE && GhostFludd::hoverEmitted())
        sRecord.runFlags |= SUSAMUNE_GHOST_RUN_ASSISTED;
    s32 qf;
    if (observerStatsSuppressed() || !sRecord.inputs ||
        (!sRecording && !sRecord.completed) ||
        sAttemptSerial != gQFTTimer.attemptSerial() ||
        input.flags != 0 || !gQFTTimer.currentQf(&qf) || qf < 0 ||
        sRecord.segmentCount == 0) return;
    qf = SusamuneGhostClockMap(&sRecordClock, qf);
    if (sRecord.inputCount &&
        inputQf(sRecord, sRecord.inputCount - 1) >= (u32)qf) return;
    if (!sRecording && (u32)qf != sRecord.endQf) return;
    if (sRecord.formatVersion >= SUSAMUNE_GHOST_FILE_VERSION_V8)
        GhostCamera::capture(sRecord.samples, static_cast<u32>(qf),
                             static_cast<u8>(sRecord.segmentCount - 1));
    if (sRecord.inputCount >= SusamuneGhostInputLimit(sRecord.formatVersion)) {
        sRecord.teachingFlags |= SUSAMUNE_GHOST_TEACHING_INPUT_TRUNCATED;
        return;
    }
    if (static_cast<u32>(qf) < sRecord.startQf ||
        static_cast<u32>(qf) - sRecord.startQf > SusamuneGhostDurationLimit(sRecord.formatVersion)) {
        sRecord.teachingFlags |= SUSAMUNE_GHOST_TEACHING_INPUT_TRUNCATED; return;
    }
    SusamuneGhostInputSample &sample = inputAt(sRecord, sRecord.inputCount++);
    sample.qf = (u32)qf;
    sample.input = input;
    if (sRecord.formatVersion >= SUSAMUNE_GHOST_FILE_VERSION_V10) {
        const u32 relative = static_cast<u32>(qf) - sRecord.startQf;
        GhostSimulation::CameraObservation camera; GhostSimulation::readCamera(camera);
        u8 *p = reinterpret_cast<u8 *>(&sample);
        p[0] = relative >> 8; p[1] = relative;
        const u16 yaw = camera.valid ? static_cast<u16>(camera.yaw) : 0;
        p[2] = yaw >> 8; p[3] = yaw;
        p[15] = ((relative >> 9) & 0x80u) | (camera.valid ? camera.mode : 0x7fu);
        GhostContext::input(sRecord.samples, sRecord.segmentCount - 1, qf, sRecord.inputCount - 1);
    }
    if (sRecord.formatVersion >= SUSAMUNE_GHOST_FILE_VERSION_V6) {
        SusamuneGhostFluddSample &visual =
            *reinterpret_cast<SusamuneGhostFluddSample *>(&sample + 1);
        GhostFludd::capture(visual);
        // A restored legacy recording keeps its original file semantics.
        if (sRecord.formatVersion == SUSAMUNE_GHOST_FILE_VERSION_V6) {
            if (visual.mode & SUSAMUNE_GHOST_VISUAL_YOSHI) memset(&visual, 0, sizeof(visual));
            else visual.mode &= ~SUSAMUNE_GHOST_FLUDD_BURST;
        }
    }
}

void captureSplit(u16 route, u8 endpoint, s32 absoluteQf) {
    if (observerStatsSuppressed() || (!sRecording && !sRecord.completed) ||
        sAttemptSerial != gQFTTimer.attemptSerial() || absoluteQf < 0 ||
        route >= SUSAMUNE_SPLIT_STATS_ROUTE_COUNT ||
        endpoint != sRecord.splitCount ||
        endpoint >= SUSAMUNE_GHOST_SPLIT_MAX_COUNT) return;
    absoluteQf = SusamuneGhostClockMap(&sRecordClock, absoluteQf);
    if (sRecord.splitCount &&
        (sRecord.splits[0].route != route ||
         sRecord.splits[sRecord.splitCount - 1].qf > (u32)absoluteQf)) return;
    SusamuneGhostSplitSample &split = sRecord.splits[sRecord.splitCount++];
    split.qf = (u32)absoluteQf;
    split.schema = SUSAMUNE_SPLIT_STATS_SCHEMA_HASH;
    split.route = route;
    split.endpoint = endpoint;
    split.reserved = 0;
    GhostRecording::split(sRecordToken, split);
}

bool comparisonSplit(u16 route, u8 endpoint, s32 *out) {
    if (!out || sRaceSplitSerial != gQFTTimer.attemptSerial() ||
        sRaceSplitPlaybackToken != sPlaybackToken) return false;
    // A stage's route flags can settle after the first QFT observation.
    if (!sRaceSplitCount) captureComparisonSplits();
    if (endpoint >= sRaceSplitCount) return false;
    const SusamuneGhostSplitSample &split = sRaceSplits[endpoint];
    if (split.route != route || split.endpoint != endpoint ||
        split.schema != SUSAMUNE_SPLIT_STATS_SCHEMA_HASH) return false;
    *out = (s32)split.qf;
    return true;
}

static const SusamuneGhostInputSample *playbackObservation(
        const Track &track, u16 segmentIndex, s32 qf) {
    if (!track.inputs || !track.inputCount || qf < 0 ||
        segmentIndex >= track.segmentCount) return nullptr;
    u32 lo = 0, hi = track.inputCount;
    while (lo < hi) {
        const u32 mid = lo + (hi - lo) / 2;
        if (inputQf(track, mid) <= (u32)qf) lo = mid + 1;
        else hi = mid;
    }
    if (!lo || inputQf(track, lo - 1) <
                    track.segments[segmentIndex].startQf) return nullptr;
    if ((track.teachingFlags & SUSAMUNE_GHOST_TEACHING_INPUT_TRUNCATED) &&
        (u32)qf > inputQf(track, track.inputCount - 1)) return nullptr;
    return &inputAt(track, lo - 1);
}

static bool playbackInput(const Track &track, u16 segmentIndex,
                          SusamunePracticeInput *out) {
    if (GhostVisualProvider::active())
        return out && GhostVisualProvider::input(&track == &sObserverSecondary ? 1u : 0u, *out);
    const s32 qf = sVisualQf + (&track == &sObserverSecondary ? sObserverSecondaryOffset : 0);
    const SusamuneGhostInputSample *sample = playbackObservation(track, segmentIndex, qf);
    if (!sample || !out) return false;
    *out = sample->input;
    if (track.formatVersion >= SUSAMUNE_GHOST_FILE_VERSION_V10) out->flags = 0;
    return true;
}

static void visualFludd(const Track &track, u16 segmentIndex, VisualState &out, s32 qf) {
    memset(&out.fludd, 0, sizeof(out.fludd));
    out.visualQf = qf < 0 ? 0 : (u32)qf;
    out.recordingToken = observerRunning()
        ? 0x40000000u | sObserverVisualToken : sPlaybackToken;
    if (track.formatVersion < SUSAMUNE_GHOST_FILE_VERSION_V6) return;
    const SusamuneGhostInputSample *sample = playbackObservation(track, segmentIndex, qf);
    if (sample) memcpy(&out.fludd, sample + 1, sizeof(out.fludd));
}

bool playbackInputState(unsigned runner, SusamunePracticeInput *out) {
    if (!out || runner > 1) return false;
    if (GhostWorldRuntime::active())
        return runner == 0 && GhostWorldRuntime::inputState(*out);
    if (GhostVisualProvider::active()) return GhostVisualProvider::input(runner, *out);
    if (runner && !observerHasTwo()) return false;
    return runner ? playbackInput(sObserverSecondary, sObserverSecondarySegment, out)
                  : playbackInput(sPlayback, sPlaybackSegment, out);
}

void drawInputs(Menu *menu, u8 mode) {
    const bool worldReplay = GhostWorldRuntime::active();
    if (!menu || menu->shown() || !mode ||
        (!worldReplay && (!sGhostVisible || !displayEnabled()))) return;
    const int panelY = 218;
    SusamunePracticeInput input;
    if (playbackInputState(0, &input)) {
        gInputDisplay.drawSnapshot(menu, input, 460, panelY, 65,
            (worldReplay ? ReplaySession::sourceTas() : playbackIsTas()) ? "TAS 1" : "Ghost 1");
    } else if (!worldReplay) {
        menu->drawText("Inputs not recorded", 438, panelY, 12, 12,
                       JUtility::TColor(220, 240, 255, 255));
    }
    if (mode < 2) return;
    if (observerHasTwo()) {
        if (sSecondaryGhostVisible &&
            playbackInputState(1, &input))
            gInputDisplay.drawSnapshot(menu, input, 330, panelY, 65,
                                       playbackIsTas(true) ? "TAS 2" : "Ghost 2");
    } else if (!worldReplay && !observerActive()) {
        const PADStatus &raw = JUTGamePad::mPadStatus[0];
        input.buttons = raw.mButton;
        input.stickX = (s8)raw.mStickX;
        input.stickY = (s8)raw.mStickY;
        input.substickX = (s8)raw.mSubStickX;
        input.substickY = (s8)raw.mSubStickY;
        input.triggerL = raw.mTriggerLeft;
        input.triggerR = raw.mTriggerRight;
        input.analogA = raw.mAnalogA;
        input.analogB = raw.mAnalogB;
        input.error = (s8)raw.mCurError;
        input.flags = 0;
        gInputDisplay.drawSnapshot(menu, input, 330, panelY, 65, "You");
    }
}

bool exportLatest(void *out, u32 capacity, u8 sourceProfile,
                  const char *profileName, u32 *outSize, u32 *outRecordToken) {
    (void)out;(void)capacity;(void)sourceProfile;(void)profileName;
    if(outSize)*outSize=0;if(outRecordToken)*outRecordToken=0;
    return false;
}

bool inspectFile(const void *data, u32 size, SusamuneGhostFileHeader *header) {
    (void)data;(void)size;if(header)*header={};return false;
}

bool importPlayback(const void *data, u32 size, bool imported) {
    (void)data;(void)size;(void)imported;return false;
}

bool beginObserverPreparation(bool twoGhosts) {
    TMarioGamePad *pad = gpApplication.mGamePads[0];
    if (!gpMarDirector || !pad || !LevelWarp::readyForOnlineRace() ||
        gSettings.getBool(SETTING_DISABLE_WARPS)) {
        return false;
    }
    captureLiveRoute();
    if (!liveRouteStorable() || hasUnsavedPB()) {
        return false;
    }

    stopAll();
    sAttemptSerial = gQFTTimer.attemptSerial();
    captureLiveRoute();
    GhostRecordingNative::prepareWatch(twoGhosts);
    sObserverPhase = twoGhosts ? OBSERVER_PREPARING_TWO
                               : OBSERVER_PREPARING_ONE;
    return true;
}

bool importObserverTrack(const void *data, u32 size, bool secondary) {
    (void)data;(void)size;(void)secondary;return false;
}

bool observerTrackReady(bool secondary) {
    if (!secondary && GhostRecordingNative::watchReady()) return true;
    return secondary ? sObserverSecondaryReady : sObserverPrimaryReady;
}

bool startObserver() {
    if (GhostRecordingNative::watchReady()) {
        if (!GhostRecordingNative::startWatch()) return false;
        sObserverPhase = OBSERVER_OFF;
        sGhostVisible = sSecondaryGhostVisible = false;
        sRecording = false;
        gBinds.suppressUntilRelease();
        return true;
    }
    const bool two = sObserverPhase == OBSERVER_PREPARING_TWO;
    if ((sObserverPhase != OBSERVER_PREPARING_ONE && !two) ||
        !sObserverPrimaryReady || (two && !sObserverSecondaryReady) ||
        !gpMarDirector ||
        gpMarDirector->mCurState != TMarDirector::STATE_NORMAL ||
        actionsFastForwardActive() ||
        gSettings.getBool(SETTING_DISABLE_WARPS) ||
        !observerRoutesCompatible()) {
        return false;
    }
    ++sObserverVisualToken;
    sObserverPrimarySegment = 0;
    if (!configureObserverSegment()) return false;
    StageLoader::cancel();
    sClockPhase = CLOCK_UNAVAILABLE;
    ILing::invalidateForAssist();
    Records::invalidateAttempt();
    armObserverSegment();
    gBinds.suppressUntilRelease();
    return true;
}

void stopObserver() {
    GhostRecordingNative::cancelWatch();
    if (GhostWorldRuntime::active()) GhostWorldRuntime::stop();
    endObserver(observerRunning(), nullptr);
}

bool takeoverMomentum(TVec3f &velocity) {
    velocity.set(0, 0, 0);
    if (sPlaybackSegment >= sPlayback.segmentCount || sGhostYoshi || sGhostHeldObjectId) return false;
    const Segment &segment = sPlayback.segments[sPlaybackSegment];
    if (segment.sampleCount < 2 || sPlaybackCursor < segment.firstSample ||
        sPlaybackCursor >= segment.firstSample + segment.sampleCount) return false;
    const u32 first = sPlaybackCursor + 1 < segment.firstSample + segment.sampleCount ?
        sPlaybackCursor : sPlaybackCursor - 1;
    const Sample &a = sPlayback.samples[first], &b = sPlayback.samples[first + 1];
    if (!b.deltaQf || b.deltaQf > 8) return false;
    const f32 scale = 4.0f / b.deltaQf;
    velocity.set((samplePosition(sampleX(b)) - samplePosition(sampleX(a))) * scale,
                 (samplePosition(sampleY(b)) - samplePosition(sampleY(a))) * scale,
                 (samplePosition(sampleZ(b)) - samplePosition(sampleZ(a))) * scale);
    if (velocity.x * velocity.x + velocity.y * velocity.y + velocity.z * velocity.z > 160000.0f) {
        velocity.set(0, 0, 0); return false;
    }
    return true;
}

u32 takeoverStatus(u16 animation, bool grounded, bool momentum) {
    if (momentum) {
        if (grounded && (animation == 0x48 || animation == 0x72)) return TMario::STATE_RUNNING;
        if (!grounded) {
            // Retail MarioJump handlers, not the misleading legacy enum labels.
            if (animation == 0x4d) return TMario::STATE_JUMP;
            if (animation == 0x50 || animation == 0x4c) return TMario::STATE_D_JUMP;
            if (animation == 0x6f) return TMario::STATE_TRIPLE_J;
            if (animation == 0xcb) return TMario::STATE_WALLJUMP;
            if (animation == 0xbf) return TMario::STATE_SIDE_FLIP;
            if (animation == 0xf7) return TMario::STATE_BACK_FLIP;
            if (animation == 0xf6) return 0x00000888u; // broad jump
            if (animation == 0x10f) return 0x02000889u; // rotating broad jump
        }
    }
    return grounded ? TMario::STATE_IDLE : TMario::STATE_FALL;
}

bool takeOverObserver() {
    if (GhostVisualProvider::active()) return false;
    if (!observerRunning() || observerHasTwo() || observerLoading() ||
        !sObserverStageReady || !sGhostVisible || !gpMap || !gpMarDirector ||
        gpMarDirector->mCurState != TMarDirector::STATE_NORMAL ||
        !sObserverMarioOwned || !sObserverMarioBaselineFinalized ||
        sObserverMario != gpMarioOriginal) return false;
    if (!PracticeSession::manualPaused() && !PracticeSession::requestPauseToggle(true))
        return false;
    const TVec3f position = sGhostPosition;
    const s16 yaw = sGhostYaw;
    const u16 animation = sGhostAnimationId;
    TVec3f velocity;
    const bool momentum = takeoverMomentum(velocity);
    if (PracticeSession::freeCamera()) PracticeSession::requestFreeCameraToggle();
    endObserver(false, nullptr);
    TMario *mario = gpMarioOriginal;
    // This misleadingly named retail bit suppresses model entry when set.
    mario->mAttributes.mIsVisible = false;
    mario->mPrevAttributes.mIsVisible = false;
    if (gpCamera) {
        Vec move = {0.0f, position.y - mario->mTranslation.y, 0.0f};
        gpCamera->addMoveCameraAndMario(move);
    }
    // Nearby poses estimate velocity; collision and world state remain live.
    mario->dropObject();
    mario->mTranslation = mario->mLastPosition = position;
    mario->mLastPos = mario->mLastGroundedPos = position;
    mario->mAngle.y = mario->mModelAngleY = yaw;
    mario->mAccelerationDirection = yaw;
    mario->mSpeed.set(0.0f, 0.0f, 0.0f);
    mario->mPrevSpeed = mario->mSpeed;
    mario->mForwardSpeed = 0.0f;
    mario->mWallTriangle = mario->mRoofTriangle = gpMap->getIllegalCheckData();
    mario->mFloorBelow = gpMap->checkGround(position.x, position.y + 25.0f,
                                           position.z, &mario->mFloorTriangle);
    const bool grounded = position.y >= mario->mFloorBelow && position.y <= mario->mFloorBelow + 4.0f;
    const u32 state = takeoverStatus(animation, grounded, momentum);
    mario->changePlayerStatus(state, 0, false);
    const bool matched = state != TMario::STATE_IDLE && state != TMario::STATE_FALL;
    if (momentum) {
        if (grounded) velocity.y = 0;
        mario->mSpeed = mario->mPrevSpeed = velocity;
        const f32 angle = yaw * 0.00009587379924f;
        const f32 forward = velocity.x * sinf(angle) + velocity.z * cosf(angle);
        mario->mForwardSpeed = forward;
    }
    mario->setAnimation(matched ? animation : grounded ? TMario::ANIMATION_IDLE : TMario::ANIMATION_FALL, 1.0f);
    GhostModel::refreshPlayerAfterTakeover();
    PracticeSession::stripShortcutButtons(JUTGamePad::START | JUTGamePad::A);
    gBinds.suppressUntilRelease();
    return true;
}

bool displayEnabled() {
    return observerRunning() || gSettings.getBool(SETTING_GHOST_DISPLAY);
}

bool observerActive() {
    return observerRunning();
}

static u16 observerSegmentAt(const Track &track, u32 qf) {
    for (u16 i = 0; i < track.segmentCount; ++i) {
        const Segment &segment = track.segments[i];
        if (segment.sampleCount && qf >= segment.startQf && qf <= segment.endQf)
            return i;
    }
    return 0xffff;
}

bool observerTimeline(ObserverTimeline *out) {
    if (!out || !observerRunning() || !sPlayback.valid) return false;
    out->startQf = sPlayback.startQf;
    out->endQf = sPlayback.endQf;
    out->qf = observerQf();
    out->secondaryStartQf = sObserverSecondary.startQf;
    out->secondaryOffsetQf = sObserverSecondaryOffset;
    out->splitCount = sPlayback.splitCount;
    out->alignedSplit = sObserverAlignedSplit;
    out->paused = sObserverPaused;
    return true;
}

bool observerSplit(u8 index, ObserverSplit *out) {
    if (!out || !observerRunning() || index >= sPlayback.splitCount) return false;
    const SusamuneGhostSplitSample &a = sPlayback.splits[index];
    out->qf = a.qf;
    out->schema = a.schema;
    out->route = a.route;
    out->endpoint = a.endpoint;
    out->secondaryQf = 0;
    out->comparable = false;
    if (!observerHasTwo()) return true;
    for (u8 i = 0; i < sObserverSecondary.splitCount; ++i) {
        const SusamuneGhostSplitSample &b = sObserverSecondary.splits[i];
        if (!a.schema || a.schema != b.schema || a.route != b.route ||
            a.endpoint != b.endpoint) continue;
        const u16 first = observerSegmentAt(sPlayback, a.qf);
        const u16 second = observerSegmentAt(sObserverSecondary, b.qf);
        if (first == 0xffff || second != first) continue;
        const Segment &scene = sPlayback.segments[first];
        if (!segmentRouteEquals(sObserverSecondary.segments[second],
            scene.routeArea, scene.routeEpisode, scene.routeVariant,
            scene.routeParentArea, scene.routeFlags)) continue;
        out->secondaryQf = b.qf;
        out->comparable = true;
        break;
    }
    return true;
}

bool observerPause(bool paused) {
    if (!observerRunning() || observerLoading() || !gpMarDirector) return false;
    observerQf();
    sObserverRawQf = gpMarDirector->unk5C;
    sObserverScrubClock = true;
    sObserverPaused = paused;
    sObserverPastEnd = false;
    return true;
}

bool observerPaused() {
    return observerRunning() && !observerLoading() && sObserverPaused;
}

bool observerSeek(u32 qf) {
    if (!observerRunning() || observerLoading() || !sObserverStageReady ||
        !gpMarDirector || gpMarDirector->mCurState != TMarDirector::STATE_NORMAL)
        return false;
    if (qf < sPlayback.startQf) qf = sPlayback.startQf;
    if (qf > sPlayback.endQf) qf = sPlayback.endQf;
    u16 segment = observerSegmentAt(sPlayback, qf);
    if (segment == 0xffff) {
        // A stage-loading gap has no poses. Snap forward to its next scene.
        for (u16 i = 0; i < sPlayback.segmentCount; ++i) {
            if (sPlayback.segments[i].startQf > qf) {
                segment = i;
                qf = sPlayback.segments[i].startQf;
                break;
            }
        }
    }
    if (segment == 0xffff || !observerPause(true)) return false;
    ++sObserverVisualToken;
    sObserverLastQf = qf;
    if (segment != sObserverPrimarySegment) {
        sObserverPrimarySegment = segment;
        if (!configureObserverSegment()) return false;
        sObserverSeekQf = qf;
        armObserverSegment();
    } else {
        updateObserverVisual(qf);
        anchorObserverMario();
    }
    return true;
}

bool observerAlignSplit(u8 index) {
    ObserverSplit split;
    if (!observerSplit(index, &split) || !split.comparable || observerLoading() ||
        !sObserverStageReady || !gpMarDirector ||
        gpMarDirector->mCurState != TMarDirector::STATE_NORMAL)
        return false;
    const u16 segment = observerSegmentAt(sPlayback, split.qf);
    const s32 offset = static_cast<s32>(split.secondaryQf) - static_cast<s32>(split.qf);
    u32 baseQf, endQf;
    // Reject an unusable pair before changing either cursor or its clock.
    if (!observerSegmentRange(segment, offset, &baseQf, &endQf) ||
        !observerPause(true)) return false;
    const bool changedScene = segment != sObserverPrimarySegment;
    sObserverPrimarySegment = segment;
    sObserverSecondaryOffset = offset;
    configureObserverSegment();
    ++sObserverVisualToken;
    sObserverAlignedSplit = index;
    sObserverLastQf = split.qf;
    sObserverSeekQf = -1;
    if (changedScene) {
        sObserverSeekQf = split.qf;
        armObserverSegment();
    } else {
        updateObserverVisual(split.qf);
        anchorObserverMario();
    }
    return true;
}

bool observerClearAlignment() {
    if (!observerRunning() || observerLoading() || !observerPause(true)) return false;
    const u32 qf = observerQf();
    sObserverSecondaryOffset = 0;
    sObserverAlignedSplit = -1;
    configureObserverSegment();
    return observerSeek(qf);
}

bool observerVisualAt(unsigned runner, u32 qf, VisualState *out) {
    if (!out || runner > 1 || !observerRunning() || !sObserverStageReady ||
        (runner && !observerHasTwo())) return false;
    if (GhostVisualProvider::active()) {
        if (qf > 0x7fffffffu) return false;
        GhostVisualProvider::Frame frame;
        if (!GhostVisualProvider::historical(providerQuery(runner, static_cast<s32>(qf), true, true), frame)) return false;
        *out = frame.visual;
        return out->visible;
    }
    const Track &track = runner ? sObserverSecondary : sPlayback;
    const u16 segment = runner ? sObserverSecondarySegment : sObserverPrimarySegment;
    static u32 cursors[2], tokens[2];
    static s32 cursorQfs[2];
    if (tokens[runner] != sObserverVisualToken) {
        cursors[runner] = 0;
        cursorQfs[runner] = 0;
        tokens[runner] = sObserverVisualToken;
    }
    TVec3f position;
    if (!sampleObserverTrack(track, segment, qf, &cursors[runner], &cursorQfs[runner], &position,
        &out->yaw, &out->animationId, &out->animationPhase, &out->yoshi,
        &out->heldObjectId, &out->heldNameKey)) return false;
    out->x = position.x; out->y = position.y; out->z = position.z;
    out->visible = true;
    visualFludd(track, segment, *out, qf);
    return true;
}
#pragma clang section text=""

bool recordedCameraAvailable() {
    if (GhostVisualProvider::active()) return GhostVisualProvider::cameraAvailable();
    if (!sPlayback.valid || sPlayback.formatVersion < SUSAMUNE_GHOST_FILE_VERSION_V8)
        return false;
    return GhostCamera::prefixSize(sPlayback.samples) > SUSAMUNE_GHOST_CAMERA_HEADER_SIZE;
}

bool recordedCameraView(GhostCamera::View *out) {
    if (GhostVisualProvider::active()) {
        if (!out || !observerRunning() || !sObserverStageReady) return false;
        return GhostVisualProvider::camera(providerQuery(0, observerQf(), true), *out);
    }
    if (!observerRunning() || !sObserverStageReady ||
        sObserverPrimarySegment >= sPlayback.segmentCount || !recordedCameraAvailable())
        return false;
    const s32 qf = observerQf();
    return qf >= 0 && GhostCamera::evaluate(sPlayback.samples, static_cast<u32>(qf),
        static_cast<u8>(sObserverPrimarySegment), out);
}

bool observerStatsSuppressed() {
    return observerRunning() || sObserverCleanupWarp;
}

bool observerCleanupPending() {
    return sObserverCleanupWarp;
}

bool observerPreparing() {
    return sObserverPhase == OBSERVER_PREPARING_ONE ||
           sObserverPhase == OBSERVER_PREPARING_TWO;
}

int observerGhostCount() {
    if (sObserverPhase == OBSERVER_WARPING_TWO ||
        sObserverPhase == OBSERVER_ACTIVE_TWO) return 2;
    if (sObserverPhase == OBSERVER_WARPING_ONE ||
        sObserverPhase == OBSERVER_ACTIVE_ONE) return 1;
    return 0;
}

bool observerLoading() {
    return sObserverPhase == OBSERVER_WARPING_ONE ||
           sObserverPhase == OBSERVER_WARPING_TWO;
}

int observerVisibleCount() {
    if (!observerRunning()) return 0;
    return (sGhostVisible ? 1 : 0) + (sSecondaryGhostVisible ? 1 : 0);
}

bool playbackInfo(PlaybackInfo *out) {
    if (!out || !sPlayback.valid) return false;
    out->sampleCount = sPlayback.count;
    out->startQf = sPlayback.startQf;
    out->endQf = sPlayback.endQf;
    out->resultQf = sPlayback.resultQf;
    out->routeVariant = sPlayback.parentEpisode;
    out->area = sPlayback.area;
    out->episode = sPlayback.episode;
    out->completed = sPlayback.completed;
    out->pinned = sPlaybackPinned;
    out->runFlags = sPlayback.runFlags;
    return true;
}

bool comparisonDelta(u16 route, u8 endpoint, s32 absoluteQf, s32 *out) {
    s32 target;
    if (!out || absoluteQf < 0 || !comparisonSplit(route, endpoint, &target))
        return false;
    *out = SusamuneGhostClockMap(&sRecordClock, absoluteQf) - target;
    return true;
}

bool playbackIsTas(bool secondary) {
    if (GhostVisualProvider::active())
        return (GhostVisualProvider::runFlags(secondary ? 1u : 0u) & SUSAMUNE_GHOST_RUN_TAS) != 0;
    const Track &track = secondary ? sObserverSecondary : sPlayback;
    return track.valid && (track.runFlags & SUSAMUNE_GHOST_RUN_TAS);
}

bool raceContext(RaceContext *out) {
    if (!out || !sRaceContextValid || !sPlaybackPinned ||
        ((ILing::pbProfile() == 4) != (sPlayback.sourceProfile == SUSAMUNE_GHOST_HOVERLESS_PROFILE)) ||
        sRaceContextPlaybackToken != sPlaybackToken ||
        sRaceContext.source != sPlaybackRaceSource)
        return false;
    *out = sRaceContext;
    return true;
}

bool bindRaceContext(s16 ilEntry, s32 startingPbQf) {
    if (!sRaceContextValid || !sPlaybackPinned ||
        ((ILing::pbProfile() == 4) != (sPlayback.sourceProfile == SUSAMUNE_GHOST_HOVERLESS_PROFILE)) ||
        sRaceContextPlaybackToken != sPlaybackToken ||
        sRaceContext.source != sPlaybackRaceSource ||
        sRaceContext.attemptSerial != gQFTTimer.attemptSerial())
        return false;
    sRaceContext.ilEntry = ilEntry;
    sRaceContext.startingPbQf = startingPbQf;
    return true;
}

#if TIMEWARP_LIVE_RACING
bool renderVisualState(unsigned int runner, VisualState *out) {
    if (ReplaySession::blocksResults()) return false;
    if (const auto *group = LiveRace::groupState()) {
        if (!observerPreparing() && !observerStatsSuppressed())
            return runner + 1 < group->config.players && LiveGhost::visualStateFor(runner, out);
    }
    if (runner > 1 || !out) return false;
    if (runner && !observerPreparing() && !observerStatsSuppressed() &&
        (!GhostVisualProvider::active() || LiveRace::opponentModel() >= 0))
        return LiveGhost::visualState(out);
    return runner ? secondaryVisualState(out) : visualState(out);
}

bool captureLiveVisual(VisualState *out) {
    TMarDirector *director = RetailInput::stageDirector();
    TMario *mario = gpMarioOriginal;
    if (!out || gpApplication.mContext != TApplication::CONTEXT_DIRECT_STAGE ||
        !director || director != gpMarDirector || !director->_260 ||
        !OSIsThreadTerminated(&gSetupThread) ||
        director->mCurState < TMarDirector::STATE_GAME_STARTING ||
        director->mCurState == TMarDirector::STATE_STAGE_EXIT ||
        director->mCurState == TMarDirector::STATE_STAGE_EXIT_2 ||
        gpApplication.mCurrentScene.mAreaID == TGameSequence::AREA_OPTION ||
        director->mAreaID != gpApplication.mCurrentScene.mAreaID ||
        director->mEpisodeID != gpApplication.mCurrentScene.mEpisodeID ||
        !mario || !mario->mModelData || observerPreparing() ||
        observerStatsSuppressed()) return false;

    VisualState state = {};
    const f32 positions[3] = {mario->mTranslation.x, mario->mTranslation.y, mario->mTranslation.z};
    for (unsigned i = 0; i < 3; ++i) {
        union { f32 value; u32 bits; } word = {positions[i]};
        if ((word.bits & 0x7fffffffu) > 0x49742400u) return false;
    }
    if (!captureAnimation(&state.animationId, &state.animationPhase)) return false;
    state.x = mario->mTranslation.x;
    state.y = mario->mTranslation.y;
    state.z = mario->mTranslation.z;
    state.yaw = mario->mModelAngleY;
    state.yoshi = captureYoshiState();
    // The recording helper allocates a descriptor; live observations do not.
    if (const TTakeActor *held = mario->mHeldObject) {
        state.heldObjectId = held->mObjectID;
        state.heldNameKey = held->mKeyCode;
    }
    GhostFludd::capture(state.fludd);
    state.visible = true;
    *out = state;
    return true;
}
#endif

bool visualState(VisualState *out) {
    if (!out) return false;
    if (GhostVisualProvider::active()) {
        *out = {};
        GhostVisualProvider::Frame frame;
        if (!GhostVisualProvider::read(0, frame)) return false;
        *out = frame.visual;
        return true;
    }
    out->x = sGhostPosition.x;
    out->y = sGhostPosition.y;
    out->z = sGhostPosition.z;
    out->yaw = sGhostYaw;
    out->animationId = sGhostAnimationId;
    out->animationPhase = sGhostAnimationPhase;
    out->heldObjectId = sGhostHeldObjectId;
    out->heldNameKey = sGhostHeldNameKey;
    out->yoshi = sGhostYoshi;
    out->visible = sGhostVisible;
    visualFludd(sPlayback, observerRunning() ? sObserverPrimarySegment : sPlaybackSegment, *out, sVisualQf);
    return true;
}

bool secondaryVisualState(VisualState *out) {
    if (!out) return false;
    if (GhostVisualProvider::active()) {
        *out = {};
        GhostVisualProvider::Frame frame;
        if (!GhostVisualProvider::read(1, frame)) return false;
        *out = frame.visual;
        return true;
    }
    out->x = sSecondaryGhostPosition.x;
    out->y = sSecondaryGhostPosition.y;
    out->z = sSecondaryGhostPosition.z;
    out->yaw = sSecondaryGhostYaw;
    out->animationId = sSecondaryGhostAnimationId;
    out->animationPhase = sSecondaryGhostAnimationPhase;
    out->heldObjectId = sSecondaryGhostHeldObjectId;
    out->heldNameKey = sSecondaryGhostHeldNameKey;
    out->yoshi = sSecondaryGhostYoshi;
    out->visible = sSecondaryGhostVisible;
    visualFludd(sObserverSecondary, sObserverSecondarySegment, *out,
                sVisualQf + sObserverSecondaryOffset);
    return true;
}

void prepareVisual() {
    if (ReplaySession::blocksResults()) {sGhostVisible = sSecondaryGhostVisible = false;return;}
    if (GhostVisualProvider::active()) {
        if (!RetailInput::stageDirector() || !gpMarioOriginal || !gpMarDirector->_260 ||
            !OSIsThreadTerminated(&gSetupThread) || actionsFastForwardActive()) {
            GhostVisualProvider::suspend();
            sGhostVisible = sSecondaryGhostVisible = false;
            return;
        }
        if (observerRunning()) return;
        s32 qf;
        if (!gQFTTimer.currentQf(&qf)) {
            GhostVisualProvider::suspend();
            sGhostVisible = sSecondaryGhostVisible = false;
            return;
        }
        sVisualQf = recordQf(qf);
        refreshProvidedVisual(sVisualQf, false);
        return;
    }
    if (observerRunning()) return;
    sGhostVisible = false;
    sSecondaryGhostVisible = false;
    if (!gpMarDirector || !gpMarioOriginal || sStageRoutePending ||
        !sLiveRouteValid || actionsFastForwardActive() ||
        gQFTTimer.attemptSerial() != sAttemptSerial ||
        sClockPhase == CLOCK_UNAVAILABLE ||
        sClockPhase == CLOCK_WAIT_STAGE) {
        return;
    }

    s32 qf;
    if (!gQFTTimer.currentQf(&qf)) return;
    if (sBoundaryPending || sClockPhase == CLOCK_PROVISIONAL) {
        updateProvisionalPlayback(qf);
    } else if (sClockPhase == CLOCK_ACTIVE ||
               sClockPhase == CLOCK_FINISHED) {
        updatePlayback(qf);
    }
}

bool hasSaveableTrack() {
    if (GhostRecording::ownsSession()) { char name[48];return GhostRecording::copySelection(name,sizeof(name),nullptr); }
    return latestSaveableTrack().track != nullptr;
}
void prepareStreamDeparture(bool keepIncomplete) {
    if (!GhostRecording::capturing()) return;
    if (sRecord.valid && sRecord.count>=2 &&
        (keepIncomplete || (sRecord.completed && sClockPhase==CLOCK_FINISHED)))
        finishStreamRecord(sRecord);
    else GhostRecording::cancelActive();
}
void prepareStreamDeparture() {
    if (!GhostRecording::automaticCapture() || !hasSaveableTrack()) prepareStreamDeparture(true);
}

bool copySaveableName(char *out, u32 size, u32 *outToken) {
    if (GhostRecording::ownsSession()) {
        unsigned token=0;const bool ok=GhostRecording::copySelection(out,size,&token);
        if(outToken)*outToken=token;return ok;
    }
    if (!out || size == 0) return false;
    out[0] = '\0';
    if (outToken) *outToken = 0;
    const SaveSelection selection = latestSaveableTrack();
    if (!selection.track) return false;

    char name[SUSAMUNE_GHOST_NAME_SIZE];
    formatTrackName(*selection.track, name, sizeof(name));
    const u32 length = strlen(name);
    if (length + 1 > size) return false;
    memcpy(out, name, length + 1);
    if (outToken) *outToken = selection.identityToken;
    return true;
}

bool copySaveableName(char *out, u32 size) {
    return copySaveableName(out, size, nullptr);
}

bool copyWarpDiscardName(u8 area, u8 episode, s32 routeVariant,
                         bool boundaryReset,
                         char *out, u32 size, u32 *outToken) {
    (void)area;
    (void)episode;
    (void)routeVariant;
    (void)boundaryReset;
    // Every explicit course departure is destructive product-wise, including
    // same-route restarts. The PB token, not a route prediction, is the guard.
    return copyUnsavedPBName(out, size, outToken);
}

bool copyUnsavedPBName(char *out, u32 size, u32 *outToken) {
    if (GhostRecording::ownsSession()) {
        unsigned token=0;const bool found=GhostRecording::copyProtectedName(out,size,&token);
        if(outToken)*outToken=token;return found;
    }
    if (!out || size == 0) return false;
    out[0] = '\0';
    if (outToken) *outToken = 0;

    const Track *track = nullptr;
    if (sRecord.valid && sRecord.pb && !sRecord.saved &&
        sRecord.pbToken != 0) {
        track = &sRecord;
    } else if (sPlayback.valid && sPlayback.pb && !sPlayback.saved &&
               sPlayback.pbToken != 0) {
        track = &sPlayback;
    }
    if (!track) return false;

    char name[SUSAMUNE_GHOST_NAME_SIZE];
    formatTrackName(*track, name, sizeof(name));
    const u32 length = strlen(name);
    if (length + 1 > size) return false;
    memcpy(out, name, length + 1);
    if (outToken) *outToken = track->pbToken;
    return true;
}

bool copyPlaybackUnsavedPBName(char *out, u32 size, u32 *outToken) {
    if (!out || size == 0) return false;
    out[0] = '\0';
    if (outToken) *outToken = 0;
    if (GhostRecording::ownsSession()) return false;
    if (!sPlayback.valid || !sPlayback.pb || sPlayback.saved ||
        sPlayback.pbToken == 0) {
        return false;
    }

    char name[SUSAMUNE_GHOST_NAME_SIZE];
    formatTrackName(sPlayback, name, sizeof(name));
    const u32 length = strlen(name);
    if (length + 1 > size) return false;
    memcpy(out, name, length + 1);
    if (outToken) *outToken = sPlayback.pbToken;
    return true;
}

bool hasUnsavedPB() {
    if (GhostRecording::ownsSession()) { char name[48];return GhostRecording::copyProtectedName(name,sizeof(name),nullptr); }
    return (sRecord.valid && sRecord.pb && !sRecord.saved &&
            sRecord.pbToken != 0) ||
           (sPlayback.valid && sPlayback.pb && !sPlayback.saved &&
            sPlayback.pbToken != 0);
}

bool hasUnsavedPBToken(u32 token) {
    if (GhostRecording::ownsSession()) return GhostRecording::protectedToken(token);
    if (token == 0) return false;
    return (sRecord.valid && sRecord.pb && !sRecord.saved &&
            sRecord.pbToken == token) ||
           (sPlayback.valid && sPlayback.pb && !sPlayback.saved &&
            sPlayback.pbToken == token);
}

bool unprotectUnsavedPB(u32 token) {
    if (token == 0) return false;
    const bool managed=GhostRecording::ownsSession();
    if (managed && !GhostRecording::unprotect(token)) return false;
    Track *track = nullptr;
    if (sRecord.valid && sRecord.pb && !sRecord.saved &&
        sRecord.pbToken == token) {
        track = &sRecord;
    } else if (sPlayback.valid && sPlayback.pb && !sPlayback.saved &&
               sPlayback.pbToken == token) {
        track = &sPlayback;
    }
    if (!track) return managed;
    track->pb = false;
    track->pbToken = 0;
    return true;
}

bool discardUnsavedPB(u32 token) {
    if (token == 0) return false;
    const bool managed=GhostRecording::ownsSession();
    if (managed && (!GhostRecording::protectedToken(token) || !GhostRecording::discard(token))) return false;
    if (sRecord.valid && sRecord.pb && !sRecord.saved &&
        sRecord.pbToken == token) {
        clearRecord();
        sRecording = false;
        sPendingContinueRecording = false;
        sBoundaryPending = false;
        return true;
    }
    if (sPlayback.valid && sPlayback.pb && !sPlayback.saved &&
        sPlayback.pbToken == token) {
        clearTrack(sPlayback);
        bumpPlaybackToken();
        sPlaybackPinned = false;
        sPinRouteCheckPending = false;
        sGhostVisible = false;
        rewindPlayback();
        return true;
    }
    return managed;
}

bool markCurrentRecordingPB(s32 resultQf) {
    if (resultQf < 0 || !sRecord.valid || !sRecord.completed ||
        (sRecord.runFlags & (SUSAMUNE_GHOST_RUN_ASSISTED |
                             SUSAMUNE_GHOST_RUN_TAS)) ||
        sRecord.resultQf != static_cast<u32>(resultQf)) {
        return false;
    }
    if (!sRecord.pb || sRecord.pbToken == 0) {
        sRecord.pbToken = nextPBToken();
    }
    sRecord.pb = true;
    sRecord.saved = false;
    GhostRecording::protect(sRecordToken, sRecord.pbToken);
    return !GhostRecording::ownsSession() || GhostRecording::protectedToken(sRecord.pbToken);
}

bool playbackPinned() { return sPlaybackPinned; }

void unpinPlayback() {
    sPlaybackPinned = false;
    sPinRouteCheckPending = false;
}

void clearPlayback() {
    if (sObserverPhase != OBSERVER_OFF) {
        stopObserver();
        return;
    }
    // Callers must consume the exact PB token first. This keeps a missed UI
    // guard from silently destroying a promoted accepted run.
    if (sPlayback.valid && sPlayback.pb && !sPlayback.saved &&
        sPlayback.pbToken != 0) {
        return;
    }
    GhostVisualProvider::stopActive();
    clearTrack(sPlayback);
    bumpPlaybackToken();
    sPlaybackPinned = false;
    sPinRouteCheckPending = false;
    sGhostVisible = false;
    rewindPlayback();
}

void releaseSavedRecording(u32 recordToken) {
    if (recordToken & kPlaybackTokenBit) {
        if ((recordToken & ~kPlaybackTokenBit) == sPlaybackToken &&
            sPlayback.valid) {
            sPlayback.saved = true;
            sPlayback.pb = false;
            sPlayback.pbToken = 0;
        }
        return;
    }
    if (recordToken != 0 && recordToken == sPlaybackOriginRecordToken &&
        sPlayback.valid) {
        sPlayback.saved = true;
        sPlayback.pb = false;
        sPlayback.pbToken = 0;
        return;
    }
    if (recordToken != 0 && recordToken == sRecordToken && sRecord.valid) {
        sRecord.saved = true;
        sRecord.pb = false;
        sRecord.pbToken = 0;
        if (sPlaybackPinned && !sRecording) clearRecord();
    }
}

namespace {

bool recorderBanksValid() {
    const __UINTPTR_TYPE__ record = reinterpret_cast<__UINTPTR_TYPE__>(sRecord.samples);
    const __UINTPTR_TYPE__ play = reinterpret_cast<__UINTPTR_TYPE__>(sPlayback.samples);
    const bool first = record == SUSAMUNE_GHOST_RECORD_PPC_BASE;
    if ((!first && record != SUSAMUNE_GHOST_PLAY_PPC_BASE) ||
        play != (first ? SUSAMUNE_GHOST_PLAY_PPC_BASE : SUSAMUNE_GHOST_RECORD_PPC_BASE) ||
        reinterpret_cast<__UINTPTR_TYPE__>(sRecord.segments) != record + kSegmentTableOffset ||
        reinterpret_cast<__UINTPTR_TYPE__>(sPlayback.segments) != play + kSegmentTableOffset)
        return false;
    if (!sRecord.inputs && !sPlayback.inputs) return true;
#if IS_EMULATOR
    const __UINTPTR_TYPE__ inputRecord = SUSAMUNE_DOLPHIN_GHOST_INPUT_RECORD_PPC_BASE;
    const __UINTPTR_TYPE__ inputPlay = SUSAMUNE_DOLPHIN_GHOST_INPUT_PLAY_PPC_BASE;
#else
    const __UINTPTR_TYPE__ inputRecord = SUSAMUNE_GHOST_INPUT_RECORD_PPC_BASE;
    const __UINTPTR_TYPE__ inputPlay = SUSAMUNE_GHOST_INPUT_PLAY_PPC_BASE;
#endif
    return reinterpret_cast<__UINTPTR_TYPE__>(sRecord.inputs) == (first ? inputRecord : inputPlay) &&
           reinterpret_cast<__UINTPTR_TYPE__>(sPlayback.inputs) == (first ? inputPlay : inputRecord);
}

bool savedRngValid(const SavestateData &data) {
    const u32 *rng = data.words + kSavedRngWord;
    if (rng[0]) return rngControlValidateSavestate(rng, RNG_CONTROL_SAVESTATE_DATA_WORDS);
    for (u32 i = 0; i < RNG_CONTROL_SAVESTATE_DATA_WORDS; ++i) if (rng[i]) return false;
    return true;
}

bool decodeSavedPrefix(const SavestateData &data, SavedPrefix *saved) {
    static_assert(sizeof(SavedPrefix) <= kSavedRngWord * sizeof(u32), "RNG metadata overlaps legacy prefix");
    if (!savedRngValid(data)) return false;
    memcpy(saved, &data, sizeof(*saved));
    if (!saved->magic) {
        for (u32 i = 0; i < sizeof(data.words) / sizeof(data.words[0]); ++i) {
            if (i >= kSavedRngWord && i < 124) continue;
            if (data.words[i]) return false;
        }
        return true;
    }
    const Track &track = saved->track;
    if (saved->magic != kSavedPrefixMagic ||
        !SusamuneGhostPersonalProfile(track.sourceProfile) ||
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
        track.endQf > static_cast<u32>(SusamuneGhostClockMap(
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

} // namespace

bool captureSavestate(SavestateData &out,
                      StateCodec::ReadSpan (&spans)[3]) {
    memset(&out, 0, sizeof(out));
    memset(spans, 0, sizeof(spans));
    if (observerStatsSuppressed() ||
        (!sRecording && !sPendingContinueRecording) || !sRecord.count) return true;
    if (!recorderBanksValid() || (sRecord.inputCount && !sRecord.inputs)) return false;
    s32 qf;
    if (!gQFTTimer.currentQf(&qf) || qf < 0 ||
        sAttemptSerial != gQFTTimer.attemptSerial()) return false;
    SavedPrefix saved = {};
    saved.magic = kSavedPrefixMagic;
    saved.capturedQf = static_cast<u32>(qf);
    saved.track = sRecord;
    saved.track.samples = nullptr;
    saved.track.segments = nullptr;
    saved.track.inputs = nullptr;
    saved.clock = sRecordClock;
    saved.serial = sAttemptSerial;
    saved.lastSampleQf = sLastSampleQf;
    saved.clockLastQf = sClockLastQf;
    saved.clockEpochStartQf = sClockEpochStartQf;
    saved.pendingPreviousClockQf = sPendingPreviousClockQf;
    saved.boundaryPriorQf = sBoundaryPriorQf;
    saved.liveParentEpisode = sLiveParentEpisode;
    saved.clockObservations = sClockObservations;
    saved.boundaryBaseSegmentCount = sBoundaryBaseSegmentCount;
    saved.phase = sClockPhase;
    saved.flags = (sRecording ? PREFIX_RECORDING : 0) |
        (sStageRoutePending ? PREFIX_STAGE_PENDING : 0) |
        (sPendingHadLiveRoute ? PREFIX_HAD_ROUTE : 0) |
        (sPendingContinueRecording ? PREFIX_CONTINUE : 0) |
        (sBoundaryPending ? PREFIX_BOUNDARY : 0) |
        (sLiveRouteValid ? PREFIX_LIVE_ROUTE : 0);
    saved.liveArea = sLiveArea;
    saved.liveEpisode = sLiveEpisode;
    saved.liveRouteParentArea = sLiveRouteParentArea;
    saved.liveRouteFlags = sLiveRouteFlags;
    saved.endpoint = sRestoredPrefix ? sRestoredEndpoint : ILing::savestateGhostEndpoint();
    memcpy(&out, &saved, sizeof(saved));
    if (sRecord.formatVersion >= SUSAMUNE_GHOST_FILE_VERSION_V8) {
        out.words[126] = GhostCamera::prefixSize(sRecord.samples);
        out.words[127] = SUSAMUNE_GHOST_CAMERA_MAGIC;
    }
    if (sRecord.formatVersion >= SUSAMUNE_GHOST_FILE_VERSION_V10) {
        out.words[124] = GhostContext::prefixSize(sRecord.samples);
        out.words[125] = SUSAMUNE_GHOST_CONTEXT_MAGIC;
    }
    if (!decodeSavedPrefix(out, &saved)) return false;
    spans[0] = {sRecord.samples, sRecord.count * static_cast<u32>(sizeof(Sample))};
    spans[1] = {sRecord.segments, sRecord.segmentCount * static_cast<u32>(sizeof(Segment))};
    spans[2] = {sRecord.inputs, sRecord.inputCount * SusamuneGhostInputStride(sRecord.formatVersion)};
    return true;
}

bool savestateRestoreSpans(const SavestateData &data,
                          StateCodec::WriteSpan (&spans)[3]) {
    memset(spans, 0, sizeof(spans));
    SavedPrefix saved;
    if (!decodeSavedPrefix(data, &saved)) return false;
    if (!saved.magic) return true;
    if (!recorderBanksValid() || (saved.track.inputCount && !sRecord.inputs)) return false;
    spans[0] = {sRecord.samples, saved.track.count * static_cast<u32>(sizeof(Sample))};
    spans[1] = {sRecord.segments, saved.track.segmentCount * static_cast<u32>(sizeof(Segment))};
    spans[2] = {sRecord.inputs, saved.track.inputCount * SusamuneGhostInputStride(saved.track.formatVersion)};
    return true;
}

bool captureSavestate(SavestateData &out,
                      StateCodec::ReadSpan (&spans)[kSavestateSpanCount]) {
    memset(spans, 0, sizeof(spans));
    StateCodec::ReadSpan (&core)[3] = *reinterpret_cast<StateCodec::ReadSpan (*)[3]>(spans);
    if (!captureSavestate(out, core)) return false;
    if (!rngControlCaptureSavestate(out.words + kSavedRngWord, RNG_CONTROL_SAVESTATE_DATA_WORDS)) return false;
    if (out.words[126]) spans[3] = {GhostCamera::prefix(sRecord.samples), out.words[126]};
    if (out.words[124]) spans[4] = {GhostContext::prefix(sRecord.samples), out.words[124]};
    return true;
}

bool savestateRestoreSpans(const SavestateData &data,
                          StateCodec::WriteSpan (&spans)[kSavestateSpanCount]) {
    memset(spans, 0, sizeof(spans));
    StateCodec::WriteSpan (&core)[3] = *reinterpret_cast<StateCodec::WriteSpan (*)[3]>(spans);
    if (!savestateRestoreSpans(data, core)) return false;
    if (data.words[126]) spans[3] = {GhostCamera::prefix(sRecord.samples), data.words[126]};
    if (data.words[124]) spans[4] = {GhostContext::prefix(sRecord.samples), data.words[124]};
    return true;
}

int savestateRngStatus(const SavestateData &data) {
    if (!savedRngValid(data)) return -1;
    return data.words[kSavedRngWord] || !rngControlSavestateRequired() ? 1 : 0;
}

bool restoreSavestateRng(const SavestateData &data) {
    if (data.words[kSavedRngWord])
        return rngControlRestoreSavestate(data.words + kSavedRngWord, RNG_CONTROL_SAVESTATE_DATA_WORDS);
    rngControlRestoreLegacySavestate();
    return !rngControlSavestateRequired();
}

void restoreSavestate(const SavestateData &data) {
    SavedPrefix saved;
    if (!decodeSavedPrefix(data, &saved)) __builtin_trap();
    onSavestateLoaded();
    if (!saved.magic) return;
    Sample *samples = sRecord.samples;
    Segment *segments = sRecord.segments;
    SusamuneGhostInputSample *inputs = sRecord.inputs;
    sRecord = saved.track;
    sRecord.samples = samples;
    sRecord.segments = segments;
    sRecord.inputs = inputs;
    sRecord.runFlags |= SUSAMUNE_GHOST_RUN_ASSISTED | SUSAMUNE_GHOST_RUN_TAS | SUSAMUNE_GHOST_RUN_SAVESTATE_USED;
    if (sRecord.formatVersion >= SUSAMUNE_GHOST_FILE_VERSION_V10) GhostContext::restored(sRecord.samples);
    sRestoredPrefix = true;
    sRestoredEndpoint = saved.endpoint;
    sRecord.pb = false;
    sRecord.pbToken = 0;
    bumpRecordToken();
    sRecordIdentityToken = sRecordToken;
    sRecordClock = saved.clock;
    sAttemptSerial = saved.serial;
    sLastSampleQf = saved.lastSampleQf;
    sClockLastQf = saved.clockLastQf;
    sClockEpochStartQf = saved.clockEpochStartQf;
    sPendingPreviousClockQf = saved.pendingPreviousClockQf;
    sBoundaryPriorQf = saved.boundaryPriorQf;
    sLiveParentEpisode = saved.liveParentEpisode;
    sClockObservations = saved.clockObservations;
    sBoundaryBaseSegmentCount = saved.boundaryBaseSegmentCount;
    sClockPhase = static_cast<ClockPhase>(saved.phase);
    sRecording = (saved.flags & PREFIX_RECORDING) != 0;
    sStageRoutePending = (saved.flags & PREFIX_STAGE_PENDING) != 0;
    sPendingHadLiveRoute = (saved.flags & PREFIX_HAD_ROUTE) != 0;
    sPendingContinueRecording = (saved.flags & PREFIX_CONTINUE) != 0;
    sBoundaryPending = (saved.flags & PREFIX_BOUNDARY) != 0;
    sLiveRouteValid = (saved.flags & PREFIX_LIVE_ROUTE) != 0;
    sLiveArea = saved.liveArea;
    sLiveEpisode = saved.liveEpisode;
    sLiveRouteParentArea = saved.liveRouteParentArea;
    sLiveRouteFlags = saved.liveRouteFlags;
}

void onSavestateLoaded() {
    GhostStageContext::invalidateAfterRestore();
    GhostCamera::beginFrame();
    memset(&sRecordClock, 0, sizeof(sRecordClock));
    sRaceSplitCount = 0;
    clearRaceContext();
    if (sObserverPhase != OBSERVER_OFF) {
        releaseObserverMario(false);
        endObserver(false, nullptr);
        if (gMenu) gMenu->toast("Observer stopped: savestate loaded");
        return;
    }
    sAttemptSerial = gQFTTimer.attemptSerial();
    clearRecord();
    sRecording = false;
    sGhostVisible = false;
    sStageRoutePending = false;
    sPendingHadLiveRoute = false;
    sPendingContinueRecording = false;
    sBoundaryPending = false;
    sPinRouteCheckPending = false;
    if (!sPlaybackPinned) {
        stopAll();
        sAttemptSerial = gQFTTimer.attemptSerial();
        if (gpMarDirector) captureLiveRoute();
        return;
    }

    captureLiveRoute();
    rewindPlayback();
    s32 qf;
    bool stopped;
    if (gQFTTimer.currentQf(&qf, &stopped)) {
        sClockPhase = stopped ? CLOCK_FINISHED : CLOCK_PROVISIONAL;
        sClockObservations = 1;
        sClockLastQf = qf;
        sClockEpochStartQf = qf;
    } else {
        sClockPhase = CLOCK_UNAVAILABLE;
    }
}

}  // namespace Ghost

#if MOONSHINE_MEMORY_TELEMETRY
extern "C" bool memoryTelemetryGhosts(unsigned *out) {
    const Ghost::Track *tracks[2] = {&Ghost::sRecord, &Ghost::sPlayback};
    for (unsigned i = 0; i < 2; ++i) {
        const Ghost::Track &track = *tracks[i];
        if (track.count > SusamuneGhostPoseLimit(track.formatVersion) ||
            track.inputCount > SusamuneGhostInputLimit(track.formatVersion)) return false;
        out[i * 2] = track.count * sizeof(Ghost::Sample);
        out[i * 2 + 1] = track.inputCount * SusamuneGhostInputStride(track.formatVersion);
    }
    return true;
}
#endif
