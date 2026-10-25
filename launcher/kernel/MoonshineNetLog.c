#include "MoonshineNetLog.h"
#include "SusamuneCfg.h"
#include "susamune/live_race_wire.h"
#include "ff_utf8.h"
#include <stdarg.h>
#include <string.h>

#define LOG_LIMIT (4u * 1024u * 1024u)
static char sBuffer[8192], sPath[160];
static unsigned sUsed, sWritten, sOmitted, sSampleAt, sFlushAt, sEpoch, sState;
static unsigned sFlushMs;
static int sStarted, sFailed, sCreated;
struct Stream {
    TWLiveEndpoint endpoint;
    unsigned count, sequence, remoteMs, scene, area, flags, lastAt, gap;
    unsigned char kind, outgoing;
    unsigned char members;
    struct { unsigned player, sequence, remoteMs, scene, area, flags; } poses[3];
};
static struct Stream sStreams[6];

static unsigned clockTicks(void) { return read32(HW_TIMER); }
static unsigned milliseconds(unsigned ticks) { return ticks / 1898u; }
/* The kernel has no libc heap; even libc snprintf pulls in its allocator. */
static void emit(char *out, unsigned cap, unsigned *length, char c)
{
    if (*length + 1 < cap) out[*length] = c;
    ++*length;
}
static unsigned formatLine(char *out, unsigned cap, const char *fmt, va_list args)
{
    unsigned length = 0;
    while (*fmt) {
        if (*fmt != '%') { emit(out, cap, &length, *fmt++); continue; }
        unsigned width = 0;
        ++fmt;
        while (*fmt >= '0' && *fmt <= '9') width = width * 10 + (*fmt++ - '0');
        if (*fmt == 's') {
            const char *s = va_arg(args, const char *);
            while (*s) emit(out, cap, &length, *s++);
        } else if (*fmt == '%') emit(out, cap, &length, '%');
        else {
            unsigned value, count = 0, base = *fmt == 'x' ? 16 : 10;
            char digits[12];
            if (*fmt == 'd') {
                int signedValue = va_arg(args, int);
                value = (unsigned)signedValue;
                if (signedValue < 0) { emit(out, cap, &length, '-'); value = 0u - value; }
            } else value = va_arg(args, unsigned);
            do { digits[count++] = "0123456789abcdef"[value % base]; value /= base; } while (value);
            while (width > count) { emit(out, cap, &length, '0'); --width; }
            while (count) emit(out, cap, &length, digits[--count]);
        }
        if (*fmt) ++fmt;
    }
    if (cap) out[length < cap ? length : cap - 1] = 0;
    return length;
}
static void pathFormat(const char *fmt, ...)
{
    va_list args;
    va_start(args, fmt); formatLine(sPath, sizeof(sPath), fmt, args); va_end(args);
}
static void append(const char *format, ...)
{
    int length;
    va_list args;
    unsigned remaining = sizeof(sBuffer) - sUsed;
    if (sWritten + sUsed >= LOG_LIMIT) return;
    if (remaining > LOG_LIMIT - sWritten - sUsed) remaining = LOG_LIMIT - sWritten - sUsed;
    if (sFailed) return;
    va_start(args, format);
    length = formatLine(sBuffer + sUsed, remaining, format, args);
    va_end(args);
    if (length < 0 || (unsigned)length >= remaining) { ++sOmitted; return; }
    sUsed += length;
}
void MoonshineNetLogEvent(const char *event, unsigned epoch, unsigned state, int error)
{
    unsigned now = clockTicks();
    if (!sStarted) {
        sStarted = 1; sFlushAt = now;
        append("Moonshine PR33 connection log; clock_hz=1898437 protocol=%u\n", MSR_PROTOCOL);
    }
    append("%u %s epoch=%u state=%u error=%d\n", now, event, epoch, state, error);
}
void MoonshineNetLogPacket(int outgoing, const TWLiveEndpoint *endpoint,
    const void *data, unsigned bytes)
{
    MSRHeader h;
    const unsigned char *p = data;
    unsigned i, slot = 6, now = clockTicks();
    if (sFailed || !MSRDecodeHeader(data, bytes, &h)) return;
    if (h.kind != MSR_POSE && h.kind != MSR_GROUP_POSES) {
        append("%u %s peer=%u.%u.%u.%u:%u kind=%u seq=%u round=%u bytes=%u kick=%u\n",
            now, outgoing ? "queue_tx" : "deliver_rx", endpoint->ip[0], endpoint->ip[1],
            endpoint->ip[2], endpoint->ip[3], endpoint->port, h.kind, h.sequence, h.round,
            bytes, h.kind == MSR_LEAVE && h.payloadBytes == 1 && p[32] == 1);
        return;
    }
    for (i = 0; i < 6; ++i) {
        if (sStreams[i].kind && sStreams[i].outgoing == outgoing &&
            !memcmp(endpoint, &sStreams[i].endpoint, sizeof(*endpoint))) { slot = i; break; }
        if (!sStreams[i].kind || now - sStreams[i].lastAt > 1898437u * 5u) slot = i;
    }
    if (slot == 6) return;
    {
        struct Stream *s = &sStreams[slot];
        if (s->outgoing != outgoing || memcmp(endpoint, &s->endpoint, sizeof(*endpoint)))
            memset(s, 0, sizeof(*s));
        unsigned gap = now - s->lastAt;
        if (s->kind && gap > s->gap) s->gap = gap;
        s->endpoint = *endpoint; s->outgoing = outgoing; s->kind = h.kind;
        ++s->count; s->sequence = h.sequence; s->lastAt = now;
        s->members = 0;
        if (h.kind == MSR_POSE && h.payloadBytes >= MSR_POSE_BASE_BYTES) {
            s->remoteMs = MSRRead32(p + 36); s->scene = MSRRead32(p + 40);
            s->area = MSRRead32(p + 32); s->flags = p[69];
        } else if (h.kind == MSR_GROUP_POSES && h.payloadBytes >= 4 && p[32] <= 3 &&
            h.payloadBytes == 4u + p[32] * MSR_GROUP_ENTRY_BYTES) {
            s->members = p[32];
            for (i = 0; i < s->members; ++i) {
                const unsigned char *entry = p + 36 + i * MSR_GROUP_ENTRY_BYTES;
                s->poses[i].player = entry[0]; s->poses[i].sequence = MSRRead32(entry + 4);
                s->poses[i].remoteMs = MSRRead32(entry + 12); s->poses[i].scene = MSRRead32(entry + 16);
                s->poses[i].area = MSRRead32(entry + 8); s->poses[i].flags = entry[45];
            }
        }
    }
}
void MoonshineNetLogSample(const struct MoonshineNetStatus *worker, unsigned txQueued,
    unsigned rxQueued, unsigned ppcConsumed)
{
    unsigned i, now = clockTicks();
    if (sFailed) return;
    if (!sStarted || worker->epoch != sEpoch || worker->state != sState) {
        if (worker->epoch != sEpoch) memset(sStreams, 0, sizeof(sStreams));
        sEpoch = worker->epoch; sState = worker->state;
        MoonshineNetLogEvent("transport", sEpoch, sState, worker->lastError);
    }
    if (now - sSampleAt < 1898437u) return;
    sSampleAt = now;
    append("%u stats epoch=%u tx=%u rx=%u drop=%u err_tx=%u err_rx=%u error=%d tx_q=%u rx_q=%u ppc_rx=%u tx_max_ms=%u rx_max_ms=%u replace_tx=%u replace_rx=%u omitted=%u flush_ms=%u\n",
        now, worker->epoch, worker->sent, worker->received, worker->dropped,
        worker->sendErrors, worker->receiveErrors, worker->lastError, txQueued, rxQueued,
        ppcConsumed, milliseconds(worker->txMaxTicks), milliseconds(worker->rxMaxTicks),
        worker->txCoalesced, worker->rxCoalesced, sOmitted, sFlushMs);
    for (i = 0; i < 6; ++i) {
        struct Stream *s = &sStreams[i];
        if (!s->kind) continue;
        append("%u poses %s peer=%u.%u.%u.%u:%u kind=%u count=%u seq=%u remote_ms=%u scene=%u area=%08x visible=%u max_gap_ms=%u age_ms=%u\n",
            now, s->outgoing ? "tx" : "rx", s->endpoint.ip[0], s->endpoint.ip[1],
            s->endpoint.ip[2], s->endpoint.ip[3], s->endpoint.port, s->kind, s->count,
            s->sequence, s->remoteMs, s->scene, s->area, s->flags, milliseconds(s->gap), milliseconds(now - s->lastAt));
        s->count = s->gap = 0;
        for (unsigned j = 0; j < s->members; ++j)
            append("%u bundle %s peer_port=%u player=%u seq=%u remote_ms=%u scene=%u area=%08x visible=%u\n",
                now, s->outgoing ? "tx" : "rx", s->endpoint.port, s->poses[j].player,
                s->poses[j].sequence, s->poses[j].remoteMs, s->poses[j].scene,
                s->poses[j].area, s->poses[j].flags);
    }
}
int MoonshineNetLogPending(void)
{
    return sStarted && !sFailed && sUsed &&
        (sUsed >= sizeof(sBuffer) / 2 || clockTicks() - sFlushAt >= 1898437u * 5u);
}
void MoonshineNetLogService(void)
{
    FIL file;
    FRESULT result;
    UINT written;
    unsigned i;
    if (!MoonshineNetLogPending()) return;
    sFlushAt = clockTicks();
    if (!sCreated) {
        pathFormat("%s/logs", SusamuneCfgStoragePrefix());
        result = f_mkdir_char(sPath);
        if (result != FR_OK && result != FR_EXIST) { sFailed = 1; return; }
        for (i = 0; i < 32; ++i) {
            pathFormat("%s/logs/connection_%08x_%02u.log",
                SusamuneCfgStoragePrefix(), sFlushAt, i);
            result = f_open_char(&file, sPath, FA_WRITE | FA_CREATE_NEW);
            if (result != FR_EXIST) break;
        }
        if (result != FR_OK) { sFailed = 1; return; }
        sCreated = 1;
    } else {
        result = f_open_char(&file, sPath, FA_WRITE | FA_OPEN_EXISTING);
        if (result != FR_OK) { sFailed = 1; return; }
        result = f_lseek(&file, sWritten);
    }
    if (result == FR_OK) result = f_write(&file, sBuffer, sUsed, &written);
    if (result == FR_OK && written != sUsed) result = FR_DISK_ERR;
    if (result == FR_OK) result = f_sync(&file);
    if (f_close(&file) != FR_OK && result == FR_OK) result = FR_DISK_ERR;
    if (result != FR_OK) { sFailed = 1; return; }
    sWritten += sUsed; sUsed = 0;
    /* Report on the next sample; a flush must not schedule another idle write. */
    sFlushMs = milliseconds(clockTicks() - sFlushAt);
    if (sWritten >= LOG_LIMIT) sFailed = 1;
}
