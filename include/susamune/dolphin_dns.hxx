#ifndef SUSAMUNE_DOLPHIN_DNS_HXX
#define SUSAMUNE_DOLPHIN_DNS_HXX

namespace DolphinDns {
enum { NAME_BYTES = 254, QUERY_BYTES = 272 };
enum Answer { IGNORE, ADDRESS, NOT_FOUND, TRUNCATED };
// IPv4 stub resolver codec; DNS does not authenticate the eventual TLS peer.
bool normalize(const char *source, char *destination);
unsigned query(unsigned char *out, unsigned capacity, const char *name, unsigned id);
Answer answer(const unsigned char *packet, unsigned bytes, const char *name,
              unsigned id, unsigned *address);
}
namespace DolphinNetwork {
enum DnsStatus { DNS_IDLE, DNS_WAITING, DNS_RESOLVED, DNS_FAILED };
struct DnsResult { unsigned state, address; int error; };
// Requires an open native transport. Cancelling a lookup never closes that transport.
bool resolve(const char *name, unsigned server = 0x01010101u);
DnsResult dnsResult();
void cancelResolve();
}
#endif
