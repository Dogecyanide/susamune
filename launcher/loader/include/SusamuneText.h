#ifndef SUSAMUNE_TEXT_H
#define SUSAMUNE_TEXT_H

#include "grrlib.h"

void SusamuneTextLoadLanguage(const char *launchDirectory);
bool SusamuneTextJapaneseRequested(void);
void SusamuneTextShutdown(void);
const char *SusamuneText(const char *english);
GRRLIB_ttfFont *SusamuneTextFont(void);

#endif
