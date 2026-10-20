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
#endif
