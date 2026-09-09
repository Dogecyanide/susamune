#include <stdlib.h>
#include <string.h>

#include "global.h"
#include "SusamuneText.h"
#include "font_ja_zip.h"

typedef struct
{
	const char *english;
	const char *japanese;
} LauncherText;

#include "SusamuneTextData.inc"

static void *sFontData;
static GRRLIB_ttfFont *sFont;
static bool sJapanese;

void SusamuneTextSetJapanese(bool enabled)
{
	unsigned int size = 0;
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

void SusamuneTextShutdown(void)
{
	GRRLIB_FreeTTF(sFont);
	sFont = NULL;
	free(sFontData);
	sFontData = NULL;
	sJapanese = false;
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
