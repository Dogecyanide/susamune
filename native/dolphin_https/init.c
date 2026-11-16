#include <string.h>
extern unsigned char __native_bss_start[], __native_bss_end[];
/* A copied data word survives clearing BSS and resets on a fresh game boot. */
static unsigned boot = 0x4d534930u;
void MoonshineNativeInit(void) {
    if(boot==0x4d534931u)return;
    memset(__native_bss_start,0,__native_bss_end-__native_bss_start);
    boot=0x4d534931u;
}
