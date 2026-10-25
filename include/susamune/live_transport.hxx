#ifndef SUSAMUNE_LIVE_TRANSPORT_HXX
#define SUSAMUNE_LIVE_TRANSPORT_HXX
#include "susamune/live_transport.h"

namespace LiveTransport {
typedef TWLiveEndpoint Endpoint;
typedef TWLivePacket Packet;
typedef TWLiveStatus Status;
struct Diagnostics {
    unsigned short sent, received;
    unsigned char dropped, sendErrors, receiveErrors;
    int lastError;
};
bool begin(unsigned short localPort);
Status poll();
bool diagnostics(const Status &status, Diagnostics *out);
bool localEndpoint(Endpoint *endpoint);
bool sendControl(const Endpoint &endpoint, const void *data, unsigned bytes);
bool publishPose(const Endpoint &endpoint, const void *data, unsigned bytes);
bool receive(Packet &packet);
void stop();
}

// NAT probe: one socket sends RFC 5389 Binding Requests to two STUN servers on
// different IPs and compares the public endpoints they report. Online play uses
// the reported endpoint as this player's address in the room code.
namespace LiveStun {
enum { REQUEST_BYTES = 20, TRANSACTION_BYTES = 12, SERVER_COUNT = 2, ATTEMPTS = 6 };
enum State { IDLE, RUNNING, DONE, FAILED };
enum Verdict { NO_REPLY, ONE_REPLY, SAME_MAPPING, DIFFERENT_MAPPING };
struct Result {
    unsigned char state, verdict, attempts, answered; // answered: one bit per server
    int error;
    TWLiveEndpoint mapped[SERVER_COUNT];
};
void request(unsigned char *out, const unsigned char *transaction);
// Only a Binding Success Response to this transaction with an IPv4 XOR-MAPPED-ADDRESS.
bool mapped(const void *data, unsigned bytes, const unsigned char *transaction, TWLiveEndpoint *out);
// Standalone probe: owns the transport for its run.
bool start(unsigned short localPort);
// Probe on a transport the caller already runs and polls; the caller hands
// every received packet to accept() first.
bool startShared();
bool accept(const LiveTransport::Packet &packet);
void cancel();
void update();
const Result &result();
}
#endif
