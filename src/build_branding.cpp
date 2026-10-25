#include "susamune/build_branding.hxx"
#include "susamune/menu.hxx"

namespace {

const char kVersion[] __attribute__((section(".rodata.build_branding.version"))) =
    "3.0.0 Timewarp";
const char kTitle[] __attribute__((section(".rodata.build_branding.title"))) =
    "Moonshine 3.0.0 Timewarp";
const char kCodename[] __attribute__((section(".rodata.build_branding.codename"))) =
    "TIMEWARP";
const char kCrashFormat[] __attribute__((section(".rodata.build_branding.crash"))) =
    "\nMOONSHINE 3.0.0 Timewarp\n"
    "REPORT %08X-%08X\n%s  MOD %08X\n"
    "EXCEPTION %u  CONTEXT %u\n"
    "PC %08X  LR %08X\nSP %08X  DAR %08X\n"
    "DSISR %08X  SRR1 %08X\n"
    "SCENE %08X  LAST %u\nSAVE: %s\n"
    "Photo this block; share .core/.bin/.txt\n";

}

namespace BuildBranding {
const char *version(const char *) { return kVersion; }
const char *title(const char *) { return kTitle; }
const char *codename(const char *) { return kCodename; }
const char *crashFormat(const char *) { return kCrashFormat; }
void drawHeader(Menu *menu, const char *product, const char *,
                int left, int top, int right, int titleSize, int versionSize) {
    menu->drawText(product, left - 2, top, titleSize, titleSize,
                   JUtility::TColor(238, 242, 252, 255));
    menu->drawText(kVersion, right - Menu::textWidth(kVersion, versionSize), top + 9,
                   versionSize, versionSize, JUtility::TColor(255, 196, 90, 255));
}
}
