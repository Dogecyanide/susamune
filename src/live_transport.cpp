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

// STUN codec begin
namespace LiveStun {
namespace {
const unsigned char kCookie[4] = {0x21, 0x12, 0xa4, 0x42};
unsigned read16(const unsigned char *p) { return static_cast<unsigned>(p[0]) << 8 | p[1]; }
}
void request(unsigned char *out, const unsigned char *transaction) {
    out[0] = 0; out[1] = 1; out[2] = out[3] = 0; // Binding Request, no attributes.
    for (unsigned i = 0; i < 4; ++i) out[4 + i] = kCookie[i];
    for (unsigned i = 0; i < TRANSACTION_BYTES; ++i) out[8 + i] = transaction[i];
}
bool mapped(const void *data, unsigned bytes, const unsigned char *transaction, TWLiveEndpoint *out) {
    const unsigned char *p = static_cast<const unsigned char *>(data);
    if (bytes < 20 || read16(p) != 0x0101) return false;
    const unsigned end = 20 + read16(p + 2);
    if (end > bytes) return false;
    for (unsigned i = 0; i < 4; ++i) if (p[4 + i] != kCookie[i]) return false;
    for (unsigned i = 0; i < TRANSACTION_BYTES; ++i) if (p[8 + i] != transaction[i]) return false;
    for (unsigned at = 20; at + 4 <= end;) {
        const unsigned type = read16(p + at), size = read16(p + at + 2);
        if (size > end - at - 4) return false;
        if (type == 0x0020 && size == 8 && p[at + 5] == 1) {
            const unsigned port = read16(p + at + 6) ^ 0x2112u;
            if (!port) return false;
            for (unsigned i = 0; i < 4; ++i) out->ip[i] = p[at + 8 + i] ^ kCookie[i];
            out->port = static_cast<unsigned short>(port);
            out->reserved = 0;
            return true;
        }
        at += 4 + ((size + 3) & ~3u);
    }
    return false;
}
}
// STUN codec end

// STUN probe begin
namespace LiveStun {
namespace {
// No DNS on the IOS socket path. Resolved 2026-10-21 from the Netherlands:
// stun.l.google.com -> 74.125.250.129 and stun.cloudflare.com -> 162.159.207.0.
const TWLiveEndpoint kServers[SERVER_COUNT] = {
    {{74, 125, 250, 129}, 19302, 0}, {{162, 159, 207, 0}, 3478, 0}};
Result sResult;
unsigned char sTransaction[TRANSACTION_BYTES];
unsigned sStarted, sSent;
bool sShared, sReady;
bool same(const TWLiveEndpoint &a, const TWLiveEndpoint &b) {
    for (unsigned i = 0; i < 4; ++i) if (a.ip[i] != b.ip[i]) return false;
    return a.port == b.port;
}
void transaction(unsigned char *out, unsigned index) {
    for (unsigned i = 0; i < TRANSACTION_BYTES; ++i) out[i] = sTransaction[i];
    out[TRANSACTION_BYTES - 1] ^= static_cast<unsigned char>(index + 1);
}
void finish(int error) {
    if (!sShared) LiveTransport::stop();
    sResult.error = error;
    sResult.verdict = sResult.answered == (1u << SERVER_COUNT) - 1 ?
        (same(sResult.mapped[0], sResult.mapped[1]) ? SAME_MAPPING : DIFFERENT_MAPPING) :
        sResult.answered ? ONE_REPLY : NO_REPLY;
    sResult.state = error && !sResult.answered ? FAILED : DONE;
}
bool begin(bool shared) {
    sResult = Result{};
    sShared = sReady = shared;
    const OSTime stamp = OSGetTime();
    const unsigned tick = OSGetTick();
    for (unsigned i = 0; i < TRANSACTION_BYTES; ++i)
        sTransaction[i] = static_cast<unsigned char>((i < 8 ? stamp >> (i * 8) : tick >> ((i - 8) * 8)) ^ (0x5d * i));
    sResult.state = RUNNING;
    sStarted = tick;
    sSent = tick - OSMillisecondsToTicks(500);
    return true;
}
}
const Result &result() { return sResult; }
bool start(unsigned short localPort) {
    return sResult.state != RUNNING && LiveTransport::begin(localPort) && begin(false);
}
bool startShared() { return sResult.state != RUNNING && begin(true); }
void cancel() { if (sResult.state == RUNNING && sShared) finish(-1); }
bool accept(const LiveTransport::Packet &packet) {
    if (sResult.state != RUNNING) return false;
    bool server = false;
    unsigned char id[TRANSACTION_BYTES];
    for (unsigned i = 0; i < SERVER_COUNT; ++i) {
        if (!same(packet.endpoint, kServers[i])) continue;
        server = true;
        transaction(id, i);
        if (!(sResult.answered >> i & 1u) && mapped(packet.data, packet.bytes, id, &sResult.mapped[i]))
            sResult.answered |= 1u << i;
    }
    return server;
}
void update() {
    if (sResult.state != RUNNING) return;
    const unsigned now = OSGetTick();
    if (!sShared) {
        const LiveTransport::Status status = LiveTransport::poll();
        if (status.state != TW_LIVE_READY) {
            // The ARM side may not have taken BEGIN yet (still IDLE), and DHCP can take
            // seconds before READY. Wait up to 30 s for an address; only a retired or
            // failed transport, or IDLE after READY, ends the probe early.
            if (status.state == TW_LIVE_FAILED || status.state == TW_LIVE_RETIRING ||
                (status.state == TW_LIVE_IDLE && sReady) ||
                now - sStarted > OSMillisecondsToTicks(sReady ? 15000 : 30000)) finish(status.error ? status.error : -1);
            return;
        }
        if (!sReady) {
            // The probe's own 15 s and the first request start once the address is known.
            sReady = true; sStarted = now; sSent = now - OSMillisecondsToTicks(500);
        }
        LiveTransport::Packet packet;
        for (unsigned n = 0; n < TW_LIVE_RING_COUNT && LiveTransport::receive(packet); ++n) accept(packet);
    }
    if (sResult.answered == (1u << SERVER_COUNT) - 1) { finish(0); return; }
    if (now - sSent < OSMillisecondsToTicks(500)) return;
    if (sResult.attempts == ATTEMPTS || now - sStarted > OSMillisecondsToTicks(15000)) { finish(0); return; }
    unsigned char id[TRANSACTION_BYTES], data[REQUEST_BYTES];
    bool sent = false;
    for (unsigned i = 0; i < SERVER_COUNT; ++i) {
        if (sResult.answered >> i & 1u) continue;
        transaction(id, i);
        request(data, id);
        if (LiveTransport::sendControl(kServers[i], data, sizeof(data))) sent = true;
    }
    if (sent) { ++sResult.attempts; sSent = now; }
}
}
// STUN probe end
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
