#include "susamune/ghost_recording_manifest.h"
/* Canonical header admission and catalogue fields, shared by both storage backends. */
static u16 ReadBe16(const u8 *p)
{
	return ((u16)p[0] << 8) | p[1];
}

static u32 ReadBe32(const u8 *p)
{
	return ((u32)p[0] << 24) | ((u32)p[1] << 16) |
	       ((u32)p[2] << 8) | p[3];
}

static s32 ReadBeS32(const u8 *p)
{
	return (s32)ReadBe32(p);
}

static u32 CrcUpdate(u32 crc, const u8 *data, u32 size)
{
	u32 i;
	u32 bit;

	for (i = 0; i < size; i++)
	{
		crc ^= data[i];
		for (bit = 0; bit < 8; bit++)
			crc = (crc >> 1) ^
			      (SUSAMUNE_GHOST_CRC32_POLY & (0u - (crc & 1u)));
	}
	return crc;
}

static u32 CrcUpdateHeader(u32 crc, const u8 *header,
	                       u32 zeroStart, u32 zeroEnd)
{
	u32 i;
	u8 value;

	for (i = 0; i < SUSAMUNE_GHOST_FILE_HEADER_SIZE; i++)
	{
		value = (i >= zeroStart && i < zeroEnd) ? 0 : header[i];
		crc = CrcUpdate(crc, &value, 1);
	}
	return crc;
}

static bool BytesAreZero(const u8 *bytes, u32 size)
{
	u32 i;
	for (i = 0; i < size; i++)
		if (bytes[i] != 0)
			return false;
	return true;
}

static bool RouteIsValid(u8 area, u8 episode, u8 parentArea,
	                     u8 routeFlags, s32 routeVariant)
{
	return area <= SUSAMUNE_GHOST_ROUTE_AREA_MAX &&
	       episode <= SUSAMUNE_GHOST_ROUTE_EPISODE_MAX &&
	       (parentArea == SUSAMUNE_GHOST_ROUTE_PARENT_NONE ||
	        parentArea <= SUSAMUNE_GHOST_ROUTE_AREA_MAX) &&
	       (routeFlags & ~SUSAMUNE_GHOST_ROUTE_FLAGS_V1) == 0 &&
	       (((routeFlags & SUSAMUNE_GHOST_ROUTE_INTERNAL_SCENE) != 0) ==
	        (parentArea != SUSAMUNE_GHOST_ROUTE_PARENT_NONE)) &&
	       ((routeFlags & SUSAMUNE_GHOST_ROUTE_PARENT_START) == 0 ||
	        parentArea != SUSAMUNE_GHOST_ROUTE_PARENT_NONE) &&
	       routeVariant >= SUSAMUNE_GHOST_ROUTE_VARIANT_NONE &&
	       routeVariant <= SUSAMUNE_GHOST_ROUTE_VARIANT_MAX;
}

static bool GameRegionPairIsValid(u32 gameId, u8 region)
{
	return (gameId == SUSAMUNE_GHOST_GAME_ID_JP &&
	        region == SUSAMUNE_GHOST_REGION_JP) ||
	       (gameId == SUSAMUNE_GHOST_GAME_ID_US &&
	        region == SUSAMUNE_GHOST_REGION_US) ||
	       (gameId == SUSAMUNE_GHOST_GAME_ID_PAL &&
	        region == SUSAMUNE_GHOST_REGION_PAL);
}

static bool PortableRouteIsValid(u8 area, u8 episode, u8 parentArea,
	                             u8 routeFlags, s32 routeVariant)
{
	u8 expectedParent;

	switch (area)
	{
#define PORTABLE_ROUTE_CASE(routeArea, parent) \
		case routeArea: expectedParent = parent; break;
		SUSAMUNE_GHOST_PORTABLE_ROUTE_LIST(PORTABLE_ROUTE_CASE)
#undef PORTABLE_ROUTE_CASE
		default: return false;
	}
	if (!RouteIsValid(area, episode, parentArea, routeFlags, routeVariant) ||
	    parentArea != expectedParent)
		return false;
	if (expectedParent == SUSAMUNE_GHOST_ROUTE_PARENT_NONE)
		return routeFlags == 0;
	return (routeFlags & SUSAMUNE_GHOST_ROUTE_INTERNAL_SCENE) != 0 &&
	       (routeFlags & ~(SUSAMUNE_GHOST_ROUTE_INTERNAL_SCENE |
	                       SUSAMUNE_GHOST_ROUTE_PARENT_START)) == 0;
}

static bool HeaderTextIsValid(const u8 *field, u32 capacity, u32 length,
	                          bool required)
{
	u32 i;

	if (length > capacity || (required && length == 0))
		return false;
	for (i = 0; i < length; i++)
		if (field[i] < SUSAMUNE_GHOST_TEXT_MIN ||
		    field[i] > SUSAMUNE_GHOST_TEXT_MAX ||
		    field[i] == '/' || field[i] == '\\')
			return false;
	for (; i < capacity; i++)
		if (field[i] != 0)
			return false;
	return true;
}

static bool V4AttachmentsAreValid(const u8 *header)
{
	u8 count = header[SUSAMUNE_GHOST_V4_ATTACHMENT_COUNT_OFFSET];
	u16 flags = ReadBe16(header + SUSAMUNE_GHOST_V4_ATTACHMENT_FLAGS_OFFSET);
	u32 i;
	u32 prior;
	const u8 *descriptor;

	if (count > SUSAMUNE_GHOST_V4_ATTACHMENT_DESCRIPTOR_COUNT ||
	    header[SUSAMUNE_GHOST_V4_ATTACHMENT_SIZE_OFFSET] !=
	        SUSAMUNE_GHOST_V4_ATTACHMENT_DESCRIPTOR_SIZE ||
	    (flags & ~SUSAMUNE_GHOST_V4_ATTACHMENT_FLAGS) != 0 ||
	    ReadBe16(header + SUSAMUNE_GHOST_V4_ATTACHMENT_RESERVED_OFFSET) != 0)
		return false;
	for (i = 0; i < SUSAMUNE_GHOST_V4_ATTACHMENT_DESCRIPTOR_COUNT; i++)
	{
		descriptor = header + SUSAMUNE_GHOST_V4_ATTACHMENT_TABLE_OFFSET +
		             i * SUSAMUNE_GHOST_V4_ATTACHMENT_DESCRIPTOR_SIZE;
		if (i < count)
		{
			if (BytesAreZero(descriptor,
			                 SUSAMUNE_GHOST_V4_ATTACHMENT_DESCRIPTOR_SIZE))
				return false;
			for (prior = 0; prior < i; prior++)
				if (memcmp(descriptor,
				           header + SUSAMUNE_GHOST_V4_ATTACHMENT_TABLE_OFFSET +
				               prior * SUSAMUNE_GHOST_V4_ATTACHMENT_DESCRIPTOR_SIZE,
				           SUSAMUNE_GHOST_V4_ATTACHMENT_DESCRIPTOR_SIZE) == 0)
					return false;
		}
		else if (!BytesAreZero(
		             descriptor,
		             SUSAMUNE_GHOST_V4_ATTACHMENT_DESCRIPTOR_SIZE))
			return false;
	}
	return true;
}

static enum ValidateResult ValidateCanonicalHeader(const u8 *header,
	                                                u32 available,
	                                                u16 profile,
	                                                bool imported, u32 gameId, u8 region)
{
	u32 fileSize;
	u32 payloadSize;
	u32 sampleCount;
	u32 headerCrc;
	u32 required;
	u32 startQf;
	u32 endQf;
	u32 resultQf;
	s32 routeVariant;
	u16 version;
	u16 segmentCount;
	u32 sourceGameId;
	u8 sourceRegion;
	bool portable;

	if (available < SUSAMUNE_GHOST_FILE_HEADER_SIZE)
		return VALIDATE_INVALID;
#ifdef MS_RECORDING_CATALOG_ADMISSION
    if (ReadBe32(header) == MS_RECORDING_MANIFEST_MAGIC) {
        if (imported) return VALIDATE_INVALID;
        if (ReadBe16(header+4)>MS_RECORDING_MANIFEST_VERSION) return VALIDATE_FORWARD;
        return MsRecordingManifestValid(header, available, gameId, profile)
            ? VALIDATE_OK : VALIDATE_INVALID;
    }
#endif
	if (ReadBe32(header) != SUSAMUNE_GHOST_FILE_MAGIC)
		return VALIDATE_INVALID;
	version = ReadBe16(header + 4);
	if (version != SUSAMUNE_GHOST_FILE_VERSION_V3 &&
	    version != SUSAMUNE_GHOST_FILE_VERSION_V4 &&
	    version != SUSAMUNE_GHOST_FILE_VERSION_V5 &&
	    version != SUSAMUNE_GHOST_FILE_VERSION_V6 &&
	    version != SUSAMUNE_GHOST_FILE_VERSION_V7 &&
	    version != SUSAMUNE_GHOST_FILE_VERSION_V8 &&
	    version != SUSAMUNE_GHOST_FILE_VERSION_V9 &&
	    version != SUSAMUNE_GHOST_FILE_VERSION_V10)
		return VALIDATE_FORWARD;
	if (ReadBe16(header + 6) != SUSAMUNE_GHOST_FILE_HEADER_SIZE)
		return VALIDATE_INVALID;
	headerCrc = CrcUpdateHeader(SUSAMUNE_GHOST_CRC32_INIT, header, 12, 20) ^
	            SUSAMUNE_GHOST_CRC32_XOR_OUT;
	if (headerCrc != ReadBe32(header + 16))
		return VALIDATE_INVALID;

	fileSize = ReadBe32(header + 8);
	payloadSize = ReadBe32(header + 72);
	sampleCount = ReadBe32(header + 68);
	required = ReadBe32(header + 24);
	if (!SusamuneGhostRunFlagsValid(ReadBe32(header + 28)))
		return VALIDATE_INVALID;
	if ((required & ~(version == SUSAMUNE_GHOST_FILE_VERSION_V10
                        ? SUSAMUNE_GHOST_SUPPORTED_REQUIRED_FEATURES_V10
                        : version == SUSAMUNE_GHOST_FILE_VERSION_V9
                        ? SUSAMUNE_GHOST_SUPPORTED_REQUIRED_FEATURES_V9
                        : version == SUSAMUNE_GHOST_FILE_VERSION_V8
                        ? SUSAMUNE_GHOST_SUPPORTED_REQUIRED_FEATURES_V8
                        : version == SUSAMUNE_GHOST_FILE_VERSION_V7
                        ? SUSAMUNE_GHOST_SUPPORTED_REQUIRED_FEATURES_V7
                        : version == SUSAMUNE_GHOST_FILE_VERSION_V6
	                    ? SUSAMUNE_GHOST_SUPPORTED_REQUIRED_FEATURES_V6
	                    : version == SUSAMUNE_GHOST_FILE_VERSION_V5
	                    ? SUSAMUNE_GHOST_SUPPORTED_REQUIRED_FEATURES_V5
	                    : version == SUSAMUNE_GHOST_FILE_VERSION_V4
	                    ? SUSAMUNE_GHOST_SUPPORTED_REQUIRED_FEATURES_V4
	                    : SUSAMUNE_GHOST_SUPPORTED_REQUIRED_FEATURES_V3)) != 0)
		return VALIDATE_FORWARD;
	if (version >= SUSAMUNE_GHOST_FILE_VERSION_V4 &&
	    required != (version == SUSAMUNE_GHOST_FILE_VERSION_V10
                        ? SUSAMUNE_GHOST_SUPPORTED_REQUIRED_FEATURES_V10
                        : version == SUSAMUNE_GHOST_FILE_VERSION_V9
                        ? SUSAMUNE_GHOST_SUPPORTED_REQUIRED_FEATURES_V9
                        : version == SUSAMUNE_GHOST_FILE_VERSION_V8
                        ? SUSAMUNE_GHOST_SUPPORTED_REQUIRED_FEATURES_V8
                        : version == SUSAMUNE_GHOST_FILE_VERSION_V7
                        ? SUSAMUNE_GHOST_SUPPORTED_REQUIRED_FEATURES_V7
                        : version == SUSAMUNE_GHOST_FILE_VERSION_V6
	        ? SUSAMUNE_GHOST_SUPPORTED_REQUIRED_FEATURES_V6
	        : version == SUSAMUNE_GHOST_FILE_VERSION_V5
	        ? SUSAMUNE_GHOST_SUPPORTED_REQUIRED_FEATURES_V5
	        : SUSAMUNE_GHOST_REQUIRED_EXTENDED_CODEC))
		return VALIDATE_INVALID;

	if (sampleCount < SUSAMUNE_GHOST_MIN_SAMPLE_COUNT ||
	    sampleCount > SusamuneGhostPoseLimit(version))
		return VALIDATE_INVALID;
	segmentCount = ReadBe16(
		header + SUSAMUNE_GHOST_V4_SEGMENT_COUNT_OFFSET);
	if (segmentCount == 0 ||
	    segmentCount > SUSAMUNE_GHOST_V4_MAX_SEGMENTS ||
	    ReadBe16(header + SUSAMUNE_GHOST_V4_SEGMENT_SIZE_OFFSET) !=
	        SUSAMUNE_GHOST_V4_SEGMENT_SIZE ||
	    ReadBe32(header +
	             SUSAMUNE_GHOST_V4_SEGMENT_TABLE_OFFSET_FIELD) !=
	        SUSAMUNE_GHOST_V4_SEGMENT_TABLE_OFFSET ||
	    ReadBe32(header +
	             SUSAMUNE_GHOST_V4_SEGMENT_TABLE_SIZE_OFFSET) !=
	        SUSAMUNE_GHOST_V4_SEGMENT_TABLE_SIZE ||
	    ReadBe32(header +
	             SUSAMUNE_GHOST_V4_SAMPLE_DATA_OFFSET_FIELD) !=
	        SUSAMUNE_GHOST_V4_SAMPLE_DATA_OFFSET ||
	    ReadBe32(header +
	             SUSAMUNE_GHOST_V4_SAMPLE_DATA_SIZE_OFFSET) !=
	        sampleCount * SUSAMUNE_GHOST_POSE_SAMPLE_SIZE ||
	    payloadSize != fileSize - SUSAMUNE_GHOST_FILE_HEADER_SIZE ||
	    (version >= SUSAMUNE_GHOST_FILE_VERSION_V5
	        ? fileSize < SUSAMUNE_GHOST_V4_SAMPLE_DATA_OFFSET +
	            sampleCount * SUSAMUNE_GHOST_POSE_SAMPLE_SIZE +
	            SUSAMUNE_GHOST_TEACHING_HEADER_SIZE +
                (version >= SUSAMUNE_GHOST_FILE_VERSION_V8 ? SUSAMUNE_GHOST_CAMERA_HEADER_SIZE : 0u) +
                (version >= SUSAMUNE_GHOST_FILE_VERSION_V10 ? SUSAMUNE_GHOST_CONTEXT_HEADER_SIZE : 0u) ||
	          fileSize > SUSAMUNE_GHOST_V5_MAX_FILE_SIZE
	        : fileSize != SUSAMUNE_GHOST_V4_SAMPLE_DATA_OFFSET +
	            sampleCount * SUSAMUNE_GHOST_POSE_SAMPLE_SIZE ||
	          fileSize > SUSAMUNE_GHOST_V4_MAX_FILE_SIZE))
		return VALIDATE_INVALID;
	if ((version == SUSAMUNE_GHOST_FILE_VERSION_V3 &&
	     !BytesAreZero(header +
	                         SUSAMUNE_GHOST_V3_SEGMENT_CHECKSUM_OFFSET + 4,
	                   SUSAMUNE_GHOST_FILE_HEADER_SIZE -
	                       SUSAMUNE_GHOST_V3_SEGMENT_CHECKSUM_OFFSET - 4)) ||
	    (version >= SUSAMUNE_GHOST_FILE_VERSION_V4 &&
	     !V4AttachmentsAreValid(header)))
		return VALIDATE_INVALID;

	sourceGameId = ReadBe32(header + 32);
	sourceRegion = header[37];
	portable = imported && sourceGameId != gameId;
	if (header[36] != SUSAMUNE_GHOST_DISC_REVISION ||
	    (!imported &&
	     (sourceGameId != gameId || sourceRegion != region ||
	      header[38] != profile || !SusamuneGhostPersonalProfile(profile))) ||
	    (imported &&
	     (!GameRegionPairIsValid(sourceGameId, sourceRegion) ||
	      !SusamuneGhostPersonalProfile(header[38]))))
		return VALIDATE_INVALID;
	if (header[39] != SUSAMUNE_GHOST_RECORDING_POSE_QF ||
	    header[40] != (version >= SUSAMUNE_GHOST_FILE_VERSION_V4
	                      ? SUSAMUNE_GHOST_CODEC_POSE_ATTACHMENTS
	                      : SUSAMUNE_GHOST_CODEC_RAW) ||
	    header[41] != SUSAMUNE_GHOST_POSE_SAMPLE_SIZE ||
	    ReadBe16(header + 42) != SUSAMUNE_GHOST_TRANSFORM_INTERVAL_QF)
		return VALIDATE_INVALID;
	routeVariant = ReadBeS32(header + 48);
	if (!(portable
	          ? PortableRouteIsValid(header[44], header[45], header[46],
	                                 header[47], routeVariant)
	          : RouteIsValid(header[44], header[45], header[46], header[47],
	                         routeVariant)))
		return VALIDATE_INVALID;
	startQf = ReadBe32(header + 56);
	endQf = ReadBe32(header + 60);
	resultQf = ReadBe32(header + 52);
	if (startQf > SUSAMUNE_GHOST_QF_MAX || endQf > SUSAMUNE_GHOST_QF_MAX ||
	    endQf < startQf || ReadBe32(header + 64) == 0 ||
	    ReadBe32(header + 64) != endQf - startQf ||
	    ReadBe32(header + 64) > SusamuneGhostDurationLimit(version))
		return VALIDATE_INVALID;
	if (resultQf != SUSAMUNE_GHOST_RESULT_QF_NONE &&
	    (resultQf < startQf || resultQf > endQf))
		return VALIDATE_INVALID;
	if (header[95] != SUSAMUNE_GHOST_CHECKSUM_CRC32)
		return VALIDATE_FORWARD;
	if (!HeaderTextIsValid(header + 96, SUSAMUNE_GHOST_AUTHOR_SIZE,
	                       header[92], false) ||
	    !HeaderTextIsValid(header + 120, SUSAMUNE_GHOST_NAME_SIZE,
	                       header[93], true) ||
	    !HeaderTextIsValid(header + 168, SUSAMUNE_GHOST_PROFILE_NAME_SIZE,
	                       header[94], false) ||
	    (ReadBe32(header + 84) == 0 && ReadBe32(header + 88) == 0))
		return VALIDATE_INVALID;

	return VALIDATE_OK;
}

static u8 SanitizeText(char *out, u32 capacity, const u8 *in, u32 length)
{
	u32 i;
	u32 count = length < capacity - 1 ? length : capacity - 1;

	for (i = 0; i < count; i++)
		out[i] = in[i] >= 0x20 && in[i] <= 0x7e ? (char)in[i] : '?';
	out[count] = '\0';
	return (u8)count;
}

static void FillInfo(struct SusamuneGhostSlotInfo *info, const u8 *header,
	                 u32 generation, u16 flags)
{
	memset(info, 0, sizeof(*info));
	info->generation = generation;
	info->payloadSize = ReadBe32(header + 8);
	info->gameId = ReadBe32(header + 32);
	info->sampleCount = ReadBe32(header + 68);
	info->durationQf = ReadBe32(header + 64);
	info->resultQf = ReadBe32(header + 52);
	info->requiredFeatures = ReadBe32(header + 24);
	info->runFlags = ReadBe32(header + 28);
	info->routeVariant = ReadBeS32(header + 48);
	info->status = SUSAMUNE_GHOST_STATUS_OK;
	info->flags = SUSAMUNE_GHOST_SLOT_PRESENT | flags;
	info->sampleIntervalQf = ReadBe16(header + 42);
	info->routeArea = header[44];
	info->routeEpisode = header[45];
	info->routeParentArea = header[46];
	info->routeFlags = header[47];
	info->recordingMode = header[39];
	info->sampleCodec = header[40];
	info->discRevision = header[36];
	info->region = header[37];
	info->authorLength = SanitizeText(info->author, sizeof(info->author),
	                                header + 96, header[92]);
	info->nameLength = SanitizeText(info->name, sizeof(info->name),
	                              header + 120, header[93]);
	info->canonicalVersion = (u8)ReadBe16(header + 4);
#ifdef MS_RECORDING_CATALOG_ADMISSION
    if (ReadBe32(header) == MS_RECORDING_MANIFEST_MAGIC) {
        info->flags |= SUSAMUNE_GHOST_SLOT_STREAMED;
        info->canonicalVersion = MS_RECORDING_CATALOG_VERSION;
    }
#endif
}
