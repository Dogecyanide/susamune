#include <stdlib.h>
#include <string.h>
#include <sys/param.h>

#include "global.h"
#include "SusamuneText.h"
#include "font_ja_zip.h"
#include "ff_utf8.h"

typedef struct
{
	const char *english;
	const char *japanese;
} LauncherText;

#include "SusamuneTextData.inc"

static void *sFontData;
static GRRLIB_ttfFont *sFont;
static bool sJapanese;
static bool sJapaneseRequested;

static void SusamuneTextSetJapanese(bool enabled)
{
	unsigned int size = 0;
	sJapaneseRequested = enabled;
	if (enabled && sFont == NULL)
	{
		if (unzip_data(font_ja_zip, font_ja_zip_size, &sFontData, &size))
			sFont = GRRLIB_LoadTTF(sFontData, size);
		if (sFont == NULL)
		{
			free(sFontData);
			sFontData = NULL;
		}
	}
	// A failed face keeps the readable English fallback in service.
	sJapanese = enabled && sFont != NULL;
}

void SusamuneTextLoadLanguage(const char *launchDirectory)
{
	char path[MAXPATHLEN];
	char language[3];
	size_t length = 0;
	FIL file;
	UINT read = 0;
	bool japanese = false;
	SusamuneTextSetJapanese(false);
	if (launchDirectory == NULL) return;
	while (length < sizeof(path) && launchDirectory[length] != '\0') length++;
	if (length == 0 || length > sizeof(path) - sizeof("language.txt") ||
		launchDirectory[length - 1] != '/') return;
	memcpy(path, launchDirectory, length);
	memcpy(path + length, "language.txt", sizeof("language.txt"));
	// Never find another install's language when the launching app is unknown.
	if (f_open_char(&file, path, FA_READ | FA_OPEN_EXISTING) != FR_OK) return;
	if (file.obj.objsize == sizeof(language) &&
		f_read(&file, language, sizeof(language), &read) == FR_OK &&
		read == sizeof(language))
		japanese = language[0] == 'j' && language[1] == 'a' && language[2] == '\n';
	if (f_close(&file) != FR_OK) japanese = false;
	SusamuneTextSetJapanese(japanese);
}

bool SusamuneTextJapaneseRequested(void)
{
	return sJapaneseRequested;
}

void SusamuneTextShutdown(void)
{
	GRRLIB_FreeTTF(sFont);
	sFont = NULL;
	free(sFontData);
	sFontData = NULL;
	sJapanese = false;
	sJapaneseRequested = false;
}

const char *SusamuneText(const char *english)
{
	size_t lo = 0;
	size_t hi = sizeof(kText) / sizeof(kText[0]);
	if (!sJapanese || english == NULL)
		return english;
	while (lo < hi)
	{
		const size_t mid = lo + (hi - lo) / 2;
		const int order = strcmp(english, kText[mid].english);
		if (order == 0)
			return kText[mid].japanese;
		if (order < 0)
			hi = mid;
		else
			lo = mid + 1;
	}
	return english;
}

GRRLIB_ttfFont *SusamuneTextFont(void)
{
	return sJapanese ? sFont : myFont;
}
