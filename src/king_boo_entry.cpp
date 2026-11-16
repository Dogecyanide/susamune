#include "susamune/king_boo_entry.hxx"

#include "SMS/System/Application.hxx"
#include "susamune/features.hxx"
#include "susamune/addresses.hxx"

// Retail reads joint 1 before its first animation initializes the matrices.
// Clean Sirena entry leaves these two translations zero; the mod's shifted
// heap can leave previous-room data here and move the laugh-skip trigger away.
extern "C" __attribute__((naked)) void susamuneKingBooLoadAfter(void *) {
    asm volatile(
        "lis 4, gpApplication@ha\n"
        "lhz 4, gpApplication+14@l(4)\n"
        "cmpwi 4, 0x3800\n"
        "bnelr\n"
        "lwz 4, 116(3)\n"
        "lwz 4, 4(4)\n"
        "lwz 4, 88(4)\n"
        "li 0, 0\n"
        "stw 0, 60(4)\n"
        "stw 0, 92(4)\n"
        "blr\n");
}

namespace KingBooEntry {
void init() {
    // This final loadAfter call targets the empty TNameRef base implementation.
    constexpr u32 site = SUSAMUNE_MEM1_ADDR(0x802d62dcu, 0x800c3c54u, 0x800bd2f4u);
    constexpr u32 original = SUSAMUNE_MEM1_ADDR(0x4bd6e5d1u, 0x48236aa5u, 0x482355adu);
    constexpr u32 base = SUSAMUNE_MEM1_ADDR(0x800448acu, 0x802fa6f8u, 0x802f28a0u);
    if (*reinterpret_cast<volatile const u32 *>(site) != original ||
        *reinterpret_cast<volatile const u32 *>(base) != 0x4E800020u)
        return;
    writeGameCode(site, branchWord(site,
        reinterpret_cast<u32>(&susamuneKingBooLoadAfter)) | 1u);
}
}
