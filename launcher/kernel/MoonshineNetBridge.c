#include "MoonshineNetBridge.h"

#if TIMEWARP_LIVE_RACING
#include "MoonshineNet.h"
#include "global.h"
#include "string.h"
#include "susamune/live_transport.h"
#include "susamune/susamune_cfg.h"

static TWLiveMailbox sMailbox;
static TWLiveStatus sStatus;
static unsigned sStatusGeneration, sInfoGeneration, sWorkerEpoch, sPoseSeen;
static int sInitialized, sRetireLatch;
enum { BRIDGE_PROTOCOL_ERROR = -11001, BRIDGE_EXHAUSTED = -11002 };

static void Flush(volatile void *p, unsigned n) { sync_after_write((void *)p, n); }
static void Invalidate(const volatile void *p, unsigned n) { sync_before_read((void *)p, n); }
static void Barrier(void) { __asm__ volatile("" ::: "memory"); }
static const TWLiveIo sIo = {Flush, Invalidate, Barrier};

static void Publish(void)
{
    if (!TWLivePublish(&sMailbox.status, &sStatus, sizeof(sStatus), &sStatusGeneration, &sIo)) {
        /* Never expose an old READY publication after sequence exhaustion. */
        sMailbox.status.generation = 0;
        Flush(&sMailbox.status, 32); Barrier();
        if (sWorkerEpoch) MoonshineNetRequestStop(sWorkerEpoch);
        sInitialized = 0;
    }
}
static void BeginRetire(int error)
{
    if (sStatus.state == TW_LIVE_RETIRING) return;
    sRetireLatch = 1;
    sStatus.state = TW_LIVE_RETIRING;
    sStatus.error = error;
    if (sStatus.epoch == 0xffffffffu) sStatus.error = BRIDGE_EXHAUSTED;
    else ++sStatus.epoch;
    sStatus.txRead = sStatus.rxWrite = sStatus.ackSequence = 0;
    sPoseSeen = 0;
    sMailbox.networkInfo.generation = 0;
    Flush(&sMailbox.networkInfo, 32); Barrier();
    if (sWorkerEpoch) MoonshineNetRequestStop(sWorkerEpoch);
    Publish();
}
static int FinishRetire(void)
{
    if (sStatus.state != TW_LIVE_RETIRING) return !sWorkerEpoch;
    if (sWorkerEpoch && !MoonshineNetRetired(sWorkerEpoch)) return 0;
    sWorkerEpoch = 0;
    sStatus.state = sStatus.error == BRIDGE_EXHAUSTED ? TW_LIVE_FAILED : TW_LIVE_IDLE;
    Publish();
    return 1;
}
static void ToWorker(struct MoonshineNetEndpoint *out, const TWLiveEndpoint *in)
{
    unsigned i;
    for (i = 0; i < 4; ++i) out->ip[i] = in->ip[i];
    out->port[0] = (unsigned char)(in->port >> 8);
    out->port[1] = (unsigned char)in->port;
    out->reserved[0] = out->reserved[1] = 0;
}
static unsigned Saturate(unsigned value, unsigned limit)
{
    return value < limit ? value : limit;
}

void MoonshineNetBridgeInit(void)
{
    struct SusamuneCfg *cfg = SUSAMUNE_CFG_PHYS_PTR;
    unsigned address = (unsigned)&sMailbox + 0x80000000u;
    if (sInitialized || cfg->magic != SUSAMUNE_CFG_MAGIC || cfg->version != SUSAMUNE_CFG_VERSION ||
        !TWLiveDescriptorValid(TW_LIVE_MAGIC, TW_LIVE_ABI, address, sizeof(sMailbox), TW_LIVE_CAP_UDP, 0)) return;
    memset(&sMailbox, 0, sizeof(sMailbox));
    Flush(&sMailbox, sizeof(sMailbox)); Barrier();
    if (!MoonshineNetInit()) return;
    sInitialized = 1;
    sStatus.epoch = 1;
    sStatus.state = TW_LIVE_IDLE;
    Publish();
    cfg->liveTransport.abi = TW_LIVE_ABI;
    cfg->liveTransport.ppcAddress = address;
    cfg->liveTransport.bytes = sizeof(sMailbox);
    cfg->liveTransport.capabilities = TW_LIVE_CAP_UDP;
    cfg->liveTransport.reserved = 0;
    cfg->liveTransport.magic = TW_LIVE_MAGIC;
    Flush(&cfg->ackSeq, 32); Barrier();
}

int MoonshineNetBridgeRetire(void)
{
    if (!sInitialized) return !sWorkerEpoch || MoonshineNetRetired(sWorkerEpoch);
    if (!sRetireLatch) BeginRetire(0);
    return FinishRetire();
}

void MoonshineNetBridgeService(void)
{
    TWLiveCommand command;
    TWLiveIndices indices;
    struct MoonshineNetStatus worker;
    int changed = 0;
    if (!sInitialized) return;
    if (sStatus.state == TW_LIVE_RETIRING) { FinishRetire(); return; }
    if (TWLiveRead(&command, &sMailbox.command, sizeof(command), &sIo) &&
        command.epoch == sStatus.epoch && command.sequence && command.sequence != sStatus.ackSequence) {
        if (command.reserved[0] || command.reserved[1] || command.localPort > 65535u) {
            BeginRetire(BRIDGE_PROTOCOL_ERROR); return;
        }
        if (command.operation == TW_LIVE_STOP) { BeginRetire(0); return; }
        if (command.operation != TW_LIVE_BEGIN) { BeginRetire(BRIDGE_PROTOCOL_ERROR); return; }
        if (sStatus.state == TW_LIVE_IDLE) {
            struct MoonshineNetConfig config;
            if (!TWLiveRead(&indices, &sMailbox.indices, sizeof(indices), &sIo)) return;
            if (indices.epoch != sStatus.epoch || indices.txWrite || indices.rxRead) {
                BeginRetire(BRIDGE_PROTOCOL_ERROR); return;
            }
            memset(&config, 0, sizeof(config));
            config.epoch = sStatus.epoch;
            config.localPort[0] = (unsigned char)(command.localPort >> 8);
            config.localPort[1] = (unsigned char)command.localPort;
            sRetireLatch = 0;
            if (!MoonshineNetStart(&config)) { BeginRetire(BRIDGE_PROTOCOL_ERROR); return; }
            sWorkerEpoch = sStatus.epoch;
            sStatus.state = TW_LIVE_OPENING;
            sStatus.ackSequence = command.sequence;
            sStatus.error = 0;
            Publish();
        }
    }
    if (!sWorkerEpoch || !MoonshineNetPoll(&worker) || worker.epoch != sWorkerEpoch) return;
    if (worker.state == MOONSHINE_NET_FAILED || worker.state == MOONSHINE_NET_DRAINING) {
        BeginRetire(worker.lastError); return;
    }
    if (worker.state != MOONSHINE_NET_READY) return;
    {
        unsigned diagnostics[3];
        diagnostics[0] = (Saturate(worker.sent, 65535u) << 16) | Saturate(worker.received, 65535u);
        diagnostics[1] = 0x01000000u | (Saturate(worker.dropped, 255u) << 16) |
            (Saturate(worker.sendErrors, 255u) << 8) | Saturate(worker.receiveErrors, 255u);
        diagnostics[2] = (unsigned)worker.lastError;
        if (sStatus.state != TW_LIVE_READY ||
            sMailbox.networkInfo.reserved[0] != diagnostics[0] ||
            sMailbox.networkInfo.reserved[1] != diagnostics[1] ||
            sMailbox.networkInfo.reserved[2] != diagnostics[2]) {
            TWLiveNetworkInfo info;
            unsigned i;
            memset(&info, 0, sizeof(info));
            info.epoch = sStatus.epoch;
            for (i = 0; i < 4; ++i) info.endpoint.ip[i] = worker.local.ip[i];
            info.endpoint.port = ((unsigned)worker.local.port[0] << 8) | worker.local.port[1];
            for (i = 0; i < 3; ++i) info.reserved[i] = diagnostics[i];
            if (!TWLivePublish(&sMailbox.networkInfo, &info, sizeof(info), &sInfoGeneration, &sIo)) {
                BeginRetire(BRIDGE_EXHAUSTED); return;
            }
        }
    }
    if (sStatus.state != TW_LIVE_READY) {
        sStatus.state = TW_LIVE_READY; changed = 1;
    }
    if (!TWLiveRead(&indices, &sMailbox.indices, sizeof(indices), &sIo)) {
        if (changed) Publish();
        return;
    }
    if (indices.epoch != sStatus.epoch || !TWLiveCountValid(indices.txWrite, sStatus.txRead) ||
        !TWLiveCountValid(sStatus.rxWrite, indices.rxRead)) { BeginRetire(BRIDGE_PROTOCOL_ERROR); return; }
    if (indices.txWrite != sStatus.txRead) {
        TWLivePacket packet;
        struct MoonshineNetEndpoint endpoint;
        const TWLivePacket *slot = &sMailbox.tx[sStatus.txRead & (TW_LIVE_RING_COUNT - 1)];
        Invalidate(slot, sizeof(*slot)); Barrier();
        TWLiveCopyIn(&packet, slot, sizeof(packet));
        if (!TWLivePacketValid(&packet, sStatus.epoch)) { BeginRetire(BRIDGE_PROTOCOL_ERROR); return; }
        ToWorker(&endpoint, &packet.endpoint);
        if (MoonshineNetSendTo(sWorkerEpoch, &endpoint, packet.data, packet.bytes)) {
            ++sStatus.txRead; changed = 1;
        }
    }
    {
        TWLivePose pose;
        if (TWLiveRead(&pose, &sMailbox.pose, sizeof(pose), &sIo) && pose.epoch == sStatus.epoch &&
            pose.generation != sPoseSeen && pose.bytes && pose.bytes <= TW_LIVE_PACKET_BYTES &&
            TWLiveEndpointValid(&pose.endpoint)) {
            struct MoonshineNetEndpoint endpoint;
            ToWorker(&endpoint, &pose.endpoint);
            if (MoonshineNetPublishPose(sWorkerEpoch, &endpoint, pose.data, pose.bytes)) sPoseSeen = pose.generation;
        }
    }
    if (sStatus.rxWrite - indices.rxRead < TW_LIVE_RING_COUNT) {
        struct MoonshineNetPacket packet;
        if (MoonshineNetReceive(sWorkerEpoch, &packet) && packet.epoch == sStatus.epoch &&
            packet.bytes && packet.bytes <= TW_LIVE_PACKET_BYTES) {
            TWLivePacket out;
            TWLivePacket *slot = &sMailbox.rx[sStatus.rxWrite & (TW_LIVE_RING_COUNT - 1)];
            unsigned i;
            memset(&out, 0, sizeof(out));
            out.epoch = sStatus.epoch; out.bytes = packet.bytes;
            for (i = 0; i < 4; ++i) out.endpoint.ip[i] = packet.endpoint.ip[i];
            out.endpoint.port = ((unsigned)packet.endpoint.port[0] << 8) | packet.endpoint.port[1];
            if (TWLiveEndpointValid(&out.endpoint)) {
                TWLiveCopyIn(out.data, packet.data, packet.bytes);
                TWLiveCopyOut(slot, &out, sizeof(out));
                Flush(slot, sizeof(*slot)); Barrier();
                ++sStatus.rxWrite; changed = 1;
            }
        }
    }
    if (changed) Publish();
}
#else
void MoonshineNetBridgeInit(void) {}
void MoonshineNetBridgeService(void) {}
int MoonshineNetBridgeRetire(void) { return 1; }
#endif
