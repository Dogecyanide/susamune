#ifndef SUSAMUNE_THEME_FILES_H
#define SUSAMUNE_THEME_FILES_H

#include <stddef.h>
#include "ff.h"

FRESULT SusamuneThemeFindFile(char *out, size_t outSize, const char *device,
	const char *leaf, FILINFO *info);

#endif
