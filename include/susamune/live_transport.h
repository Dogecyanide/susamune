#ifndef SUSAMUNE_LIVE_TRANSPORT_H
#define SUSAMUNE_LIVE_TRANSPORT_H

#define TW_LIVE_MAGIC 0x4d4e4554u
#define TW_LIVE_ABI 1u
#define TW_LIVE_CAP_UDP 1u
#define TW_LIVE_PACKET_BYTES 256u
#define TW_LIVE_RING_COUNT 4u
#define TW_LIVE_MAILBOX_LIMIT 4096u
#define TW_LIVE_DATA_BEGIN 0x92f60000u
#define TW_LIVE_DATA_END 0x92fe0000u

enum TWLiveState { TW_LIVE_UNAVAILABLE, TW_LIVE_IDLE, TW_LIVE_OPENING,
    TW_LIVE_READY, TW_LIVE_RETIRING, TW_LIVE_FAILED };
enum TWLiveOperation { TW_LIVE_BEGIN = 1, TW_LIVE_STOP = 2 };

/* IPv4 octets are bytes; port is a host-value integer on both processors. */
typedef struct { unsigned char ip[4]; unsigned short port, reserved; } TWLiveEndpoint;
typedef struct {
    unsigned epoch, bytes;
    TWLiveEndpoint endpoint;
    unsigned reserved[4];
    unsigned char data[TW_LIVE_PACKET_BYTES];
} TWLivePacket;
typedef struct {
    unsigned generation, issued, epoch, operation, sequence, localPort, reserved[2];
} TWLiveCommand;
typedef struct {
    unsigned generation, issued, epoch, txWrite, rxRead, reserved[3];
} TWLiveIndices;
typedef struct {
    unsigned generation, issued, epoch, state, ackSequence, txRead, rxWrite;
    int error;
} TWLiveStatus;
typedef struct {
    unsigned generation, issued, epoch, bytes;
    TWLiveEndpoint endpoint;
    unsigned reserved[2];
    unsigned char data[TW_LIVE_PACKET_BYTES];
} TWLivePose;
typedef struct {
    unsigned generation, issued, epoch;
    TWLiveEndpoint endpoint;
    unsigned reserved[3];
} TWLiveNetworkInfo;
typedef struct __attribute__((aligned(32))) {
    TWLiveCommand command;                 /* PPC writer. */
    TWLiveIndices indices;                 /* PPC writer, including RX consumption. */
    TWLiveStatus status;                   /* ARM-main writer, including TX consumption. */
    TWLivePacket tx[TW_LIVE_RING_COUNT];    /* PPC writer until ARM consumes. */
    TWLivePacket rx[TW_LIVE_RING_COUNT];    /* ARM writer until PPC consumes. */
    TWLivePose pose;                       /* PPC writer, may overwrite unread poses. */
    TWLiveNetworkInfo networkInfo;         /* ARM-main writer. */
} TWLiveMailbox;

typedef struct {
    void (*flush)(volatile void *, unsigned);
    void (*invalidate)(const volatile void *, unsigned);
    void (*barrier)(void);
} TWLiveIo;

static inline int TWLiveDescriptorValid(unsigned magic, unsigned abi, unsigned address,
    unsigned bytes, unsigned capabilities, unsigned reserved)
{
    return magic == TW_LIVE_MAGIC && abi == TW_LIVE_ABI &&
        capabilities == TW_LIVE_CAP_UDP && !reserved && !(address & 31u) &&
        bytes == sizeof(TWLiveMailbox) && bytes <= TW_LIVE_MAILBOX_LIMIT &&
        address >= TW_LIVE_DATA_BEGIN && address <= TW_LIVE_DATA_END &&
        bytes <= TW_LIVE_DATA_END - address;
}
static inline int TWLiveEndpointValid(const TWLiveEndpoint *endpoint)
{
    return endpoint->port && !endpoint->reserved &&
        (endpoint->ip[0] | endpoint->ip[1] | endpoint->ip[2] | endpoint->ip[3]);
}
static inline int TWLiveCountValid(unsigned produced, unsigned consumed)
{
    return produced - consumed <= TW_LIVE_RING_COUNT;
}
static inline int TWLivePacketValid(const TWLivePacket *packet, unsigned epoch)
{
    return epoch && packet->epoch == epoch && packet->bytes &&
        packet->bytes <= TW_LIVE_PACKET_BYTES && TWLiveEndpointValid(&packet->endpoint);
}
static inline void TWLiveCopyIn(void *destination, const volatile void *source, unsigned bytes)
{
    unsigned i;
    unsigned char *out = (unsigned char *)destination;
    const volatile unsigned char *in = (const volatile unsigned char *)source;
    for (i = 0; i < bytes; ++i) out[i] = in[i];
}
static inline void TWLiveCopyOut(volatile void *destination, const void *source, unsigned bytes)
{
    unsigned i;
    volatile unsigned char *out = (volatile unsigned char *)destination;
    const unsigned char *in = (const unsigned char *)source;
    for (i = 0; i < bytes; ++i) out[i] = in[i];
}
/* A writer never wraps its generation; withdrawal must reach RAM before reuse. */
static inline int TWLivePublish(volatile void *destination, const void *draft,
    unsigned bytes, unsigned *issued, const TWLiveIo *io)
{
    volatile unsigned *generation = (volatile unsigned *)destination;
    unsigned next;
    if (*issued == 0xffffffffu) return 0;
    next = ++*issued;
    *generation = 0;
    generation[1] = next;
    io->flush(destination, 32); io->barrier();
    TWLiveCopyOut((volatile unsigned char *)destination + 8,
        (const unsigned char *)draft + 8, bytes - 8);
    io->flush(destination, bytes); io->barrier();
    *generation = next;
    io->flush(destination, 32); io->barrier();
    return 1;
}
/* The private copy is unusable on failure; callers never spin for a writer. */
static inline int TWLiveRead(void *snapshot, const volatile void *source,
    unsigned bytes, const TWLiveIo *io)
{
    const volatile unsigned *generation = (const volatile unsigned *)source;
    unsigned first, last;
    io->invalidate(source, 32); io->barrier();
    first = *generation;
    if (!first) return 0;
    io->invalidate(source, bytes); io->barrier();
    TWLiveCopyIn(snapshot, source, bytes);
    io->invalidate(source, 32); io->barrier();
    last = *generation;
    return last && first == last && ((const unsigned *)snapshot)[0] == first &&
        ((const unsigned *)snapshot)[1] == first;
}
/* The durable issued word also covers a PPC reset during withdrawal. */
static inline int TWLiveResume(unsigned *issued, const volatile void *source, const TWLiveIo *io)
{
    const volatile unsigned *words = (const volatile unsigned *)source;
    unsigned committed;
    io->invalidate(source, 32); io->barrier();
    committed = words[0];
    *issued = words[1];
    return !committed || committed == *issued;
}

typedef char tw_live_endpoint_size[(sizeof(TWLiveEndpoint) == 8) ? 1 : -1];
typedef char tw_live_lines[(sizeof(TWLiveCommand) == 32 && sizeof(TWLiveIndices) == 32 && sizeof(TWLiveStatus) == 32) ? 1 : -1];
typedef char tw_live_packet_size[(sizeof(TWLivePacket) == 288 && sizeof(TWLivePose) == 288) ? 1 : -1];
typedef char tw_live_network_info_size[(sizeof(TWLiveNetworkInfo) == 32) ? 1 : -1];
typedef char tw_live_mailbox_size[(sizeof(TWLiveMailbox) == 2720 && sizeof(TWLiveMailbox) <= TW_LIVE_MAILBOX_LIMIT) ? 1 : -1];
typedef char tw_live_mailbox_owners[(__builtin_offsetof(TWLiveMailbox, command) == 0 &&
    __builtin_offsetof(TWLiveMailbox, indices) == 32 && __builtin_offsetof(TWLiveMailbox, status) == 64 &&
    __builtin_offsetof(TWLiveMailbox, tx) == 96 && __builtin_offsetof(TWLiveMailbox, rx) == 1248 &&
    __builtin_offsetof(TWLiveMailbox, pose) == 2400 &&
    __builtin_offsetof(TWLiveMailbox, networkInfo) == 2688) ? 1 : -1];
#endif
