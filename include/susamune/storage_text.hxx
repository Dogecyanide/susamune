#pragma once
#if IS_EMULATOR
#define STORAGE_TEXT(console, dolphin) dolphin
#else
#define STORAGE_TEXT(console, dolphin) console
#endif
