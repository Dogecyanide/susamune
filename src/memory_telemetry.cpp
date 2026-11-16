#include "susamune/ghost_trace.hxx"
#include "susamune/memory_telemetry.hxx"
#if MOONSHINE_MEMORY_TELEMETRY
#include "susamune/memory_telemetry_scan.h"
#include "susamune/memory_capture.hxx"
#include "susamune/ghost_memory.hxx"
#include "susamune/addresses.hxx"
#include "SMS/System/Application.hxx"
#include "Dolphin/OS.h"
#include "Dolphin/string.h"

extern "C" bool memoryTelemetryStates(unsigned *);
extern "C" bool memoryTelemetryGhosts(unsigned *);

namespace MemoryTelemetry {
namespace {
unsigned sLast, sSerial, sPage;
unsigned word(unsigned address) { return *reinterpret_cast<volatile const unsigned *>(address); }
}
void update(LiveRaceSession::Session &session, unsigned now) {
    // A private-build observer uses the existing authenticated session; no RAM commands.
    if (!session.info.connected || session.info.host ||
        strcmp(session.info.remoteName, "Memory monitor")) { sPage = 0; return; }
    if (MemoryCapture::send(session, now) || session.info.pending) return;
    if (!sPage) { if (now - sLast < 500u) return; sLast = now; }
#if MOONSHINE_GHOST_TRACE
    unsigned values[16]={sPage?0x4d4d5435u:0x4d4d5434u,++sSerial,
        (static_cast<unsigned>(SUSAMUNE_GAME_VERSION-1)<<24)|(static_cast<unsigned>(gpApplication.mContext)<<16)|
        (static_cast<unsigned>(gpApplication.mCurrentScene.mAreaID)<<8)|gpApplication.mCurrentScene.mEpisodeID,1};
    if(sPage)GhostTrace::status(values+4);else GhostMemory::status(values+4);
    values[15]=now;
#else
    unsigned values[16] = {0x4d4d5431u + sPage, ++sSerial,
        (static_cast<unsigned>(SUSAMUNE_GAME_VERSION - 1) << 24) |
        (static_cast<unsigned>(gpApplication.mContext) << 16) |
        (static_cast<unsigned>(gpApplication.mCurrentScene.mAreaID) << 8) |
        gpApplication.mCurrentScene.mEpisodeID};
#if TIMEWARP_QF_MEMORY
    if (sPage == 3) { values[3]=1u|(MOONSHINE_MEMORY_CAPTURE?2u:0u);GhostMemory::status(values+4);values[15]=now; }
    else
#endif
    if (sPage == 1) {
        if (memoryTelemetryStates(values + 4)) values[3] |= 1;
        if (memoryTelemetryGhosts(values + 10)) values[3] |= 2;
        values[15] = now;
    } else {
    MemoryPoolSample audio = {}, archive = {};
    const unsigned started = OSGetTick();
    const bool interrupts = OSDisableInterrupts();
    if (!sPage && MemoryWaveSample(SUSAMUNE_MEM1_ADDR(0x803e6334u, 0x803fd82cu, 0x803f4fccu), word, audio)) {
        values[3] |= 1; values[4] = audio.capacity; values[5] = audio.used;
        values[6] = audio.largestFree; values[7] = audio.tailExtent;
    }
    const unsigned manager = word(SUSAMUNE_MEM1_ADDR(0x804097c8u, 0x8040e230u, 0x80405908u));
    if (!sPage && MemoryArchiveSample(manager, SUSAMUNE_MEM1_ADDR(0x80400b8cu, 0x80404290u, 0x803fba30u), word, archive)) {
        values[3] |= 2; values[8] = archive.capacity; values[9] = archive.used;
        values[10] = archive.largestFree; values[11] = archive.tailExtent;
    }
    if (sPage == 2) {
        const unsigned vtable = SUSAMUNE_MEM1_ADDR(0x803a8548u, 0x803dff38u, 0x803d78f0u);
        const unsigned root = word(SUSAMUNE_MEM1_ADDR(0x80409830u, 0x8040e298u, 0x80405970u));
        const unsigned system = word(SUSAMUNE_MEM1_ADDR(0x80409828u, 0x8040e290u, 0x80405968u));
        if (MemoryExpSample(root, vtable, word, audio)) {
            values[3] |= 1; values[4] = audio.capacity; values[5] = audio.used;
            values[6] = audio.largestFree;
        }
        if (MemoryExpSample(system, vtable, word, archive)) {
            values[3] |= 2; values[8] = archive.capacity; values[9] = archive.used;
            values[10] = archive.largestFree;
        }
    }
    const unsigned heap = sPage == 2 ? word(SUSAMUNE_MEM1_ADDR(0x80409cc0u, 0x8040e690u, 0x80405d68u)) :
        reinterpret_cast<unsigned>(gpApplication.mCurrentHeap);
    if (MemoryReadable(heap, 0x78) && word(heap) ==
        SUSAMUNE_MEM1_ADDR(0x803a8690u, 0x803e0070u, 0x803d7a28u)) {
        const unsigned start = word(heap + 0x30), end = word(heap + 0x34);
        const unsigned head = word(heap + 0x6c), tail = word(heap + 0x70);
        if (MemoryReadable(start, 0) && MemoryReadable(end, 0) && end >= start &&
            head >= start && head <= tail && tail <= end && word(heap + 0x38) == end - start &&
            word(heap + 0x68) == tail - head) {
            values[3] |= 4; values[12] = end - start; values[13] = tail - head;
        }
    }
    OSRestoreInterrupts(interrupts);
    values[14] = OSGetTick() - started; values[15] = now;
    }
#endif
    unsigned char body[64];
    for (unsigned i = 0; i < 16; ++i) MSRWrite32(body + i * 4, values[i]);
    if (LiveRaceSession::sendReliable(session, MSR_READY, body, sizeof(body), session.nowMs))
        sPage = (sPage + 1) % (MOONSHINE_GHOST_TRACE ? 2u : TIMEWARP_QF_MEMORY ? 4u : 3u);
}
}
#endif
