#ifndef SUSAMUNE_DOLPHIN_TCP_HXX
#define SUSAMUNE_DOLPHIN_TCP_HXX
namespace DolphinTcp {
enum State { CLOSED, CONNECTING, OPEN, ENDED, FAILED };
void configure(unsigned ip, unsigned mask, unsigned router);
void tick(unsigned milliseconds);
void receive(const unsigned char *packet, unsigned bytes);
bool connect(unsigned ip, unsigned short port);
int send(const void *data, unsigned bytes);
int read(void *data, unsigned capacity);
State state();
int error();
void close();
unsigned char *dnsBuffer();
}
namespace DolphinNetwork {
bool sendIp(const void *packet, unsigned bytes, unsigned destination);
}
#endif
