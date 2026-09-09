#ifndef SUSAMUNE_TEXT_H
#define SUSAMUNE_TEXT_H

#include "grrlib.h"

void SusamuneTextSetJapanese(bool enabled);
void SusamuneTextShutdown(void);
const char *SusamuneText(const char *english);
GRRLIB_ttfFont *SusamuneTextFont(void);

#endif
