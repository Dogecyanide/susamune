#include "SusamuneCrash.h"

#include "SusamuneCfg.h"
#include "ff_utf8.h"
#include "string.h"
#include "susamune/crash_report.h"
#include "susamune/mod_bin.h"
#include "vsprintf.h"

extern u32 GAME_ID;
extern int dbgprintf(const char *fmt, ...);

static struct SusamuneCrashReport Snapshot;
static struct SusamuneCrashCore CoreSnapshot;
static char BinPaths[2][64];
static char TextPaths[2][64];
static char CorePaths[2][64];
static char Line[256];
static u32 AttemptedSeq;
static u32 SeenCoreSeq;
static u32 SeenFullSeq;
static u32 LastPoll;
static bool CrashEnabled;
static bool HaveFull;
static bool HaveCore;
static bool RetryPending;
static u32 Attempts;
static u32 SavedFlags;
static u32 LastAttempt;
static FIL TextFile;
static int TextStatus;

static const u32 CrcNibbleTable[16] = {
	0x00000000u, 0x1DB71064u, 0x3B6E20C8u, 0x26D930ACu,
	0x76DC4190u, 0x6B6B51F4u, 0x4DB26158u, 0x5005713Cu,
	0xEDB88320u, 0xF00F9344u, 0xD6D6A3E8u, 0xCB61B38Cu,
	0x9B64C2B0u, 0x86D3D2D4u, 0xA00AE278u, 0xBDBDF21Cu
};

static inline u32 CrcByte(u32 crc, u8 byte)
{
	crc ^= byte;
	crc = (crc >> 4) ^ CrcNibbleTable[crc & 15u];
	return (crc >> 4) ^ CrcNibbleTable[crc & 15u];
}

static u32 ReportChecksum(const void *report, u32 size)
{
	const u8 *bytes = (const u8*)report;
	u32 crc = 0xFFFFFFFFu;
	u32 i;
	for (i = 0; i < size; ++i)
	{
		bool checksumByte =
			i >= __builtin_offsetof(struct SusamuneCrashReport, checksum) &&
			i < __builtin_offsetof(struct SusamuneCrashReport, checksum) + 4;
		crc = CrcByte(crc, checksumByte ? 0u : bytes[i]);
	}
	return crc ^ 0xFFFFFFFFu;
}

static u32 CrashChecksum(const struct SusamuneCrashReport *report)
{
	return ReportChecksum(report, sizeof(*report));
}

static bool ValidCore(const struct SusamuneCrashCore *core)
{
	return core->magic == SUSAMUNE_CRASH_CORE_MAGIC &&
		core->version == SUSAMUNE_CRASH_CORE_VERSION &&
		core->reportSize == sizeof(*core) &&
		core->state == SUSAMUNE_CRASH_STATE_READY &&
		core->contextValid <= 1 && core->build[sizeof(core->build) - 1] == 0 &&
		core->checksum == ReportChecksum(core, sizeof(*core));
}

static void PublishAck(u32 status, int error)
{
	struct SusamuneCrashAck *ack = SUSAMUNE_CRASH_ACK_PHYS_PTR;
	memset(ack, 0, sizeof(*ack));
	ack->magic = SUSAMUNE_CRASH_ACK_MAGIC;
	ack->captureSeq = AttemptedSeq;
	ack->status = status;
	ack->error = (u32)error;
	ack->attempts = Attempts;
	ack->savedFlags = SavedFlags;
	sync_after_write(ack, sizeof(*ack));
}

static bool ValidReport(const struct SusamuneCrashReport *report)
{
	return report->magic == SUSAMUNE_CRASH_MAGIC &&
		report->version == SUSAMUNE_CRASH_VERSION &&
		report->reportSize == sizeof(*report) &&
		report->state == SUSAMUNE_CRASH_STATE_READY &&
		report->breadcrumbCount <= SUSAMUNE_CRASH_BREADCRUMB_COUNT &&
		report->stackSize <= SUSAMUNE_CRASH_STACK_SIZE &&
		report->pcWindowSize <= SUSAMUNE_CRASH_CODE_WINDOW_SIZE &&
		report->lrWindowSize <= SUSAMUNE_CRASH_CODE_WINDOW_SIZE &&
		report->directorWindowSize <= SUSAMUNE_CRASH_DIRECTOR_SIZE &&
		report->marioWindowSize <= SUSAMUNE_CRASH_MARIO_SIZE &&
		report->checksum == CrashChecksum(report);
}

static bool GenerationNewer(u32 candidate, u32 current)
{
	return (s32)(candidate - current) > 0;
}

static bool ReadReport(const char *path, struct SusamuneCrashReport *report)
{
	FIL file;
	UINT read = 0;
	int ret = f_open_char(&file, path, FA_READ | FA_OPEN_EXISTING);
	int closeRet;
	if (ret != FR_OK)
		return false;
	if (file.obj.objsize != sizeof(*report))
	{
		f_close(&file);
		return false;
	}
	ret = f_read(&file, report, sizeof(*report), &read);
	closeRet = f_close(&file);
	return ret == FR_OK && closeRet == FR_OK && read == sizeof(*report) &&
		ValidReport(report);
}

static bool ReadCore(const char *path)
{
	FIL file;
	UINT got = 0;
	int ret = f_open_char(&file, path, FA_READ | FA_OPEN_EXISTING);
	int closeRet;
	if (ret != FR_OK)
		return false;
	if (file.obj.objsize != sizeof(CoreSnapshot))
	{
		f_close(&file);
		return false;
	}
	ret = f_read(&file, &CoreSnapshot, sizeof(CoreSnapshot), &got);
	closeRet = f_close(&file);
	return ret == FR_OK && closeRet == FR_OK && got == sizeof(CoreSnapshot) &&
		ValidCore(&CoreSnapshot);
}

static u32 ModFileCrc(const struct SusamuneModHeader *header, u32 fileSize)
{
	const u8 *bytes = (const u8*)header;
	u32 crc = 0xFFFFFFFFu;
	u32 i;
	for (i = 0; i < fileSize; ++i)
		crc = CrcByte(crc, bytes[i]);
	return crc ^ 0xFFFFFFFFu;
}

static bool ValidStagedMod(const struct SusamuneModHeader *header)
{
	u32 fileSize;
	sync_before_read((void*)header, SUSAMUNE_MOD_HEADER_SIZE);
	if (!SusamuneModHeaderValid(header, GAME_ID))
		return false;
	fileSize = SusamuneModFileSize(header);
	sync_before_read((void*)header, fileSize);
	return SusamuneModFileValid(header, GAME_ID, fileSize);
}

void SusamuneCrashInit(void)
{
	struct SusamuneCrashReport *mailbox = SUSAMUNE_CRASH_PHYS_PTR;
	const struct SusamuneModHeader *mod = SUSAMUNE_MOD_PHYS_PTR;
	u32 generation = 0;
	u32 modFileSize;
	u32 i;

	memset(mailbox, 0, sizeof(*mailbox));
	CrashEnabled = SusamuneCfgStorageAvailable();
	AttemptedSeq = 0;
	SeenCoreSeq = SeenFullSeq = 0;
	Attempts = SavedFlags = 0;
	HaveFull = HaveCore = RetryPending = false;
	LastPoll = read32(HW_TIMER);
	LastAttempt = LastPoll;
	memset(SUSAMUNE_CRASH_CORE_PHYS_PTR, 0, sizeof(CoreSnapshot));
	sync_after_write(SUSAMUNE_CRASH_CORE_PHYS_PTR, sizeof(CoreSnapshot));
	_sprintf(BinPaths[0], "%s/susamune_crash_a.bin",
		SusamuneCfgStoragePrefix());
	_sprintf(BinPaths[1], "%s/susamune_crash_b.bin",
		SusamuneCfgStoragePrefix());
	_sprintf(TextPaths[0], "%s/susamune_crash_a.txt",
		SusamuneCfgStoragePrefix());
	_sprintf(TextPaths[1], "%s/susamune_crash_b.txt",
		SusamuneCfgStoragePrefix());
	_sprintf(CorePaths[0], "%s/susamune_crash_a.core",
		SusamuneCfgStoragePrefix());
	_sprintf(CorePaths[1], "%s/susamune_crash_b.core",
		SusamuneCfgStoragePrefix());

	if (CrashEnabled)
	{
		for (i = 0; i < 2; ++i)
		{
			if (ReadReport(BinPaths[i], &Snapshot) &&
				GenerationNewer(Snapshot.captureSeq, generation))
				generation = Snapshot.captureSeq;
			if (ReadCore(CorePaths[i]) &&
				GenerationNewer(CoreSnapshot.captureSeq, generation))
				generation = CoreSnapshot.captureSeq;
		}
	}

	mailbox->magic = SUSAMUNE_CRASH_MAGIC;
	mailbox->version = SUSAMUNE_CRASH_VERSION;
	mailbox->reportSize = sizeof(*mailbox);
	mailbox->state = SUSAMUNE_CRASH_STATE_ARMED;
	mailbox->captureSeq = generation + 1;
	if (mailbox->captureSeq == 0)
		mailbox->captureSeq = 1;
	mailbox->gameId = GAME_ID;
	if (ValidStagedMod(mod))
	{
		modFileSize = SusamuneModFileSize(mod);
		sync_before_read((void*)mod, modFileSize);
		mailbox->modFileCrc32 = ModFileCrc(mod, modFileSize);
		mailbox->modFileSize = modFileSize;
		mailbox->modCodeSize = mod->memSize;
		mailbox->modWriteCount = mod->writeCount;
		mailbox->arenaReserve = mod->arenaReserve;
	}
	sync_after_write(mailbox, sizeof(*mailbox));
	PublishAck(CrashEnabled ? SUSAMUNE_CRASH_ACK_PENDING :
		SUSAMUNE_CRASH_ACK_UNAVAILABLE, 0);
}

bool SusamuneCrashPending(void)
{
	struct SusamuneCrashReport *mailbox = SUSAMUNE_CRASH_PHYS_PTR;
	struct SusamuneCrashCore *core = SUSAMUNE_CRASH_CORE_PHYS_PTR;
	bool fullReady, coreReady;
	if (!CrashEnabled)
		return false;
	if (TimerDiffTicks(LastPoll) < 15820)
		return false;
	LastPoll = read32(HW_TIMER);
	sync_before_read(mailbox, 32);
	sync_before_read(core, 32);
	fullReady = mailbox->magic == SUSAMUNE_CRASH_MAGIC &&
		mailbox->version == SUSAMUNE_CRASH_VERSION &&
		mailbox->reportSize == sizeof(*mailbox) &&
		mailbox->state == SUSAMUNE_CRASH_STATE_READY;
	coreReady = core->magic == SUSAMUNE_CRASH_CORE_MAGIC &&
		core->version == SUSAMUNE_CRASH_CORE_VERSION &&
		core->reportSize == sizeof(*core) &&
		core->state == SUSAMUNE_CRASH_STATE_READY;
	if ((fullReady && mailbox->captureSeq != SeenFullSeq) ||
	    (coreReady && core->captureSeq != SeenCoreSeq))
		return true;
	if (Attempts >= 3)
		return false;
	if (fullReady && !HaveFull)
		return true;
	return RetryPending && TimerDiffTicks(LastAttempt) >= 474600;
}

static const char *ExceptionName(u32 exception)
{
	static const char *names[] = {
		"System reset", "Machine check", "DSI", "ISI",
		"External interrupt", "Alignment", "Program",
		"Floating point unavailable", "Decrementer", "System call",
		"Trace", "Performance monitor", "IABR", "Reserved", "Thermal"
	};
	return exception < sizeof(names) / sizeof(names[0]) ? names[exception] :
		"Unknown";
}

static const char *RegionName(u32 gameId)
{
	if (gameId == SUSAMUNE_MOD_GAME_ID_JP)
		return "JP/GMSJ";
	if (gameId == SUSAMUNE_MOD_GAME_ID_US)
		return "US/GMSE";
	if (gameId == SUSAMUNE_MOD_GAME_ID_PAL)
		return "PAL/GMSP";
	return "unknown";
}

static void Emit(const char *text, u32 length)
{
	UINT wrote = 0;
	if (TextStatus != FR_OK)
		return;
	TextStatus = f_write(&TextFile, text, length, &wrote);
	if (TextStatus == FR_OK && wrote != length)
		TextStatus = FR_DISK_ERR;
}

static void EmitString(const char *text)
{
	Emit(text, strlen(text));
}

static void EmitHex(const char *label, u32 base, const u8 *data, u32 size)
{
	u32 offset, i;
	Emit(Line, _sprintf(Line, "%s base=%08X size=%u\r\n", label, base, size));
	for (offset = 0; offset < size; offset += 16)
	{
		u32 count = size - offset < 16 ? size - offset : 16;
		u32 length = _sprintf(Line, "%08X:", base + offset);
		for (i = 0; i < count; ++i)
			length += _sprintf(Line + length, " %02X", data[offset + i]);
		length += _sprintf(Line + length, "\r\n");
		Emit(Line, length);
	}
}

static int WriteText(u32 target)
{
	u32 i, start;
	int closeRet;
	TextStatus = f_open_char(&TextFile, TextPaths[target],
		FA_WRITE | FA_CREATE_ALWAYS);
	if (TextStatus != FR_OK)
		return TextStatus;

	if (HaveCore)
	{
		Emit(Line, _sprintf(Line, "%.63s\r\n", CoreSnapshot.build));
		Emit(Line, _sprintf(Line,
			"REPORT %08X-%08X  %s  MOD %08X\r\n",
			CoreSnapshot.captureSeq, CoreSnapshot.checksum,
			RegionName(CoreSnapshot.gameId), CoreSnapshot.modFileCrc32));
		Emit(Line, _sprintf(Line, "EXCEPTION %u (%s)  CONTEXT %s\r\n",
			CoreSnapshot.exception, ExceptionName(CoreSnapshot.exception),
			CoreSnapshot.contextValid ? "available" : "unavailable"));
		Emit(Line, _sprintf(Line, "PC %08X  LR %08X  SP %08X\r\n",
			CoreSnapshot.srr0, CoreSnapshot.lr, CoreSnapshot.gpr[1]));
		Emit(Line, _sprintf(Line, "DAR %08X  DSISR %08X  SRR1 %08X\r\n",
			CoreSnapshot.dar, CoreSnapshot.dsisr, CoreSnapshot.srr1));
		Emit(Line, _sprintf(Line, "SCENE %08X  CONTEXT %u  LAST %u %08X %08X\r\n",
			CoreSnapshot.currentScene, CoreSnapshot.appContext,
			CoreSnapshot.lastEvent, CoreSnapshot.lastArg0, CoreSnapshot.lastArg1));
		EmitString("Share this report and matching .core/.bin files.\r\n\r\n");
	}
	if (!HaveFull)
	{
		EmitString("Minimal capture only; optional capture did not complete.\r\n");
		for (i = 0; i < 32; i += 4)
			Emit(Line, _sprintf(Line,
				"r%02u=%08X r%02u=%08X r%02u=%08X r%02u=%08X\r\n",
				i, CoreSnapshot.gpr[i], i + 1, CoreSnapshot.gpr[i + 1],
				i + 2, CoreSnapshot.gpr[i + 2], i + 3, CoreSnapshot.gpr[i + 3]));
		goto finish;
	}
	Emit(Line, _sprintf(Line, "Moonshine crash report v%u\r\n",
		Snapshot.version));
	Emit(Line, _sprintf(Line,
		"generation=%u region=%s game_id=%08X mod_crc32=%08X\r\n",
		Snapshot.captureSeq, RegionName(Snapshot.gameId), Snapshot.gameId,
		Snapshot.modFileCrc32));
	Emit(Line, _sprintf(Line, "full_crc32=%08X\r\n", Snapshot.checksum));
	Emit(Line, _sprintf(Line,
		"mod_file_size=%u mod_code_size=%u hook_writes=%u arena_reserve=%u\r\n",
		Snapshot.modFileSize, Snapshot.modCodeSize, Snapshot.modWriteCount,
		Snapshot.arenaReserve));
	Emit(Line, _sprintf(Line,
		"exception=%u (%s) flags=%04X dsisr=%08X dar=%08X\r\n",
		Snapshot.exception, ExceptionName(Snapshot.exception),
		Snapshot.captureFlags, Snapshot.dsisr, Snapshot.dar));
	Emit(Line, _sprintf(Line,
		"srr0=%08X srr1=%08X lr=%08X cr=%08X ctr=%08X xer=%08X\r\n",
		Snapshot.srr0, Snapshot.srr1, Snapshot.lr, Snapshot.cr,
		Snapshot.ctr, Snapshot.xer));
	Emit(Line, _sprintf(Line,
		"time_base=%08X%08X context_mode=%u context_state=%u thread=%08X\r\n",
		Snapshot.timeBaseHigh, Snapshot.timeBaseLow, Snapshot.contextMode,
		Snapshot.contextState, Snapshot.currentThread));

	for (i = 0; i < 32; i += 4)
		Emit(Line, _sprintf(Line,
			"r%02u=%08X r%02u=%08X r%02u=%08X r%02u=%08X\r\n",
			i, Snapshot.gpr[i], i + 1, Snapshot.gpr[i + 1],
			i + 2, Snapshot.gpr[i + 2], i + 3, Snapshot.gpr[i + 3]));

	Emit(Line, _sprintf(Line,
		"app=%08X director=%08X heap=%08X context=%u cutscene=%08X\r\n",
		Snapshot.appAddress, Snapshot.appDirector, Snapshot.appHeap,
		Snapshot.appContext, Snapshot.cutSceneId));
	Emit(Line, _sprintf(Line,
		"scenes prev=%02X/%02X/%04X current=%02X/%02X/%04X next=%02X/%02X/%04X\r\n",
		Snapshot.prevScene >> 24, Snapshot.prevScene >> 16 & 0xFF,
		Snapshot.prevScene & 0xFFFF, Snapshot.currentScene >> 24,
		Snapshot.currentScene >> 16 & 0xFF, Snapshot.currentScene & 0xFFFF,
		Snapshot.nextScene >> 24, Snapshot.nextScene >> 16 & 0xFF,
		Snapshot.nextScene & 0xFFFF));
	Emit(Line, _sprintf(Line,
		"globals mar_director=%08X mario=%08X camera=%08X ready=%u state_area_episode=%08X\r\n",
		Snapshot.marDirector, Snapshot.mario, Snapshot.camera,
		Snapshot.directorReady, Snapshot.directorStateAreaEpisode));
	Emit(Line, _sprintf(Line,
		"director game_state=%08X demo_states=%08X collected_shine=%08X\r\n",
		Snapshot.directorGameState, Snapshot.directorDemoStates,
		Snapshot.directorCollectedShine));

	EmitString("\r\nBreadcrumbs (event 1=app, 2=context, 3=setup-enter, "
		"4=setup-return, 5=stage-ready, 6=practice, 7=replay, "
		"8=savestate, 9=ghost, 10=storage, 11=draw):\r\n");
	start = Snapshot.breadcrumbSeq - Snapshot.breadcrumbCount;
	for (i = 0; i < Snapshot.breadcrumbCount &&
		i < SUSAMUNE_CRASH_BREADCRUMB_COUNT; ++i)
	{
		const struct SusamuneCrashBreadcrumb *entry =
			&Snapshot.breadcrumbs[(start + i) %
				SUSAMUNE_CRASH_BREADCRUMB_COUNT];
		Emit(Line, _sprintf(Line, "%02u event=%u time=%08X%08X arg0=%08X arg1=%08X\r\n",
			i, entry->event, entry->timeBaseHigh, entry->timeBaseLow,
			entry->arg0, entry->arg1));
	}

	EmitString("\r\nBacktrace:\r\n");
	for (i = 0; i < SUSAMUNE_CRASH_BACKTRACE_COUNT; ++i)
	{
		const struct SusamuneCrashFrame *frame = &Snapshot.backtrace[i];
		if (frame->stackPointer == 0)
			break;
		Emit(Line, _sprintf(Line, "%02u sp=%08X lr=%08X\r\n", i,
			frame->stackPointer, frame->returnAddress));
	}

	EmitString("\r\nMemory windows:\r\n");
	EmitHex("stack", Snapshot.stackBase, Snapshot.stack, Snapshot.stackSize);
	EmitHex("pc", Snapshot.pcWindowBase, Snapshot.pcWindow,
		Snapshot.pcWindowSize);
	EmitHex("lr", Snapshot.lrWindowBase, Snapshot.lrWindow,
		Snapshot.lrWindowSize);
	EmitHex("director", Snapshot.directorWindowBase, Snapshot.directorWindow,
		Snapshot.directorWindowSize);
	EmitHex("mario", Snapshot.marioWindowBase, Snapshot.marioWindow,
		Snapshot.marioWindowSize);

finish:
	if (TextStatus == FR_OK)
		TextStatus = f_sync(&TextFile);
	closeRet = f_close(&TextFile);
	if (TextStatus == FR_OK && closeRet != FR_OK)
		TextStatus = closeRet;
	return TextStatus;
}

static int WriteBinary(const char *path, const void *data, u32 size)
{
	FIL file;
	UINT wrote = 0;
	int ret, closeRet;
	ret = f_open_char(&file, path, FA_WRITE | FA_CREATE_ALWAYS);
	if (ret == FR_OK)
	{
		ret = f_write(&file, data, size, &wrote);
		if (ret == FR_OK && wrote != size)
			ret = FR_DISK_ERR;
		if (ret == FR_OK)
			ret = f_sync(&file);
		closeRet = f_close(&file);
		if (ret == FR_OK && closeRet != FR_OK)
			ret = closeRet;
	}
	return ret;
}

void SusamuneCrashService(void)
{
	struct SusamuneCrashReport *mailbox = SUSAMUNE_CRASH_PHYS_PTR;
	struct SusamuneCrashCore *core = SUSAMUNE_CRASH_CORE_PHYS_PTR;
	bool fullValid, coreValid;
	u32 sequence, target;
	int ret, error = FR_OK;

	sync_before_read(mailbox, sizeof(*mailbox));
	sync_before_read(core, sizeof(*core));
	if (mailbox->state == SUSAMUNE_CRASH_STATE_READY)
		SeenFullSeq = mailbox->captureSeq;
	if (core->state == SUSAMUNE_CRASH_STATE_READY)
		SeenCoreSeq = core->captureSeq;
	memcpy(&CoreSnapshot, core, sizeof(CoreSnapshot));
	coreValid = ValidCore(&CoreSnapshot);
	fullValid = mailbox->state == SUSAMUNE_CRASH_STATE_READY;
	if (fullValid)
	{
		memcpy(&Snapshot, mailbox, sizeof(Snapshot));
		fullValid = ValidReport(&Snapshot);
	}
	sequence = coreValid ? CoreSnapshot.captureSeq : mailbox->captureSeq;
	if (sequence != AttemptedSeq)
	{
		AttemptedSeq = sequence;
		Attempts = SavedFlags = 0;
		HaveFull = HaveCore = RetryPending = false;
	}
	LastAttempt = read32(HW_TIMER);
	++Attempts;
	if (!coreValid && !fullValid)
	{
		Attempts = 3;
		PublishAck(SUSAMUNE_CRASH_ACK_FAILED, FR_INVALID_OBJECT);
		return;
	}
	if (fullValid && Snapshot.captureSeq == sequence && !HaveFull)
	{
		HaveFull = true;
		SavedFlags &= ~SUSAMUNE_CRASH_SAVED_TEXT;
	}
	HaveCore = coreValid && CoreSnapshot.captureSeq == sequence;
	target = sequence & 1u;
	PublishAck(SUSAMUNE_CRASH_ACK_PENDING, 0);
	if (HaveCore && !(SavedFlags & SUSAMUNE_CRASH_SAVED_CORE))
	{
		ret = WriteBinary(CorePaths[target], &CoreSnapshot, sizeof(CoreSnapshot));
		if (ret == FR_OK) SavedFlags |= SUSAMUNE_CRASH_SAVED_CORE;
		else error = ret;
	}
	if (HaveFull && !(SavedFlags & SUSAMUNE_CRASH_SAVED_FULL))
	{
		ret = WriteBinary(BinPaths[target], &Snapshot, sizeof(Snapshot));
		if (ret == FR_OK) SavedFlags |= SUSAMUNE_CRASH_SAVED_FULL;
		else if (error == FR_OK) error = ret;
	}
	if (!(SavedFlags & SUSAMUNE_CRASH_SAVED_TEXT))
	{
		ret = WriteText(target);
		if (ret == FR_OK) SavedFlags |= SUSAMUNE_CRASH_SAVED_TEXT;
		else if (error == FR_OK) error = ret;
	}
	RetryPending = error != FR_OK && Attempts < 3;
	PublishAck(error != FR_OK ? (RetryPending ? SUSAMUNE_CRASH_ACK_PENDING :
		SUSAMUNE_CRASH_ACK_FAILED) : (HaveFull ? SUSAMUNE_CRASH_ACK_SAVED :
		SUSAMUNE_CRASH_ACK_CORE_ONLY), error);
	dbgprintf("Moonshine: crash %u saved_flags=%X error=%d attempt=%u\r\n",
		sequence, SavedFlags, error, Attempts);
}
