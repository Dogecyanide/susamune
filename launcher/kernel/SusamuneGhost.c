#include "MoonshineNetLog.h"
#include "GhostTraceBranchStorage.h"
#include "susamune/ghost_trace_stream_storage.h"
/*

Susamune ghost storage (Nintendont kernel side).

The PPC owns the request cache line and an immutable transfer payload until
acknowledgement. The ARM owns the response line and performs at most one fixed
file-header operation or 16 KiB of payload I/O per DI-idle service pass.

*/

#include "SusamuneGhost.h"
#include "SusamuneTransfer.h"
#include "SusamuneCfg.h"
#include "GhostServiceNative.h"
#include "GhostServiceAccount.h"
#if TIMEWARP_LIVE_RACING
#include "MoonshineNetLog.h"
#endif
#include "string.h"
#include "debug.h"
#include "ff_utf8.h"

#include "susamune/ghost_format.h"
#include "susamune/ghost_camera.h"
#include "susamune/data_paths.h"
#include "susamune/ghost_storage.h"
#include "susamune/mod_bin.h"

extern u32 GAME_ID;

#define GHOST_BANK_COUNT 2u
#define GHOST_PATH_SIZE  128u
#define GHOST_PAYLOAD (SusamuneTransferActive() ? SusamuneTransferGhostBase() : SUSAMUNE_GHOST_STORAGE_DATA_PHYS_PTR)

typedef char ImportGhostPathFits[
	sizeof("1:" MOONSHINE_DATA_ROOT MOONSHINE_GHOSTS_DIR "/import/") - 1u +
	        SUSAMUNE_GHOST_IMPORT_LEAF_SIZE <= GHOST_PATH_SIZE
		? 1 : -1];

enum BankState
{
	BANK_EMPTY,
	BANK_INVALID,
	BANK_VALID,
	BANK_UNSAFE
};

struct BankInfo
{
	u32 generation;
	u32 flags;
	u32 payloadSize;
	u32 durationQf;
	u32 payloadChecksum;
	u8 state;
};

struct SlotCatalog
{
	struct BankInfo bank[GHOST_BANK_COUNT];
	struct SusamuneGhostSlotInfo info;
	s8 activeBank;
	u8 unsafe;
};

struct ImportedSlot
{
	struct SusamuneGhostSlotInfo info;
	char leaf[SUSAMUNE_GHOST_IMPORT_LEAF_SIZE];
};

enum OperationPhase
{
	OP_IDLE,
	OP_VALIDATE_SAVE,
	OP_PERSONAL_SCAN_OPEN,
	OP_PERSONAL_SCAN_NEXT,
	OP_SCAN_ENVELOPES,
	OP_SCAN_ACTIVE_HEADERS,
	OP_SAVE_OPEN,
	OP_SAVE_DATA,
	OP_SAVE_SYNC_DATA,
	OP_SAVE_COMMIT,
	OP_SAVE_FINISH,
	OP_LOAD_OPEN,
	OP_LOAD_DATA,
	OP_LOAD_CLOSE,
	OP_VALIDATE_LOAD,
	OP_EXPORT_OPEN,
	OP_EXPORT_DATA,
	OP_EXPORT_SYNC_DATA,
	OP_EXPORT_COMMIT,
	OP_EXPORT_FINISH,
	OP_IMPORT_SCAN_OPEN,
	OP_IMPORT_SCAN_NEXT,
	OP_IMPORT_SCAN_FILE_OPEN,
	OP_IMPORT_SCAN_FILE_READ,
	OP_IMPORT_SCAN_FILE_CLOSE,
	OP_DELETE_OPEN,
	OP_DELETE_FINISH,
	OP_DELETE_RECLAIM,
	OP_IMPORTED_DELETE,
    OP_WEB_WAIT, OP_WEB_READ, OP_WEB_VALIDATE
};

enum ValidateResult
{
	VALIDATE_INVALID,
	VALIDATE_OK,
	VALIDATE_FORWARD
};

enum ReadResult
{
	READ_INVALID,
	READ_MISSING,
	READ_VALID,
	READ_UNSAFE,
	READ_IO
};

struct GhostRequest
{
	u32 seq;
	u16 command;
	u16 profile;
	u32 slot;
	u32 payloadSize;
	u32 flags;
	u32 expectedGeneration;
	char leaf[SUSAMUNE_GHOST_IMPORT_LEAF_SIZE];
};

struct ImportedCatalogWork
{
	struct ImportedSlot catalog[1];
	struct ImportedSlot candidate;
	DIR dir;
	FILINFO entry;
};

// Requests are serialized; switching profiles invalidates the old view.
union GhostCatalogStorage
{
	struct SlotCatalog personal[1];
	struct ImportedCatalogWork imported;
};

// Personal slot scans run while the overlaid directory iterator stays open.
typedef char PersonalCatalogDoesNotOverlapDirectory[
	sizeof(struct SlotCatalog) <=
	        __builtin_offsetof(struct ImportedCatalogWork, dir) ? 1 : -1];

static union GhostCatalogStorage CatalogStorage;
#define Catalog         CatalogStorage.personal
#define ImportedCatalog CatalogStorage.imported.catalog
#define ImportCandidate  CatalogStorage.imported.candidate
#define ImportDir        CatalogStorage.imported.dir
#define ImportEntry      CatalogStorage.imported.entry
static struct GhostRequest Request;
#if MOONSHINE_LOADING_DIAGNOSTICS
static unsigned RequestStartedTick;
#endif
static struct SusamuneGhostStorageEnvelope IoEnvelope;
static FIL IoFile;
static bool IoFileOpen;
static bool Retiring, CloseFailed;
static char WebFinalPath[GHOST_PATH_SIZE], WebTempPath[GHOST_PATH_SIZE];
static u32 WebBytes;
static bool GhostSupported;
static bool CatalogReady;
static bool CatalogUnsafe;
static bool ImportedCatalogReady;
static u16 CatalogProfile;
static u16 CatalogCount;
static u16 ImportedCatalogCount;
static u32 CatalogDurationQf;
static u32 GhostAckSeq;
static u32 ScanFile;
static struct SusamuneGhostSlotInfo ScanBankInfo[GHOST_BANK_COUNT];
static int ScanIoError;
static enum OperationPhase Phase;
static u32 IoOffset;
static u32 IoChecksum;
static u8 IoBank;
static u8 LoadAttemptedBanks;
static bool ImportDirOpen;
static u32 ImportCandidateSize;
static u32 ImportPrefixSize;
static struct SusamuneGhostCatalogPage Page;
static bool DirectoryScan;
static bool AutoProbe;
static u32 ScanSlot;
static u32 AutoReuseSlot;
static u32 PageOrdinal;
static u64 PageDuration;

// Four adjacent pages per namespace, inside the existing ARM data reservation.
// Only metadata is cached; loads and mutations always revalidate their files.
#define GHOST_LIST_CACHE_ENTRIES 64u
struct GhostListCache
{
	struct SusamuneGhostCatalogEntry entries[GHOST_LIST_CACHE_ENTRIES];
	u64 duration;
	u32 first;
	u32 count;
	u32 total;
	u32 nextSlot;
	u16 profile;
	// ARM bool is a word; keep this marker byte-sized to retain the cache stride.
	u8 valid;
	u32 directoryFingerprint;
};
typedef char GhostListCacheStrideUnchanged[
    sizeof(struct GhostListCache) == GHOST_LIST_CACHE_ENTRIES *
        sizeof(struct SusamuneGhostCatalogEntry) + 32u ? 1 : -1];
/* Online TLS survives page leases; local scans reclaim these metadata caches. */
static union {
    struct GhostListCache list[2];
    unsigned char session[GHOST_SERVICE_SESSION_SIZE];
} BrowseMemory ALIGNED(32);
#define ListCache BrowseMemory.list
typedef char WebFitsListCache[sizeof(BrowseMemory.session)<=sizeof(ListCache)?1:-1];
static bool WebCacheOwned;
static struct GhostAccount WebAccount;
static struct GhostServiceUpload WebUpload;
static bool WebAccountLoaded;
static u32 WebAccountGeneration;
static u8 WebAccountBank;
static void WebAccountStart(unsigned action, unsigned bytes);
static bool ScanCaching;
static bool CachedSaveScan;
static u32 ScanFingerprint;

static void FingerprintPersonalName(u32 id, u8 bank)
{
	unsigned i;
	if (!ScanFingerprint) return;
	for (i = 0; i < 4; ++i, id >>= 8)
		ScanFingerprint = (ScanFingerprint ^ (id & 255u)) * 16777619u;
	ScanFingerprint = (ScanFingerprint ^ bank) * 16777619u;
}

static struct GhostListCache *RequestListCache(void)
{
	return &ListCache[Request.profile == SUSAMUNE_GHOST_IMPORTED_PROFILE];
}

static void AppendPageEntry(u32 id, const struct SusamuneGhostSlotInfo *info,
	                       const char *leaf)
{
	struct SusamuneGhostCatalogEntry *entry = NULL;
	struct GhostListCache *cache = RequestListCache();
	if (ScanCaching && PageOrdinal >= cache->first &&
	    PageOrdinal - cache->first < GHOST_LIST_CACHE_ENTRIES)
		entry = &cache->entries[cache->count++];
	if (entry)
	{
		entry->id = id;
		entry->info = *info;
		if (leaf) memcpy(entry->leaf, leaf, sizeof(entry->leaf));
		else memset(entry->leaf, 0, sizeof(entry->leaf));
	}
	if (PageOrdinal >= Page.first && Page.count < SUSAMUNE_GHOST_CATALOG_PAGE_ENTRIES)
	{
		struct SusamuneGhostCatalogEntry *out = &Page.entries[Page.count++];
		if (entry) *out = *entry;
		else
		{
			out->id = id;
			out->info = *info;
			if (leaf) memcpy(out->leaf, leaf, sizeof(out->leaf));
		}
	}
	++PageOrdinal;
}


static const u8 *ValidationBytes;
static u32 ValidationSize;
static u32 ValidationOffset;
static u32 ValidationPoseEnd;
static u32 ValidationInputEnd;
static u32 ValidationTeachingEnd;
static u32 ValidationCameraEnd, ValidationContextCrc, ValidationContextCount;
static u32 ValidationCameraCrc, ValidationCameraCount;
static u32 ValidationPreviousCameraQf, ValidationPreviousCameraSegment;
static u32 ValidationInputStride;
static u32 ValidationTeachingCrc;
static u32 ValidationPreviousInputQf;
static u32 ValidationInputCount;
static u32 ValidationSplitCount;
static u32 ValidationPreviousSplitQf;
static u32 ValidationPayloadCrc;
static u32 ValidationFileCrc;
static u32 ValidationRawCrc;
static u32 ValidationSample;
static u32 ValidationSegmentDuration;
static u16 ValidationSegment;
static u16 ValidationSegmentCount;
static u16 ValidationVersion;
static u8 ValidationAttachmentCount;
static u16 ValidationAttachmentFlags;

static const char *GhostRegion;
static u8 GhostRegionId;

static int GhostCloseFile(FIL *file)
{
	int result = f_close(file);
	if (result != FR_OK) CloseFailed = true;
	return result;
}

static int GhostCloseDirectory(DIR *directory)
{
	int result = f_closedir(directory);
	if (result != FR_OK) CloseFailed = true;
	return result;
}

/* Failed closes can leave live FatFS objects, including stack-local readers. */
#define f_close GhostCloseFile
#define f_closedir GhostCloseDirectory

static volatile struct SusamuneGhostStorageMailbox *GhostBlock(void)
{
	return SUSAMUNE_GHOST_STORAGE_PHYS_PTR;
}





#define MS_RECORDING_CATALOG_ADMISSION 1
#include "GhostCanonical.inc"

static u32 ReadBe24(const u8 *p)
{
	return ((u32)p[0] << 16) | ((u32)p[1] << 8) | p[2];
}

static s32 ReadBeS24(const u8 *p)
{
	u32 value = ReadBe24(p);
	return (s32)(value | ((value & 0x800000u) ? 0xFF000000u : 0u));
}







static void WriteBe16(u8 *p, u16 value)
{
	p[0] = (u8)(value >> 8);
	p[1] = (u8)value;
}

static void WriteBe32(u8 *p, u32 value)
{
	p[0] = (u8)(value >> 24);
	p[1] = (u8)(value >> 16);
	p[2] = (u8)(value >> 8);
	p[3] = (u8)value;
}

static void EncodeEnvelope(const struct SusamuneGhostStorageEnvelope *e, u8 *raw)
{
	u32 i;
	WriteBe32(raw, e->magic);
	WriteBe16(raw + 4, e->version);
	WriteBe16(raw + 6, e->headerSize);
	WriteBe32(raw + 8, e->generation);
	WriteBe32(raw + 12, e->flags);
	WriteBe32(raw + 16, e->gameId);
	WriteBe16(raw + 20, e->profile);
	WriteBe16(raw + 22, e->slot);
	WriteBe32(raw + 24, e->payloadSize);
	WriteBe32(raw + 28, e->durationQf);
	WriteBe32(raw + 32, e->payloadChecksum);
	WriteBe32(raw + 36, e->headerChecksum);
	for (i = 0; i < 6; ++i)
		WriteBe32(raw + 40 + i * 4, e->reserved[i]);
}

static void DecodeEnvelope(const u8 *raw, struct SusamuneGhostStorageEnvelope *e)
{
	u32 i;
	e->magic = ReadBe32(raw);
	e->version = ReadBe16(raw + 4);
	e->headerSize = ReadBe16(raw + 6);
	e->generation = ReadBe32(raw + 8);
	e->flags = ReadBe32(raw + 12);
	e->gameId = ReadBe32(raw + 16);
	e->profile = ReadBe16(raw + 20);
	e->slot = ReadBe16(raw + 22);
	e->payloadSize = ReadBe32(raw + 24);
	e->durationQf = ReadBe32(raw + 28);
	e->payloadChecksum = ReadBe32(raw + 32);
	e->headerChecksum = ReadBe32(raw + 36);
	for (i = 0; i < 6; ++i)
		e->reserved[i] = ReadBe32(raw + 40 + i * 4);
}

static int WriteEnvelope(FIL *file,
	                     const struct SusamuneGhostStorageEnvelope *e, UINT *wrote)
{
	u8 raw[SUSAMUNE_GHOST_ENVELOPE_SIZE];
	EncodeEnvelope(e, raw);
	return f_write(file, raw, sizeof(raw), wrote);
}

static u32 EnvelopeChecksum(const struct SusamuneGhostStorageEnvelope *envelope)
{
	u8 raw[SUSAMUNE_GHOST_ENVELOPE_SIZE];
	EncodeEnvelope(envelope, raw);
	WriteBe32(raw + 36, 0);
	return CrcUpdate(SUSAMUNE_GHOST_CRC32_INIT, raw, sizeof(raw)) ^
	       SUSAMUNE_GHOST_CRC32_XOR_OUT;
}















static bool ValidateV3SegmentTable(const u8 *bytes, bool portable)
{
	const u8 *table = bytes + SUSAMUNE_GHOST_V3_SEGMENT_TABLE_OFFSET;
	u16 count = ReadBe16(bytes + SUSAMUNE_GHOST_V3_SEGMENT_COUNT_OFFSET);
	u32 totalSamples = ReadBe32(bytes + 68);
	u32 expectedSample = 0;
	u32 previousEnd = 0;
	u32 firstStart = 0;
	u32 lastStart = 0;
	u32 lastEnd = 0;
	u32 crc;
	u32 i;
	const u8 *segment;
	u32 firstSample;
	u32 sampleCount;
	u32 startQf;
	u32 endQf;
	s32 routeVariant;

	crc = CrcUpdate(SUSAMUNE_GHOST_CRC32_INIT, table,
	                SUSAMUNE_GHOST_V3_SEGMENT_TABLE_SIZE) ^
	      SUSAMUNE_GHOST_CRC32_XOR_OUT;
	if (crc != ReadBe32(bytes +
	                    SUSAMUNE_GHOST_V3_SEGMENT_CHECKSUM_OFFSET) ||
	    !BytesAreZero(table + count * SUSAMUNE_GHOST_V3_SEGMENT_SIZE,
	                  SUSAMUNE_GHOST_V3_SEGMENT_TABLE_SIZE -
	                      count * SUSAMUNE_GHOST_V3_SEGMENT_SIZE))
		return false;

	for (i = 0; i < count; i++)
	{
		segment = table + i * SUSAMUNE_GHOST_V3_SEGMENT_SIZE;
		firstSample = ReadBe32(segment);
		sampleCount = ReadBe32(segment + 4);
		startQf = ReadBe32(segment + 8);
		endQf = ReadBe32(segment + 12);
		routeVariant = ReadBeS32(segment + 16);
		if (firstSample != expectedSample || sampleCount == 0 ||
		    expectedSample > totalSamples ||
		    sampleCount > totalSamples - expectedSample ||
		    startQf > SUSAMUNE_GHOST_QF_MAX ||
		    endQf > SUSAMUNE_GHOST_QF_MAX || endQf < startQf ||
		    (i != 0 && startQf < previousEnd) ||
		    !(portable
		          ? PortableRouteIsValid(segment[20], segment[21], segment[22],
		                                 segment[23], routeVariant)
		          : RouteIsValid(segment[20], segment[21], segment[22],
		                         segment[23], routeVariant)) ||
		    !SusamuneGhostSegmentMetadataValid(ReadBe16(bytes + 4), i,
		        ReadBe32(segment + 24), ReadBe32(segment + 28)))
			return false;
		if (i == 0)
		{
			firstStart = startQf;
			if (segment[20] != bytes[44] || segment[21] != bytes[45] ||
			    segment[22] != bytes[46] || segment[23] != bytes[47] ||
			    routeVariant != ReadBeS32(bytes + 48))
				return false;
		}
		expectedSample += sampleCount;
		previousEnd = endQf;
		lastStart = startQf;
		lastEnd = endQf;
	}

	if (expectedSample != totalSamples || firstStart != ReadBe32(bytes + 56) ||
	    lastEnd != ReadBe32(bytes + 60))
		return false;
	if (ReadBe32(bytes + 52) != SUSAMUNE_GHOST_RESULT_QF_NONE &&
	    (ReadBe32(bytes + 52) < lastStart ||
	     ReadBe32(bytes + 52) > lastEnd))
		return false;
	return true;
}

static enum ReadResult ReadEnvelope(u16 profile,u32 slot,u8 bank,struct SusamuneGhostStorageEnvelope *envelope,u8 *header,int *ioError);
static bool RecordingSourceValid(const u8 *manifest)
{
#if MOONSHINE_GHOST_TRACE
    struct MsTraceFileIdentity source;
    return GhostTraceFileIdentity(ReadBe32(manifest+16),ReadBe32(manifest+20),GAME_ID,&source) &&
        source.capabilities==ReadBe32(manifest+24) && source.bytes==ReadBe32(manifest+224) &&
        source.chunks==ReadBe32(manifest+228) && source.headerHash==ReadBe32(manifest+232) &&
        source.footerHash==ReadBe32(manifest+236);
#else
    (void)manifest;return false;
#endif
}
#if MOONSHINE_GHOST_TRACE
struct RecordingPinTransaction { u32 sequence,operation;struct MsTraceBranch pin;u8 manifest[256]; };
#define RECORDING_PIN ((struct RecordingPinTransaction*)(MS_TRACE_CONTROL_PHYS+MS_TRACE_LIBRARY_PIN_OFFSET))
typedef char RecordingPinFits[MS_TRACE_LIBRARY_PIN_OFFSET+sizeof(struct RecordingPinTransaction)<=MS_TRACE_READ_ARM_OFFSET?1:-1];
#endif
static bool PrepareRecordingPin(const u8 *manifest,u32 generation,u32 checksum,bool saving)
{
#if MOONSHINE_GHOST_TRACE
    struct RecordingPinTransaction*t=RECORDING_PIN;struct MsTraceBranch*b=&t->pin;unsigned region;
    if(!GhostTraceStorageAdmitted()||!generation||Request.slot==0xffffffffu)return false;
    t->sequence=0;memcpy(t->manifest,manifest,256);
    if((CrcUpdate(SUSAMUNE_GHOST_CRC32_INIT,t->manifest,256)^SUSAMUNE_GHOST_CRC32_XOR_OUT)!=checksum ||
       !MsRecordingManifestValid(t->manifest,256,GAME_ID,Request.profile))return false;
    manifest=t->manifest;memset(b,0,sizeof(*b));region=GAME_ID==0x474d534au?1:GAME_ID==0x474d5345u?2:3;
    b->nonce=b->parent.nonce=ReadBe32(manifest+16);b->run=b->parent.run=ReadBe32(manifest+20);
    b->game=GAME_ID;b->capabilities=ReadBe32(manifest+24);b->parent.generation=ReadBe32(manifest+240);
    b->parent.frame=ReadBe32(manifest+68);b->parent.chunk=ReadBe32(manifest+228);
    b->fence.fileBytes=ReadBe32(manifest+224)-32;b->fence.headerHash=ReadBe32(manifest+232);
    b->ownerKind=MS_TRACE_OWNER_LIBRARY|(region<<8)|Request.profile;b->ownerId=Request.slot+1;b->ownerGeneration=generation;
    if(!MsTraceBranchValid(b,MS_TRACE_BRANCH_PIN)||(saving&&(!RecordingSourceValid(manifest)||!GhostTraceBranchStore(b,MS_TRACE_BRANCH_PIN))))return false;
    t->operation=saving?SUSAMUNE_GHOST_CMD_SAVE:SUSAMUNE_GHOST_CMD_DELETE;t->sequence=Request.seq;return true;
#else
    (void)manifest;(void)generation;(void)checksum;(void)saving;return false;
#endif
}
static const u8 *RecordingSaveBytes(void)
{
#if MOONSHINE_GHOST_TRACE
    if(IoEnvelope.version==SUSAMUNE_GHOST_ENVELOPE_VERSION_STREAMED){
        const struct RecordingPinTransaction*t=RECORDING_PIN;
        return GhostTraceStorageAdmitted()&&t->sequence==Request.seq&&t->operation==SUSAMUNE_GHOST_CMD_SAVE?t->manifest:NULL;
    }
#endif
    return (const u8*)GHOST_PAYLOAD;
}
static bool PrepareRecordingDelete(u8 bank)
{
    struct SusamuneGhostStorageEnvelope envelope;u8 header[256];int error=0;
    if(ReadEnvelope(Request.profile,Request.slot,bank,&envelope,header,&error)!=READ_VALID ||
       envelope.generation!=Request.expectedGeneration || envelope.version!=SUSAMUNE_GHOST_ENVELOPE_VERSION_STREAMED)return false;
    return PrepareRecordingPin(header,envelope.generation,envelope.payloadChecksum,false);
}
static void ReleaseRecordingPin(void)
{
#if MOONSHINE_GHOST_TRACE
    struct RecordingPinTransaction*t=RECORDING_PIN;
    if(GhostTraceStorageAdmitted()&&t->sequence==Request.seq&&t->operation==SUSAMUNE_GHOST_CMD_DELETE){
        GhostTraceBranchRelease(&t->pin,MS_TRACE_BRANCH_PIN);t->sequence=0;
    }
#endif
}

static enum ValidateResult BeginCanonicalValidation(const u8 *bytes,
	                                                  u32 size,
	                                                  u16 profile,
	                                                  bool imported)
{
	enum ValidateResult result =
		ValidateCanonicalHeader(bytes, size, profile, imported, GAME_ID, GhostRegionId);
	bool portable;

	if (result != VALIDATE_OK)
		return result;
    if (ReadBe32(bytes)==MS_RECORDING_MANIFEST_MAGIC) {
        if (!RecordingSourceValid(bytes)) return VALIDATE_INVALID;
        ValidationBytes=bytes;ValidationSize=size;ValidationOffset=size;
        ValidationVersion=MS_RECORDING_CATALOG_VERSION;
        ValidationRawCrc=CrcUpdate(SUSAMUNE_GHOST_CRC32_INIT,bytes,size)^SUSAMUNE_GHOST_CRC32_XOR_OUT;
        return VALIDATE_OK;
    }
	portable = imported && ReadBe32(bytes + 32) != GAME_ID;
	if (ReadBe32(bytes + 8) != size)
		return VALIDATE_INVALID;
	if (!ValidateV3SegmentTable(bytes, portable))
		return VALIDATE_INVALID;

	ValidationPoseEnd = SUSAMUNE_GHOST_V4_SAMPLE_DATA_OFFSET +
	    ReadBe32(bytes + 68) * SUSAMUNE_GHOST_POSE_SAMPLE_SIZE;
	ValidationInputEnd = ValidationPoseEnd;
	ValidationTeachingEnd = size;
	ValidationCameraEnd = size;
	ValidationContextCrc = SUSAMUNE_GHOST_CRC32_INIT;
	ValidationContextCount = 0;
	ValidationCameraCrc = SUSAMUNE_GHOST_CRC32_INIT;
	ValidationCameraCount = ValidationPreviousCameraQf = ValidationPreviousCameraSegment = 0;
	ValidationInputCount = 0;
	ValidationSplitCount = 0;
	ValidationPreviousInputQf = 0;
	ValidationPreviousSplitQf = 0;
	ValidationTeachingCrc = SUSAMUNE_GHOST_CRC32_INIT;
	ValidationInputStride = SusamuneGhostInputStride(ReadBe16(bytes + 4));
	if (ReadBe16(bytes + 4) >= SUSAMUNE_GHOST_FILE_VERSION_V5)
	{
		const u8 *teaching = bytes + ValidationPoseEnd;
		u32 teachingSize = size - ValidationPoseEnd;
		if (ReadBe16(bytes + 4) >= SUSAMUNE_GHOST_FILE_VERSION_V8) {
			if (ReadBe32(teaching + 8) > SUSAMUNE_GHOST_V6_INPUT_MAX_COUNT ||
			    ReadBe32(teaching + 12) > SUSAMUNE_GHOST_SPLIT_MAX_COUNT) return VALIDATE_INVALID;
			teachingSize = SUSAMUNE_GHOST_TEACHING_HEADER_SIZE +
			    ReadBe32(teaching + 8) * ValidationInputStride +
			    ReadBe32(teaching + 12) * SUSAMUNE_GHOST_SPLIT_SAMPLE_SIZE;
			if (teachingSize > size - ValidationPoseEnd) return VALIDATE_INVALID;
			ValidationTeachingEnd = ValidationPoseEnd + teachingSize;
			if (size - ValidationTeachingEnd < SUSAMUNE_GHOST_CAMERA_HEADER_SIZE ||
                ReadBe32(bytes + ValidationTeachingEnd + 8) > SUSAMUNE_GHOST_CAMERA_MAX_COUNT)
                return VALIDATE_INVALID;
            ValidationCameraEnd = ValidationTeachingEnd + SUSAMUNE_GHOST_CAMERA_HEADER_SIZE +
                ReadBe32(bytes + ValidationTeachingEnd + 8) * SUSAMUNE_GHOST_CAMERA_SAMPLE_SIZE;
            if (ValidationCameraEnd > size ||
                !SusamuneGhostCameraHeaderValid(bytes + ValidationTeachingEnd,
                    ValidationCameraEnd - ValidationTeachingEnd)) return VALIDATE_INVALID;
            if (ReadBe16(bytes + 4) >= SUSAMUNE_GHOST_FILE_VERSION_V10) {
                if (!SusamuneGhostContextHeaderValid(bytes + ValidationCameraEnd,
                        size - ValidationCameraEnd)) return VALIDATE_INVALID;
            } else if (ValidationCameraEnd != size) return VALIDATE_INVALID;
		}
		if (!SusamuneGhostTeachingHeaderValid(teaching, teachingSize) ||
		    teaching[5] != (ReadBe16(bytes + 4) >= SUSAMUNE_GHOST_FILE_VERSION_V10
                ? SUSAMUNE_GHOST_TEACHING_STEERING_VERSION
                : ReadBe16(bytes + 4) >= SUSAMUNE_GHOST_FILE_VERSION_V7
                ? SUSAMUNE_GHOST_TEACHING_VISUAL_VERSION
                : ReadBe16(bytes + 4) == SUSAMUNE_GHOST_FILE_VERSION_V6
		        ? SUSAMUNE_GHOST_TEACHING_FLUDD_VERSION : SUSAMUNE_GHOST_TEACHING_VERSION))
			return VALIDATE_INVALID;
		ValidationInputEnd = ValidationPoseEnd +
		    SUSAMUNE_GHOST_TEACHING_HEADER_SIZE +
		    ReadBe32(teaching + 8) * ValidationInputStride;
	}

	ValidationBytes = bytes;
	ValidationSize = size;
	ValidationOffset = SUSAMUNE_GHOST_V4_SAMPLE_DATA_OFFSET;
	ValidationPayloadCrc = SUSAMUNE_GHOST_CRC32_INIT;
	ValidationFileCrc = CrcUpdateHeader(SUSAMUNE_GHOST_CRC32_INIT,
	                                    bytes, 12, 16);
	ValidationRawCrc = CrcUpdate(SUSAMUNE_GHOST_CRC32_INIT, bytes,
	                             SUSAMUNE_GHOST_FILE_HEADER_SIZE);
	ValidationPayloadCrc = CrcUpdate(
		ValidationPayloadCrc,
		bytes + SUSAMUNE_GHOST_V3_SEGMENT_TABLE_OFFSET,
		SUSAMUNE_GHOST_V3_SEGMENT_TABLE_SIZE);
	ValidationFileCrc = CrcUpdate(
		ValidationFileCrc,
		bytes + SUSAMUNE_GHOST_V3_SEGMENT_TABLE_OFFSET,
		SUSAMUNE_GHOST_V3_SEGMENT_TABLE_SIZE);
	ValidationRawCrc = CrcUpdate(
		ValidationRawCrc,
		bytes + SUSAMUNE_GHOST_V3_SEGMENT_TABLE_OFFSET,
		SUSAMUNE_GHOST_V3_SEGMENT_TABLE_SIZE);
	ValidationSample = 0;
	ValidationSegmentDuration = 0;
	ValidationSegment = 0;
	ValidationSegmentCount = ReadBe16(
		bytes + SUSAMUNE_GHOST_V4_SEGMENT_COUNT_OFFSET);
	ValidationVersion = ReadBe16(bytes + 4);
	ValidationAttachmentCount =
		ValidationVersion >= SUSAMUNE_GHOST_FILE_VERSION_V4
			? bytes[SUSAMUNE_GHOST_V4_ATTACHMENT_COUNT_OFFSET] : 0;
	ValidationAttachmentFlags =
		ValidationVersion >= SUSAMUNE_GHOST_FILE_VERSION_V4
			? ReadBe16(bytes + SUSAMUNE_GHOST_V4_ATTACHMENT_FLAGS_OFFSET) : 0;
	return VALIDATE_OK;
}

// Returns -1 while another bounded chunk remains, otherwise ValidateResult.
static int ContinueCanonicalValidation(void)
{
    if (ValidationVersion==MS_RECORDING_CATALOG_VERSION)
        return ValidationSize==MS_RECORDING_MANIFEST_BYTES &&
            MsRecordingManifestValid(ValidationBytes,ValidationSize,GAME_ID,Request.profile)
            ? VALIDATE_OK : VALIDATE_INVALID;
	u32 phaseEnd = ValidationPoseEnd;
	u32 stride = SUSAMUNE_GHOST_POSE_SAMPLE_SIZE;
	u32 remaining, chunk, end;
	if (ValidationOffset >= ValidationPoseEnd)
	{
		if (ValidationOffset == ValidationPoseEnd) {
			phaseEnd += SUSAMUNE_GHOST_TEACHING_HEADER_SIZE;
			stride = SUSAMUNE_GHOST_TEACHING_HEADER_SIZE;
		} else if (ValidationOffset < ValidationInputEnd) {
			phaseEnd = ValidationInputEnd;
			stride = ValidationInputStride;
		} else if (ValidationOffset < ValidationTeachingEnd) {
			phaseEnd = ValidationTeachingEnd;
			stride = SUSAMUNE_GHOST_SPLIT_SAMPLE_SIZE;
		} else if (ValidationOffset == ValidationTeachingEnd) {
			phaseEnd = ValidationTeachingEnd + SUSAMUNE_GHOST_CAMERA_HEADER_SIZE;
			stride = SUSAMUNE_GHOST_CAMERA_HEADER_SIZE;
		} else if (ValidationOffset < ValidationCameraEnd) {
			phaseEnd = ValidationCameraEnd;
			stride = SUSAMUNE_GHOST_CAMERA_SAMPLE_SIZE;
        } else if (ValidationOffset == ValidationCameraEnd) {
            phaseEnd = ValidationCameraEnd + SUSAMUNE_GHOST_CONTEXT_HEADER_SIZE;
            stride = SUSAMUNE_GHOST_CONTEXT_HEADER_SIZE;
        } else {
            phaseEnd = ValidationSize;
            stride = SUSAMUNE_GHOST_CONTEXT_RECORD_SIZE;
        }
	}
	remaining = phaseEnd - ValidationOffset;
	chunk = remaining > SUSAMUNE_GHOST_STORAGE_CHUNK_SIZE
	              ? SUSAMUNE_GHOST_STORAGE_CHUNK_SIZE : remaining;
	chunk -= chunk % stride;
	end = ValidationOffset + chunk;
	u32 delta;
	u32 segmentFirst;
	u32 segmentSamples;
	u32 segmentDuration;
	bool segmentLast;
	s32 position;
	u32 animation;
	u8 yoshi;
	u8 held;
	const u8 *sample;
	const u8 *segment;

	ValidationPayloadCrc = CrcUpdate(ValidationPayloadCrc,
	                                 ValidationBytes + ValidationOffset, chunk);
	ValidationFileCrc = CrcUpdate(ValidationFileCrc,
	                              ValidationBytes + ValidationOffset, chunk);
	ValidationRawCrc = CrcUpdate(ValidationRawCrc,
	                             ValidationBytes + ValidationOffset, chunk);

	if (ValidationOffset > ValidationPoseEnd && ValidationOffset < ValidationTeachingEnd)
		ValidationTeachingCrc = CrcUpdate(ValidationTeachingCrc,
		    ValidationBytes + ValidationOffset, chunk);
	if (ValidationOffset > ValidationTeachingEnd && ValidationOffset < ValidationCameraEnd)
		ValidationCameraCrc = CrcUpdate(ValidationCameraCrc,
		    ValidationBytes + ValidationOffset, chunk);
    if (ValidationOffset > ValidationCameraEnd)
        ValidationContextCrc = CrcUpdate(ValidationContextCrc,
            ValidationBytes + ValidationOffset, chunk);
	while (ValidationOffset < end)
	{
		sample = ValidationBytes + ValidationOffset;
        if (ValidationVersion >= SUSAMUNE_GHOST_FILE_VERSION_V10 &&
            ValidationOffset >= ValidationCameraEnd) {
            u32 contextSegment;
            const u8 *previous;
            if (ValidationOffset == ValidationCameraEnd) {
                ValidationOffset += SUSAMUNE_GHOST_CONTEXT_HEADER_SIZE;
                continue;
            }
            contextSegment = ReadBe16(sample + 24);
            if (contextSegment >= ValidationSegmentCount) return VALIDATE_INVALID;
            segment = ValidationBytes + SUSAMUNE_GHOST_V4_SEGMENT_TABLE_OFFSET +
                contextSegment * SUSAMUNE_GHOST_V4_SEGMENT_SIZE;
            previous = ValidationContextCount ? sample - SUSAMUNE_GHOST_CONTEXT_RECORD_SIZE : 0;
            if (!SusamuneGhostContextRecordValid(sample, ValidationSegmentCount,
                    ValidationInputCount, ReadBe32(segment + 8), ReadBe32(segment + 12), previous))
                return VALIDATE_INVALID;
            ++ValidationContextCount;
            ValidationOffset += SUSAMUNE_GHOST_CONTEXT_RECORD_SIZE;
            continue;
        }
		if (ValidationOffset >= ValidationTeachingEnd) {
			u32 cameraSegment;
			if (ValidationOffset == ValidationTeachingEnd) {
				ValidationOffset += SUSAMUNE_GHOST_CAMERA_HEADER_SIZE;
				continue;
			}
			cameraSegment = sample[23] & 63u;
			if (cameraSegment >= ValidationSegmentCount) return VALIDATE_INVALID;
			segment = ValidationBytes + SUSAMUNE_GHOST_V4_SEGMENT_TABLE_OFFSET +
			    cameraSegment * SUSAMUNE_GHOST_V4_SEGMENT_SIZE;
			if (!SusamuneGhostCameraSampleValid(sample, ReadBe32(segment + 8), ReadBe32(segment + 12),
			        ValidationPreviousCameraQf, cameraSegment, ValidationPreviousCameraSegment,
			        ValidationCameraCount == 0)) return VALIDATE_INVALID;
			ValidationPreviousCameraQf = ReadBe32(sample);
			ValidationPreviousCameraSegment = cameraSegment;
			++ValidationCameraCount;
			ValidationOffset += SUSAMUNE_GHOST_CAMERA_SAMPLE_SIZE;
			continue;
		}
		if (ValidationOffset >= ValidationPoseEnd)
		{
			if (ValidationOffset == ValidationPoseEnd) {
				ValidationOffset += SUSAMUNE_GHOST_TEACHING_HEADER_SIZE;
				continue;
			}
			if (ValidationOffset < ValidationInputEnd) {
				if (!SusamuneGhostTeachingInputValidVersion(sample,
				        ReadBe32(ValidationBytes + 56), ReadBe32(ValidationBytes + 60),
				        ValidationPreviousInputQf, ValidationInputCount == 0, ValidationVersion) ||
				    (ValidationVersion >= SUSAMUNE_GHOST_FILE_VERSION_V6 &&
                     !SusamuneGhostVisualValid(sample + 16,
                         ValidationVersion >= SUSAMUNE_GHOST_FILE_VERSION_V7)))
					return VALIDATE_INVALID;
				ValidationPreviousInputQf = SusamuneGhostTeachingInputQf(sample,
                    ReadBe32(ValidationBytes + 56), ValidationVersion);
				ValidationInputCount++;
				ValidationOffset += ValidationInputStride;
			} else {
				const u8 *first = ValidationBytes + ValidationInputEnd;
				if (!SusamuneGhostTeachingSplitValid(sample,
				        ReadBe32(ValidationBytes + 56), ReadBe32(ValidationBytes + 60),
				        ValidationPreviousSplitQf, ReadBe16(first + 8),
				        ReadBe32(first + 4), ValidationSplitCount))
					return VALIDATE_INVALID;
				ValidationPreviousSplitQf = ReadBe32(sample);
				ValidationSplitCount++;
				ValidationOffset += SUSAMUNE_GHOST_SPLIT_SAMPLE_SIZE;
			}
			continue;
		}
		position = ReadBeS24(sample + 4);
		if (position < -SUSAMUNE_GHOST_MAX_POSITION_FIXED ||
		    position > SUSAMUNE_GHOST_MAX_POSITION_FIXED)
			return VALIDATE_INVALID;
		position = ReadBeS24(sample + 7);
		if (position < -SUSAMUNE_GHOST_MAX_POSITION_FIXED ||
		    position > SUSAMUNE_GHOST_MAX_POSITION_FIXED)
			return VALIDATE_INVALID;
		position = ReadBeS24(sample + 10);
		if (position < -SUSAMUNE_GHOST_MAX_POSITION_FIXED ||
		    position > SUSAMUNE_GHOST_MAX_POSITION_FIXED)
			return VALIDATE_INVALID;
		animation = ReadBe24(sample + 13);
		if ((animation >> 15) > SUSAMUNE_GHOST_ANIMATION_ID_MAX)
			return VALIDATE_INVALID;
		if (ValidationVersion == SUSAMUNE_GHOST_FILE_VERSION_V3)
		{
			if ((animation & SUSAMUNE_GHOST_ANIMATION_RESERVED_MASK) != 0)
				return VALIDATE_INVALID;
		}
		else
		{
			yoshi = (animation >> SUSAMUNE_GHOST_V4_YOSHI_SHIFT) &
			        SUSAMUNE_GHOST_V4_YOSHI_MASK;
			held = animation & SUSAMUNE_GHOST_V4_HELD_INDEX_MASK;
			if (yoshi > SUSAMUNE_GHOST_V4_YOSHI_UNKNOWN ||
			    (held != 0 && held > ValidationAttachmentCount &&
			     !(held == SUSAMUNE_GHOST_V4_HELD_UNKNOWN &&
			       (ValidationAttachmentFlags &
			        SUSAMUNE_GHOST_V4_ATTACHMENT_HELD_OVERFLOW) != 0)))
				return VALIDATE_INVALID;
		}

		delta = ReadBe16(sample + 2);
		if (ValidationSegment >= ValidationSegmentCount)
			return VALIDATE_INVALID;
		segment = ValidationBytes +
			SUSAMUNE_GHOST_V3_SEGMENT_TABLE_OFFSET +
			ValidationSegment * SUSAMUNE_GHOST_V3_SEGMENT_SIZE;
		segmentFirst = ReadBe32(segment);
		segmentSamples = ReadBe32(segment + 4);
		segmentDuration = ReadBe32(segment + 12) - ReadBe32(segment + 8);
		segmentLast = ValidationSample + 1 ==
			segmentFirst + segmentSamples;
		if (ValidationSample == segmentFirst)
		{
			if (delta != 0)
				return VALIDATE_INVALID;
			ValidationSegmentDuration = 0;
		}
		else
		{
			if (delta == 0 ||
			    (delta < SUSAMUNE_GHOST_TRANSFORM_INTERVAL_QF &&
			     !segmentLast))
				return VALIDATE_INVALID;
			ValidationSegmentDuration += delta;
			if (ValidationSegmentDuration > segmentDuration)
				return VALIDATE_INVALID;
		}
		if (segmentLast)
		{
			if (ValidationSegmentDuration != segmentDuration)
				return VALIDATE_INVALID;
			ValidationSegment++;
		}
		ValidationSample++;
		ValidationOffset += SUSAMUNE_GHOST_POSE_SAMPLE_SIZE;
	}

	if (ValidationOffset < ValidationSize)
		return -1;
	if (ValidationOffset != ValidationSize)
		return VALIDATE_INVALID;

	if (ValidationVersion >= SUSAMUNE_GHOST_FILE_VERSION_V5 &&
	    ((ValidationTeachingCrc ^ SUSAMUNE_GHOST_CRC32_XOR_OUT) !=
	        ReadBe32(ValidationBytes + ValidationPoseEnd + 20) ||
	     ValidationInputCount != ReadBe32(ValidationBytes + ValidationPoseEnd + 8) ||
	     ValidationSplitCount != ReadBe32(ValidationBytes + ValidationPoseEnd + 12)))
		return VALIDATE_INVALID;

	if (ValidationVersion >= SUSAMUNE_GHOST_FILE_VERSION_V8 &&
	    (ValidationCameraCount != ReadBe32(ValidationBytes + ValidationTeachingEnd + 8) ||
	     (ValidationCameraCrc ^ SUSAMUNE_GHOST_CRC32_XOR_OUT) !=
	         ReadBe32(ValidationBytes + ValidationTeachingEnd + 16))) return VALIDATE_INVALID;

    if (ValidationVersion >= SUSAMUNE_GHOST_FILE_VERSION_V10 &&
        (ValidationContextCount != ReadBe32(ValidationBytes + ValidationCameraEnd + 8) ||
         (ValidationContextCrc ^ SUSAMUNE_GHOST_CRC32_XOR_OUT) !=
             ReadBe32(ValidationBytes + ValidationCameraEnd + 16))) return VALIDATE_INVALID;

	ValidationPayloadCrc ^= SUSAMUNE_GHOST_CRC32_XOR_OUT;
	ValidationFileCrc ^= SUSAMUNE_GHOST_CRC32_XOR_OUT;
	ValidationRawCrc ^= SUSAMUNE_GHOST_CRC32_XOR_OUT;
	if (ValidationSample != ReadBe32(ValidationBytes + 68) ||
	    ValidationSegment != ValidationSegmentCount ||
	    ValidationPayloadCrc != ReadBe32(ValidationBytes + 20) ||
	    ValidationFileCrc != ReadBe32(ValidationBytes + 12))
		return VALIDATE_INVALID;
	return VALIDATE_OK;
}

static bool GenerationIsNewer(u32 candidate, u32 current)
{
	return (s32)(candidate - current) > 0;
}

static void BuildGhostPath(char *path, u16 profile, u32 slot, u8 bank)
{
	_sprintf(path, "%s" MOONSHINE_GHOSTS_DIR "/%s/p%u/g%02u%c.sgh",
	         SusamuneCfgStoragePrefix(), GhostRegion, profile, slot,
	         bank == 0 ? 'a' : 'b');
}

static void BuildImportDirectory(char *path)
{
	_sprintf(path, "%s" MOONSHINE_GHOSTS_DIR "/%s",
	         SusamuneCfgStoragePrefix(), SUSAMUNE_GHOST_IMPORT_DIRECTORY);
}

static void BuildImportPath(char *path, const char *leaf)
{
	_sprintf(path, "%s" MOONSHINE_GHOSTS_DIR "/%s/%s",
	         SusamuneCfgStoragePrefix(), SUSAMUNE_GHOST_IMPORT_DIRECTORY,
	         leaf);
}

static u8 FoldAscii(u8 value)
{
	return value >= 'A' && value <= 'Z' ? (u8)(value + ('a' - 'A')) : value;
}

static bool ImportLeafIsValid(const WCHAR *source, char *out)
{
	static const char extension[] = SUSAMUNE_GHOST_SHARE_EXTENSION;
	u32 length = 0;
	u32 extensionLength = sizeof(extension) - 1u;
	u32 i;
	u8 value;

	while (source[length] != 0)
	{
		if (length + 1u >= SUSAMUNE_GHOST_IMPORT_LEAF_SIZE ||
		    source[length] < 0x20u || source[length] > 0x7Eu)
			return false;
		value = (u8)source[length];
		if (value == '"' || value == '*' || value == '/' || value == ':' ||
		    value == '<' || value == '>' || value == '?' || value == '\\' ||
		    value == '|')
			return false;
		out[length++] = (char)value;
	}
	if (length <= extensionLength || out[length - 1u] == ' ' ||
	    out[length - 1u] == '.')
		return false;
	out[length] = 0;
	for (i = 0; i < extensionLength; i++)
		if (FoldAscii((u8)out[length - extensionLength + i]) !=
		    FoldAscii((u8)extension[i]))
			return false;
	return true;
}

static const char *RouteAbbreviation(u8 area)
{
	switch (area)
	{
		case 0x00: return "AS";
		case 0x01: return "DP";
		case 0x02: return "BH";
		case 0x03: return "RH";
		case 0x04: return "GB";
		case 0x05: return "PP";
		case 0x06: return "SB";
		case 0x08: return "PV";
		case 0x09: return "NB";
		case 0x34: return "CM";
		case 0x3C: return "BW";
		default: return NULL;
	}
}

static void BuildExportRoute(char *route, const u8 *header)
{
	u8 area = header[44];
	u32 episode = header[45];
	u8 parentArea = header[46];
	s32 variant = ReadBeS32(header + 48);
	const char *abbreviation;

	// Internal starts use the logical parent episode when it was captured.
	if (parentArea != SUSAMUNE_GHOST_ROUTE_PARENT_NONE && variant >= 0)
	{
		area = parentArea;
		episode = (u32)variant;
	}
	abbreviation = RouteAbbreviation(area);
	if (abbreviation != NULL)
		_sprintf(route, "%s%u", abbreviation, episode + 1u);
	else
		_sprintf(route, "A%02XE%02X", area, episode);
}

static void BuildCompactTime(char *time, u32 durationQf)
{
	u32 millis = (u32)(((u64)durationQf * 1001u) / 120u);
	u32 minutes = millis / 60000u;
	u32 seconds = (millis / 1000u) % 60u;

	if (minutes != 0)
		_sprintf(time, "%u%02u%03u", minutes, seconds, millis % 1000u);
	else
		_sprintf(time, "%u%03u", seconds, millis % 1000u);
}

static void BuildExportPath(char *path, u16 profile, const u8 *header)
{
	char route[8];
	char time[8];
	u32 fatTime = get_fattime();
	u32 year = 1980u + ((fatTime >> 25) & 0x7Fu);
	u32 month = (fatTime >> 21) & 0x0Fu;
	u32 day = (fatTime >> 16) & 0x1Fu;

	BuildExportRoute(route, header);
	BuildCompactTime(time, ReadBe32(header + 64));
	_sprintf(path,
	         "%s" MOONSHINE_GHOSTS_DIR "/%s/%s/p%u/"
	         "%04u_%02u_%02u_%s_%s[%08X]%s",
	         SusamuneCfgStoragePrefix(), SUSAMUNE_GHOST_SHARE_DIRECTORY,
	         GhostRegion, profile, year, month, day, route, time,
	         ReadBe32(header + SUSAMUNE_GHOST_FILE_CHECKSUM_OFFSET),
	         SUSAMUNE_GHOST_SHARE_EXTENSION);
}

static enum ReadResult ReadEnvelope(u16 profile, u32 slot, u8 bank,
	                                struct SusamuneGhostStorageEnvelope *envelope,
	                                u8 *header,
	                                int *ioError)
{
	char path[GHOST_PATH_SIZE];
	u8 raw[SUSAMUNE_GHOST_ENVELOPE_SIZE + SUSAMUNE_GHOST_FILE_HEADER_SIZE];
	FIL file;
	UINT read = 0;
	UINT readSize;
	u32 i;
	FSIZE_t size;
	int ret;
	int closeRet;
	enum ValidateResult validate;

	BuildGhostPath(path, profile, slot, bank);
	ret = f_open_char(&file, path, FA_READ | FA_OPEN_EXISTING);
	if (ret == FR_NO_FILE)
		return READ_MISSING;
	if (ret != FR_OK)
	{
		*ioError = ret;
		return READ_IO;
	}

	size = f_size(&file);
	readSize = size < sizeof(raw) ? (UINT)size : sizeof(raw);
	memset(raw, 0, sizeof(raw));
	ret = f_read(&file, raw, readSize, &read);
	closeRet = f_close(&file);
	if (ret != FR_OK || closeRet != FR_OK || read != readSize)
	{
		*ioError = ret != FR_OK ? ret :
		           closeRet != FR_OK ? closeRet : FR_DISK_ERR;
		return READ_IO;
	}

	if (read >= 6 && ReadBe32(raw) == SUSAMUNE_GHOST_ENVELOPE_MAGIC &&
	    ReadBe16(raw + 4) > SUSAMUNE_GHOST_ENVELOPE_VERSION_STREAMED)
		return READ_UNSAFE;
	if (size < SUSAMUNE_GHOST_ENVELOPE_SIZE ||
	    ReadBe32(raw) != SUSAMUNE_GHOST_ENVELOPE_MAGIC)
		return READ_INVALID;

	DecodeEnvelope(raw, envelope);
	if ((envelope->version != 1 && envelope->version != SUSAMUNE_GHOST_ENVELOPE_VERSION && envelope->version != SUSAMUNE_GHOST_ENVELOPE_VERSION_STREAMED) ||
	    envelope->headerSize != SUSAMUNE_GHOST_ENVELOPE_SIZE ||
	    envelope->gameId != GAME_ID || envelope->profile != profile ||
	    envelope->slot != (u16)slot ||
	    (envelope->version == 1 ? slot > 0xFFFFu : envelope->reserved[0] != slot) ||
	    (envelope->flags & ~SUSAMUNE_GHOST_ENVELOPE_TOMBSTONE) != 0 ||
	    envelope->payloadSize > SUSAMUNE_GHOST_MAX_FILE_SIZE ||
	    envelope->durationQf > (envelope->version==SUSAMUNE_GHOST_ENVELOPE_VERSION_STREAMED?0x7fffffffu:SUSAMUNE_GHOST_QF_MAX) ||
	    envelope->headerChecksum != EnvelopeChecksum(envelope))
		return READ_INVALID;
	for (i = envelope->version == 1 ? 0 : 1; i < sizeof(envelope->reserved) / sizeof(envelope->reserved[0]); i++)
		if (envelope->reserved[i] != 0)
			return READ_INVALID;

	if ((envelope->flags & SUSAMUNE_GHOST_ENVELOPE_TOMBSTONE) != 0)
	{
		if (envelope->payloadSize != 0 || envelope->durationQf != 0 ||
		    envelope->payloadChecksum != 0 || size != sizeof(*envelope))
			return READ_INVALID;
		return READ_VALID;
	}
	else if (envelope->payloadSize < SUSAMUNE_GHOST_FILE_HEADER_SIZE ||
	         size != sizeof(*envelope) + envelope->payloadSize)
	{
		return READ_INVALID;
	}

	// The envelope and canonical header come from the same bounded read.
	// Full payload CRC, poses and teaching data remain checked on load.
	memcpy(header, raw + SUSAMUNE_GHOST_ENVELOPE_SIZE,
	       SUSAMUNE_GHOST_FILE_HEADER_SIZE);
	validate = ValidateCanonicalHeader(header,
	                                   SUSAMUNE_GHOST_FILE_HEADER_SIZE,
	                                   profile, false, GAME_ID, GhostRegionId);
	if (validate == VALIDATE_FORWARD)
		return READ_UNSAFE;
	if (validate != VALIDATE_OK ||
        ((envelope->version==SUSAMUNE_GHOST_ENVELOPE_VERSION_STREAMED) != (ReadBe32(header)==MS_RECORDING_MANIFEST_MAGIC)) ||
	    ReadBe32(header + 8) != envelope->payloadSize ||
	    ReadBe32(header + 64) != envelope->durationQf)
		return READ_INVALID;
	return READ_VALID;
}

static void CopyEnvelopeInfo(struct BankInfo *out,
	                         const struct SusamuneGhostStorageEnvelope *envelope)
{
	out->generation = envelope->generation;
	out->flags = envelope->flags;
	out->payloadSize = envelope->payloadSize;
	out->durationQf = envelope->durationQf;
	out->payloadChecksum = envelope->payloadChecksum;
	out->state = BANK_VALID;
}

static bool BanksEquivalent(const struct BankInfo *a,
	                        const struct BankInfo *b)
{
	return a->flags == b->flags && a->payloadSize == b->payloadSize &&
	       a->durationQf == b->durationQf &&
	       a->payloadChecksum == b->payloadChecksum;
}

static void MarkSlotUnsafe(struct SlotCatalog *slot)
{
	memset(&slot->info, 0, sizeof(slot->info));
	slot->unsafe = 1;
	slot->activeBank = -1;
	slot->info.flags = SUSAMUNE_GHOST_SLOT_UNSAFE;
	slot->info.status = SUSAMUNE_GHOST_STATUS_SLOT_UNSAFE;
}

static void RecomputeSlot(void)
{
	struct SlotCatalog *slot = &Catalog[0];
	struct BankInfo *a = &slot->bank[0];
	struct BankInfo *b = &slot->bank[1];
	u32 delta;

	memset(&slot->info, 0, sizeof(slot->info));
	slot->unsafe = 0;
	slot->activeBank = -1;
	if (a->state == BANK_UNSAFE || b->state == BANK_UNSAFE)
	{
		MarkSlotUnsafe(slot);
		return;
	}
	if (a->state != BANK_VALID && b->state != BANK_VALID)
	{
		if (a->state == BANK_INVALID || b->state == BANK_INVALID)
			MarkSlotUnsafe(slot);
		return;
	}
	if (a->state != BANK_VALID)
		slot->activeBank = 1;
	else if (b->state != BANK_VALID)
		slot->activeBank = 0;
	else
	{
		delta = b->generation - a->generation;
		if (delta == 0)
		{
			if (!BanksEquivalent(a, b))
			{
				MarkSlotUnsafe(slot);
				return;
			}
			slot->activeBank = 0;
		}
		else if (delta == 0x80000000u)
		{
			MarkSlotUnsafe(slot);
			return;
		}
		else
			slot->activeBank = GenerationIsNewer(b->generation,
		                                            a->generation) ? 1 : 0;
	}
}

static void RecomputeCatalogTotals(void)
{
	CatalogUnsafe = Catalog[0].unsafe;
	CatalogCount = (Catalog[0].info.flags & SUSAMUNE_GHOST_SLOT_PRESENT) != 0;
	CatalogDurationQf = CatalogCount ? Catalog[0].info.durationQf : 0;
}





static void FillSlotInfo(const u8 *header)
{
	struct SlotCatalog *slot = &Catalog[0];
	struct BankInfo *bank = &slot->bank[(u8)slot->activeBank];

	FillInfo(&slot->info, header, bank->generation, 0);
}

static void InsertImportCandidate(void)
{
	AppendPageEntry(0, &ImportCandidate.info, ImportCandidate.leaf);
	PageDuration += ImportCandidate.info.durationQf;
}

static void DispatchRequest(void);

static int StorageStatusForResult(int result)
{
	return result == FR_NO_PATH || result == FR_NOT_READY ||
	       result == FR_WRITE_PROTECTED || result == FR_DENIED ||
	       result == FR_INVALID_DRIVE || result == FR_NO_FILESYSTEM
	           ? SUSAMUNE_GHOST_STATUS_STORAGE_UNAVAILABLE
	           : SUSAMUNE_GHOST_STATUS_IO(result);
}

static void PublishBusy(void)
{
	volatile struct SusamuneGhostStorageMailbox *mailbox = GhostBlock();

	mailbox->response.responseMagic = SUSAMUNE_GHOST_STORAGE_MAGIC;
	mailbox->response.protocolVersion = SUSAMUNE_GHOST_STORAGE_VERSION;
	mailbox->response.flags = SUSAMUNE_GHOST_RESPONSE_BUSY;
	mailbox->response.status = SUSAMUNE_GHOST_STATUS_OK;
	mailbox->response.payloadSize = 0;
	mailbox->response.generation = 0;
	mailbox->response.profile = Request.profile;
	sync_after_write((void*)&mailbox->response, 32);
}

static void FinishRequest(int status, u32 payloadSize, u32 generation)
{
#if TIMEWARP_LIVE_RACING && MOONSHINE_LOADING_DIAGNOSTICS
    MoonshineNetLogIo("ghost",Request.seq,Request.command,payloadSize,read32(HW_TIMER)-RequestStartedTick,status);
#endif
	volatile struct SusamuneGhostStorageMailbox *mailbox = GhostBlock();
	if (Request.command == SUSAMUNE_GHOST_CMD_SAVE && ImportDirOpen)
	{
		const int closed = f_closedir(&ImportDir);
		ImportDirOpen = false;
		if (closed != FR_OK) status = StorageStatusForResult(closed);
	}
	if (status != SUSAMUNE_GHOST_STATUS_OK && !WebCacheOwned)
		RequestListCache()->valid = false;
	mailbox->response.responseMagic = SUSAMUNE_GHOST_STORAGE_MAGIC;
	mailbox->response.protocolVersion = SUSAMUNE_GHOST_STORAGE_VERSION;
	mailbox->response.flags = GhostSupported ? SUSAMUNE_GHOST_RESPONSE_READY : 0;
	mailbox->response.ackSeq = Request.seq;
	mailbox->response.status = status;
	mailbox->response.payloadSize = payloadSize;
	mailbox->response.generation = generation;
	mailbox->response.slot = (Request.command == SUSAMUNE_GHOST_CMD_LIST ||
		Request.command == SUSAMUNE_GHOST_CMD_IMPORT_SCAN) ? 0 : Request.slot;
	mailbox->response.slotCount = status == SUSAMUNE_GHOST_STATUS_OK &&
	(Request.command == SUSAMUNE_GHOST_CMD_LIST ||
		Request.command == SUSAMUNE_GHOST_CMD_IMPORT_SCAN) ? Page.count : 0;
	mailbox->response.profile = Request.profile;
	GhostAckSeq = Request.seq;
	Phase = OP_IDLE;
	sync_after_write((void*)&mailbox->response, 32);
}

static void InvalidateRequestCatalog(void)
{
	RequestListCache()->valid = false;
	if (Request.profile == SUSAMUNE_GHOST_IMPORTED_PROFILE)
		ImportedCatalogReady = false;
	else
		CatalogReady = false;
}

static void FinishIoError(int result)
{
	if (IoFileOpen)
	{
		f_close(&IoFile);
		IoFileOpen = false;
	}
	if (ImportDirOpen)
	{
		f_closedir(&ImportDir);
		ImportDirOpen = false;
	}
	InvalidateRequestCatalog();
	FinishRequest(StorageStatusForResult(result), 0, 0);
}

static bool PersonalSlotValid(u32 slot)
{
	return slot != SUSAMUNE_GHOST_SLOT_AUTO && (slot < 45u || slot >= 48u);
}

static void InitPage(void)
{
	struct GhostListCache *cache = RequestListCache();
	memset(&Page, 0, sizeof(Page));
	Page.magic = SUSAMUNE_GHOST_CATALOG_PAGE_MAGIC;
	Page.version = SUSAMUNE_GHOST_CATALOG_PAGE_VERSION;
	Page.first = Request.command == SUSAMUNE_GHOST_CMD_SAVE
		? (cache->profile == Request.profile ? cache->first : 0) : Request.slot;
	PageOrdinal = 0;
	PageDuration = CachedSaveScan ? cache->duration : 0;
	ScanFingerprint = Request.profile == SUSAMUNE_GHOST_IMPORTED_PROFILE ? 0 : 2166136261u;
	AutoReuseSlot = SUSAMUNE_GHOST_SLOT_AUTO;
	ScanCaching = Request.command == SUSAMUNE_GHOST_CMD_LIST ||
	              Request.command == SUSAMUNE_GHOST_CMD_IMPORT_SCAN ||
	              Request.command == SUSAMUNE_GHOST_CMD_SAVE;
	if (ScanCaching)
	{
		cache->valid = false;
		cache->profile = Request.profile;
		cache->first = Page.first - Page.first % GHOST_LIST_CACHE_ENTRIES;
		cache->count = 0;
	}
}

static void CommitListCache(void)
{
	if (ScanCaching)
	{
		struct GhostListCache *cache = RequestListCache();
		cache->total = PageOrdinal;
		cache->duration = PageDuration;
		cache->nextSlot = Page.nextSlot;
		cache->directoryFingerprint = ScanFingerprint;
		cache->valid = true;
		ScanCaching = false;
	}
}

static void PublishPage(void)
{
	CommitListCache();
	Page.totalCount = PageOrdinal;
	Page.totalDurationQfLo = (u32)PageDuration;
	Page.totalDurationQfHi = (u32)(PageDuration >> 32);
	memcpy((void*)GHOST_PAYLOAD, &Page, sizeof(Page));
	sync_after_write((void*)GHOST_PAYLOAD, sizeof(Page));
	FinishRequest(SUSAMUNE_GHOST_STATUS_OK, sizeof(Page), 0);
}

static bool PublishCachedPage(void)
{
	struct GhostListCache *cache = RequestListCache();
	u32 count;
	u32 offset;
	if (!(Request.flags & SUSAMUNE_GHOST_REQUEST_CACHED_LIST) ||
	    !cache->valid || cache->profile != Request.profile ||
	    Request.slot < cache->first || Request.slot > cache->total)
		return false;
	offset = Request.slot - cache->first;
	count = cache->total - Request.slot;
	if (count > SUSAMUNE_GHOST_CATALOG_PAGE_ENTRIES)
		count = SUSAMUNE_GHOST_CATALOG_PAGE_ENTRIES;
	if (offset > cache->count || count > cache->count - offset)
		return false;
	memset(&Page, 0, sizeof(Page));
	Page.magic = SUSAMUNE_GHOST_CATALOG_PAGE_MAGIC;
	Page.version = SUSAMUNE_GHOST_CATALOG_PAGE_VERSION;
	Page.first = Request.slot;
	Page.count = count;
	Page.nextSlot = cache->nextSlot;
	memcpy(Page.entries, &cache->entries[offset], count * sizeof(Page.entries[0]));
	PageOrdinal = cache->total;
	PageDuration = cache->duration;
	ScanCaching = false;
	PublishPage();
	return true;
}

static void BeginSingleSlot(u32 slot)
{
	memset(Catalog, 0, sizeof(Catalog));
	CatalogReady = false;
	CatalogUnsafe = false;
	CatalogProfile = Request.profile;
	ScanSlot = slot;
	ScanFile = 0;
	ScanIoError = FR_OK;
	Phase = OP_SCAN_ENVELOPES;
}

static void BeginCatalogScan(void)
{
	ImportedCatalogReady = false;
	DirectoryScan = Request.command == SUSAMUNE_GHOST_CMD_LIST ||
	                Request.slot == SUSAMUNE_GHOST_SLOT_AUTO;
	if (DirectoryScan)
	{
		const struct GhostListCache *cache = RequestListCache();
		CachedSaveScan = Request.command == SUSAMUNE_GHOST_CMD_SAVE &&
			cache->valid && cache->directoryFingerprint && cache->profile == Request.profile &&
			PersonalSlotValid(cache->nextSlot);
		InitPage();
		Phase = OP_PERSONAL_SCAN_OPEN;
	}
	else
	{
		if (Request.command == SUSAMUNE_GHOST_CMD_SAVE) RequestListCache()->valid = false;
		BeginSingleSlot(Request.slot);
	}
}

static void PersonalScanOpenPass(void)
{
	char path[GHOST_PATH_SIZE];
	int ret;
	_sprintf(path, "%s" MOONSHINE_GHOSTS_DIR "/%s/p%u",
	         SusamuneCfgStoragePrefix(), GhostRegion, Request.profile);
	ret = f_opendir_char(&ImportDir, path);
	if (ret != FR_OK)
	{
		FinishIoError(ret);
		return;
	}
	ImportDirOpen = true;
	Phase = OP_PERSONAL_SCAN_NEXT;
}

static bool ParsePersonalLeaf(const char *leaf, u32 *id, u8 *bank)
{
	const char *p = leaf;
	u32 value = 0;
	char canonical[32];
	if (*p++ != 'g' || *p < '0' || *p > '9') return false;
	while (*p >= '0' && *p <= '9')
	{
		const u32 digit = (u32)(*p++ - '0');
		if (value > (0xFFFFFFFFu - digit) / 10u) return false;
		value = value * 10u + digit;
	}
	if ((*p != 'a' && *p != 'b') || strcmp(p + 1, ".sgh") ||
	    !PersonalSlotValid(value))
		return false;
	*bank = *p == 'b';
	_sprintf(canonical, "g%02u%c.sgh", value, *p);
	if (strcmp(canonical, leaf)) return false;
	*id = value;
	return true;
}

static void RetryPersonalScan(void)
{
	const int ret = f_closedir(&ImportDir);
	ImportDirOpen = false;
	CachedSaveScan = false;
	if (ret != FR_OK) { FinishIoError(ret); return; }
	Request.slot = SUSAMUNE_GHOST_SLOT_AUTO;
	BeginCatalogScan();
}

static void PersonalScanNextPass(void)
{
	char leaf[32];
	u32 n;
	u32 id;
	u8 bank;
	int ret;
	const DIR beforeRead = ImportDir;
	memset(&ImportEntry, 0, sizeof(ImportEntry));
	ret = f_readdir(&ImportDir, &ImportEntry);
	if (ret != FR_OK)
	{
		if (CachedSaveScan) RetryPersonalScan();
		else FinishIoError(ret);
		return;
	}
	if (!ImportEntry.fname[0])
	{
		const struct GhostListCache *cache = RequestListCache();
		if (CachedSaveScan && (PageOrdinal != cache->total || Page.nextSlot != cache->nextSlot ||
		    !ScanFingerprint || ScanFingerprint != cache->directoryFingerprint))
		{ RetryPersonalScan(); return; }
		if (Request.command == SUSAMUNE_GHOST_CMD_SAVE)
		{
			// FatFS clears its end iterator. Retain the pre-read position so a
			// committed append can prove that the cached ordering stayed valid.
			ImportDir = beforeRead;
		}
		else
		{
			ret = f_closedir(&ImportDir);
			ImportDirOpen = false;
			if (ret != FR_OK)
			{
				FinishIoError(ret);
				return;
			}
		}
		DirectoryScan = false;
		if (Request.command == SUSAMUNE_GHOST_CMD_LIST) PublishPage();
		else
		{
			Request.slot = AutoReuseSlot != SUSAMUNE_GHOST_SLOT_AUTO ? AutoReuseSlot :
			               Page.nextSlot == SUSAMUNE_GHOST_SLOT_AUTO ? 0 : Page.nextSlot;
			if (!PersonalSlotValid(Request.slot)) Request.slot = 48;
			AutoProbe = true;
			BeginSingleSlot(Request.slot);
		}
		return;
	}
	if (ImportEntry.fattrib & AM_DIR) { ScanFingerprint = 0; return; }
	for (n = 0; n < sizeof(leaf); ++n)
	{
		if (ImportEntry.fname[n] > 0x7Fu) { ScanFingerprint = 0; return; }
		leaf[n] = (char)ImportEntry.fname[n];
		if (!leaf[n]) break;
	}
	if (n == sizeof(leaf) || !ParsePersonalLeaf(leaf, &id, &bank))
	{ ScanFingerprint = 0; return; }
	FingerprintPersonalName(id, bank);
	if (id >= Page.nextSlot) Page.nextSlot = id + 1u;
	if (Page.nextSlot == 45u) Page.nextSlot = 48u;
	if (CachedSaveScan)
	{
		struct GhostListCache *cache = RequestListCache();
		if (bank) return;
		if (PageOrdinal >= cache->total) { RetryPersonalScan(); return; }
		if (PageOrdinal >= cache->first && PageOrdinal - cache->first < GHOST_LIST_CACHE_ENTRIES)
		{
			const struct SusamuneGhostCatalogEntry *entry = &cache->entries[PageOrdinal - cache->first];
			// The complete names witness is only a metadata hint. Targets still
			// receive both bank checks; source and publication checks are unchanged.
			if (entry->id != id || !(entry->info.flags & SUSAMUNE_GHOST_SLOT_PRESENT) ||
			    (entry->info.flags & SUSAMUNE_GHOST_SLOT_UNSAFE))
			{ RetryPersonalScan(); return; }
			AppendPageEntry(id, &entry->info, NULL);
		}
		else ++PageOrdinal;
		return;
	}
	if (bank)
	{
		char path[GHOST_PATH_SIZE];
		FILINFO other;
		BuildGhostPath(path, Request.profile, id, 0);
		ret = f_stat_char(path, &other);
		if (ret == FR_OK) return;
		ScanFingerprint = 0;
		if (ret != FR_NO_FILE)
		{
			FinishIoError(ret);
			return;
		}
	}
	BeginSingleSlot(id);
}

static void FinishSingleSlot(void)
{
	CatalogReady = true;
	RecomputeCatalogTotals();
	if (DirectoryScan)
	{
		if (!CatalogCount || CatalogUnsafe) ScanFingerprint = 0;
		if (Request.command == SUSAMUNE_GHOST_CMD_SAVE && !CatalogUnsafe &&
			Catalog[0].activeBank >= 0 &&
		    (Catalog[0].bank[(u8)Catalog[0].activeBank].flags &
		         SUSAMUNE_GHOST_ENVELOPE_TOMBSTONE) &&
		    ScanSlot < AutoReuseSlot)
			AutoReuseSlot = ScanSlot;
		if (CatalogCount || CatalogUnsafe)
		{
			AppendPageEntry(ScanSlot, &Catalog[0].info, NULL);
			PageDuration += CatalogDurationQf;
		}
		Phase = OP_PERSONAL_SCAN_NEXT;
		return;
	}
	if (AutoProbe && (CatalogCount || CatalogUnsafe))
	{
		if (CachedSaveScan) { RetryPersonalScan(); return; }
		++Request.slot;
		if (Request.slot == 45u) Request.slot = 48u;
		if (Request.slot == SUSAMUNE_GHOST_SLOT_AUTO)
		{
			FinishRequest(SUSAMUNE_GHOST_STATUS_STORAGE_UNAVAILABLE, 0, 0);
			return;
		}
		BeginSingleSlot(Request.slot);
		return;
	}
	AutoProbe = false;
	DispatchRequest();
}

static void ScanEnvelopePass(void)
{
	struct SusamuneGhostStorageEnvelope envelope;
	u8 header[SUSAMUNE_GHOST_FILE_HEADER_SIZE];
	enum ReadResult result;
	result = ReadEnvelope(Request.profile, ScanSlot, (u8)ScanFile,
	                      &envelope, header, &ScanIoError);
	if (result == READ_IO)
	{
		FinishIoError(ScanIoError);
		return;
	}
	if (result == READ_VALID)
	{
		CopyEnvelopeInfo(&Catalog[0].bank[ScanFile], &envelope);
		if ((envelope.flags & SUSAMUNE_GHOST_ENVELOPE_TOMBSTONE) == 0)
			FillInfo(&ScanBankInfo[ScanFile], header, envelope.generation, 0);
	}
	else
		Catalog[0].bank[ScanFile].state = result == READ_UNSAFE ? BANK_UNSAFE :
		                                result == READ_MISSING ? BANK_EMPTY : BANK_INVALID;
	++ScanFile;
	if (ScanFile == GHOST_BANK_COUNT)
	{
		RecomputeSlot();
		Phase = OP_SCAN_ACTIVE_HEADERS;
	}
}

static void ScanActiveHeaderPass(void)
{
	struct SlotCatalog *slot = &Catalog[0];
	if (!slot->unsafe && slot->activeBank >= 0 &&
	    (slot->bank[(u8)slot->activeBank].flags & SUSAMUNE_GHOST_ENVELOPE_TOMBSTONE) == 0)
		slot->info = ScanBankInfo[(u8)slot->activeBank];
	FinishSingleSlot();
}

static void BeginImportScan(void)
{
	CatalogReady = false;
	memset(ImportedCatalog, 0, sizeof(ImportedCatalog));
	memset(&ImportCandidate, 0, sizeof(ImportCandidate));
	ImportedCatalogReady = false;
	ImportedCatalogCount = 0;
	DirectoryScan = Request.command == SUSAMUNE_GHOST_CMD_LIST || Request.command == SUSAMUNE_GHOST_CMD_IMPORT_SCAN;
	if (DirectoryScan)
	{
		InitPage();
		Phase = OP_IMPORT_SCAN_OPEN;
	} else {
		memcpy(ImportCandidate.leaf, Request.leaf, sizeof(ImportCandidate.leaf));
		Phase = OP_IMPORT_SCAN_FILE_OPEN;
	}
}

static void EnsureCatalog(void)
{
	if (Request.profile == SUSAMUNE_GHOST_IMPORTED_PROFILE) BeginImportScan();
	else BeginCatalogScan();
}

static void PrepareEnvelope(struct SusamuneGhostStorageEnvelope *envelope,
	                        u32 flags,
	                        u32 generation, u32 payloadSize,
	                        u32 durationQf, u32 payloadChecksum)
{
	memset(envelope, 0, sizeof(*envelope));
	envelope->magic = SUSAMUNE_GHOST_ENVELOPE_MAGIC;
	envelope->version = SUSAMUNE_GHOST_ENVELOPE_VERSION;
	envelope->headerSize = sizeof(*envelope);
	envelope->generation = generation;
	envelope->flags = flags;
	envelope->gameId = GAME_ID;
	envelope->profile = Request.profile;
	envelope->slot = (u16)Request.slot;
	envelope->reserved[0] = Request.slot;
	envelope->payloadSize = payloadSize;
	envelope->durationQf = durationQf;
	envelope->payloadChecksum = payloadChecksum;
	envelope->headerChecksum = EnvelopeChecksum(envelope);
}

static void StartLoadBank(u8 bank)
{
	IoBank = bank;
	LoadAttemptedBanks |= (u8)(1u << bank);
	IoOffset = 0;
	IoChecksum = SUSAMUNE_GHOST_CRC32_INIT;
	Phase = OP_LOAD_OPEN;
}

static void StartImportedLoad(void)
{
	IoOffset = 0;
	IoChecksum = SUSAMUNE_GHOST_CRC32_INIT;
	Phase = OP_LOAD_OPEN;
}

static void QuarantineImportedSlot(int status)
{
	memset(&ImportedCatalog[0].info, 0,
	       sizeof(ImportedCatalog[0].info));
	ImportedCatalog[0].info.flags =
		SUSAMUNE_GHOST_SLOT_PRESENT |
		SUSAMUNE_GHOST_SLOT_IMPORTED |
		SUSAMUNE_GHOST_SLOT_UNSAFE;
	ImportedCatalog[0].info.status = status;
}

static void FailCorruptLoad(void)
{
	struct SlotCatalog *slot = &Catalog[0];
	u8 next;

	if (Request.profile == SUSAMUNE_GHOST_IMPORTED_PROFILE)
	{
		QuarantineImportedSlot(SUSAMUNE_GHOST_STATUS_INVALID_FILE);
		FinishRequest(SUSAMUNE_GHOST_STATUS_INVALID_FILE, 0, 0);
		return;
	}

	slot->bank[IoBank].state = BANK_INVALID;
	RecomputeSlot();
	RecomputeCatalogTotals();
	if (slot->unsafe)
	{
		FinishRequest(SUSAMUNE_GHOST_STATUS_SLOT_UNSAFE, 0, 0);
		return;
	}
	if (slot->activeBank >= 0)
	{
		next = (u8)slot->activeBank;
		if (slot->bank[next].generation != Request.expectedGeneration)
		{
			FinishRequest(SUSAMUNE_GHOST_STATUS_INVALID_FILE, 0, 0);
			return;
		}
		if ((slot->bank[next].flags &
		     SUSAMUNE_GHOST_ENVELOPE_TOMBSTONE) == 0 &&
		    (LoadAttemptedBanks & (1u << next)) == 0)
		{
			StartLoadBank(next);
			return;
		}
	}
	FinishRequest(SUSAMUNE_GHOST_STATUS_INVALID_FILE, 0, 0);
}

static void DispatchRequest(void)
{
	struct SlotCatalog *slot;
	struct BankInfo *active;
	u32 generation;
	u32 duration;

	if (Request.profile == SUSAMUNE_GHOST_IMPORTED_PROFILE)
	{
		if (!ImportedCatalogReady)
		{
			BeginImportScan();
			return;
		}
		if (Request.command == SUSAMUNE_GHOST_CMD_LIST ||
		    Request.command == SUSAMUNE_GHOST_CMD_IMPORT_SCAN)
		{
			PublishPage();
			return;
		}
		if (ImportedCatalogCount == 0 ||
		    (ImportedCatalog[0].info.flags &
		     SUSAMUNE_GHOST_SLOT_PRESENT) == 0)
		{
			FinishRequest(SUSAMUNE_GHOST_STATUS_NOT_FOUND, 0, 0);
			return;
		}
		if (ImportedCatalog[0].info.generation != Request.expectedGeneration)
		{
			FinishRequest(SUSAMUNE_GHOST_STATUS_INVALID_FILE, 0, 0);
			return;
		}
		if (Request.command == SUSAMUNE_GHOST_CMD_DELETE)
		{
			Phase = OP_IMPORTED_DELETE;
			return;
		}
		if ((ImportedCatalog[0].info.flags &
		     SUSAMUNE_GHOST_SLOT_UNSAFE) != 0)
		{
			FinishRequest(SUSAMUNE_GHOST_STATUS_SLOT_UNSAFE, 0, 0);
			return;
		}
		if (Request.command == SUSAMUNE_GHOST_CMD_LOAD)
		{
			StartImportedLoad();
			return;
		}
		FinishRequest(SUSAMUNE_GHOST_STATUS_INVALID_REQUEST, 0, 0);
		return;
	}

	if (!CatalogReady || CatalogProfile != Request.profile)
	{
		BeginCatalogScan();
		return;
	}
	if (Request.command == SUSAMUNE_GHOST_CMD_LIST)
	{
		PublishPage();
		return;
	}

	slot = &Catalog[0];
	if (Request.command != SUSAMUNE_GHOST_CMD_SAVE && slot->activeBank >= 0 &&
		slot->bank[(u8)slot->activeBank].generation != Request.expectedGeneration) {
		FinishRequest(SUSAMUNE_GHOST_STATUS_INVALID_FILE, 0, 0);
		return;
	}
	if (slot->unsafe)
	{
		FinishRequest(SUSAMUNE_GHOST_STATUS_SLOT_UNSAFE, 0, 0);
		return;
	}
    if ((slot->info.flags&SUSAMUNE_GHOST_SLOT_STREAMED) &&
        (Request.command==SUSAMUNE_GHOST_CMD_EXPORT || Request.command==SUSAMUNE_GHOST_CMD_WEB_UPLOAD)) {
        FinishRequest(SUSAMUNE_GHOST_STATUS_FORWARD_VERSION,0,0);return;
    }
	if (Request.command == SUSAMUNE_GHOST_CMD_LOAD ||
	    Request.command == SUSAMUNE_GHOST_CMD_EXPORT || Request.command == SUSAMUNE_GHOST_CMD_WEB_UPLOAD)
	{
		if (slot->activeBank < 0)
		{
			FinishRequest(SUSAMUNE_GHOST_STATUS_NOT_FOUND, 0, 0);
			return;
		}
		active = &slot->bank[(u8)slot->activeBank];
		if ((active->flags & SUSAMUNE_GHOST_ENVELOPE_TOMBSTONE) != 0)
		{
			FinishRequest(SUSAMUNE_GHOST_STATUS_NOT_FOUND, 0,
			              active->generation);
			return;
		}
		LoadAttemptedBanks = 0;
		StartLoadBank((u8)slot->activeBank);
		return;
	}

	// An unreadable bank makes mutation of this slot ambiguous.
	if (CatalogUnsafe)
	{
		FinishRequest(SUSAMUNE_GHOST_STATUS_SLOT_UNSAFE, 0, 0);
		return;
	}
	if (Request.command == SUSAMUNE_GHOST_CMD_DELETE)
	{
		if (slot->activeBank < 0 ||
		    (slot->bank[(u8)slot->activeBank].flags &
		     SUSAMUNE_GHOST_ENVELOPE_TOMBSTONE) != 0)
		{
			FinishRequest(SUSAMUNE_GHOST_STATUS_NOT_FOUND, 0, 0);
			return;
		}
        if((slot->info.flags&SUSAMUNE_GHOST_SLOT_STREAMED) && !PrepareRecordingDelete((u8)slot->activeBank)) {
            FinishRequest(SUSAMUNE_GHOST_STATUS_INVALID_FILE,0,0);return;
        }
		generation = slot->bank[(u8)slot->activeBank].generation + 1u;
		IoBank = (u8)(1 - slot->activeBank);
		PrepareEnvelope(&IoEnvelope, SUSAMUNE_GHOST_ENVELOPE_TOMBSTONE,
		                generation, 0, 0, 0);
		Phase = OP_DELETE_OPEN;
		return;
	}
	if (Request.command != SUSAMUNE_GHOST_CMD_SAVE ||
	    !PersonalSlotValid(Request.slot))
	{
		FinishRequest(SUSAMUNE_GHOST_STATUS_INVALID_SLOT, 0, 0);
		return;
	}
	if ((slot->info.flags & SUSAMUNE_GHOST_SLOT_PRESENT) != 0)
	{
		FinishRequest(SUSAMUNE_GHOST_STATUS_SLOT_OCCUPIED, 0,
		              slot->info.generation);
		return;
	}


	duration = ReadBe32((const u8*)GHOST_PAYLOAD + 64);
	if (slot->activeBank >= 0)
	{
		generation = slot->bank[(u8)slot->activeBank].generation + 1u;
		IoBank = (u8)(1 - slot->activeBank);
	}
	else
	{
		generation = 1;
		IoBank = 0;
	}
	PrepareEnvelope(&IoEnvelope, 0, generation, Request.payloadSize,
	                duration, ValidationRawCrc);
    if (ReadBe32((const u8*)GHOST_PAYLOAD)==MS_RECORDING_MANIFEST_MAGIC) {
        if(!PrepareRecordingPin((const u8*)GHOST_PAYLOAD,generation,ValidationRawCrc,true)) {
            FinishRequest(SUSAMUNE_GHOST_STATUS_INVALID_FILE,0,0);return;
        }
        IoEnvelope.version=SUSAMUNE_GHOST_ENVELOPE_VERSION_STREAMED;
        IoEnvelope.headerChecksum=EnvelopeChecksum(&IoEnvelope);
    }
	Phase = OP_SAVE_OPEN;
}

static void SaveOpenPass(void)
{
	char path[GHOST_PATH_SIZE];
	struct SusamuneGhostStorageEnvelope blank;
	UINT wrote = 0;
	int ret;

	BuildGhostPath(path, Request.profile, Request.slot, IoBank);
	ret = f_open_char(&IoFile, path, FA_WRITE | FA_CREATE_ALWAYS);
	if (ret != FR_OK)
	{
		FinishIoError(ret);
		return;
	}
	IoFileOpen = true;
	memset(&blank, 0, sizeof(blank));
	ret = f_write(&IoFile, &blank, sizeof(blank), &wrote);
	if (ret != FR_OK || wrote != sizeof(blank))
	{
		FinishIoError(ret != FR_OK ? ret : FR_DISK_ERR);
		return;
	}
	IoOffset = 0;
	Phase = OP_SAVE_DATA;
}

static void SaveDataPass(void)
{
	u32 remaining = Request.payloadSize - IoOffset;
	u32 chunk = remaining > SUSAMUNE_GHOST_STORAGE_CHUNK_SIZE
	              ? SUSAMUNE_GHOST_STORAGE_CHUNK_SIZE : remaining;
	UINT wrote = 0;
	int ret;

	if (chunk == 0)
	{
		Phase = OP_SAVE_SYNC_DATA;
		return;
	}
    const u8 *payload=RecordingSaveBytes();
    if(!payload){FinishIoError(FR_INVALID_OBJECT);return;}
	ret = f_write(&IoFile, payload + IoOffset,
	              chunk, &wrote);
	if (ret != FR_OK || wrote != chunk)
	{
		FinishIoError(ret != FR_OK ? ret : FR_DISK_ERR);
		return;
	}
	IoOffset += chunk;
	if (IoOffset == Request.payloadSize)
		Phase = OP_SAVE_SYNC_DATA;
}

static void SaveSyncDataPass(void)
{
	int ret = f_sync(&IoFile);
	if (ret != FR_OK)
	{
		FinishIoError(ret);
		return;
	}
	Phase = OP_SAVE_COMMIT;
}

static void SaveCommitPass(void)
{
	UINT wrote = 0;
	int ret = f_lseek(&IoFile, 0);

	if (ret == FR_OK)
		ret = WriteEnvelope(&IoFile, &IoEnvelope, &wrote);
	if (ret != FR_OK || wrote != sizeof(IoEnvelope))
	{
		FinishIoError(ret != FR_OK ? ret : FR_DISK_ERR);
		return;
	}
	Phase = OP_SAVE_FINISH;
}

static void SaveFinishPass(void)
{
	struct SlotCatalog *slot = &Catalog[0];
	int ret = f_sync(&IoFile);
	int closeRet = f_close(&IoFile);

	IoFileOpen = false;
	if (ret != FR_OK || closeRet != FR_OK)
	{
		InvalidateRequestCatalog();
		FinishRequest(StorageStatusForResult(ret != FR_OK ? ret : closeRet),
		              0, 0);
		return;
	}
	CopyEnvelopeInfo(&slot->bank[IoBank], &IoEnvelope);
	RecomputeSlot();
	if (slot->activeBank != (s8)IoBank)
	{
		MarkSlotUnsafe(slot);
		RecomputeCatalogTotals();
		FinishRequest(SUSAMUNE_GHOST_STATUS_SLOT_UNSAFE, 0, 0);
		return;
	}
	FillSlotInfo(RecordingSaveBytes());
	RecomputeCatalogTotals();
	if (ScanCaching && ImportDirOpen && AutoReuseSlot == SUSAMUNE_GHOST_SLOT_AUTO &&
	    Request.slot == Page.nextSlot)
	{
		FILINFO appended;
		char expected[32];
		unsigned i;
		_sprintf(expected, "g%02u%c.sgh", Request.slot, IoBank ? 'b' : 'a');
		memset(&appended, 0, sizeof(appended));
		if (f_readdir(&ImportDir, &appended) == FR_OK && !(appended.fattrib & AM_DIR))
		{
			for (i = 0; expected[i] && appended.fname[i] == (unsigned char)expected[i]; ++i) {}
			if (!expected[i] && !appended.fname[i])
			{
				// Reuse only the completed scan plus the committed new row.
				// Reused directory holes and uncertain ordering require a fresh scan.
				FingerprintPersonalName(Request.slot, IoBank);
				AppendPageEntry(Request.slot, &slot->info, NULL);
				PageDuration += CatalogDurationQf;
				Page.nextSlot = Request.slot + 1;
				if (Page.nextSlot == 45u) Page.nextSlot = 48u;
				CommitListCache();
			}
		}
	}
	FinishRequest(SUSAMUNE_GHOST_STATUS_OK, 0, IoEnvelope.generation);
}

static void LoadOpenPass(void)
{
	struct BankInfo *bank = NULL;
	char path[GHOST_PATH_SIZE];
	u32 payloadSize;
	u32 dataOffset;
	int ret;
	int closeRet;

	if (Request.profile == SUSAMUNE_GHOST_IMPORTED_PROFILE)
	{
		BuildImportPath(path, ImportedCatalog[0].leaf);
		payloadSize = ImportedCatalog[0].info.payloadSize;
		dataOffset = 0;
	}
	else
	{
		bank = &Catalog[0].bank[IoBank];
		BuildGhostPath(path, Request.profile, Request.slot, IoBank);
		payloadSize = bank->payloadSize;
		dataOffset = sizeof(struct SusamuneGhostStorageEnvelope);
	}
	ret = f_open_char(&IoFile, path, FA_READ | FA_OPEN_EXISTING);
	if (ret == FR_NO_FILE)
	{
		FailCorruptLoad();
		return;
	}
	if (ret != FR_OK)
	{
		FinishIoError(ret);
		return;
	}
	IoFileOpen = true;
	if (f_size(&IoFile) != (FSIZE_t)dataOffset + payloadSize)
	{
		closeRet = f_close(&IoFile);
		IoFileOpen = false;
		if (closeRet != FR_OK)
			FinishRequest(StorageStatusForResult(closeRet), 0, 0);
		else
			FailCorruptLoad();
		return;
	}
	ret = f_lseek(&IoFile, dataOffset);
	if (ret != FR_OK)
	{
		FinishIoError(ret);
		return;
	}
	IoOffset = 0;
	IoChecksum = SUSAMUNE_GHOST_CRC32_INIT;
	Phase = OP_LOAD_DATA;
}

static void LoadDataPass(void)
{
	u32 payloadSize = Request.profile == SUSAMUNE_GHOST_IMPORTED_PROFILE
		? ImportedCatalog[0].info.payloadSize
		: Catalog[0].bank[IoBank].payloadSize;
	u32 remaining = payloadSize - IoOffset;
	u32 chunk = remaining > SUSAMUNE_GHOST_STORAGE_CHUNK_SIZE
	              ? SUSAMUNE_GHOST_STORAGE_CHUNK_SIZE : remaining;
	UINT read = 0;
	int ret;

	if (chunk == 0)
	{
		Phase = OP_LOAD_CLOSE;
		return;
	}
	ret = f_read(&IoFile, (void*)(GHOST_PAYLOAD + IoOffset), chunk, &read);
	if (ret != FR_OK || read != chunk)
	{
		FinishIoError(ret != FR_OK ? ret : FR_DISK_ERR);
		return;
	}
	IoChecksum = CrcUpdate(IoChecksum,
	                       (const u8*)(GHOST_PAYLOAD + IoOffset), chunk);
	IoOffset += chunk;
	if (IoOffset == payloadSize)
		Phase = OP_LOAD_CLOSE;
}

static void LoadClosePass(void)
{
	struct SlotCatalog *slot = NULL;
	struct BankInfo *bank = NULL;
	bool imported = Request.profile == SUSAMUNE_GHOST_IMPORTED_PROFILE;
	u32 payloadSize;
	enum ValidateResult validate;
	int closeRet = f_close(&IoFile);

	IoFileOpen = false;
	if (closeRet != FR_OK)
	{
		FinishRequest(StorageStatusForResult(closeRet), 0, 0);
		return;
	}
	IoChecksum ^= SUSAMUNE_GHOST_CRC32_XOR_OUT;
	if (imported)
		payloadSize = ImportedCatalog[0].info.payloadSize;
	else
	{
		slot = &Catalog[0];
		bank = &slot->bank[IoBank];
		payloadSize = bank->payloadSize;
	}
	if (!imported && IoChecksum != bank->payloadChecksum)
	{
		FailCorruptLoad();
		return;
	}
	validate = BeginCanonicalValidation((const u8*)GHOST_PAYLOAD,
	                                    payloadSize, Request.profile,
	                                    imported);
	if (validate == VALIDATE_FORWARD)
	{
		if (imported)
			ImportedCatalogReady = false;
		else
		{
			bank->state = BANK_UNSAFE;
			RecomputeSlot();
			RecomputeCatalogTotals();
		}
		FinishRequest(SUSAMUNE_GHOST_STATUS_FORWARD_VERSION, 0, 0);
		return;
	}
	if (validate != VALIDATE_OK)
	{
		FailCorruptLoad();
		return;
	}
	Phase = OP_VALIDATE_LOAD;
}

static void ValidateLoadPass(void)
{
	bool imported = Request.profile == SUSAMUNE_GHOST_IMPORTED_PROFILE;
	struct SlotCatalog *slot = imported ? NULL : &Catalog[0];
	struct BankInfo *bank = imported ? NULL : &slot->bank[IoBank];
	u32 payloadSize = imported
		? ImportedCatalog[0].info.payloadSize : bank->payloadSize;
	int validate = ContinueCanonicalValidation();

	if (validate < 0)
		return;
	if (validate != VALIDATE_OK)
	{
		FailCorruptLoad();
		return;
	}
	if (!imported && ValidationRawCrc != bank->payloadChecksum)
	{
		FailCorruptLoad();
		return;
	}
	if (imported && ReadBe32((const u8*)GHOST_PAYLOAD + 12) != Request.expectedGeneration)
	{
		FinishRequest(SUSAMUNE_GHOST_STATUS_INVALID_FILE, 0, 0);
		return;
	}
	if (imported)
	{
		FillInfo(&ImportedCatalog[0].info,
		         (const u8*)GHOST_PAYLOAD, Request.expectedGeneration,
		         SUSAMUNE_GHOST_SLOT_IMPORTED);
		}
	else
	{
		FillSlotInfo((const u8*)GHOST_PAYLOAD);
		RecomputeCatalogTotals();
	}
	if (Request.command == SUSAMUNE_GHOST_CMD_EXPORT)
	{
		Phase = OP_EXPORT_OPEN;
		return;
	}
	if (Request.command == SUSAMUNE_GHOST_CMD_WEB_UPLOAD) {
		WebAccountStart(GHOST_ACCOUNT_UPLOAD, payloadSize); return;
	}
	sync_after_write((void*)GHOST_PAYLOAD, payloadSize);
	FinishRequest(SUSAMUNE_GHOST_STATUS_OK, payloadSize,
	              imported ? ReadBe32((const u8*)GHOST_PAYLOAD +
	                                  SUSAMUNE_GHOST_FILE_CHECKSUM_OFFSET)
	                       : bank->generation);
}

static void ExportOpenPass(void)
{
	char path[GHOST_PATH_SIZE];
	u8 blank[SUSAMUNE_GHOST_FILE_HEADER_SIZE];
	UINT wrote = 0;
	int ret;

	BuildExportPath(path, Request.profile, (const u8*)GHOST_PAYLOAD);
	ret = f_open_char(&IoFile, path, FA_WRITE | FA_CREATE_NEW);
	if (ret != FR_OK)
	{
		if (ret == FR_EXIST)
		{
			FinishRequest(SUSAMUNE_GHOST_STATUS_SLOT_OCCUPIED, 0, 0);
			return;
		}
		FinishIoError(ret);
		return;
	}
	IoFileOpen = true;
	memset(blank, 0, sizeof(blank));
	ret = f_write(&IoFile, blank, sizeof(blank), &wrote);
	if (ret != FR_OK || wrote != sizeof(blank))
	{
		FinishIoError(ret != FR_OK ? ret : FR_DISK_ERR);
		return;
	}
	IoOffset = SUSAMUNE_GHOST_FILE_HEADER_SIZE;
	Phase = OP_EXPORT_DATA;
}

static void ExportDataPass(void)
{
	u32 remaining = ValidationSize - IoOffset;
	u32 chunk = remaining > SUSAMUNE_GHOST_STORAGE_CHUNK_SIZE
	              ? SUSAMUNE_GHOST_STORAGE_CHUNK_SIZE : remaining;
	UINT wrote = 0;
	int ret;

	if (chunk == 0)
	{
		Phase = OP_EXPORT_SYNC_DATA;
		return;
	}
	ret = f_write(&IoFile, (const void*)(GHOST_PAYLOAD + IoOffset),
	              chunk, &wrote);
	if (ret != FR_OK || wrote != chunk)
	{
		FinishIoError(ret != FR_OK ? ret : FR_DISK_ERR);
		return;
	}
	IoOffset += chunk;
	if (IoOffset == ValidationSize)
		Phase = OP_EXPORT_SYNC_DATA;
}

static void ExportSyncDataPass(void)
{
	int ret = f_sync(&IoFile);
	if (ret != FR_OK)
	{
		FinishIoError(ret);
		return;
	}
	Phase = OP_EXPORT_COMMIT;
}

static void ExportCommitPass(void)
{
	UINT wrote = 0;
	int ret = f_lseek(&IoFile, 0);

	if (ret == FR_OK)
		ret = f_write(&IoFile, (const void*)GHOST_PAYLOAD,
		              SUSAMUNE_GHOST_FILE_HEADER_SIZE, &wrote);
	if (ret != FR_OK || wrote != SUSAMUNE_GHOST_FILE_HEADER_SIZE)
	{
		FinishIoError(ret != FR_OK ? ret : FR_DISK_ERR);
		return;
	}
	Phase = OP_EXPORT_FINISH;
}

static void ExportFinishPass(void)
{
	struct BankInfo *bank = &Catalog[0].bank[IoBank];
	int ret = f_sync(&IoFile);
	int closeRet = f_close(&IoFile);

	IoFileOpen = false;
	if (ret != FR_OK || closeRet != FR_OK)
	{
		InvalidateRequestCatalog();
		FinishRequest(StorageStatusForResult(ret != FR_OK ? ret : closeRet),
		              0, 0);
		return;
	}
	FinishRequest(SUSAMUNE_GHOST_STATUS_OK, 0, bank->generation);
}

static void ImportScanOpenPass(void)
{
	char path[GHOST_PATH_SIZE];
	int ret;

	BuildImportDirectory(path);
	ret = f_opendir_char(&ImportDir, path);
	if (ret != FR_OK)
	{
		FinishIoError(ret);
		return;
	}
	ImportDirOpen = true;
	Phase = OP_IMPORT_SCAN_NEXT;
}

static void ImportScanNextPass(void)
{
	int ret;
	int closeRet;

	memset(&ImportEntry, 0, sizeof(ImportEntry));
	ret = f_readdir(&ImportDir, &ImportEntry);
	if (ret != FR_OK)
	{
		FinishIoError(ret);
		return;
	}
	if (ImportEntry.fname[0] == 0)
	{
		closeRet = f_closedir(&ImportDir);
		ImportDirOpen = false;
		if (closeRet != FR_OK)
		{
			FinishRequest(StorageStatusForResult(closeRet), 0, 0);
			return;
		}
		ImportedCatalogReady = true;
		PublishPage();
		return;
	}
	if ((ImportEntry.fattrib & AM_DIR) != 0)
		return;

	memset(&ImportCandidate, 0, sizeof(ImportCandidate));
	if (!ImportLeafIsValid(ImportEntry.fname, ImportCandidate.leaf))
		return;
	if (ImportEntry.fsize < SUSAMUNE_GHOST_FILE_HEADER_SIZE ||
	    ImportEntry.fsize > SUSAMUNE_GHOST_MAX_FILE_SIZE ||
	    ImportEntry.fsize > SUSAMUNE_GHOST_STORAGE_PAYLOAD_SIZE)
		return;
	ImportCandidateSize = (u32)ImportEntry.fsize;
	Phase = OP_IMPORT_SCAN_FILE_OPEN;
}

static void ImportScanFileOpenPass(void)
{
	char path[GHOST_PATH_SIZE];
	int ret;
	int closeRet;

	BuildImportPath(path, ImportCandidate.leaf);
	ret = f_open_char(&IoFile, path, FA_READ | FA_OPEN_EXISTING);
	if (ret == FR_NO_FILE)
	{
		if (DirectoryScan) Phase = OP_IMPORT_SCAN_NEXT;
		else FinishRequest(SUSAMUNE_GHOST_STATUS_NOT_FOUND, 0, 0);
		return;
	}
	if (ret != FR_OK)
	{
		FinishIoError(ret);
		return;
	}
	IoFileOpen = true;
	if (!DirectoryScan) ImportCandidateSize = (u32)f_size(&IoFile);
	if (ImportCandidateSize < SUSAMUNE_GHOST_FILE_HEADER_SIZE ||
		ImportCandidateSize > SUSAMUNE_GHOST_MAX_FILE_SIZE ||
		f_size(&IoFile) != ImportCandidateSize)
	{
		closeRet = f_close(&IoFile);
		IoFileOpen = false;
		if (closeRet != FR_OK)
			FinishIoError(closeRet);
		else
			if (DirectoryScan) Phase = OP_IMPORT_SCAN_NEXT;
		else FinishRequest(SUSAMUNE_GHOST_STATUS_NOT_FOUND, 0, 0);
		return;
	}
	ImportPrefixSize = ImportCandidateSize < SUSAMUNE_GHOST_V3_SAMPLE_DATA_OFFSET
		? ImportCandidateSize : SUSAMUNE_GHOST_V3_SAMPLE_DATA_OFFSET;
	Phase = OP_IMPORT_SCAN_FILE_READ;
}

static void ImportScanFileReadPass(void)
{
	UINT read = 0;
	int ret = f_read(&IoFile, (void*)GHOST_PAYLOAD,
	                 ImportPrefixSize, &read);

	if (ret != FR_OK || read != ImportPrefixSize)
	{
		FinishIoError(ret != FR_OK ? ret : FR_DISK_ERR);
		return;
	}
	Phase = OP_IMPORT_SCAN_FILE_CLOSE;
}

static void ImportScanFileClosePass(void)
{
	const u8 *bytes = (const u8*)GHOST_PAYLOAD;
	enum ValidateResult validate;
	bool portable;
	int closeRet = f_close(&IoFile);

	IoFileOpen = false;
	if (closeRet != FR_OK)
	{
		FinishIoError(closeRet);
		return;
	}
	validate = ValidateCanonicalHeader(bytes, ImportCandidateSize,
	                                   SUSAMUNE_GHOST_IMPORTED_PROFILE,
	                                   true, GAME_ID, GhostRegionId);
	if (validate != VALIDATE_OK ||
	    ReadBe32(bytes + 8) != ImportCandidateSize ||
	    ImportPrefixSize < SUSAMUNE_GHOST_V3_SAMPLE_DATA_OFFSET)
	{
		if (DirectoryScan) Phase = OP_IMPORT_SCAN_NEXT;
		else FinishRequest(SUSAMUNE_GHOST_STATUS_NOT_FOUND, 0, 0);
		return;
	}
	portable = ReadBe32(bytes + 32) != GAME_ID;
	if (!ValidateV3SegmentTable(bytes, portable))
	{
		if (DirectoryScan) Phase = OP_IMPORT_SCAN_NEXT;
		else FinishRequest(SUSAMUNE_GHOST_STATUS_NOT_FOUND, 0, 0);
		return;
	}
	FillInfo(&ImportCandidate.info, bytes, ReadBe32(bytes + 12),
	         SUSAMUNE_GHOST_SLOT_IMPORTED);
	if (DirectoryScan)
	{
		InsertImportCandidate();
		Phase = OP_IMPORT_SCAN_NEXT;
	} else {
		ImportedCatalog[0] = ImportCandidate;
		ImportedCatalogCount = 1;
		ImportedCatalogReady = true;
		DispatchRequest();
	}
}

static void DeleteOpenPass(void)
{
	char path[GHOST_PATH_SIZE];
	UINT wrote = 0;
	int ret;

	BuildGhostPath(path, Request.profile, Request.slot, IoBank);
	ret = f_open_char(&IoFile, path, FA_WRITE | FA_CREATE_ALWAYS);
	if (ret != FR_OK)
	{
		FinishIoError(ret);
		return;
	}
	IoFileOpen = true;
	ret = WriteEnvelope(&IoFile, &IoEnvelope, &wrote);
	if (ret != FR_OK || wrote != sizeof(IoEnvelope))
	{
		FinishIoError(ret != FR_OK ? ret : FR_DISK_ERR);
		return;
	}
	Phase = OP_DELETE_FINISH;
}

static void DeleteFinishPass(void)
{
	struct SlotCatalog *slot = &Catalog[0];
	int ret = f_sync(&IoFile);
	int closeRet = f_close(&IoFile);

	IoFileOpen = false;
	if (ret != FR_OK || closeRet != FR_OK)
	{
		InvalidateRequestCatalog();
		FinishRequest(StorageStatusForResult(ret != FR_OK ? ret : closeRet),
		              0, 0);
		return;
	}
	CopyEnvelopeInfo(&slot->bank[IoBank], &IoEnvelope);
	RecomputeSlot();
	if (slot->activeBank != (s8)IoBank)
		MarkSlotUnsafe(slot);
	RecomputeCatalogTotals();
	if (slot->unsafe)
		FinishRequest(SUSAMUNE_GHOST_STATUS_SLOT_UNSAFE, 0, 0);
	else
		Phase = OP_DELETE_RECLAIM;
}

static void DeleteReclaimPass(void)
{
	char path[GHOST_PATH_SIZE];
	int ret;

	// The committed tombstone wins even if power fails during reclamation.
	BuildGhostPath(path, Request.profile, Request.slot, (u8)(1u - IoBank));
	ret = f_unlink_char(path);
	if (ret != FR_OK && ret != FR_NO_FILE)
	{
		FinishIoError(ret);
		return;
	}
	ReleaseRecordingPin();
	InvalidateRequestCatalog();
	FinishRequest(SUSAMUNE_GHOST_STATUS_OK, 0, IoEnvelope.generation);
}

static void ImportedDeletePass(void)
{
	char path[GHOST_PATH_SIZE];
	int ret;

	BuildImportPath(path, ImportedCatalog[0].leaf);
	ret = f_unlink_char(path);
	if (ret == FR_NO_FILE)
	{
		ImportedCatalogReady = false;
		FinishRequest(SUSAMUNE_GHOST_STATUS_NOT_FOUND, 0, 0);
		return;
	}
	if (ret != FR_OK)
	{
		FinishIoError(ret);
		return;
	}
	ImportedCatalogReady = false;
	FinishRequest(SUSAMUNE_GHOST_STATUS_OK, 0, 0);
}

static void WebFail(int status)
{
    if (IoFileOpen) {
        if (f_close(&IoFile) != FR_OK) CloseFailed = true;
        IoFileOpen = false;
    }
    if (Request.command == SUSAMUNE_GHOST_CMD_WEB_DOWNLOAD && !CloseFailed)
        f_unlink_char(WebTempPath);
    FinishRequest(status, 0, 0);
}

static void WebStart(void)
{
    struct GhostServiceEntry entry;
    unsigned i, offset;
    int ret;
    static const char digits[] = "0123456789abcdef";
    if (!SusamuneTransferActive() || Request.profile != SUSAMUNE_GHOST_IMPORTED_PROFILE ||
        Request.slot || Request.flags || Request.expectedGeneration ||
        Request.payloadSize != (Request.command == SUSAMUNE_GHOST_CMD_WEB_LIST
            ? sizeof(struct GhostServiceQuery) : sizeof(struct GhostServiceEntry))) {
        FinishRequest(SUSAMUNE_GHOST_STATUS_INVALID_REQUEST, 0, 0); return;
    }
    sync_before_read((void*)GHOST_PAYLOAD, Request.payloadSize);
    WebBytes = 0;
    if (Request.command == SUSAMUNE_GHOST_CMD_WEB_DOWNLOAD) {
        memcpy(&entry, (const void*)GHOST_PAYLOAD, sizeof(entry));
        if (!entry.bytes || entry.bytes > SUSAMUNE_GHOST_MAX_FILE_SIZE) {
            FinishRequest(SUSAMUNE_GHOST_STATUS_PAYLOAD_TOO_LARGE, 0, 0); return;
        }
        BuildImportDirectory(WebTempPath);
        ret = f_mkdir_char(WebTempPath);
        if (ret != FR_OK && ret != FR_EXIST) { FinishIoError(ret); return; }
        strcpy(WebFinalPath, WebTempPath); strcat(WebFinalPath, "/g_");
        offset = strlen(WebFinalPath);
        for (i = 0; i < 32; ++i) {
            WebFinalPath[offset++] = digits[entry.sha256[i] >> 4];
            WebFinalPath[offset++] = digits[entry.sha256[i] & 15];
        }
        strcpy(WebFinalPath + offset, SUSAMUNE_GHOST_SHARE_EXTENSION);
        strcat(WebTempPath, "/download.tmp");
        ret = f_stat_char(WebFinalPath, &ImportEntry);
        if (ret == FR_OK) { FinishRequest(SUSAMUNE_GHOST_STATUS_SLOT_OCCUPIED, 0, 0); return; }
        if (ret != FR_NO_FILE) { FinishIoError(ret); return; }
        ret = f_open_char(&IoFile, WebTempPath, FA_WRITE | FA_CREATE_ALWAYS);
        if (ret != FR_OK) { FinishIoError(ret); return; }
        IoFileOpen = true; WebBytes = entry.bytes;
    }
    if (!WebCacheOwned) { memset(&BrowseMemory,0,sizeof(BrowseMemory)); WebCacheOwned=true; }
    if (!GhostServiceStart((void*)GHOST_PAYLOAD, SusamuneTransferStageSize(), GhostRegion,
            GetCurrentTime(), WebBytes ? &entry : NULL, BrowseMemory.session)) {
        WebFail(GHOST_SERVICE_NETWORK); return;
    }
    Phase = OP_WEB_WAIT;
}

struct WebAccountRecord { u32 magic, generation, linked; struct GhostAccountSecret secret; u32 crc; };
static void WebAccountPath(char *path,unsigned bank,bool temp) {
    _sprintf(path,"%s/delfino-link-%c.bin%s",SusamuneCfgStoragePrefix(),bank?'b':'a',temp?".tmp":"");
}
static int WebAccountRead(const char *path,struct WebAccountRecord *record) {
    UINT got=0;int ret=f_open_char(&IoFile,path,FA_READ),closed;
    if(ret!=FR_OK)return ret;
    ret=f_read(&IoFile,record,sizeof(*record),&got);closed=f_close(&IoFile);
    if(ret!=FR_OK || closed!=FR_OK)return FR_DISK_ERR;
    if(got!=sizeof(*record) || record->magic!=GHOST_SERVICE_ACCOUNT_MAGIC || record->linked>1 ||
        record->crc!=CrcUpdate(0,(const u8*)record,sizeof(*record)-4) ||
        (record->linked && !GhostAccountSecretValid(&record->secret)))return FR_INVALID_OBJECT;
    return FR_OK;
}
/* A durable unlinked generation precedes rotation. Never fall back to an older token after a lost reply. */
static int WebAccountStore(bool linked) {
    struct WebAccountRecord record,check;
    char path[GHOST_PATH_SIZE],temp[GHOST_PATH_SIZE];UINT wrote=0;
    unsigned bank=1-WebAccountBank;int ret,closed;
    memset(&record,0,sizeof(record));record.magic=GHOST_SERVICE_ACCOUNT_MAGIC;
    record.generation=WebAccountGeneration+1;record.linked=linked;
    if(linked)record.secret=WebAccount.secret;
    record.crc=CrcUpdate(0,(const u8*)&record,sizeof(record)-4);
    WebAccountPath(path,bank,false);WebAccountPath(temp,bank,true);
    ret=f_open_char(&IoFile,temp,FA_WRITE|FA_CREATE_ALWAYS);if(ret!=FR_OK)return ret;
    ret=f_write(&IoFile,&record,sizeof(record),&wrote);
    if(ret==FR_OK && wrote==sizeof(record))ret=f_sync(&IoFile);else ret=FR_DISK_ERR;
    closed=f_close(&IoFile);if(ret!=FR_OK || closed!=FR_OK)return FR_DISK_ERR;
    ret=WebAccountRead(temp,&check);
    if(ret!=FR_OK || memcmp(&record,&check,sizeof(record)))return FR_DISK_ERR;
    ret=f_unlink_char(path);if(ret!=FR_OK && ret!=FR_NO_FILE)return ret;
    ret=f_rename_char(temp,path);if(ret!=FR_OK)return ret;
    ret=WebAccountRead(path,&check);
    if(ret!=FR_OK || memcmp(&record,&check,sizeof(record)))return FR_DISK_ERR;
    WebAccountGeneration=record.generation;WebAccountBank=bank;
    memset(&record,0,sizeof(record));memset(&check,0,sizeof(check));return FR_OK;
}
static int WebAccountLoad(void) {
    struct WebAccountRecord record;char path[GHOST_PATH_SIZE];unsigned bank;int ret;
    if(WebAccountLoaded)return FR_OK;
    for(bank=0;bank<2;++bank){
        WebAccountPath(path,bank,false);ret=WebAccountRead(path,&record);
        if(ret==FR_NO_FILE)continue;
        if(ret!=FR_OK)return ret;
        if(!WebAccountGeneration || GenerationIsNewer(record.generation,WebAccountGeneration)) {
            WebAccountGeneration=record.generation;WebAccountBank=bank;
            memset(&WebAccount.secret,0,sizeof(WebAccount.secret));
            if(record.linked)WebAccount.secret=record.secret;
        }
    }
    memset(&record,0,sizeof(record));WebAccountLoaded=true;return FR_OK;
}
static void WebAccountStart(unsigned action,unsigned bytes)
{
    int ret=WebAccountLoad();
    if(ret!=FR_OK){FinishIoError(ret);return;}
    if(action==GHOST_ACCOUNT_UPLOAD && !GhostAccountSecretValid(&WebAccount.secret)){
        FinishRequest(GHOST_SERVICE_LINK_REQUIRED,0,0);return;
    }
    if(action==GHOST_ACCOUNT_UPLOAD || action==GHOST_ACCOUNT_UNLINK) {
        ret=WebAccountStore(false);if(ret!=FR_OK){FinishIoError(ret);return;}
    }
    WebAccount.changed=0;
    WebBytes=0;
    if(!WebCacheOwned){memset(&BrowseMemory,0,sizeof(BrowseMemory));WebCacheOwned=true;}
    if(!SusamuneTransferActive() || !GhostServiceAction((void*)GHOST_PAYLOAD,
        SusamuneTransferStageSize(),GetCurrentTime(),action,bytes,&WebAccount,BrowseMemory.session,
        action==GHOST_ACCOUNT_UPLOAD?&WebUpload:NULL)) {
        WebFail(GHOST_SERVICE_NETWORK);return;
    }
    Phase=OP_WEB_WAIT;
}

static void WebWaitPass(void)
{
    unsigned bytes = 0, count;
    void *data;
    int result;
    if (Retiring || SusamuneTransferCancelled(TW_OWNER_GHOST)) GhostServiceCancel();
    if (WebBytes) {
        count = GhostServiceRead(&data);
        if (count) {
            UINT wrote = 0;
            int ret = f_write(&IoFile, data, count, &wrote);
            GhostServiceReadAck(count);
            if (ret != FR_OK || wrote != count) {
                /* Keep the lease until the worker retires every IOS request. */
                GhostServiceCancel();
                WebBytes = 0;
            }
            return;
        }
    }
    GhostBlock()->response.generation=GhostServiceProgress();
    sync_after_write((void*)&GhostBlock()->response,32);
    result = GhostServicePoll(&bytes);
    if (!result) return;
#if TIMEWARP_LIVE_RACING
    {
        unsigned i; const struct GhostServiceTrace *trace;
        for(i=0;(trace=GhostServiceTrace(i))!=NULL;++i)MoonshineNetLogWeb(trace);
    }
#endif
    GhostServiceRelease();
    if(Request.command==SUSAMUNE_GHOST_CMD_WEB_UPLOAD || Request.command==SUSAMUNE_GHOST_CMD_WEB_ACCOUNT) {
        if(WebAccount.changed) {
            int saved=WebAccountStore(GhostAccountSecretValid(&WebAccount.secret));WebAccount.changed=0;
            if(saved!=FR_OK){memset(&WebAccount.secret,0,sizeof(WebAccount.secret));WebFail(SUSAMUNE_GHOST_STATUS_IO(saved));return;}
        } else if(Request.command==SUSAMUNE_GHOST_CMD_WEB_UPLOAD)memset(&WebAccount.secret,0,sizeof(WebAccount.secret));
    }
    if (result < 0 || Retiring || SusamuneTransferCancelled(TW_OWNER_GHOST)) {
        WebFail(result < 0 ? result : GHOST_SERVICE_CANCELLED); return;
    }
    if (Request.command == SUSAMUNE_GHOST_CMD_WEB_LIST || Request.command == SUSAMUNE_GHOST_CMD_WEB_ACCOUNT ||
        Request.command == SUSAMUNE_GHOST_CMD_WEB_UPLOAD) {
        sync_after_write((void*)GHOST_PAYLOAD, bytes);
        FinishRequest(SUSAMUNE_GHOST_STATUS_OK, bytes, 0); return;
    }
    if (!WebBytes || bytes != WebBytes) { WebFail(SUSAMUNE_GHOST_STATUS_INVALID_FILE); return; }
    {
        int ret = f_sync(&IoFile), closeRet = f_close(&IoFile);
        IoFileOpen = false;
        if (closeRet != FR_OK) CloseFailed = true;
        if (ret != FR_OK || closeRet != FR_OK) { WebFail(SUSAMUNE_GHOST_STATUS_IO(FR_DISK_ERR)); return; }
        ret = f_open_char(&IoFile, WebTempPath, FA_READ);
        if (ret != FR_OK) { WebFail(SUSAMUNE_GHOST_STATUS_IO(ret)); return; }
        IoFileOpen = true;
        if (f_size(&IoFile) != WebBytes) { WebFail(SUSAMUNE_GHOST_STATUS_INVALID_FILE); return; }
    }
    IoOffset = 0; Phase = OP_WEB_READ;
}

static void WebReadPass(void)
{
    UINT got = 0;
    unsigned chunk = WebBytes - IoOffset;
    int ret;
    if (chunk > SUSAMUNE_GHOST_STORAGE_CHUNK_SIZE) chunk = SUSAMUNE_GHOST_STORAGE_CHUNK_SIZE;
    ret = f_read(&IoFile, (void*)(GHOST_PAYLOAD + IoOffset), chunk, &got);
    if (ret != FR_OK || got != chunk) { WebFail(SUSAMUNE_GHOST_STATUS_INVALID_FILE); return; }
    IoOffset += got;
    if (IoOffset != WebBytes) return;
    ret = f_close(&IoFile); IoFileOpen = false;
    if (ret != FR_OK) { CloseFailed = true; WebFail(SUSAMUNE_GHOST_STATUS_IO(ret)); return; }
    ret = BeginCanonicalValidation((const u8*)GHOST_PAYLOAD, WebBytes, SUSAMUNE_GHOST_IMPORTED_PROFILE, true);
    if (ret != VALIDATE_OK) { WebFail(SUSAMUNE_GHOST_STATUS_INVALID_FILE); return; }
    Phase = OP_WEB_VALIDATE;
}

static void WebValidatePass(void)
{
    int ret = ContinueCanonicalValidation();
    if (ret < 0) return;
    if (ret != VALIDATE_OK) { WebFail(SUSAMUNE_GHOST_STATUS_INVALID_FILE); return; }
    ret = f_rename_char(WebTempPath, WebFinalPath);
    if (ret != FR_OK) { WebFail(SUSAMUNE_GHOST_STATUS_IO(ret)); return; }
    ImportedCatalogReady = false;
    FinishRequest(SUSAMUNE_GHOST_STATUS_OK, 0, 0);
}

static void StartRequest(void)
{
	volatile struct SusamuneGhostStorageMailbox *mailbox = GhostBlock();
	const volatile struct SusamuneGhostStorageRequest *request =
		&mailbox->request;
	enum ValidateResult validate;

	sync_before_read((void*)request, 32);
	if (request->requestSeq == GhostAckSeq)
		return;
	if (!SusamuneTransferAllows(TW_OWNER_GHOST, request->requestSeq, 0, request->command)) return;
#if MOONSHINE_LOADING_DIAGNOSTICS
    RequestStartedTick=read32(HW_TIMER);
#endif
	Request.seq = request->requestSeq;
	Request.command = request->command;
	Request.profile = request->profile;
	Request.slot = request->slot;
	Request.payloadSize = request->payloadSize;
	Request.flags = request->flags;
	Request.expectedGeneration = request->expectedGeneration;

	AutoProbe = false;
	ScanCaching = false;
	CachedSaveScan = false;
	PublishBusy();

	if (request->requestMagic != SUSAMUNE_GHOST_STORAGE_MAGIC ||
	    request->protocolVersion != SUSAMUNE_GHOST_STORAGE_VERSION ||
	    request->reserved != 0 ||
	    (Request.flags & ~SUSAMUNE_GHOST_REQUEST_CACHED_LIST) != 0 ||
	    (Request.flags != 0 && Request.command != SUSAMUNE_GHOST_CMD_LIST))
	{
		FinishRequest(request->requestMagic == SUSAMUNE_GHOST_STORAGE_MAGIC &&
		              request->protocolVersion > SUSAMUNE_GHOST_STORAGE_VERSION
		                  ? SUSAMUNE_GHOST_STATUS_FORWARD_VERSION
		                  : SUSAMUNE_GHOST_STATUS_INVALID_REQUEST,
		              0, 0);
		return;
	}
	if (!GhostSupported)
	{
		FinishRequest(SUSAMUNE_GHOST_STATUS_STORAGE_UNAVAILABLE, 0, 0);
		return;
	}
	if (Request.command < SUSAMUNE_GHOST_CMD_SAVE ||
	    Request.command > SUSAMUNE_GHOST_CMD_WEB_ACCOUNT)
	{
		FinishRequest(SUSAMUNE_GHOST_STATUS_INVALID_REQUEST, 0, 0);
		return;
	}
    if (Request.command == SUSAMUNE_GHOST_CMD_WEB_LIST || Request.command == SUSAMUNE_GHOST_CMD_WEB_DOWNLOAD) {
        WebStart(); return;
    }
    if(Request.command==SUSAMUNE_GHOST_CMD_WEB_ACCOUNT) {
        if(Request.profile!=SUSAMUNE_GHOST_IMPORTED_PROFILE || Request.slot>GHOST_ACCOUNT_UNLINK ||
            Request.flags || Request.payloadSize || Request.expectedGeneration) {
            FinishRequest(SUSAMUNE_GHOST_STATUS_INVALID_REQUEST,0,0);return;
        }
        WebAccountStart(Request.slot,0);return;
    }
    if(WebCacheOwned) {
        GhostServiceForget();memset(&BrowseMemory,0,sizeof(BrowseMemory));WebCacheOwned=false;
    }
	if (Request.profile != SUSAMUNE_GHOST_IMPORTED_PROFILE && !SusamuneGhostPersonalProfile(Request.profile))
	{
		FinishRequest(SUSAMUNE_GHOST_STATUS_INVALID_SLOT, 0, 0);
		return;
	}
	if (Request.command == SUSAMUNE_GHOST_CMD_DELETE)
		RequestListCache()->valid = false;
	if (Request.command == SUSAMUNE_GHOST_CMD_LIST || Request.command == SUSAMUNE_GHOST_CMD_IMPORT_SCAN)
	{
		if (Request.payloadSize || Request.expectedGeneration ||
			(Request.command == SUSAMUNE_GHOST_CMD_IMPORT_SCAN && Request.profile != SUSAMUNE_GHOST_IMPORTED_PROFILE)) {
			FinishRequest(SUSAMUNE_GHOST_STATUS_INVALID_REQUEST, 0, 0);
			return;
		}
		if (!PublishCachedPage()) EnsureCatalog();
		return;
	}
	if (Request.profile == SUSAMUNE_GHOST_IMPORTED_PROFILE)
	{
		char normalized[SUSAMUNE_GHOST_IMPORT_LEAF_SIZE];
		WCHAR wide[SUSAMUNE_GHOST_IMPORT_LEAF_SIZE];
		u32 length;
		if ((Request.command != SUSAMUNE_GHOST_CMD_LOAD && Request.command != SUSAMUNE_GHOST_CMD_DELETE) ||
			Request.payloadSize != sizeof(Request.leaf)) {
			FinishRequest(SUSAMUNE_GHOST_STATUS_INVALID_REQUEST, 0, 0);
			return;
		}
		sync_before_read((void*)GHOST_PAYLOAD, sizeof(Request.leaf));
		memcpy(Request.leaf, (const void*)GHOST_PAYLOAD, sizeof(Request.leaf));
		for (length = 0; length < sizeof(Request.leaf); ++length)
		{
			wide[length] = (u8)Request.leaf[length];
			if (!wide[length]) break;
		}
		if (length == sizeof(Request.leaf) || !ImportLeafIsValid(wide, normalized) || strcmp(normalized, Request.leaf))
		{
			FinishRequest(SUSAMUNE_GHOST_STATUS_INVALID_REQUEST, 0, 0);
			return;
		}
		EnsureCatalog();
		return;
	}
	if (!PersonalSlotValid(Request.slot) &&
		!(Request.command == SUSAMUNE_GHOST_CMD_SAVE && Request.slot == SUSAMUNE_GHOST_SLOT_AUTO)) {
		FinishRequest(SUSAMUNE_GHOST_STATUS_INVALID_SLOT, 0, 0);
		return;
	}
	if (Request.command != SUSAMUNE_GHOST_CMD_SAVE)
	{
		memset(&WebUpload,0,sizeof(WebUpload));
		if(Request.command==SUSAMUNE_GHOST_CMD_WEB_UPLOAD && Request.payloadSize==sizeof(WebUpload)) {
			sync_before_read((void*)GHOST_PAYLOAD,sizeof(WebUpload));
			memcpy(&WebUpload,(void*)GHOST_PAYLOAD,sizeof(WebUpload));
			if(!GhostServiceDescriptionValid(WebUpload.description)) {
				FinishRequest(SUSAMUNE_GHOST_STATUS_INVALID_REQUEST,0,0);return;
			}
			Request.payloadSize=0;
		}
		if (Request.payloadSize)
		{
			FinishRequest(SUSAMUNE_GHOST_STATUS_INVALID_REQUEST, 0, 0);
			return;
		}
		EnsureCatalog();
		return;
	}
	if (Request.expectedGeneration)
	{
		FinishRequest(SUSAMUNE_GHOST_STATUS_INVALID_REQUEST, 0, 0);
		return;
	}
	if (Request.payloadSize < SUSAMUNE_GHOST_FILE_HEADER_SIZE ||
	    Request.payloadSize > SUSAMUNE_GHOST_MAX_FILE_SIZE ||
	    Request.payloadSize > SUSAMUNE_GHOST_STORAGE_PAYLOAD_SIZE)
	{
		FinishRequest(SUSAMUNE_GHOST_STATUS_PAYLOAD_TOO_LARGE, 0, 0);
		return;
	}

	sync_before_read((void*)GHOST_PAYLOAD, Request.payloadSize);
	validate = BeginCanonicalValidation((const u8*)GHOST_PAYLOAD,
	                                    Request.payloadSize,
	                                    Request.profile, false);
	if (validate == VALIDATE_FORWARD)
	{
		FinishRequest(SUSAMUNE_GHOST_STATUS_FORWARD_VERSION, 0, 0);
		return;
	}
	if (validate != VALIDATE_OK)
	{
		FinishRequest(SUSAMUNE_GHOST_STATUS_INVALID_FILE, 0, 0);
		return;
	}
	Phase = OP_VALIDATE_SAVE;
}

bool SusamuneGhostQuiescent(void)
{
	return Phase == OP_IDLE && !IoFileOpen && !ImportDirOpen && !CloseFailed;
}

bool SusamuneGhostRetireFailed(void)
{
	return CloseFailed;
}

bool SusamuneGhostRequestReady(u32 seq, u32 command)
{
	volatile struct SusamuneGhostStorageMailbox *mailbox = GhostBlock();
	sync_before_read((void*)&mailbox->request, sizeof(mailbox->request));
	return Phase == OP_IDLE && !Retiring && seq && seq != GhostAckSeq &&
		mailbox->request.requestSeq == seq && mailbox->request.command == command;
}

bool SusamuneGhostReceiptReady(u32 seq, u32 command)
{
	return Phase == OP_IDLE && GhostAckSeq == seq && Request.seq == seq && Request.command == command;
}

void SusamuneGhostInit(void)
{
	volatile struct SusamuneGhostStorageMailbox *mailbox = GhostBlock();

	if (!SusamuneGhostQuiescent()) return;
	memset(&WebAccount,0,sizeof(WebAccount));WebAccountLoaded=false;WebAccountGeneration=WebAccountBank=0;
	Retiring = false;
	/* Reserved lines belong to the transfer coordinator, even across Init. */
	memset((void*)mailbox, 0, sizeof(mailbox->request) + sizeof(mailbox->response));
	GhostRegion = SUSAMUNE_MOD_REGION_TAG(GAME_ID);
	GhostRegionId = GAME_ID == SUSAMUNE_GHOST_GAME_ID_JP
		? SUSAMUNE_GHOST_REGION_JP
		: GAME_ID == SUSAMUNE_GHOST_GAME_ID_US
		? SUSAMUNE_GHOST_REGION_US : SUSAMUNE_GHOST_REGION_PAL;
	GhostSupported = SusamuneCfgStorageAvailable() && GhostRegion != NULL;
	GhostAckSeq = 0;
    GhostServiceForget();WebCacheOwned=false;
	memset(ListCache, 0, sizeof(ListCache));
	ScanCaching = false;
	CatalogReady = false;
	CatalogUnsafe = false;
	ImportedCatalogReady = false;
	ImportedCatalogCount = 0;
	IoFileOpen = false;
	ImportDirOpen = false;
	Phase = OP_IDLE;

	mailbox->response.responseMagic = SUSAMUNE_GHOST_STORAGE_MAGIC;
	mailbox->response.protocolVersion = SUSAMUNE_GHOST_STORAGE_VERSION;
	mailbox->response.flags = GhostSupported
		? SUSAMUNE_GHOST_RESPONSE_READY : 0;
	mailbox->response.ackSeq = 0;
	mailbox->response.status = GhostSupported
		? SUSAMUNE_GHOST_STATUS_OK
		: SUSAMUNE_GHOST_STATUS_STORAGE_UNAVAILABLE;
	mailbox->response.slotCount = 0;
	sync_after_write((void*)mailbox, sizeof(mailbox->request) + sizeof(mailbox->response));
}

bool SusamuneGhostPending(void)
{
	volatile struct SusamuneGhostStorageMailbox *mailbox = GhostBlock();

	if (Phase != OP_IDLE)
		return Retiring || SusamuneTransferAllows(TW_OWNER_GHOST, Request.seq, 0, Request.command);
	if (Retiring)
		return false;
	sync_before_read((void*)&mailbox->request, 32);
	return mailbox->request.requestSeq != GhostAckSeq &&
		SusamuneTransferAllows(TW_OWNER_GHOST, mailbox->request.requestSeq, 0, mailbox->request.command);
}

void SusamuneGhostService(void)
{
	int validate;
	if (Phase != OP_IDLE && !Retiring &&
		!SusamuneTransferAllows(TW_OWNER_GHOST, Request.seq, 0, Request.command)) return;

    if ((Phase == OP_WEB_READ || Phase == OP_WEB_VALIDATE) &&
        (Retiring || SusamuneTransferCancelled(TW_OWNER_GHOST))) { WebFail(GHOST_SERVICE_CANCELLED); return; }
	switch (Phase)
	{
        case OP_WEB_WAIT: WebWaitPass(); break;
        case OP_WEB_READ: WebReadPass(); break;
        case OP_WEB_VALIDATE: WebValidatePass(); break;
		case OP_IDLE:

			if (!Retiring) StartRequest();
			break;
		case OP_VALIDATE_SAVE:
			validate = ContinueCanonicalValidation();
			if (validate < 0)
				break;
			if (validate != VALIDATE_OK)
				FinishRequest(SUSAMUNE_GHOST_STATUS_INVALID_FILE, 0, 0);
			else
				EnsureCatalog();
			break;
		case OP_PERSONAL_SCAN_OPEN:
			PersonalScanOpenPass();
			break;
		case OP_PERSONAL_SCAN_NEXT:
			PersonalScanNextPass();
			break;
		case OP_SCAN_ENVELOPES:
			ScanEnvelopePass();
			break;
		case OP_SCAN_ACTIVE_HEADERS:
			ScanActiveHeaderPass();
			break;
		case OP_SAVE_OPEN:
			SaveOpenPass();
			break;
		case OP_SAVE_DATA:
			SaveDataPass();
			break;
		case OP_SAVE_SYNC_DATA:
			SaveSyncDataPass();
			break;
		case OP_SAVE_COMMIT:
			SaveCommitPass();
			break;
		case OP_SAVE_FINISH:
			SaveFinishPass();
			break;
		case OP_LOAD_OPEN:
			LoadOpenPass();
			break;
		case OP_LOAD_DATA:
			LoadDataPass();
			break;
		case OP_LOAD_CLOSE:
			LoadClosePass();
			break;
		case OP_VALIDATE_LOAD:
			ValidateLoadPass();
			break;
		case OP_EXPORT_OPEN:
			ExportOpenPass();
			break;
		case OP_EXPORT_DATA:
			ExportDataPass();
			break;
		case OP_EXPORT_SYNC_DATA:
			ExportSyncDataPass();
			break;
		case OP_EXPORT_COMMIT:
			ExportCommitPass();
			break;
		case OP_EXPORT_FINISH:
			ExportFinishPass();
			break;
		case OP_IMPORT_SCAN_OPEN:
			ImportScanOpenPass();
			break;
		case OP_IMPORT_SCAN_NEXT:
			ImportScanNextPass();
			break;
		case OP_IMPORT_SCAN_FILE_OPEN:
			ImportScanFileOpenPass();
			break;
		case OP_IMPORT_SCAN_FILE_READ:
			ImportScanFileReadPass();
			break;
		case OP_IMPORT_SCAN_FILE_CLOSE:
			ImportScanFileClosePass();
			break;
		case OP_DELETE_OPEN:
			DeleteOpenPass();
			break;
		case OP_DELETE_FINISH:
			DeleteFinishPass();
			break;
		case OP_DELETE_RECLAIM:
			DeleteReclaimPass();
			break;
		case OP_IMPORTED_DELETE:
			ImportedDeletePass();
			break;
	}
}

bool SusamuneGhostRetire(void)
{
	volatile struct SusamuneGhostStorageMailbox *mailbox = GhostBlock();
	Retiring = true;
	if (Phase != OP_IDLE) SusamuneGhostService();
	if (!SusamuneGhostQuiescent()) return false;
	sync_before_read((void*)&mailbox->request, sizeof(mailbox->request));
	GhostAckSeq = mailbox->request.requestSeq;
	return true;
}
