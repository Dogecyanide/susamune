// Included by the config owner; service runs under its existing FatFS guard.
static char HoverlessPaths[2][80];
static u32 HoverlessGeneration, HoverlessAck;
static s32 HoverlessActive = -1;
static bool HoverlessReady;

static int ReadHoverless(const char *path, struct SusamuneHoverlessFile *file)
{
	FIL f;
	UINT got = 0;
	int ret = f_open_char(&f, path, FA_READ | FA_OPEN_EXISTING);
	if (ret != FR_OK) return ret;
	if (f_size(&f) != sizeof(*file)) ret = FR_INVALID_OBJECT;
	else ret = f_read(&f, file, sizeof(*file), &got);
	const int closed = f_close(&f);
	if (ret != FR_OK) return ret;
	if (closed != FR_OK) return closed;
	return got == sizeof(*file) && SusamuneHoverlessValid(file, GAME_ID)
		? FR_OK : FR_INVALID_OBJECT;
}

static void InitHoverless(const char *region)
{
	struct SusamuneHoverlessCfg *cfg = SUSAMUNE_HOVERLESS_PHYS_PTR;
	struct SusamuneHoverlessFile file;
	u32 i;
	bool safe = true;
	memset(cfg, 0, sizeof(*cfg));
	cfg->magic = SUSAMUNE_HOVERLESS_MAGIC;
	cfg->version = SUSAMUNE_HOVERLESS_VERSION;
	cfg->rule = SUSAMUNE_HOVERLESS_RULE;
	cfg->count = SUSAMUNE_ILING_PB_MAX_SLOTS;
	cfg->activeProfile = SUSAMUNE_HOVERLESS_INHERIT_PROFILE;
	for (i = 0; i < cfg->count; ++i) cfg->values[i] = -1;
	HoverlessActive = -1;
	HoverlessGeneration = HoverlessAck = 0;
	for (i = 0; i < 2; ++i) {
		_sprintf(HoverlessPaths[i], "%s/moonshine_hoverless_v1_%s_%c.bin",
			SusamuneCfgStoragePrefix(), region, i ? 'b' : 'a');
		int ret = ReadHoverless(HoverlessPaths[i], &file);
		if (ret == FR_NO_FILE || ret == FR_NO_PATH) continue;
		if (ret != FR_OK) { safe = false; continue; }
		if (HoverlessActive >= 0 && !PbGenerationIsNewer(file.generation, HoverlessGeneration)) continue;
		memcpy(cfg->values, file.values, sizeof(cfg->values));
		cfg->activeProfile = file.activeProfile;
		HoverlessGeneration = file.generation;
		HoverlessActive = i;
	}
	HoverlessReady = safe;
	if (safe) cfg->flags = SUSAMUNE_HOVERLESS_WRITABLE;
	sync_after_write(cfg, sizeof(*cfg));
}

static bool HoverlessPending(void)
{
	struct SusamuneHoverlessCfg *cfg = SUSAMUNE_HOVERLESS_PHYS_PTR;
	if (!HoverlessReady) return false;
	sync_before_read(cfg, 32);
	return cfg->magic == SUSAMUNE_HOVERLESS_MAGIC && cfg->version == SUSAMUNE_HOVERLESS_VERSION &&
		cfg->rule == SUSAMUNE_HOVERLESS_RULE && cfg->saveSeq != HoverlessAck;
}

static void ServiceHoverless(void)
{
	struct SusamuneHoverlessCfg *cfg = SUSAMUNE_HOVERLESS_PHYS_PTR;
	struct SusamuneHoverlessFile file, verify;
	const u32 seq = cfg->saveSeq;
	const u32 target = HoverlessActive == 0 ? 1 : 0;
	FIL f;
	UINT wrote = 0;
	int ret = FR_INVALID_PARAMETER;
	sync_before_read(cfg->values, sizeof(cfg->values));
	memset(&file, 0, sizeof(file));
	file.magic = SUSAMUNE_HOVERLESS_MAGIC;
	file.version = SUSAMUNE_HOVERLESS_VERSION;
	file.rule = SUSAMUNE_HOVERLESS_RULE;
	file.count = cfg->count;
	file.activeProfile = cfg->activeProfile;
	file.gameId = GAME_ID;
	file.generation = HoverlessGeneration + 1;
	memcpy(file.values, cfg->values, sizeof(file.values));
	file.checksum = SusamuneHoverlessChecksum(&file);
	if (SusamuneHoverlessValid(&file, GAME_ID)) {
		ret = f_open_char(&f, HoverlessPaths[target], FA_WRITE | FA_CREATE_ALWAYS);
		if (ret == FR_OK) {
			ret = f_write(&f, &file, sizeof(file), &wrote);
			if (ret == FR_OK && wrote != sizeof(file)) ret = FR_DISK_ERR;
			const int closed = f_close(&f);
			if (ret == FR_OK) ret = closed;
		}
		if (ret == FR_OK) ret = ReadHoverless(HoverlessPaths[target], &verify);
		if (ret == FR_OK && memcmp(&file, &verify, sizeof(file))) ret = FR_DISK_ERR;
		if (ret == FR_OK) { HoverlessActive = target; HoverlessGeneration = file.generation; }
	}
	cfg->status = ret;
	cfg->ackSeq = HoverlessAck = seq;
	sync_after_write(&cfg->ackSeq, 32);
}
