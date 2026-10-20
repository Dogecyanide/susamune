#ifndef SUSAMUNE_LIVE_RACE_SESSION_HXX
#define SUSAMUNE_LIVE_RACE_SESSION_HXX

#if TIMEWARP_LIVE_RACING
#include "susamune/live_race_wire.h"
#include "susamune/live_transport.h"

namespace LiveRaceSession {
typedef TWLiveEndpoint Endpoint;
enum State { STOPPED, LISTENING, JOINING, ACCEPTING, CONNECTED, FAILED };
enum Error { NO_ERROR, INVALID_CONFIG, HANDSHAKE_TIMEOUT, PEER_TIMEOUT,
             RELIABLE_TIMEOUT, PEER_LEFT };
const unsigned kReliableBytes = 64;

struct Config {
    char name[MSR_NAME_BYTES];
    unsigned pin, nonceHigh, nonceLow;
    unsigned char region, timing;
};
struct Callbacks {
    void *context;
    bool (*sendControl)(void *, const Endpoint &, const void *, unsigned);
    bool (*sendLatestPose)(void *, const Endpoint &, const void *, unsigned);
    void (*onPose)(void *, const MSRHeader &, const MSRPose &, unsigned receivedMs);
    void (*onControl)(void *, const MSRHeader &, const void *, unsigned bytes);
};
struct Status {
    State state;
    Error error;
    Endpoint peer;
    char remoteName[MSR_NAME_BYTES + 1];
    unsigned pingMs;
    unsigned char remoteRegion;
    bool connected, pending, host;
};

// Single caller; callbacks borrow their arguments and must not reenter the session.
struct Session {
    Config config;
    Callbacks callbacks;
    Status info;
    Endpoint allowedPeer;
    unsigned nowMs, startedMs, lastReceiveMs, lastHandshakeMs, lastPingMs;
    unsigned sessionHigh, sessionLow, guestNonceHigh, guestNonceLow;
    unsigned sendSequence, receiveSequence, poseSendSequence, poseReceiveSequence;
    unsigned reliableSentMs, reliableStartedMs, pingSequence, pingSentMs;
    MSRHeader pendingHeader, receivedHeader;
    unsigned char pendingData[kReliableBytes], receivedData[kReliableBytes];
    bool initialized, restricted, handshakeSent, guestAccepted, handshakeAck;
    bool poseSeen, controlSeen, controlAck, pingPending, pingSent;
};
static_assert(sizeof(Session) <= 2048, "Live session exceeds its fixed budget");

// Supply a fresh nonzero nonce for each new attempt. PIN/tag are not encryption.
bool init(Session &, const Config &, const Callbacks &);
// A zero allowedPeer accepts the first valid HELLO; otherwise require that peer.
bool startHost(Session &, const Endpoint &allowedPeer, unsigned nowMs);
bool startGuest(Session &, const Endpoint &host, unsigned nowMs);
void stop(Session &);
void tick(Session &, unsigned nowMs);
bool receivePacket(Session &, const Endpoint &from, const void *, unsigned bytes,
                   unsigned nowMs);
bool publishPose(Session &, const MSRPose &, unsigned round = 0);
bool sendReliable(Session &, unsigned kind, const void *, unsigned bytes,
                  unsigned round = 0);
Status status(const Session &);
}
#endif
#endif
