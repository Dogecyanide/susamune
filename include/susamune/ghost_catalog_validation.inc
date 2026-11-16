#include "susamune/ghost_recording_manifest.h"
// Shared CPU-only catalogue admission; caller supplies the current game identity.
bool safeText(const char *text, u32 capacity, u32 length, bool required) {
    if (length > capacity || (required && length == 0)) return false;
    for (u32 i = 0; i < length; i++) {
        const u8 value = static_cast<u8>(text[i]);
        if (value < SUSAMUNE_GHOST_TEXT_MIN ||
            value > SUSAMUNE_GHOST_TEXT_MAX || value == '/' || value == '\\') {
            return false;
        }
    }
    for (u32 i = length; i < capacity; i++) {
        if (text[i] != 0) return false;
    }
    return true;
}

bool gameRegionPairIsValid(u32 gameId, u8 region) {
    return (gameId == SUSAMUNE_GHOST_GAME_ID_JP &&
            region == SUSAMUNE_GHOST_REGION_JP) ||
           (gameId == SUSAMUNE_GHOST_GAME_ID_US &&
            region == SUSAMUNE_GHOST_REGION_US) ||
           (gameId == SUSAMUNE_GHOST_GAME_ID_PAL &&
            region == SUSAMUNE_GHOST_REGION_PAL);
}

bool portableRouteIsValid(u8 area, u8 episode, u8 parentArea,
                          u8 routeFlags, s32 routeVariant) {
    u8 expectedParent;
    switch (area) {
#define PORTABLE_ROUTE_CASE(routeArea, parent) \
    case routeArea: expectedParent = parent; break;
        SUSAMUNE_GHOST_PORTABLE_ROUTE_LIST(PORTABLE_ROUTE_CASE)
#undef PORTABLE_ROUTE_CASE
    default: return false;
    }
    if (episode > SUSAMUNE_GHOST_ROUTE_EPISODE_MAX ||
        routeVariant < SUSAMUNE_GHOST_ROUTE_VARIANT_NONE ||
        routeVariant > SUSAMUNE_GHOST_ROUTE_VARIANT_MAX ||
        parentArea != expectedParent) {
        return false;
    }
    if (expectedParent == SUSAMUNE_GHOST_ROUTE_PARENT_NONE) {
        return routeFlags == 0;
    }
    return (routeFlags & SUSAMUNE_GHOST_ROUTE_INTERNAL_SCENE) != 0 &&
           (routeFlags & ~(SUSAMUNE_GHOST_ROUTE_INTERNAL_SCENE |
                           SUSAMUNE_GHOST_ROUTE_PARENT_START)) == 0;
}

void makeUnsafe(SusamuneGhostSlotInfo *out, u32 generation) {
    memset(out, 0, sizeof(*out));
    out->generation = generation;
    out->flags = SUSAMUNE_GHOST_SLOT_UNSAFE;
    out->status = SUSAMUNE_GHOST_STATUS_INVALID_FILE;
}

__attribute__((always_inline)) static inline bool validateCatalogSlot(const SusamuneGhostSlotInfo &raw,
                  SusamuneGhostSlotInfo *out, bool imported,u32 kGameId,u8 kRegion) {
    if (!out) return false;
    memset(out, 0, sizeof(*out));

    const u16 knownFlags = SUSAMUNE_GHOST_SLOT_PRESENT |
        SUSAMUNE_GHOST_SLOT_UNSAFE | SUSAMUNE_GHOST_SLOT_IMPORTED | SUSAMUNE_GHOST_SLOT_STREAMED;
    if ((raw.flags & ~knownFlags) != 0 || raw.reserved[0] != 0) {
        makeUnsafe(out, raw.generation);
        return false;
    }
    if ((raw.flags & SUSAMUNE_GHOST_SLOT_UNSAFE) != 0) {
        if (imported &&
            (raw.flags & (SUSAMUNE_GHOST_SLOT_PRESENT |
                          SUSAMUNE_GHOST_SLOT_IMPORTED)) !=
                (SUSAMUNE_GHOST_SLOT_PRESENT |
                 SUSAMUNE_GHOST_SLOT_IMPORTED)) {
            makeUnsafe(out, raw.generation);
            return false;
        }
        makeUnsafe(out, raw.generation);
        if (imported) {
            out->flags |= SUSAMUNE_GHOST_SLOT_PRESENT |
                          SUSAMUNE_GHOST_SLOT_IMPORTED;
        }
        out->status = SUSAMUNE_GHOST_STATUS_SLOT_UNSAFE;
        return true;
    }
    if ((raw.flags & SUSAMUNE_GHOST_SLOT_PRESENT) == 0) {
        return (raw.flags & SUSAMUNE_GHOST_SLOT_IMPORTED) == 0;
    }

    const bool hasParent =
        raw.routeParentArea != SUSAMUNE_GHOST_ROUTE_PARENT_NONE;
    const bool internal =
        (raw.routeFlags & SUSAMUNE_GHOST_ROUTE_INTERNAL_SCENE) != 0;
    const bool parentStart =
        (raw.routeFlags & SUSAMUNE_GHOST_ROUTE_PARENT_START) != 0;
    const u32 expectedCanonicalSize = SUSAMUNE_GHOST_V4_SAMPLE_DATA_OFFSET +
        raw.sampleCount * SUSAMUNE_GHOST_POSE_SAMPLE_SIZE;
    const bool canonicalV3 =
        raw.canonicalVersion == SUSAMUNE_GHOST_FILE_VERSION_V3 &&
        raw.requiredFeatures ==
            SUSAMUNE_GHOST_SUPPORTED_REQUIRED_FEATURES_V3 &&
        raw.sampleCodec == SUSAMUNE_GHOST_CODEC_RAW;
    const bool canonicalV4 =
        raw.canonicalVersion == SUSAMUNE_GHOST_FILE_VERSION_V4 &&
        raw.requiredFeatures ==
            SUSAMUNE_GHOST_SUPPORTED_REQUIRED_FEATURES_V4 &&
        raw.sampleCodec == SUSAMUNE_GHOST_CODEC_POSE_ATTACHMENTS;
    const bool canonicalTeaching =
        ((raw.canonicalVersion == SUSAMUNE_GHOST_FILE_VERSION_V5 &&
          raw.requiredFeatures == SUSAMUNE_GHOST_SUPPORTED_REQUIRED_FEATURES_V5) ||
         (raw.canonicalVersion == SUSAMUNE_GHOST_FILE_VERSION_V6 &&
          raw.requiredFeatures == SUSAMUNE_GHOST_SUPPORTED_REQUIRED_FEATURES_V6) ||
         (raw.canonicalVersion == SUSAMUNE_GHOST_FILE_VERSION_V7 &&
          raw.requiredFeatures == SUSAMUNE_GHOST_SUPPORTED_REQUIRED_FEATURES_V7) ||
         (raw.canonicalVersion == SUSAMUNE_GHOST_FILE_VERSION_V8 &&
          raw.requiredFeatures == SUSAMUNE_GHOST_SUPPORTED_REQUIRED_FEATURES_V8) ||
         (raw.canonicalVersion == SUSAMUNE_GHOST_FILE_VERSION_V9 &&
          raw.requiredFeatures == SUSAMUNE_GHOST_SUPPORTED_REQUIRED_FEATURES_V9) ||
         (raw.canonicalVersion == SUSAMUNE_GHOST_FILE_VERSION_V10 &&
          raw.requiredFeatures == SUSAMUNE_GHOST_SUPPORTED_REQUIRED_FEATURES_V10)) &&
        raw.sampleCodec == SUSAMUNE_GHOST_CODEC_POSE_ATTACHMENTS;
    const bool streamed = (raw.flags & SUSAMUNE_GHOST_SLOT_STREAMED) != 0;
    const bool streamedFields = !imported && raw.canonicalVersion == MS_RECORDING_CATALOG_VERSION &&
        raw.sampleCodec == MS_RECORDING_CODEC && (raw.requiredFeatures & 0x20000u) &&
        !(raw.requiredFeatures & 0xff000000u);
    const bool foreign = raw.gameId != kGameId;
    const bool namespaceSane = imported
        ? (raw.flags & SUSAMUNE_GHOST_SLOT_IMPORTED) != 0 &&
              gameRegionPairIsValid(raw.gameId, raw.region) &&
              (!foreign || portableRouteIsValid(
                  raw.routeArea, raw.routeEpisode, raw.routeParentArea,
                  raw.routeFlags, raw.routeVariant))
        : (raw.flags & SUSAMUNE_GHOST_SLOT_IMPORTED) == 0 &&
              raw.gameId == kGameId && raw.region == kRegion;
    const bool sane = raw.status == 0 &&
        namespaceSane &&
        raw.discRevision == SUSAMUNE_GHOST_DISC_REVISION &&
        (streamed ? streamedFields : (canonicalV3 || canonicalV4 || canonicalTeaching)) &&
        raw.recordingMode == (streamed ? MS_RECORDING_MODE : SUSAMUNE_GHOST_RECORDING_POSE_QF) &&
        raw.sampleIntervalQf == SUSAMUNE_GHOST_TRANSFORM_INTERVAL_QF &&
        raw.sampleCount >= (streamed ? 1u : SUSAMUNE_GHOST_MIN_SAMPLE_COUNT) &&
        (streamed || raw.sampleCount <= SusamuneGhostPoseLimit(raw.canonicalVersion)) &&
        raw.durationQf > 0 &&
        raw.durationQf <= (streamed ? SUSAMUNE_GHOST_QF_MAX : SusamuneGhostDurationLimit(raw.canonicalVersion)) &&
        (streamed ? raw.payloadSize == MS_RECORDING_MANIFEST_BYTES : canonicalTeaching ? raw.payloadSize >= expectedCanonicalSize +
                                          SUSAMUNE_GHOST_TEACHING_HEADER_SIZE +
            (raw.canonicalVersion >= SUSAMUNE_GHOST_FILE_VERSION_V8
                ? SUSAMUNE_GHOST_CAMERA_HEADER_SIZE : 0) +
            (raw.canonicalVersion >= SUSAMUNE_GHOST_FILE_VERSION_V10
                ? SUSAMUNE_GHOST_CONTEXT_HEADER_SIZE : 0)
                     : raw.payloadSize == expectedCanonicalSize) &&
        raw.payloadSize <= SUSAMUNE_GHOST_MAX_FILE_SIZE &&
        (raw.resultQf == SUSAMUNE_GHOST_RESULT_QF_NONE ||
         raw.resultQf <= SUSAMUNE_GHOST_QF_MAX) &&
        raw.routeArea <= SUSAMUNE_GHOST_ROUTE_AREA_MAX &&
        raw.routeEpisode <= SUSAMUNE_GHOST_ROUTE_EPISODE_MAX &&
        (!hasParent ||
         raw.routeParentArea <= SUSAMUNE_GHOST_ROUTE_AREA_MAX) &&
        (raw.routeFlags & ~SUSAMUNE_GHOST_ROUTE_FLAGS_V1) == 0 &&
        internal == hasParent && (!parentStart || hasParent) &&
        raw.routeVariant >= SUSAMUNE_GHOST_ROUTE_VARIANT_NONE &&
        raw.routeVariant <= SUSAMUNE_GHOST_ROUTE_VARIANT_MAX &&
        safeText(raw.author, sizeof(raw.author), raw.authorLength, false) &&
        safeText(raw.name, sizeof(raw.name), raw.nameLength, true);
    if (!sane) {
        makeUnsafe(out, raw.generation);
        return false;
    }
    memcpy(out, &raw, sizeof(*out));
    return true;
}
