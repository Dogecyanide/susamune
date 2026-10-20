#include "susamune/live_transport.hxx"

#if TIMEWARP_LIVE_RACING
#include "susamune/susamune_cfg.h"
#include "Dolphin/OS.h"
#if IS_EMULATOR
#include "susamune/dolphin_live_transport.h"
#include "susamune/hoverless.h"
#include "susamune/addresses.hxx"
#endif

namespace LiveTransport {
namespace {
volatile TWLiveMailbox *sWire;
TWLiveIndices sIndices;
unsigned sSession, sRequest, sCommandGeneration, sIndicesGeneration, sPoseGeneration;
bool sStopping;
void flush(volatile void *p, unsigned n) { DCStoreRange((void *)p, n); }
void invalidate(const volatile void *p, unsigned n) { DCInvalidateRange((void *)p, n); }
void barrier() { __asm__ volatile("sync" ::: "memory"); }
const TWLiveIo kIo = {flush, invalidate, barrier};

#if IS_EMULATOR
volatile TWDolphinLive *const kEmulator = (volatile TWDolphinLive *)TW_DOLPHIN_LIVE_BASE;
TWDolphinGame sGame;
unsigned sGameGeneration, sGameTick, sHostGeneration, sHostTick, sHostEpoch;
static_assert(0x719003A0u + SUSAMUNE_ILING_PB_MAX_SLOTS * sizeof(int) <= TW_DOLPHIN_LIVE_BASE,
    "Dolphin transport overlaps hoverless records");
static_assert(0x71900140u + sizeof(SusamuneHoverlessCfg) <= TW_DOLPHIN_LIVE_BASE,
    "Dolphin transport overlaps hoverless handoff");
static_assert(SUSAMUNE_DOLPHIN_RUNTIME_PPC_BASE + SUSAMUNE_DOLPHIN_RUNTIME_SIZE <=
    TW_DOLPHIN_LIVE_BASE, "Dolphin transport overlaps persistent runtime");

bool emulatorPresent() {
    const unsigned now = OSGetTick();
    if (!sGame.magic) {
        kEmulator->game.generation = 0;
        flush(&kEmulator->game, 32); barrier();
        volatile unsigned *words = (volatile unsigned *)kEmulator;
        for (unsigned i = 0; i < sizeof(*kEmulator) / 4; ++i) words[i] = 0;
        flush(kEmulator, sizeof(*kEmulator)); barrier();
        const OSTime stamp = OSGetTime();
        sGame.magic = TW_DOLPHIN_LIVE_MAGIC;
        sGame.abi = TW_DOLPHIN_LIVE_ABI;
        sGame.gameVersion = SUSAMUNE_GAME_VERSION;
        sGame.instance = (static_cast<unsigned>(stamp) ^ static_cast<unsigned>(stamp >> 32)) | 1u;
        sGame.bytes = sizeof(*kEmulator);
        sGameTick = now - OSMillisecondsToTicks(100);
    }
    if (now - sGameTick >= OSMillisecondsToTicks(100)) {
        sGameTick = now;
        sGame.heartbeat = sGameGeneration + 1;
        if (!TWLivePublish(&kEmulator->game, &sGame, sizeof(sGame), &sGameGeneration, &kIo)) return false;
    }
    TWDolphinHost host;
    // A host heartbeat can be withdrawn during this one bounded read.
    if (!TWLiveRead(&host, &kEmulator->host, sizeof(host), &kIo))
        return sHostEpoch && now - sHostTick < OSSecondsToTicks(3);
    if (host.instance != sGame.instance || !host.epoch || !host.heartbeat ||
        host.reserved[0] || host.reserved[1] || host.reserved[2]) return false;
    if (host.epoch != sHostEpoch) {
        sHostEpoch = host.epoch;
        sHostGeneration = 0;
        sSession = 0;
        sStopping = false;
    }
    if (host.generation != sHostGeneration) {
        sHostGeneration = host.generation;
        sHostTick = now;
    }
    return now - sHostTick < OSSecondsToTicks(3);
}
#endif

bool discover() {
#if IS_EMULATOR
    volatile TWLiveMailbox *wire = &kEmulator->wire;
#else
    volatile SusamuneCfg *cfg = SUSAMUNE_CFG_PPC_PTR;
    SusamuneLiveDescriptor descriptor;
    invalidate(cfg, 64); barrier();
    if (cfg->magic != SUSAMUNE_CFG_MAGIC || cfg->version != SUSAMUNE_CFG_VERSION) return false;
    TWLiveCopyIn(&descriptor, &cfg->liveTransport, sizeof(descriptor));
    if (!TWLiveDescriptorValid(descriptor.magic, descriptor.abi, descriptor.ppcAddress,
            descriptor.bytes, descriptor.capabilities, descriptor.reserved)) return false;
    volatile TWLiveMailbox *wire = (volatile TWLiveMailbox *)descriptor.ppcAddress;
#endif
    if (!TWLiveResume(&sCommandGeneration, &wire->command, &kIo) ||
        !TWLiveResume(&sIndicesGeneration, &wire->indices, &kIo) ||
        !TWLiveResume(&sPoseGeneration, &wire->pose, &kIo)) return false;
    sWire = wire;
    return true;
}
bool indices() {
    return TWLivePublish(&sWire->indices, &sIndices, sizeof(sIndices), &sIndicesGeneration, &kIo);
}
bool command(unsigned operation, unsigned localPort) {
    if (sRequest == 0xffffffffu) return false;
    TWLiveCommand request = {};
    request.epoch = sSession;
    request.operation = operation;
    request.sequence = ++sRequest;
    request.localPort = localPort;
    return TWLivePublish(&sWire->command, &request, sizeof(request), &sCommandGeneration, &kIo);
}
bool ready(const Status &status) {
    return sSession && !sStopping && status.epoch == sSession &&
        status.state == TW_LIVE_READY && status.ackSequence == sRequest &&
        TWLiveCountValid(sIndices.txWrite, status.txRead) &&
        TWLiveCountValid(status.rxWrite, sIndices.rxRead);
}
}

Status poll() {
    Status status = {};
#if IS_EMULATOR
    if (!emulatorPresent()) { sSession = 0; sStopping = false; return status; }
#endif
    if ((!sWire && !discover()) || !TWLiveRead(&status, &sWire->status, sizeof(status), &kIo) ||
        !status.epoch || status.state < TW_LIVE_IDLE || status.state > TW_LIVE_FAILED) return Status{};
#if IS_EMULATOR
    if (status.epoch != sHostEpoch) return Status{};
#endif
    if (sSession && sSession != status.epoch) { sSession = 0; sStopping = false; }
    return status;
}
bool diagnostics(const Status &status, Diagnostics *out) {
    TWLiveNetworkInfo info;
    if (!out || !sWire || !status.epoch || status.state != TW_LIVE_READY ||
        !TWLiveRead(&info, &sWire->networkInfo, sizeof(info), &kIo) ||
        info.epoch != status.epoch || (info.reserved[1] >> 24) != 1u) return false;
    Diagnostics next;
    next.sent = info.reserved[0] >> 16;
    next.received = info.reserved[0] & 0xffffu;
    next.dropped = (info.reserved[1] >> 16) & 0xffu;
    next.sendErrors = (info.reserved[1] >> 8) & 0xffu;
    next.receiveErrors = info.reserved[1] & 0xffu;
    next.lastError = static_cast<int>(info.reserved[2]);
    *out = next;
    return true;
}
bool localEndpoint(Endpoint *endpoint) {
    Status status = poll();
    TWLiveNetworkInfo info;
    if (!endpoint || !ready(status) || !TWLiveRead(&info, &sWire->networkInfo, sizeof(info), &kIo) ||
        info.epoch != status.epoch || !TWLiveEndpointValid(&info.endpoint)) return false;
    *endpoint = info.endpoint;
    return true;
}
bool begin(unsigned short localPort) {
    Status status = poll();
    if (!sWire || sSession || status.state != TW_LIVE_IDLE) return false;
    sIndices = {};
    sIndices.epoch = status.epoch;
    if (!indices()) return false;
    sSession = status.epoch;
    sStopping = false;
    if (command(TW_LIVE_BEGIN, localPort)) return true;
    sSession = 0;
    return false;
}
bool sendControl(const Endpoint &endpoint, const void *data, unsigned bytes) {
    Status status = poll();
    if (!ready(status) || !data || !bytes || bytes > TW_LIVE_PACKET_BYTES ||
        !TWLiveEndpointValid(&endpoint) || sIndices.txWrite - status.txRead == TW_LIVE_RING_COUNT ||
        sIndicesGeneration == 0xffffffffu) return false;
    Packet packet = {};
    packet.epoch = sSession; packet.endpoint = endpoint; packet.bytes = bytes;
    TWLiveCopyIn(packet.data, data, bytes);
    volatile Packet *slot = &sWire->tx[sIndices.txWrite & (TW_LIVE_RING_COUNT - 1)];
    TWLiveCopyOut(slot, &packet, sizeof(packet));
    flush(slot, sizeof(packet)); barrier();
    ++sIndices.txWrite;
    return indices();
}
bool publishPose(const Endpoint &endpoint, const void *data, unsigned bytes) {
    Status status = poll();
    if (!ready(status) || !data || !bytes || bytes > TW_LIVE_PACKET_BYTES ||
        !TWLiveEndpointValid(&endpoint)) return false;
    TWLivePose pose = {};
    pose.epoch = sSession; pose.endpoint = endpoint; pose.bytes = bytes;
    TWLiveCopyIn(pose.data, data, bytes);
    return TWLivePublish(&sWire->pose, &pose, sizeof(pose), &sPoseGeneration, &kIo);
}
bool receive(Packet &packet) {
    Status status = poll();
    if (!ready(status) || status.rxWrite == sIndices.rxRead || sIndicesGeneration == 0xffffffffu) return false;
    const volatile Packet *slot = &sWire->rx[sIndices.rxRead & (TW_LIVE_RING_COUNT - 1)];
    invalidate(slot, sizeof(*slot)); barrier();
    Packet candidate;
    TWLiveCopyIn(&candidate, slot, sizeof(candidate));
    ++sIndices.rxRead;
    if (!indices() || !TWLivePacketValid(&candidate, sSession)) return false;
    packet = candidate;
    return true;
}
void stop() {
    poll();
    if (sSession && !sStopping && command(TW_LIVE_STOP, 0)) sStopping = true;
}
}
#else
namespace LiveTransport {
bool begin(unsigned short) { return false; }
Status poll() { return Status{}; }
bool diagnostics(const Status &, Diagnostics *) { return false; }
bool localEndpoint(Endpoint *) { return false; }
bool sendControl(const Endpoint &, const void *, unsigned) { return false; }
bool publishPose(const Endpoint &, const void *, unsigned) { return false; }
bool receive(Packet &) { return false; }
void stop() {}
}
#endif
