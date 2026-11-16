#include "MoonshineMem2Audit.h"
#if MOONSHINE_MEM2_DIAGNOSTICS
#include <gccore.h>
#include <stdio.h>
#include <string.h>
#include "global.h"
#include "exi.h"
#include "ff_utf8.h"
#include "susamune/data_paths.h"

extern void *__SYS_GetIPCBufferLo(void);
extern void *__SYS_GetIPCBufferHi(void);
extern volatile unsigned int FoundVersion;

static const unsigned short kOffsets[] = {
    0x3118, 0x311c, 0x3120, 0x3124, 0x3128,
    0x3130, 0x3134, 0x3140, 0x3148, 0x314c
};
static const char *const kPhases[] = {"before_ios_reload", "after_ios_reload", "before_game_handoff"};
struct MemoryReceipt {
    unsigned int low[10];
    unsigned int arenaLo, arenaHi, ipcLo, ipcHi, requestedIos;
    unsigned int wiiU, wiiVc, captured;
};
static struct MemoryReceipt sReceipts[3];

void MoonshineMem2AuditCapture(unsigned int phase)
{
    unsigned int i;
    struct MemoryReceipt *receipt;
    if (phase >= 3) return;
    receipt = &sReceipts[phase];
    /* IOS rewrites these words on reload; libogc's cached arena can stay old. */
    for (i = 0; i < 10; ++i)
        receipt->low[i] = *(volatile unsigned int *)(0xc0000000u + kOffsets[i]);
    receipt->arenaLo = (unsigned int)SYS_GetArena2Lo();
    receipt->arenaHi = (unsigned int)SYS_GetArena2Hi();
    receipt->ipcLo = (unsigned int)__SYS_GetIPCBufferLo();
    receipt->ipcHi = (unsigned int)__SYS_GetIPCBufferHi();
    receipt->requestedIos = FoundVersion;
    receipt->wiiU = IsWiiU();
    receipt->wiiVc = isWiiVC;
    receipt->captured = 1;
}

static int WriteLine(FIL *file, const char *line)
{
    UINT wrote = 0;
    const UINT size = (UINT)strlen(line);
    return f_write(file, line, size, &wrote) == FR_OK && wrote == size;
}

void MoonshineMem2AuditWrite(const char *device)
{
    FIL file;
    FRESULT result;
    unsigned int generation, phase, i;
    int good;
    char path[128], line[160];
    if (!device || (strcmp(device, "sd") && strcmp(device, "usb"))) return;
    for (generation = 0; generation < 100; ++generation) {
        snprintf(path, sizeof(path), "%s:" MOONSHINE_DATA_ROOT "/mem2_probe_%02u.log", device, generation);
        result = f_open_char(&file, path, FA_WRITE | FA_CREATE_NEW);
        if (result != FR_EXIST) break;
    }
    if (generation == 100 || result != FR_OK) return;
    /* Record ownership evidence only. Never read, write or grant the candidate. */
    good = WriteLine(&file, "Moonshine MEM2 ownership probe v1\nCandidate 93400000..935e0000; bytes_granted=0\n");
    for (phase = 0; phase < 3 && good; ++phase) {
        const struct MemoryReceipt *receipt = &sReceipts[phase];
        snprintf(line, sizeof(line), "[%s] captured=%u requested_ios=%08x wii_u=%u wii_vc=%u\n",
            kPhases[phase], receipt->captured, receipt->requestedIos, receipt->wiiU, receipt->wiiVc);
        good = WriteLine(&file, line);
        for (i = 0; i < 10 && good; ++i) {
            snprintf(line, sizeof(line), "low_%04x=%08x\n", kOffsets[i], receipt->low[i]);
            good = WriteLine(&file, line);
        }
        if (good) {
            snprintf(line, sizeof(line), "libogc_arena=%08x..%08x libogc_ipc=%08x..%08x\n",
                receipt->arenaLo, receipt->arenaHi, receipt->ipcLo, receipt->ipcHi);
            good = WriteLine(&file, line);
        }
    }
    if (good) good = WriteLine(&file, "receipt_complete=1\n");
    if (good) good = f_sync(&file) == FR_OK;
    if (f_close(&file) != FR_OK) good = 0;
    gprintf("Moonshine MEM2 probe: %s (%s)\n", path, good ? "saved" : "incomplete");
}
#endif
