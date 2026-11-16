#include "susamune/live_transport.hxx"
#if IS_EMULATOR && TIMEWARP_LIVE_RACING
#include "susamune/dolphin_bba.hxx"
#include "susamune/dolphin_dns.hxx"
#include "susamune/dolphin_tcp.hxx"
#include "susamune/dolphin_live_transport.h"
#include <Dolphin/OS.h>
#include <Dolphin/string.h>
#include <Dolphin/mem.h>

namespace DolphinNetwork {
struct Arp { unsigned ip; unsigned char mac[6]; unsigned short reserved; };
struct Dns {
    DnsResult result;
    unsigned server, started, sent;
    unsigned short port, id;
    unsigned short written, received, expected;
    unsigned char tcp, phase;
    char name[DolphinDns::NAME_BYTES];
};
struct State {
    LiveTransport::Status status;
    LiveTransport::Packet packet;
    LiveTransport::Diagnostics diagnostics;
    unsigned ip,mask,router,server,offer,transaction,started,lastDhcp,lastArp,leaseAt,leaseSeconds;
    unsigned short port,ipId;
    unsigned char mac[6],dhcp,nextArp;
    bool pending;
    Arp arp[8];
    unsigned resolver;
    Dns dns;
    unsigned char frame[1536];
};
static_assert(sizeof(State)<=sizeof(TWDolphinLive),"native BBA exceeds existing Dolphin transport window");
State &s=*reinterpret_cast<State *>(TW_DOLPHIN_LIVE_BASE);
bool initialized;
unsigned epoch, dnsSequence;
unsigned read16(const unsigned char *p){return unsigned(p[0])<<8|p[1];}
unsigned read32(const unsigned char *p){return read16(p)<<16|read16(p+2);}
void put16(unsigned char *p,unsigned v){p[0]=v>>8;p[1]=v;}
void put32(unsigned char *p,unsigned v){put16(p,v>>16);put16(p+2,v);}
unsigned checksum(const unsigned char *p,unsigned bytes,unsigned sum=0) {
    while(bytes>1){sum+=read16(p);p+=2;bytes-=2;}if(bytes)sum+=unsigned(*p)<<8;
    while(sum>>16)sum=(sum&65535)+(sum>>16);return (~sum)&65535;
}
unsigned seconds(){return unsigned(OSGetTime()/(OS_TIMER_CLOCK));}
void remember(unsigned ip,const unsigned char *mac) {
    if(!ip || (mac[0]&1))return;
    unsigned slot=8;for(unsigned i=0;i<8;++i)if(s.arp[i].ip==ip){slot=i;break;}
    if(slot==8)slot=s.nextArp++&7;
    s.arp[slot].ip=ip;memcpy(s.arp[slot].mac,mac,6);
}
bool frameSend(unsigned bytes) {
    if(bytes<60){memset(s.frame+bytes,0,60-bytes);bytes=60;}
    return DolphinBba::send(s.frame,bytes);
}
void arpRequest(unsigned ip) {
    memset(s.frame,0,60);memset(s.frame,255,6);memcpy(s.frame+6,s.mac,6);
    put16(s.frame+12,0x806);put16(s.frame+14,1);put16(s.frame+16,0x800);
    s.frame[18]=6;s.frame[19]=4;put16(s.frame+20,1);
    memcpy(s.frame+22,s.mac,6);put32(s.frame+28,s.ip);put32(s.frame+38,ip);frameSend(60);
}
bool udpSend(unsigned ip,unsigned port,const void *payload,unsigned bytes,bool dhcp=false,
             unsigned sourcePort=0) {
    unsigned char mac[6];memset(mac,255,6);
    if(!dhcp) {
        const unsigned hop=(ip&s.mask)==(s.ip&s.mask)?ip:s.router;
        bool found=false;for(unsigned i=0;i<8;++i)if(s.arp[i].ip==hop){memcpy(mac,s.arp[i].mac,6);found=true;break;}
        if(!found){const unsigned now=seconds();if(now!=s.lastArp){s.lastArp=now;arpRequest(hop);}return false;}
    }
    // Payload may already be the DHCP body in this frame.
    if(payload!=s.frame+42)memcpy(s.frame+42,payload,bytes);
    memset(s.frame,0,42);memcpy(s.frame,mac,6);memcpy(s.frame+6,s.mac,6);put16(s.frame+12,0x800);
    unsigned char *ipHead=s.frame+14,*udp=s.frame+34;
    ipHead[0]=0x45;put16(ipHead+2,28+bytes);put16(ipHead+4,++s.ipId);ipHead[8]=64;ipHead[9]=17;
    put32(ipHead+12,dhcp?0:s.ip);put32(ipHead+16,ip);put16(ipHead+10,checksum(ipHead,20));
    put16(udp,dhcp?68:(sourcePort?sourcePort:s.port));put16(udp+2,port);put16(udp+4,8+bytes);
    const unsigned sum=checksum(udp,bytes+8,read16(ipHead+12)+read16(ipHead+14)+read16(ipHead+16)+read16(ipHead+18)+17+bytes+8);
    put16(udp+6,sum?sum:65535);return frameSend(42+bytes);
}
bool sendIp(const void *packet,unsigned bytes,unsigned destination) {
    if(!packet || bytes<20 || bytes>1500 || s.status.state!=TW_LIVE_READY)return false;
    const unsigned hop=(destination&s.mask)==(s.ip&s.mask)?destination:s.router;
    const unsigned char *mac=nullptr;
    for(unsigned i=0;i<8;++i)if(s.arp[i].ip==hop){mac=s.arp[i].mac;break;}
    if(!mac){const unsigned now=seconds();if(now!=s.lastArp){s.lastArp=now;arpRequest(hop);}return false;}
    memcpy(s.frame+14,packet,bytes);memcpy(s.frame,mac,6);memcpy(s.frame+6,s.mac,6);
    put16(s.frame+12,0x800);return frameSend(bytes+14);
}
void dhcpSend() {
    unsigned char *p=s.frame+42;memset(p,0,300);p[0]=1;p[1]=1;p[2]=6;
    put32(p+4,s.transaction);put16(p+10,0x8000);memcpy(p+28,s.mac,6);put32(p+236,0x63825363);
    unsigned n=240;p[n++]=53;p[n++]=1;p[n++]=s.offer?3:1;
    if(s.offer){p[n++]=50;p[n++]=4;put32(p+n,s.offer);n+=4;p[n++]=54;p[n++]=4;put32(p+n,s.server);n+=4;}
    p[n++]=55;p[n++]=4;p[n++]=1;p[n++]=3;p[n++]=6;p[n++]=51;p[n++]=255;
    udpSend(0xffffffffu,67,p,300,true);s.lastDhcp=seconds();
}
void dhcpReceive(const unsigned char *p,unsigned bytes) {
    if(bytes<240 || p[0]!=2 || p[1]!=1 || p[2]!=6 || read32(p+4)!=s.transaction ||
        memcmp(p+28,s.mac,6) || read32(p+236)!=0x63825363)return;
    unsigned kind=0,server=0,mask=0,router=0,resolver=0,lease=86400;
    for(unsigned i=240;i<bytes;) {
        const unsigned type=p[i++];if(type==255)break;if(!type)continue;
        if(i==bytes)return;const unsigned n=p[i++];if(n>bytes-i)return;
        if(type==53 && n==1)kind=p[i];
        if(type==54 && n==4)server=read32(p+i);
        if(type==1 && n==4)mask=read32(p+i);
        if(type==3 && n>=4)router=read32(p+i);
        if(type==51 && n==4)lease=read32(p+i);
        if(type==6 && n>=4 && n%4==0 && p[i] && p[i]!=127 && p[i]<224)resolver=read32(p+i);
        i+=n;
    }
    if(kind==2 && s.dhcp==1 && server && read32(p+16)) {
        s.offer=read32(p+16);s.server=server;s.dhcp=2;s.lastDhcp=seconds()-2;
    } else if(kind==5 && s.dhcp==2 && server==s.server && read32(p+16)==s.offer && mask && router) {
        s.ip=s.offer;s.mask=mask;s.router=router;s.dhcp=3;s.leaseAt=seconds();
        if(resolver)s.resolver=resolver;
        s.leaseSeconds=lease<60?60:lease;s.status.state=TW_LIVE_READY;
        remember(router,s.frame+6);
        DolphinTcp::configure(s.ip,s.mask,s.router);
    } else if(kind==6 && server==s.server) {s.status.state=TW_LIVE_FAILED;s.status.error=-2;}
}
void dnsTcpPoll() {
    Dns &dns=s.dns;
    if(!dns.phase) {
        if(!DolphinTcp::connect(dns.server,53)){dns.result.state=DNS_FAILED;dns.result.error=-5;return;}
        dns.phase=1;
    }
    const DolphinTcp::State state=DolphinTcp::state();
    if(state==DolphinTcp::FAILED || state==DolphinTcp::CLOSED || (state==DolphinTcp::ENDED && dns.phase!=2)) {
        dns.result.state=DNS_FAILED;dns.result.error=-5;DolphinTcp::close();return;
    }
    if(state!=DolphinTcp::OPEN && state!=DolphinTcp::ENDED)return;
    unsigned char *buffer=DolphinTcp::dnsBuffer();
    if(dns.phase==1) {
        const unsigned bytes=DolphinDns::query(buffer+2,512,dns.name,dns.id);
        put16(buffer,bytes);
        const int sent=DolphinTcp::send(buffer+dns.written,bytes+2-dns.written);
        if(sent<0){dns.result.state=DNS_FAILED;dns.result.error=-5;DolphinTcp::close();return;}
        dns.written+=sent;
        if(dns.written==bytes+2)dns.phase=2;
    }
    if(dns.phase!=2)return;
    const unsigned target=dns.received<2?2:2+dns.expected;
    const int got=DolphinTcp::read(buffer+dns.received,target-dns.received);
    if(got<0){dns.result.state=DNS_FAILED;dns.result.error=-5;DolphinTcp::close();return;}
    dns.received+=got;
    if(dns.received<2)return;
    if(!dns.expected) {
        dns.expected=read16(buffer);
        if(dns.expected<12 || dns.expected>512){dns.result.state=DNS_FAILED;dns.result.error=-4;DolphinTcp::close();return;}
    }
    if(dns.received!=dns.expected+2)return;
    unsigned address=0;
    const DolphinDns::Answer result=DolphinDns::answer(buffer+2,dns.expected,dns.name,dns.id,&address);
    dns.result.state=result==DolphinDns::ADDRESS?DNS_RESOLVED:DNS_FAILED;
    dns.result.address=address;
    dns.result.error=result==DolphinDns::ADDRESS?0:-4;
    DolphinTcp::close();
}
void dnsPoll() {
    Dns &dns=s.dns;
    if(dns.result.state!=DNS_WAITING)return;
    const unsigned now=seconds();
    if(s.status.state!=TW_LIVE_READY || now-dns.started>=12) {
        dns.result.state=DNS_FAILED;dns.result.error=-1;
        if(dns.tcp)DolphinTcp::close();return;
    }
    if(dns.tcp){dnsTcpPoll();return;}
    if(now-dns.sent<2)return;
    unsigned char *payload=s.frame+42;
    const unsigned bytes=DolphinDns::query(payload,sizeof(s.frame)-42,dns.name,dns.id);
    if(bytes && udpSend(dns.server,53,payload,bytes,false,dns.port))dns.sent=now;
}
void dnsReceive(const unsigned char *payload,unsigned bytes) {
    unsigned address=0;
    const DolphinDns::Answer result=DolphinDns::answer(payload,bytes,s.dns.name,s.dns.id,&address);
    if(result==DolphinDns::IGNORE)return;
    s.dns.result.state=result==DolphinDns::ADDRESS?DNS_RESOLVED:DNS_FAILED;
    s.dns.result.address=address;
    s.dns.result.error=result==DolphinDns::ADDRESS?0:(result==DolphinDns::TRUNCATED?-3:-2);
}
void consume(unsigned bytes) {
    unsigned char *p=s.frame;
    if(bytes<14 || (memcmp(p,s.mac,6) && memcmp(p,"\xff\xff\xff\xff\xff\xff",6)))return;
    const unsigned type=read16(p+12);
    if(type==0x806) {
        if(bytes<42 || read16(p+14)!=1 || read16(p+16)!=0x800 || p[18]!=6 || p[19]!=4)return;
        const unsigned op=read16(p+20);if(op!=1 && op!=2)return;
        if(s.ip && read32(p+38)==s.ip) {
            remember(read32(p+28),p+22);
            if(op==1){memcpy(p,p+22,6);memcpy(p+6,s.mac,6);put16(p+20,2);
                memcpy(p+32,p+22,6);put32(p+38,read32(p+28));memcpy(p+22,s.mac,6);put32(p+28,s.ip);frameSend(42);}
        }
        return;
    }
    if(type!=0x800 || bytes<42)return;
    const unsigned char *ip=p+14;const unsigned header=(ip[0]&15)*4,total=read16(ip+2);
    if(ip[0]>>4!=4 || header<20 || header>60 || total<header+8 || total>bytes-14 ||
        (read16(ip+6)&0x3fff) || checksum(ip,header))return;
    if(ip[9]==6) {
        if(s.status.state==TW_LIVE_READY && read32(ip+16)==s.ip)DolphinTcp::receive(ip,total);
        return;
    }
    if(ip[9]!=17)return;
    const unsigned char *udp=ip+header;const unsigned length=read16(udp+4),destination=read32(ip+16);
    if(length<8 || length!=total-header || (read16(udp+6) && checksum(udp,length,
        read16(ip+12)+read16(ip+14)+read16(ip+16)+read16(ip+18)+17+length)))return;
    if(read16(udp)==67 && read16(udp+2)==68 && (s.dhcp==1 || s.dhcp==2)){dhcpReceive(udp+8,length-8);return;}
    if(s.status.state==TW_LIVE_READY && destination==s.ip && s.dns.result.state==DNS_WAITING &&
        read32(ip+12)==s.dns.server && read16(udp)==53 && read16(udp+2)==s.dns.port) {
        dnsReceive(udp+8,length-8);return;
    }
    if(s.status.state!=TW_LIVE_READY || destination!=s.ip || read16(udp+2)!=s.port ||
        length<=8 || length-8>TW_LIVE_PACKET_BYTES)return;
    if(s.pending){++s.diagnostics.dropped;return;}
    s.packet=LiveTransport::Packet{};s.packet.epoch=s.status.epoch;s.packet.bytes=length-8;
    memcpy(s.packet.endpoint.ip,ip+12,4);s.packet.endpoint.port=read16(udp);
    if(!TWLiveEndpointValid(&s.packet.endpoint))return;
    memcpy(s.packet.data,udp+8,length-8);s.pending=true;++s.status.rxWrite;++s.diagnostics.received;
}
bool resolve(const char *name,unsigned server) {
    if(LiveTransport::poll().state!=TW_LIVE_READY || !server || (server>>24)>=224 ||
        s.dns.result.state==DNS_WAITING)return false;
    char normalized[DolphinDns::NAME_BYTES]={};
    if(!DolphinDns::normalize(name,normalized))return false;
    memset(&s.dns,0,sizeof(s.dns));
    memcpy(s.dns.name,normalized,sizeof(normalized));
    s.dns.server=server;s.dns.tcp=1;s.dns.started=seconds();s.dns.sent=s.dns.started-2;
    const unsigned nonce=OSGetTick()+(++dnsSequence*0x9e3779b9u);
    s.dns.id=nonce^(nonce>>16);
    s.dns.port=49152+((nonce>>8)&16383);
    if(s.dns.port==s.port)s.dns.port=s.dns.port==65535?49152:s.dns.port+1;
    s.dns.result.state=DNS_WAITING;
    return true;
}
DnsResult dnsResult(){LiveTransport::poll();return s.dns.result;}
void cancelResolve(){if(initialized){if(s.dns.tcp && s.dns.result.state==DNS_WAITING)DolphinTcp::close();memset(&s.dns,0,sizeof(s.dns));}}
}
namespace LiveTransport {
using namespace DolphinNetwork;
Status poll() {
    if(!initialized) {
        memset(&s,0,sizeof(s));
        if(!DolphinBba::init(s.mac))return Status{};
        initialized=true;s.status.epoch=++epoch;if(!epoch)s.status.epoch=++epoch;
        s.status.state=TW_LIVE_IDLE;
    }
    if(s.status.state==TW_LIVE_OPENING || s.status.state==TW_LIVE_READY) {
        // One receive slot stays owned until the caller consumes it; no stale queue.
        if(!s.pending || DolphinTcp::state()!=DolphinTcp::CLOSED)for(unsigned i=0;i<4 && (!s.pending || DolphinTcp::state()!=DolphinTcp::CLOSED);++i){const unsigned n=DolphinBba::receive(s.frame,sizeof(s.frame));if(!n)break;consume(n);}
        const unsigned now=seconds();
        if(s.dhcp<3 && now-s.lastDhcp>=1)dhcpSend();
        if(s.status.state==TW_LIVE_OPENING && now-s.started>=30){s.status.state=TW_LIVE_FAILED;s.status.error=-1;}
        if(s.dhcp==3 && now-s.leaseAt>=s.leaseSeconds/2){s.dhcp=2;s.started=now;s.lastDhcp=now-2;}
        if(s.ip && now-s.leaseAt>=s.leaseSeconds){s.status.state=TW_LIVE_FAILED;s.status.error=-3;}
    }
    DolphinTcp::tick(unsigned(OSGetTime()/(OS_TIMER_CLOCK/1000)));
    dnsPoll();
    return s.status;
}
bool begin(unsigned short port) {
    if(poll().state!=TW_LIVE_IDLE)return false;
    s.port=port?port:static_cast<unsigned short>(49152+(OSGetTick()&16383));
    s.transaction=OSGetTick()|1;s.started=seconds();s.lastDhcp=s.started-2;s.lastArp=s.started-2;
    s.dhcp=1;s.status.state=TW_LIVE_OPENING;return true;
}
bool localEndpoint(Endpoint *out) {
    if(!out || poll().state!=TW_LIVE_READY)return false;
    put32(out->ip,s.ip);out->port=s.port;out->reserved=0;return true;
}
bool diagnostics(const Status &,Diagnostics *out){if(!out || !initialized)return false;*out=s.diagnostics;return true;}
bool sendControl(const Endpoint &endpoint,const void *data,unsigned bytes) {
    if(poll().state!=TW_LIVE_READY || !data || !bytes || bytes>TW_LIVE_PACKET_BYTES || !TWLiveEndpointValid(&endpoint))return false;
    if(!udpSend(read32(endpoint.ip),endpoint.port,data,bytes))return false;
    ++s.diagnostics.sent;++s.status.txRead;return true;
}
bool publishPose(const Endpoint &endpoint,const void *data,unsigned bytes){return sendControl(endpoint,data,bytes);}
bool receive(Packet &packet){poll();if(!s.pending)return false;packet=s.packet;s.pending=false;return true;}
void stop(){if(!initialized)return;DolphinTcp::close();memset(&s,0,sizeof(s));initialized=false;}
}
#endif
