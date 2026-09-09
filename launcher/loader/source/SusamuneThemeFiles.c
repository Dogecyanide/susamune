#include <stdio.h>
#include <string.h>

#include "ff_utf8.h"
#include "SusamuneThemeFiles.h"

FRESULT SusamuneThemeFindFile(char *out, size_t outSize, const char *device,
	const char *leaf, FILINFO *info)
{
	int written;

	if (out == NULL || outSize == 0 || device == NULL || leaf == NULL || info == NULL)
		return FR_INVALID_NAME;
	if ((strcmp(device, "sd") != 0 && strcmp(device, "usb") != 0) ||
	    (strcmp(leaf, "background.png") != 0 && strcmp(leaf, "bgm.mp3") != 0))
		return FR_INVALID_NAME;
	written = snprintf(out, outSize, "%s:/Moonshine_Theme/%s", device, leaf);
	if (written <= 0 || (size_t)written >= outSize)
		return FR_INVALID_NAME;
	return f_stat_char(out, info);
}
