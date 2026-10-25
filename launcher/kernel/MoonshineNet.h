#ifndef MOONSHINE_NET_H
#define MOONSHINE_NET_H

#define MOONSHINE_NET_PACKET_BYTES 256u
#define MOONSHINE_NET_QUEUE_PACKETS 4u
#define MOONSHINE_NET_STACK_BYTES 8192u

/* Addresses and ports are network-order bytes; these structs are never sent. */
struct MoonshineNetEndpoint {
    unsigned char ip[4];
    unsigned char port[2];
    unsigned char reserved[2];
};

struct MoonshineNetConfig {
    unsigned epoch;
    unsigned char localPort[2];
    unsigned char reserved[2];
};

struct MoonshineNetPacket {
    struct MoonshineNetEndpoint endpoint;
    unsigned epoch;
    unsigned bytes;
    unsigned char data[MOONSHINE_NET_PACKET_BYTES];
};

enum MoonshineNetState {
    MOONSHINE_NET_IDLE,
    MOONSHINE_NET_STARTING,
    MOONSHINE_NET_READY,
    MOONSHINE_NET_DRAINING,
    MOONSHINE_NET_FAILED
};

struct MoonshineNetStatus {
    unsigned epoch;
    unsigned retiredEpoch;
    unsigned state;
    int lastError;
    unsigned pending;
    unsigned sent;
    unsigned received;
    unsigned dropped;
    unsigned sendErrors;
    unsigned receiveErrors;
    struct MoonshineNetEndpoint local;
    unsigned txMaxTicks, rxMaxTicks, txCoalesced, rxCoalesced;
};

/* Init once before PPC release; remaining calls have one ARM-main-thread owner. */
int MoonshineNetInit(void);
int MoonshineNetStart(const struct MoonshineNetConfig *config);
int MoonshineNetPoll(struct MoonshineNetStatus *status);
int MoonshineNetSendTo(unsigned epoch, const struct MoonshineNetEndpoint *endpoint,
    const void *data, unsigned bytes);
int MoonshineNetPublishPose(unsigned epoch, const struct MoonshineNetEndpoint *endpoint,
    const void *data, unsigned bytes);
/* Unauthenticated datagrams: the session layer must check sender/token/sequence. */
int MoonshineNetReceive(unsigned epoch, struct MoonshineNetPacket *packet);
void MoonshineNetRequestStop(unsigned epoch);
/* False after a timeout until all IOS writes and the socket close have retired. */
int MoonshineNetRetired(unsigned epoch);
/* Kernel exit only: false keeps the worker/queue pinned; retry without waiting. */
int MoonshineNetShutdown(void);

#endif
