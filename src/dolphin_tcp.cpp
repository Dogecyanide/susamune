#include "susamune/dolphin_tcp.hxx"
#if IS_EMULATOR && TIMEWARP_LIVE_RACING
#include <Dolphin/OS.h>
#include "susamune/dolphin_tcp_api.h"
namespace DolphinTcp {
namespace {
bool initialized;
int sendPacket(const void *data,unsigned bytes,unsigned destination) {
    return DolphinNetwork::sendIp(data,bytes,destination);
}
unsigned ticks(){return OSGetTick();}
const DolphinTcpIo io={sendPacket,ticks};
const DolphinTcpApi *api() {
#ifdef MOONSHINE_LWIP_HOST_TEST
    const auto *p=&dolphin_tcp_api;
#else
    const auto *p=reinterpret_cast<const DolphinTcpApi *>(DOLPHIN_TCP_API_BASE);
#endif
    if(p->magic!=DOLPHIN_TCP_API_MAGIC || p->version!=1 || p->apiBytes!=sizeof(*p))return nullptr;
#ifndef MOONSHINE_LWIP_HOST_TEST
    const auto *calls=reinterpret_cast<const unsigned *>(&p->initialize);
    for(unsigned i=0;i<11;++i)if((calls[i]&3) || calls[i]<DOLPHIN_HTTPS_IMAGE_BASE+0xb8u ||
        calls[i]>=DOLPHIN_HTTPS_IMAGE_BASE+DOLPHIN_HTTPS_IMAGE_CAPACITY)return nullptr;
#endif
    if(!initialized){p->initialize(&io);initialized=true;}
    return p;
}
}
void configure(unsigned ip,unsigned mask,unsigned router){if(const auto *p=api())p->configure(ip,mask,router);}
void tick(unsigned ms){if(initialized)if(const auto *p=api())p->tick(ms);}
void receive(const unsigned char *data,unsigned bytes){if(const auto *p=api())p->receive(data,bytes);}
bool connect(unsigned ip,unsigned short port){const auto *p=api();return p && p->connect(ip,port);}
int send(const void *data,unsigned bytes){const auto *p=api();return p?p->send(data,bytes):-1;}
int read(void *data,unsigned bytes){const auto *p=api();return p?p->read(data,bytes):-1;}
State state(){const auto *p=api();return p?static_cast<State>(p->state()):CLOSED;}
int error(){const auto *p=api();return p?p->error():-1;}
void close(){if(initialized)if(const auto *p=api())p->close();}
unsigned char *dnsBuffer(){const auto *p=api();return p?p->dnsBuffer():nullptr;}
}
#endif
