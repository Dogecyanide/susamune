#ifndef _SUSAMUNE_BUILD_BRANDING_HXX
#define _SUSAMUNE_BUILD_BRANDING_HXX

class Menu;

namespace BuildBranding {
// Keep legacy arguments in their source pools; the pinned timer shares them.
const char *version(const char *legacy);
const char *title(const char *legacy);
const char *codename(const char *legacy);
const char *crashFormat(const char *legacy);
void drawHeader(Menu *menu, const char *product, const char *legacyVersion,
                int left, int top, int right, int titleSize, int versionSize);
}

#endif
