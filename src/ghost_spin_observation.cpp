#include "susamune/ghost_spin_observation.hxx"
#if MOONSHINE_GHOST_TRACE
#include "susamune/features.hxx"

#if defined(SUSAMUNE_VERSION_JP)
#define SPIN_ENTRY 0x80130758u
#define SPIN_TEXT_END "0x8036fba0"
static constexpr unsigned kRetailHash = 0xb7b58844u;
#define SPIN_CALLERS "0x8012b864,0x80132cfc,0x801330a4,0x80133384,0x80134c24,0x80139384,0x8013998c,0x80139bf0,0x8013c138,0"
#elif defined(SUSAMUNE_VERSION_US)
#define SPIN_ENTRY 0x80251304u
#define SPIN_TEXT_END "0x803730c0"
static constexpr unsigned kRetailHash = 0x507141f8u;
#define SPIN_CALLERS "0x8024c3fc,0x8025390c,0x80253cb4,0x80253f94,0x80255834,0x80259f94,0x8025a530,0x8025a794,0x8025ccf4,0"
#elif defined(SUSAMUNE_VERSION_PAL)
#define SPIN_ENTRY 0x80249090u
#define SPIN_TEXT_END "0x8036b2e0"
static constexpr unsigned kRetailHash = 0x464a144au;
#define SPIN_CALLERS "0x80244188,0x8024b698,0x8024ba40,0x8024bd20,0x8024d5c0,0x80251d20,0x802522bc,0x80252520,0x80254a80,0"
#endif

extern "C" {
GhostSpinObservation::Queue *gGhostSpinObservationQueue;
void ghostSpinObservationReturn();
}

// No calls or stack writes: even a frame after the result could seed the next
// retail call's uninitialized quadrant words. All callers run on the game thread.
asm(
    ".pushsection .rodata.ghostSpinCallers,\"a\",@progbits\n"
    ".balign 4\n"
    "ghostSpinCallers:\n"
    ".long " SPIN_CALLERS "\n"
    ".popsection\n"
    ".pushsection .text.ghostSpinObservationReturn,\"ax\",@progbits\n"
    ".global ghostSpinObservationReturn\n"
    ".type ghostSpinObservationReturn,@function\n"
    "ghostSpinObservationReturn:\n"
    "lis 0,gGhostSpinObservationQueue@h\n"
    "ori 0,0,gGhostSpinObservationQueue@l\n"
    "lwzx 0,0,0\n"
    "stwx 12,0,0\n"
    "mr 12,0\n"
    "stw 11,4(12)\n"
    "mfcr 11\n"
    "stw 11,8(12)\n"
    "stw 10,12(12)\n"
    "lwz 0,0(4)\n"
    "stw 0,492(12)\n"
    "lis 10,ghostSpinCallers@ha\n"
    "addi 10,10,ghostSpinCallers@l\n"
    "mflr 11\n"
    ".Lspin_find:\n"
    "lwz 0,0(10)\n"
    "cmpwi 0,0\n"
    "beq .Lspin_unknown\n"
    "cmplw 0,11\n"
    "beq .Lspin_found\n"
    "addi 10,10,4\n"
    "b .Lspin_find\n"
    ".Lspin_found:\n"
    "lis 0,ghostSpinCallers@h\n"
    "ori 0,0,ghostSpinCallers@l\n"
    "subf 11,0,10\n"
    "srwi 11,11,2\n"
    "addi 11,11,1\n"
    "lwz 0,348(12)\n"
    "cmpwi 0,2\n"
    "beq .Lspin_play\n"
    "cmpwi 0,1\n"
    "bne .Lspin_bad\n"
    "lwz 0,16(12)\n"
    "cmplwi 0,16\n"
    "bge .Lspin_overflow\n"
    "mulli 10,0,20\n"
    "addi 10,10,28\n"
    "add 10,12,10\n"
    "stw 11,4(10)\n"
    "stw 3,8(10)\n"
    "lwz 0,0(4)\n"
    "stw 0,12(10)\n"
    "cmplwi 3,1\n"
    "bgt .Lspin_bad\n"
    "cmpwi 3,0\n"
    "bne .Lspin_yes\n"
    "cmpwi 0,4\n"
    "bne .Lspin_bad\n"
    "b .Lspin_commit\n"
    ".Lspin_yes:\n"
    "cmplwi 0,2\n"
    "blt .Lspin_bad\n"
    "cmplwi 0,3\n"
    "bgt .Lspin_bad\n"
    ".Lspin_commit:\n"
    "lwz 11,24(12)\n"
    "addi 11,11,1\n"
    "stw 11,24(12)\n"
    "stw 11,0(10)\n"
    "li 0,1\n"
    "stw 0,16(10)\n"
    "lwz 11,16(12)\n"
    "addi 11,11,1\n"
    "stw 11,16(12)\n"
    "b .Lspin_done\n"
    ".Lspin_play:\n"
    "lwz 0,20(12)\n"
    "cmpwi 0,0\n"
    "bne .Lspin_done\n"
    "lwz 0,352(12)\n"
    "lwz 10,16(12)\n"
    "cmplw 0,10\n"
    "bge .Lspin_underrun\n"
    "cmplwi 10,16\n"
    "bgt .Lspin_overflow\n"
    "mulli 10,0,20\n"
    "addi 10,10,28\n"
    "add 10,12,10\n"
    "lwz 0,4(10)\n"
    "cmplw 11,0\n"
    "bne .Lspin_caller\n"
    "lwz 11,24(12)\n"
    "addi 11,11,1\n"
    "lwz 0,0(10)\n"
    "cmplw 11,0\n"
    "bne .Lspin_sequence\n"
    "lwz 0,352(12)\n"
    "slwi 11,0,2\n"
    "add 11,12,11\n"
    "lwz 0,364(11)\n"
    "lwz 11,356(12)\n"
    "cmplw 0,11\n"
    "bne .Lspin_tick\n"
    "lwz 0,352(12)\n"
    "slwi 11,0,2\n"
    "add 11,12,11\n"
    "lwz 0,428(11)\n"
    "lwz 11,360(12)\n"
    "cmplw 0,11\n"
    "bne .Lspin_tick\n"
    "lwz 0,16(10)\n"
    "cmpwi 0,1\n"
    "bne .Lspin_bad\n"
    "lwz 0,8(10)\n"
    "cmplwi 0,1\n"
    "bgt .Lspin_bad\n"
    "cmpwi 0,0\n"
    "lwz 11,12(10)\n"
    "bne .Lspin_play_yes\n"
    "cmpwi 11,4\n"
    "bne .Lspin_bad\n"
    "b .Lspin_apply\n"
    ".Lspin_play_yes:\n"
    "cmplwi 11,2\n"
    "blt .Lspin_bad\n"
    "cmplwi 11,3\n"
    "bgt .Lspin_bad\n"
    ".Lspin_apply:\n"
    "lwz 3,8(10)\n"
    "stw 11,0(4)\n"
    "lwz 11,0(10)\n"
    "stw 11,24(12)\n"
    "lwz 11,352(12)\n"
    "addi 11,11,1\n"
    "stw 11,352(12)\n"
    "b .Lspin_done\n"
    ".Lspin_caller:\n"
    "lwz 0,20(12)\n"
    "ori 0,0,8\n"
    "stw 0,20(12)\n"
    "b .Lspin_done\n"
    ".Lspin_sequence:\n"
    "lwz 0,20(12)\n"
    "ori 0,0,16\n"
    "stw 0,20(12)\n"
    "b .Lspin_done\n"
    ".Lspin_underrun:\n"
    "lwz 0,20(12)\n"
    "ori 0,0,32\n"
    "stw 0,20(12)\n"
    "b .Lspin_done\n"
    ".Lspin_tick:\n"
    "lwz 0,20(12)\n"
    "ori 0,0,64\n"
    "stw 0,20(12)\n"
    "b .Lspin_done\n"
    ".Lspin_unknown:\n"
    "lis 0,0x8000\n"
    "ori 0,0,0x5600\n"
    "cmplw 11,0\n"
    "blt .Lspin_done\n"
    ".set ghostSpinTextEnd," SPIN_TEXT_END "\n"
    "lis 0,ghostSpinTextEnd@h\n"
    "ori 0,0,ghostSpinTextEnd@l\n"
    "cmplw 11,0\n"
    "bge .Lspin_done\n"
    "lwz 0,20(12)\n"
    "ori 0,0,2\n"
    "stw 0,20(12)\n"
    "b .Lspin_done\n"
    ".Lspin_overflow:\n"
    "lwz 0,20(12)\n"
    "ori 0,0,1\n"
    "stw 0,20(12)\n"
    "b .Lspin_done\n"
    ".Lspin_bad:\n"
    "lwz 0,20(12)\n"
    "ori 0,0,4\n"
    "stw 0,20(12)\n"
    ".Lspin_done:\n"
    "lwz 10,12(12)\n"
    "lwz 11,4(12)\n"
    "lwz 0,8(12)\n"
    "mtcrf 255,0\n"
    "lwz 0,492(12)\n"
    "lwz 12,0(12)\n"
    "addi 1,1,48\n"
    "blr\n"
    ".size ghostSpinObservationReturn,.-ghostSpinObservationReturn\n"
    ".popsection\n"
);

namespace GhostSpinObservation {
namespace {
constexpr unsigned kSite = SPIN_ENTRY + 0x188u, kOriginal = 0x38210030u;
unsigned hookWord() {
    const unsigned target = unsigned(reinterpret_cast<__UINTPTR_TYPE__>(&ghostSpinObservationReturn));
    const unsigned delta = target-kSite;
    if ((delta&3u) || delta+0x02000000u>=0x04000000u) return 0;
    return 0x48000000u|(delta&0x03fffffcu);
}
bool retailBytes(unsigned hook) {
    const auto *words=reinterpret_cast<volatile const unsigned *>(SPIN_ENTRY);
    const unsigned installed=words[0x188/4];
    if(installed!=kOriginal && (!hook || installed!=hook))return false;
    unsigned hash=2166136261u;
    for(unsigned offset=0;offset<0x190;offset+=4) {
        const unsigned word=offset==0x188?kOriginal:words[offset/4];
        for(unsigned shift=32;shift;shift-=8)hash=(hash^((word>>(shift-8))&255u))*16777619u;
    }
    return hash==kRetailHash;
}
}
bool install(Queue &queue,Mode mode) {
    if(mode!=RECORD&&mode!=PLAYBACK)return false;
    const unsigned hook=hookWord();
    if(!hook||!retailBytes(hook))return false;
    const unsigned current=*reinterpret_cast<volatile const unsigned *>(kSite);
    if(gGhostSpinObservationQueue)return gGhostSpinObservationQueue==&queue&&current==hook&&queue.mode==unsigned(mode);
    if(current!=kOriginal || (reinterpret_cast<__UINTPTR_TYPE__>(&queue)&3u))return false;
    if(mode==RECORD)queue.count=queue.error=queue.sequence=queue.read=0;
    if(queue.count>kCapacity||queue.read>queue.count||queue.error)return false;
    queue.mode=mode;gGhostSpinObservationQueue=&queue;
    writeGameCode(kSite,hook);
    return *reinterpret_cast<volatile const unsigned *>(kSite)==hook;
}
bool uninstall(Mode owner) {
    const unsigned hook=hookWord();
    if(!gGhostSpinObservationQueue)return !hook||*reinterpret_cast<volatile const unsigned *>(kSite)!=hook;
    if(owner!=NONE&&gGhostSpinObservationQueue->mode!=unsigned(owner))return true;
    if(!hook||!retailBytes(hook))return false;
    const unsigned current=*reinterpret_cast<volatile const unsigned *>(kSite);
    if(current==hook) {
        if(!gGhostSpinObservationQueue)return false;
        writeGameCode(kSite,kOriginal);
    }
    if(*reinterpret_cast<volatile const unsigned *>(kSite)!=kOriginal)return false;
    gGhostSpinObservationQueue=nullptr;return true;
}
}
#endif
