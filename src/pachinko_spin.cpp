#include "susamune/pachinko_spin.hxx"

#if defined(SUSAMUNE_VERSION_JP)
#include "SMS/Player/Mario.hxx"
#include "SMS/System/Application.hxx"
#include "susamune/features.hxx"

static_assert(__builtin_offsetof(TMario, mState) == 0x7C &&
              TMario::STATE_RUNNING == 0x04000440 &&
              __builtin_offsetof(TApplication, mCurrentScene) == 0xE &&
              __builtin_offsetof(TGameSequence, mAreaID) == 0 &&
              __builtin_offsetof(TGameSequence, mEpisodeID) == 1,
              "Pachinko spin gate uses retail field offsets");

// No C frame: the retail checker reads uninitialized locals below its caller.
// These four values reproduce JP Pachinko's measured opaque-draw residue.
extern "C" __attribute__((naked)) int susamunePachinkoRunningSpin(TMario *, int *) {
    asm volatile(
        "lis 12, gpApplication@ha\n"
        "lhz 12, gpApplication+14@l(12)\n"
        "cmpwi 12, 0x1600\n"
        "bne 1f\n"
        "lis 12, gpMarioOriginal@ha\n"
        "lwz 12, gpMarioOriginal@l(12)\n"
        "cmplw 3, 12\n"
        "bne 1f\n"
        "lwz 12, 124(3)\n"
        "lis 0, 0x0400\n"
        "ori 0, 0, 0x0440\n"
        "cmplw 12, 0\n"
        "bne 1f\n"
        "stwu 1, -48(1)\n"
        "li 0, 1\n"
        "stw 0, 16(1)\n"
        "stw 0, 28(1)\n"
        "li 0, 0\n"
        "stw 0, 20(1)\n"
        "stw 0, 24(1)\n"
        "b checkStickRotate__6TMarioFPi+4\n"
        "1: b checkStickRotate__6TMarioFPi\n");
}

namespace PachinkoSpin {
void init() {
    // The inlined spin check inside changePlayerTriJump, not the air/wait checks.
    constexpr u32 site = 0x80133380u;
    if (*reinterpret_cast<volatile const u32 *>(site) != 0x4BFFD3D9u) return;
    writeGameCode(site, branchWord(site,
        reinterpret_cast<u32>(&susamunePachinkoRunningSpin)) | 1u);
}
}
#endif
