#ifndef SUSAMUNE_LIVE_RELAY_HXX
#define SUSAMUNE_LIVE_RELAY_HXX
#if TIMEWARP_LIVE_RACING
#include "susamune/live_relay_wire.h"
#include "susamune/live_transport.h"

namespace LiveRelay {
typedef TWLiveEndpoint Endpoint;
enum State { STOPPED, OPENING, PROVING, WAITING, READY, FAILED };
enum Error { NO_ERROR, INVALID_CONFIG, SERVER_TIMEOUT, NO_ROOM, ROOM_FULL,
             SERVER_BUSY, ROOM_CLOSED, PEER_LEFT, LOBBY_EXPIRED, PROTOCOL_ERROR };
struct Callbacks {
    void *context;
    bool (*sendControl)(void *, const Endpoint &, const void *, unsigned);
    bool (*sendLatestPose)(void *, const Endpoint &, const void *, unsigned);
    void (*onPacket)(void *, const void *, unsigned, unsigned receivedMs);
};
struct Status {
    State state;
    Error error;
    unsigned roomCode;
    bool peerReady, host;
};
struct Client {
    Callbacks callbacks;
    Endpoint server;
    MSLHeader identity;
    Status info;
    unsigned requestedRoom, nowMs, startedMs, receivedMs, sentMs;
    unsigned char challenge[16];
    bool initialized, sent;
};
static_assert(sizeof(Client) <= 192, "Relay client exceeds its fixed budget");

// Single caller. onPacket may send replies; lifecycle/receive callbacks must not recurse.
bool init(Client &, const Callbacks &);
bool begin(Client &, bool host, unsigned roomCode, unsigned nonceHigh,
           unsigned nonceLow, const Endpoint &server, unsigned nowMs);
void tick(Client &, unsigned nowMs);
bool receive(Client &, const Endpoint &, const void *, unsigned bytes, unsigned nowMs);
bool sendControl(Client &, const void *inner, unsigned bytes);
bool sendPose(Client &, const void *inner, unsigned bytes);
void stop(Client &);
Status status(const Client &);
}
#endif
#endif
