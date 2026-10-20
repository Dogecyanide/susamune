/* SPDX-License-Identifier: GPL-2.0-only
 * IOS ABI references: devkitPro/libogc libogc/network_wii.c; Project Slippi
 * Nintendont bea169ecd170f9b49b73c49e831189afd0dc8c9b kernel/net.c.
 * This bounded worker is a new implementation, not Slippi's replay service.
 */
#include "MoonshineNet.h"
#ifdef MOONSHINE_NET_HOST_TEST
#include "MoonshineNetTestPlatform.h"
#else
#include "global.h"
#include "string.h"
/* The legacy declaration drops IOS_DestroyMessageQueue's returned status. */
extern s32 MoonshineNetDestroyQueue(s32 queue) __asm__("syscall_0b");
#endif

#define NET_BARRIER() __asm__ volatile ("" ::: "memory")
#define NET_TICK_US 10000
#define NET_RETRY_TICKS 10u
/* Delivered ticks are an approximate watchdog, not a wall-clock deadline. */
#define NET_TIMEOUT_TICKS 1000u
#define NET_WAKE ((struct ipcmessage *)1)
#define NET_TIMER ((struct ipcmessage *)2)
#define NET_ERROR_TIMEOUT (-10001)
#define NET_ERROR_REPLY (-10002)

enum NetOp {
    OP_NONE, OP_KD, OP_STARTUP, OP_HOST, OP_SOCKET, OP_NONBLOCK,
    OP_RCVBUF, OP_SNDBUF, OP_BIND, OP_NAME, OP_SEND, OP_RECV, OP_CLOSE
};

enum NetFailureStep {
    FAIL_TIMER = 1, FAIL_OPEN_KD, FAIL_OPEN_TOP, FAIL_KD_REPLY,
    FAIL_SUBMIT = 16, FAIL_COMPLETE = 32
};

static const char sKdPath[] ALIGNED(32) = "/dev/net/kd/request";
static const char sTopPath[] ALIGNED(32) = "/dev/net/ip/top";
static u8 sStack[MOONSHINE_NET_STACK_BYTES] ALIGNED(32);
static u32 sQueueStorage[8] ALIGNED(32);
static struct MoonshineNetPacket sTx[4], sRx[4], sPose;
static volatile u32 sTxWrite, sTxRead, sRxWrite, sRxRead, sPoseSequence;
static volatile u32 sRequestEpoch, sStopEpoch, sStatusSequence;
static struct MoonshineNetConfig sConfig;
static struct MoonshineNetStatus sStatus, sPublished;
static u32 sPoseSeen, sTicks, sDue, sSubmitted, sRetries;
static u32 sTxBudget, sRxBudget, sPreferPose, sPreferReceive;
static s32 sQueue = -1, sTimer = -1, sKd = -1, sTop = -1, sSocket = -1;
static s32 sThread = -1;
static u32 sInitialized, sFailed, sOp, sNext;
static u32 sShuttingDown;

/* One IOS request owns these buffers until its matching completion is consumed. */
static struct ipcmessage sMessage ALIGNED(32);
static ioctlv sVectors[3] ALIGNED(32);
static u8 sArgs[64] ALIGNED(32);
static u8 sReply[32] ALIGNED(32);
static u8 sAddress[32] ALIGNED(32);
static u8 sData[MOONSHINE_NET_PACKET_BYTES + 32] ALIGNED(32);
static unsigned sSendBytes;

static void put32(u8 *p, u32 v)
{
    p[0] = v >> 24; p[1] = v >> 16; p[2] = v >> 8; p[3] = v;
}

static u32 get32(const u8 *p)
{
    return ((u32)p[0] << 24) | ((u32)p[1] << 16) | ((u32)p[2] << 8) | p[3];
}

static void address(u8 *p, const struct MoonshineNetEndpoint *endpoint)
{
    memset(p, 0, 28);
    p[0] = 8; p[1] = 2;
    memcpy(p + 2, endpoint->port, 2);
    memcpy(p + 4, endpoint->ip, 4);
}

static int endpointValid(const struct MoonshineNetEndpoint *endpoint)
{
    return endpoint && (endpoint->port[0] || endpoint->port[1]) &&
        endpoint->ip[0] && endpoint->ip[0] < 224 &&
        !endpoint->reserved[0] && !endpoint->reserved[1];
}

static void publish(void)
{
    ++sStatusSequence;
    NET_BARRIER();
    sStatus.pending = sOp != OP_NONE;
    sPublished = sStatus;
    NET_BARRIER();
    ++sStatusSequence;
}

static void wake(void)
{
    /* A full event queue already wakes the worker; no caller waits for space. */
    mqueue_send_now(sQueue, NET_WAKE, 1);
}

int MoonshineNetPoll(struct MoonshineNetStatus *status)
{
    unsigned attempt, before;
    if (!status) return 0;
    for (attempt = 0; attempt != 2; ++attempt) {
        before = sStatusSequence;
        if (before & 1) continue;
        NET_BARRIER();
        *status = sPublished;
        NET_BARRIER();
        if (before == sStatusSequence) {
            if (sRequestEpoch != status->epoch) {
                status->epoch = sRequestEpoch;
                status->state = MOONSHINE_NET_STARTING;
            }
            return 1;
        }
    }
    return 0;
}

int MoonshineNetRetired(unsigned epoch)
{
    struct MoonshineNetStatus status;
    return epoch && MoonshineNetPoll(&status) && status.retiredEpoch == epoch &&
        !status.pending && (status.state == MOONSHINE_NET_IDLE ||
                           status.state == MOONSHINE_NET_FAILED);
}

int MoonshineNetStart(const struct MoonshineNetConfig *config)
{
    struct MoonshineNetStatus status;
    if (!sInitialized || sShuttingDown || !config || !config->epoch || config->reserved[0] ||
        config->reserved[1] || config->epoch == sRequestEpoch ||
        !MoonshineNetPoll(&status) || status.retiredEpoch != sRequestEpoch)
        return 0;
    sConfig = *config;
    sStopEpoch = 0;
    NET_BARRIER();
    sRequestEpoch = config->epoch;
    wake();
    return 1;
}

static int ready(unsigned epoch)
{
    struct MoonshineNetStatus status;
    return epoch && epoch == sRequestEpoch && sStopEpoch != epoch &&
        MoonshineNetPoll(&status) && status.epoch == epoch &&
        status.state == MOONSHINE_NET_READY;
}

static void packetSet(struct MoonshineNetPacket *packet, unsigned epoch,
    const struct MoonshineNetEndpoint *endpoint, const void *data, unsigned bytes)
{
    packet->endpoint = *endpoint;
    packet->epoch = epoch;
    packet->bytes = bytes;
    memcpy(packet->data, data, bytes);
}

int MoonshineNetSendTo(unsigned epoch, const struct MoonshineNetEndpoint *endpoint,
    const void *data, unsigned bytes)
{
    u32 write = sTxWrite;
    if (!data || !bytes || bytes > MOONSHINE_NET_PACKET_BYTES ||
        !endpointValid(endpoint) || !ready(epoch) || write - sTxRead >= 4)
        return 0;
    NET_BARRIER();
    packetSet(&sTx[write & 3], epoch, endpoint, data, bytes);
    NET_BARRIER();
    sTxWrite = write + 1;
    wake();
    return 1;
}

int MoonshineNetPublishPose(unsigned epoch, const struct MoonshineNetEndpoint *endpoint,
    const void *data, unsigned bytes)
{
    if (!data || !bytes || bytes > MOONSHINE_NET_PACKET_BYTES ||
        !endpointValid(endpoint) || !ready(epoch)) return 0;
    ++sPoseSequence;
    NET_BARRIER();
    packetSet(&sPose, epoch, endpoint, data, bytes);
    NET_BARRIER();
    ++sPoseSequence;
    wake();
    return 1;
}

int MoonshineNetReceive(unsigned epoch, struct MoonshineNetPacket *packet)
{
    u32 read = sRxRead;
    if (!packet || !ready(epoch) || read == sRxWrite) return 0;
    NET_BARRIER();
    *packet = sRx[read & 3];
    NET_BARRIER();
    sRxRead = read + 1;
    return packet->epoch == epoch;
}

void MoonshineNetRequestStop(unsigned epoch)
{
    if (epoch && epoch == sRequestEpoch) {
        sStopEpoch = epoch;
        NET_BARRIER();
        wake();
    }
}

static void fail(s32 error, unsigned step)
{
    /* Keep the first failure; a failed cleanup must not hide its cause. */
    if (!sFailed)
        sStatus.lastError = error < 0 && error > -1000 ?
            -(s32)(200000u + step * 1000u + (unsigned)-error) : error;
    sFailed = 1;
    sStatus.state = MOONSHINE_NET_DRAINING;
}

static void submit(unsigned op, unsigned command, unsigned inputBytes,
    unsigned outputBytes, int vectors)
{
    s32 result;
    sOp = op;
    sSubmitted = sTicks;
    memset(&sMessage, 0, sizeof(sMessage));
    sync_after_write(sArgs, sizeof(sArgs));
    sync_after_write(sReply, sizeof(sReply));
    sync_after_write(sAddress, sizeof(sAddress));
    sync_after_write(sData, sizeof(sData));
    sync_after_write(&sMessage, sizeof(sMessage));
    if (vectors) {
        sync_after_write(sVectors, sizeof(sVectors));
        result = IOS_IoctlvAsync(sTop, command, inputBytes, outputBytes,
            sVectors, sQueue, &sMessage);
    } else {
        result = IOS_IoctlAsync(op == OP_KD ? sKd : sTop, command,
            inputBytes ? sArgs : NULL, inputBytes,
            outputBytes ? sReply : NULL, outputBytes, sQueue, &sMessage);
    }
    if (result < 0) {
        sOp = OP_NONE;
        fail(result, FAIL_SUBMIT + op);
        sDue = sTicks + NET_RETRY_TICKS;
    }
}

static void complete(s32 result)
{
    unsigned op = sOp;
    sOp = OP_NONE;
    /* IOS produced these bytes on this ARM CPU; invalidation can discard them. */
    /* Resource-returning completions must be accounted for even during stop. */
    if (op == OP_SOCKET && result >= 0) sSocket = result;
    if (op == OP_CLOSE) {
        if (result >= 0) sSocket = -1;
        else { fail(result, FAIL_COMPLETE + op); sDue = sTicks + NET_RETRY_TICKS; }
        return;
    }
    if (sStopEpoch == sStatus.epoch || sFailed) return;
    if (op == OP_KD && result >= 0) {
        result = (s32)get32(sReply);
        if (result == -15) result = 0;
        if (result == -29 && sRetries++ < 100) {
            sNext = OP_KD; sDue = sTicks + NET_RETRY_TICKS; return;
        }
        if (result < 0) { fail(result, FAIL_KD_REPLY); return; }
    }
    if (op == OP_HOST) {
        if (!result && sRetries++ < 100) {
            sNext = OP_HOST; sDue = sTicks + NET_RETRY_TICKS; return;
        }
        /* IPv4 is a u32 carried in IOS's signed result field. */
        if ((u32)result >= 0x01000000u && (u32)result < 0xe0000000u) {
            put32(sStatus.local.ip, (u32)result);
            result = 0;
        } else if (!result) result = NET_ERROR_TIMEOUT;
        else if (result > 0) result = NET_ERROR_REPLY;
    }
    if (op == OP_RECV) {
        if (result == -6) return; /* IOS SO_EAGAIN, not libc errno. */
        if (result <= 0) {
            if (result < 0) { ++sStatus.receiveErrors; sStatus.lastError = result; }
            return;
        }
        if ((unsigned)result > MOONSHINE_NET_PACKET_BYTES || sAddress[0] != 8 ||
            sAddress[1] != 2 || sRxWrite - sRxRead >= 4) {
            ++sStatus.dropped; return;
        }
        {
            struct MoonshineNetPacket *p = &sRx[sRxWrite & 3];
            memset(&p->endpoint, 0, sizeof(p->endpoint));
            memcpy(p->endpoint.ip, sAddress + 4, 4);
            memcpy(p->endpoint.port, sAddress + 2, 2);
            p->epoch = sStatus.epoch; p->bytes = result;
            memcpy(p->data, sData, result);
            NET_BARRIER();
            ++sRxWrite;
            ++sStatus.received;
        }
        return;
    }
    if (op == OP_SEND) {
        if (result == (s32)sSendBytes) ++sStatus.sent;
        else { ++sStatus.sendErrors; sStatus.lastError = result < 0 ? result : NET_ERROR_REPLY; }
        return;
    }
    if (result < 0) { fail(result, FAIL_COMPLETE + op); return; }
    sRetries = 0;
    sNext = op + 1;
    if (op == OP_KD) {
        IOS_Close(sKd); sKd = -1;
        sTop = IOS_Open(sTopPath, 0);
        if (sTop < 0) fail(sTop, FAIL_OPEN_TOP);
    }
    if (op == OP_NAME) {
        if (sReply[0] != 8 || sReply[1] != 2 || !(sReply[2] || sReply[3])) {
            fail(NET_ERROR_REPLY, FAIL_COMPLETE + op); return;
        }
        memcpy(sStatus.local.port, sReply + 2, 2);
        sStatus.state = MOONSHINE_NET_READY;
        sTxBudget = sRxBudget = 1;
    }
}

static int prepareSend(void)
{
    const struct MoonshineNetPacket *packet;
    unsigned sequence = sPoseSequence;
    int pose = !(sequence & 1) && sequence != sPoseSeen &&
        (sPreferPose || sTxRead == sTxWrite);
    if (pose) packet = &sPose;
    else if (sTxRead != sTxWrite) packet = &sTx[sTxRead & 3];
    else return 0;
    NET_BARRIER();
    sSendBytes = packet->bytes;
    if (!sSendBytes || sSendBytes > MOONSHINE_NET_PACKET_BYTES) return 0;
    memcpy(sData, packet->data, sSendBytes);
    address(sArgs + 12, &packet->endpoint);
    NET_BARRIER();
    if (pose && sequence != sPoseSequence) return 0;
    if (pose) sPoseSeen = sequence;
    else ++sTxRead;
    sPreferPose = !pose;
    /* F_SETFL already selected nonblocking; UDP sends need no message flags. */
    put32(sArgs, sSocket); put32(sArgs + 4, 0); put32(sArgs + 8, 1);
    sVectors[0].data = sData; sVectors[0].len = sSendBytes;
    sVectors[1].data = sArgs; sVectors[1].len = 40;
    return 1;
}

static void retire(void)
{
    if (sKd >= 0) { IOS_Close(sKd); sKd = -1; }
    if (sTop >= 0) { IOS_Close(sTop); sTop = -1; }
    if (sTimer >= 0) { TimerDestroy(sTimer); sTimer = -1; }
    sTxRead = sTxWrite;
    sRxWrite = sRxRead;
    sPoseSeen = sPoseSequence;
    sStatus.retiredEpoch = sStatus.epoch;
    sStatus.state = sFailed ? MOONSHINE_NET_FAILED : MOONSHINE_NET_IDLE;
}

static void drive(void)
{
    if (sRequestEpoch != sStatus.epoch) {
        memset(&sStatus, 0, sizeof(sStatus));
        sStatus.epoch = sRequestEpoch;
        sStatus.state = MOONSHINE_NET_STARTING;
        sFailed = sRetries = sTicks = sDue = 0;
        sTxRead = sTxWrite; sRxWrite = sRxRead; sPoseSeen = sPoseSequence;
        sNext = OP_KD;
        publish();
        if (sStopEpoch != sStatus.epoch) {
            sTimer = TimerCreate(NET_TICK_US, NET_TICK_US, sQueue, (int)NET_TIMER);
            if (sTimer < 0) fail(sTimer, FAIL_TIMER);
            else {
                sKd = IOS_Open(sKdPath, 0);
                if (sKd < 0) fail(sKd, FAIL_OPEN_KD);
            }
        }
    }
    if (!sStatus.epoch || sStatus.retiredEpoch == sStatus.epoch) return;
    if (sOp && sTicks - sSubmitted >= NET_TIMEOUT_TICKS) fail(NET_ERROR_TIMEOUT, FAIL_COMPLETE + sOp);
    if (sStopEpoch == sStatus.epoch || sFailed) {
        sStatus.state = MOONSHINE_NET_DRAINING;
        if (sOp || (s32)(sTicks - sDue) < 0) return;
        if (sSocket >= 0) {
            put32(sArgs, sSocket);
            submit(OP_CLOSE, 3, 4, 0, 0);
        } else retire();
        return;
    }
    if (sOp || (s32)(sTicks - sDue) < 0) return;
    memset(sArgs, 0, sizeof(sArgs));
    memset(sReply, 0, sizeof(sReply));
    if (sStatus.state == MOONSHINE_NET_READY) {
        if (sTxBudget && (!sPreferReceive || !sRxBudget) && prepareSend()) {
            --sTxBudget; sPreferReceive = 1;
            submit(OP_SEND, 13, 2, 0, 1);
        } else if (sRxBudget) {
            --sRxBudget; sPreferReceive = 0;
            put32(sArgs, sSocket); put32(sArgs + 4, 4);
            memset(sAddress, 0, sizeof(sAddress)); sAddress[0] = 8; sAddress[1] = 2;
            sVectors[0].data = sArgs; sVectors[0].len = 8;
            sVectors[1].data = sData; sVectors[1].len = MOONSHINE_NET_PACKET_BYTES + 1;
            sVectors[2].data = sAddress; sVectors[2].len = 8;
            submit(OP_RECV, 12, 1, 2, 1);
        }
        return;
    }
    switch (sNext) {
    case OP_KD: submit(OP_KD, 6, 0, 32, 0); break;
    case OP_STARTUP: submit(OP_STARTUP, 31, 0, 0, 0); break;
    case OP_HOST: submit(OP_HOST, 16, 0, 0, 0); break;
    case OP_SOCKET:
        /* IOS requires protocol 0; SOCK_DGRAM selects UDP. Protocol 17 fails. */
        put32(sArgs, 2); put32(sArgs + 4, 2); put32(sArgs + 8, 0);
        submit(OP_SOCKET, 15, 12, 0, 0); break;
    case OP_NONBLOCK:
        put32(sArgs, sSocket); put32(sArgs + 4, 4); put32(sArgs + 8, 4);
        submit(OP_NONBLOCK, 5, 12, 0, 0); break;
    case OP_RCVBUF: case OP_SNDBUF:
        put32(sArgs, sSocket); put32(sArgs + 4, 0xffff);
        put32(sArgs + 8, sNext == OP_RCVBUF ? 0x1002 : 0x1001);
        put32(sArgs + 12, 4); put32(sArgs + 16, 4096);
        submit(sNext, 9, 36, 0, 0); break;
    case OP_BIND:
        put32(sArgs, sSocket); put32(sArgs + 4, 1);
        sArgs[8] = 8; sArgs[9] = 2; memcpy(sArgs + 10, sConfig.localPort, 2);
        submit(OP_BIND, 2, 36, 0, 0); break;
    case OP_NAME:
        put32(sArgs, sSocket); sReply[0] = 8; sReply[1] = 2;
        submit(OP_NAME, 7, 4, 8, 0); break;
    default: fail(NET_ERROR_REPLY, 0); break;
    }
}

static void event(struct ipcmessage *message)
{
    if (message == NET_TIMER) {
        /* DestroyTimer may leave queued ticks; they never release IOS ownership. */
        ++sTicks; sTxBudget = sRxBudget = 1;
    } else if (message == &sMessage && sOp) {
        s32 result;
        /* ResourceReply queues the same ARM-cached message it just updated. */
        result = (s32)sMessage.result;
        complete(result);
    }
    drive();
    publish();
}

static u32 worker(void *unused)
{
    struct ipcmessage *message;
    (void)unused;
    for (;;) {
        if (mqueue_recv(sQueue, &message, 0) >= 0) event(message);
    }
    return 0;
}

int MoonshineNetInit(void)
{
    s32 result;
    if (sInitialized) return !sShuttingDown;
    if (sThread >= 0 || sQueue >= 0) return 0;
    sTxWrite = sTxRead = sRxWrite = sRxRead = sPoseSequence = 0;
    sRequestEpoch = sStopEpoch = sStatusSequence = 0;
    memset(&sConfig, 0, sizeof(sConfig));
    memset(&sStatus, 0, sizeof(sStatus));
    memset(&sPublished, 0, sizeof(sPublished));
    sPoseSeen = sTicks = sDue = sSubmitted = sRetries = 0;
    sTxBudget = sRxBudget = sPreferPose = sPreferReceive = 0;
    sFailed = sOp = sNext = sShuttingDown = 0;
    sQueue = mqueue_create(sQueueStorage, 8);
    if (sQueue < 0) { sQueue = -1; return 0; }
    sThread = (s32)do_thread_create(worker, (u32 *)(sStack + sizeof(sStack)),
        sizeof(sStack), 0x40);
    if (sThread < 0) { sThread = -1; MoonshineNetShutdown(); return 0; }
    result = thread_continue(sThread);
    if (result < 0) {
        MoonshineNetShutdown(); return 0;
    }
    sInitialized = 1;
    return 1;
}

int MoonshineNetShutdown(void)
{
    sShuttingDown = 1;
    if (sRequestEpoch && !MoonshineNetRetired(sRequestEpoch)) {
        MoonshineNetRequestStop(sRequestEpoch);
        return 0;
    }
    if (sThread >= 0) {
        if (thread_cancel(sThread, 0) < 0) return 0;
        sThread = -1;
    }
    if (sQueue >= 0) {
        if (MoonshineNetDestroyQueue(sQueue) < 0) return 0;
        sQueue = -1;
    }
    sInitialized = 0;
    return 1;
}
