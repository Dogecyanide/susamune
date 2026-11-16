#include "susamune/dolphin_tcp.hxx"
#include "susamune/dolphin_tcp_api.h"
#if IS_EMULATOR && TIMEWARP_LIVE_RACING
#include "susamune/mem2_map.h"

extern "C" {
#include <string.h>
}
extern "C" {
#include "lwip/mem.h"
#include "lwip/memp.h"
#include "lwip/netif.h"
#include "lwip/pbuf.h"
#include "lwip/tcp.h"
#include "lwip/priv/tcp_priv.h"
#include "lwip/ip4.h"
}

namespace DolphinNativeTcp {
using namespace DolphinTcp;
void close();
static const DolphinTcpIo *transport;
namespace {
struct Work {
    netif interface;
    tcp_pcb *pcb;
    pbuf *incoming;
    unsigned clock;
    State phase;
    int failure;
    unsigned char dns[514];
};
static_assert(sizeof(Work) <= SUSAMUNE_DOLPHIN_TCP_STATE_SIZE,
              "native TCP state exceeds its existing gap");
Work &s = *reinterpret_cast<Work *>(SUSAMUNE_DOLPHIN_TCP_STATE_PPC_BASE);
bool initialized;

err_t output(netif *, pbuf *packet, const ip4_addr_t *destination) {
    unsigned char bytes[1500];
    if (packet->tot_len > sizeof(bytes) ||
        pbuf_copy_partial(packet, bytes, packet->tot_len, 0) != packet->tot_len)
        return ERR_BUF;
    return transport->sendIp(bytes, packet->tot_len, lwip_ntohl(destination->addr))
        ? ERR_OK : ERR_RTE;
}
err_t prepare(netif *interface) {
    interface->name[0] = 'm'; interface->name[1] = 's';
    interface->mtu = 1500;
    interface->output = output;
    return ERR_OK;
}
void failed(void *, err_t error) {
    s.pcb = nullptr;
    s.failure = error;
    s.phase = FAILED;
    if (s.incoming) pbuf_free(s.incoming);
    s.incoming = nullptr;
}
err_t connected(void *, tcp_pcb *, err_t error) {
    s.failure = error;
    s.phase = error == ERR_OK ? OPEN : FAILED;
    return ERR_OK;
}
err_t received(void *, tcp_pcb *, pbuf *packet, err_t error) {
    if (error != ERR_OK) return error;
    if (!packet) { s.phase = ENDED; return ERR_OK; }
    // tcp_recved() advances the receive window only after the consumer reads.
    if (s.incoming) pbuf_cat(s.incoming, packet);
    else s.incoming = packet;
    return ERR_OK;
}
}
void configure(unsigned ip, unsigned mask, unsigned router) {
    ip4_addr_t address = {lwip_htonl(ip)}, netmask = {lwip_htonl(mask)},
               gateway = {lwip_htonl(router)};
    if (!initialized) {
        memset(&s, 0, sizeof(s));
        mem_init(); memp_init(); netif_init(); tcp_init();
        if (!netif_add(&s.interface, &address, &netmask, &gateway, nullptr, prepare, ip_input))
            return;
        netif_set_default(&s.interface);
        netif_set_up(&s.interface); netif_set_link_up(&s.interface);
        initialized = true;
    } else if (netif_ip4_addr(&s.interface)->addr != address.addr ||
               netif_ip4_netmask(&s.interface)->addr != netmask.addr ||
               netif_ip4_gw(&s.interface)->addr != gateway.addr) {
        close();
        netif_set_addr(&s.interface, &address, &netmask, &gateway);
    }
}
void tick(unsigned milliseconds) {
    if (!initialized) return;
    unsigned count = 0;
    while (milliseconds - s.clock >= TCP_TMR_INTERVAL && count++ < 4) {
        s.clock += TCP_TMR_INTERVAL;
        tcp_tmr();
    }
    if (count > 4) s.clock = milliseconds;
    if (s.pcb && s.phase == OPEN) tcp_output(s.pcb);
}
void receive(const unsigned char *packet, unsigned bytes) {
    if (!initialized || bytes > 1500) return;
    pbuf *buffer = pbuf_alloc(PBUF_RAW, bytes, PBUF_RAM);
    if (!buffer) return;
    if (pbuf_take(buffer, packet, bytes) != ERR_OK) { pbuf_free(buffer); return; }
    ip4_input(buffer, &s.interface);
}
int connect(unsigned ip, unsigned short port) {
    if (!initialized || !port || !ip || (ip >> 24) >= 224) return false;
    close();
    s.pcb = tcp_new_ip_type(IPADDR_TYPE_V4);
    if (!s.pcb) { s.failure = ERR_MEM; s.phase = FAILED; return false; }
    tcp_arg(s.pcb, &s); tcp_recv(s.pcb, received); tcp_err(s.pcb, failed);
    ip_addr_t destination;
    ip_addr_set_ip4_u32(&destination, lwip_htonl(ip));
    s.phase = CONNECTING;
    const err_t result = tcp_connect(s.pcb, &destination, port, connected);
    if (result != ERR_OK) { close(); s.failure = result; s.phase = FAILED; return false; }
    return true;
}
int send(const void *data, unsigned bytes) {
    if (!initialized || s.phase != OPEN || !s.pcb || !data) return -1;
    if (bytes > tcp_sndbuf(s.pcb)) bytes = tcp_sndbuf(s.pcb);
    if (!bytes) return 0;
    const err_t result = tcp_write(s.pcb, data, bytes, TCP_WRITE_FLAG_COPY);
    if (result == ERR_MEM) return 0;
    if (result != ERR_OK) { s.failure = result; return -1; }
    tcp_output(s.pcb);
    return bytes;
}
int read(void *data, unsigned capacity) {
    if (!initialized || !data || s.phase == FAILED || s.phase == DolphinTcp::CLOSED) return -1;
    if (!s.incoming) return s.phase == ENDED ? -1 : 0;
    unsigned bytes = s.incoming->tot_len;
    if (bytes > capacity) bytes = capacity;
    if (pbuf_copy_partial(s.incoming, data, bytes, 0) != bytes) return -1;
    s.incoming = pbuf_free_header(s.incoming, bytes);
    if (s.pcb) tcp_recved(s.pcb, bytes);
    return bytes;
}
unsigned char *dnsBuffer() { return s.dns; }
int state() { return initialized ? s.phase : DolphinTcp::CLOSED; }
int error() { return initialized ? s.failure : 0; }
void close() {
    if (!initialized) return;
    if (s.incoming) pbuf_free(s.incoming);
    s.incoming = nullptr;
    if (s.pcb) { tcp_err(s.pcb, nullptr); tcp_abort(s.pcb); }
    s.pcb = nullptr; s.phase = DolphinTcp::CLOSED; s.failure = 0;
}
}
// DolphinNetwork polls tcp_tmr directly; no scheduler needs arming.
extern "C" void tcp_timer_needed(void) {}
extern "C" unsigned moonshine_tcp_random(void) {
    static unsigned sequence;
    // Port/sequence variation only; this is not a TLS entropy source.
    return DolphinNativeTcp::transport->ticks() ^ (++sequence * 0x9e3779b9u);
}

extern "C" {
#ifndef MOONSHINE_LWIP_HOST_TEST
void MoonshineNativeInit(void);
#endif
static void nativeInit(const DolphinTcpIo *io) {
#ifndef MOONSHINE_LWIP_HOST_TEST
    MoonshineNativeInit();
#endif
    DolphinNativeTcp::transport = io;
}
__attribute__((section(".tcpapi"),used)) const DolphinTcpApi dolphin_tcp_api={
    DOLPHIN_TCP_API_MAGIC,1,sizeof(DolphinTcpApi),nativeInit,
    DolphinNativeTcp::configure,DolphinNativeTcp::tick,DolphinNativeTcp::receive,
    DolphinNativeTcp::connect,DolphinNativeTcp::send,DolphinNativeTcp::read,
    DolphinNativeTcp::state,DolphinNativeTcp::error,DolphinNativeTcp::close,DolphinNativeTcp::dnsBuffer
};
}
#endif
