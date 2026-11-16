#include "susamune/live_race_session.hxx"
#include "susamune/live_p2p.hxx"
#include <cstring>
#include <new>

namespace {
struct Packet { TWLiveEndpoint endpoint; unsigned bytes; unsigned char data[256]; };
struct Peer {
    LiveRaceSession::Session session{};
    LiveP2P::Punch punch{};
    Packet queue[32]{};
    unsigned write=0, read=0, generation=0, now=0, nonce=0, pin=0, accepted=0;
    unsigned char report[64]{}, details[64][64]{};
    unsigned detailWrite=0, detailRead=0, detailDropped=0;
    bool host=false, offered=false;
};
TWLiveEndpoint endpoint(unsigned ip, unsigned port) {
    return {{static_cast<unsigned char>(ip>>24),static_cast<unsigned char>(ip>>16),
             static_cast<unsigned char>(ip>>8),static_cast<unsigned char>(ip)},static_cast<unsigned short>(port),0};
}
bool send(void *context,const TWLiveEndpoint &to,const void *data,unsigned bytes) {
    auto &p=*static_cast<Peer*>(context);
    if(bytes>256||p.write-p.read>=32)return false;
    auto&q=p.queue[p.write++%32];q.endpoint=to;q.bytes=bytes;std::memcpy(q.data,data,bytes);return true;
}
void pose(void*,const MSRHeader&,const MSRPose&,unsigned) {}
void control(void *context,const MSRHeader &header,const void *data,unsigned bytes) {
    auto&p=*static_cast<Peer*>(context);
    const unsigned magic=bytes==64?MSRRead32(static_cast<const unsigned char*>(data)):0;
    if(header.kind==MSR_READY && bytes==64 && magic==0x4d4d4431u){
        if(p.detailWrite-p.detailRead==64){++p.detailDropped;return;}
        std::memcpy(p.details[p.detailWrite++%64],data,64);return;
    }
    if(header.kind!=MSR_READY||bytes!=64||magic<0x4d4d5431u||magic>0x4d4d5435u)return;
    std::memcpy(p.report,data,64);++p.generation;
}
void initialize(Peer &p,bool host,unsigned pin,unsigned high,unsigned low,const TWLiveEndpoint &remote,unsigned now) {
    LiveRaceSession::Config config{};
    std::strcpy(config.name,host?"Memory monitor":"Probe test Wii");
    config.pin=pin;config.nonceHigh=high;config.nonceLow=low;
    config.region=2;config.timing=MSR_TIMING_60HZ;
    LiveRaceSession::Callbacks callbacks{&p,send,send,pose,control};
    p.host=host;p.pin=pin;p.now=now;p.nonce=low;p.offered=false;
    LiveRaceSession::init(p.session,config,callbacks);
    LiveP2P::reset(p.punch,pin,host?LiveP2P::HOST:LiveP2P::JOINER);
    if(host)LiveRaceSession::startHost(p.session,remote,now);
    else{LiveRaceSession::startGuest(p.session,remote,now);LiveP2P::add(p.punch,remote,LiveP2P::HOST);}
}
}
#ifdef _WIN32
#define API extern "C" __declspec(dllexport)
#else
#define API extern "C" __attribute__((visibility("default")))
#endif
API void* mm_create(unsigned host,unsigned pin,unsigned high,unsigned low,unsigned ip,unsigned port,unsigned now) {
    auto*p=new(std::nothrow)Peer;if(!p)return nullptr;
    initialize(*p,host!=0,pin,high,low,endpoint(ip,port),now);return p;
}
API void mm_destroy(void*peer){delete static_cast<Peer*>(peer);}
API int mm_code(unsigned ip,unsigned port,unsigned pin,char*out) {
    char raw[LiveP2P::CODE_CHARS+1];
    if(!LiveP2P::encode({endpoint(ip,port),pin},raw))return 0;
    LiveP2P::format(raw,out);return 1;
}
API unsigned mm_state(void*peer){return static_cast<Peer*>(peer)->session.info.state;}
API unsigned mm_ping(void*peer){return static_cast<Peer*>(peer)->session.info.pingMs;}
API void mm_name(void*peer,char*out){std::memcpy(out,static_cast<Peer*>(peer)->session.info.remoteName,17);}
API unsigned mm_report(void*peer,unsigned previous,void*out) {
    auto&p=*static_cast<Peer*>(peer);if(p.generation!=previous)std::memcpy(out,p.report,64);return p.generation;
}
API unsigned mm_pop(void*peer,unsigned*ip,unsigned*port,void*out) {
    auto&p=*static_cast<Peer*>(peer);if(p.read==p.write)return 0;
    auto&q=p.queue[p.read++%32];*ip=(unsigned(q.endpoint.ip[0])<<24)|(unsigned(q.endpoint.ip[1])<<16)|(unsigned(q.endpoint.ip[2])<<8)|q.endpoint.ip[3];
    *port=q.endpoint.port;std::memcpy(out,q.data,q.bytes);return q.bytes;
}
API int mm_receive(void*peer,unsigned ip,unsigned port,const void*data,unsigned bytes,unsigned now) {
    auto&p=*static_cast<Peer*>(peer);p.now=now;auto from=endpoint(ip,port);
    if(p.session.info.connected&&std::memcmp(&from,&p.session.info.peer,sizeof(from)))return 0;
    if(LiveP2P::receive(p.punch,from,data,bytes,now,p.host))return 1;
    return LiveRaceSession::receivePacket(p.session,from,data,bytes,now);
}
API void mm_tick(void*peer,unsigned now) {
    auto&p=*static_cast<Peer*>(peer);p.now=now;
    if(p.host&&(p.session.info.state==LiveRaceSession::FAILED||p.session.info.state==LiveRaceSession::STOPPED))
        initialize(p,true,p.pin,p.session.config.nonceHigh,++p.nonce,{},now);
    unsigned char packet[LiveP2P::PUNCH_BYTES];
    if(!p.session.info.connected){unsigned n=LiveP2P::due(p.punch,0,now,packet);if(n)send(&p,p.punch.peers[0].endpoint,packet,n);}
    LiveRaceSession::tick(p.session,now);
    if(p.host&&p.session.info.connected&&!p.session.info.pending&&!p.offered){
        unsigned char offer[12]={1,0,3,2,0,0,0,0,0,0,0,1};
        p.offered=LiveRaceSession::sendReliable(p.session,MSR_READY,offer,12,1);
    }
}
// Used by the host-side transport test; it has no Wii request counterpart.
API int mm_test_report(void*peer,const void*data){return LiveRaceSession::sendReliable(static_cast<Peer*>(peer)->session,MSR_READY,data,64,1);}

API unsigned mm_decode(const char*text,unsigned*ip,unsigned*port) {
    LiveP2P::Code code{};if(!LiveP2P::decode(text,&code))return 0;
    *ip=(unsigned(code.endpoint.ip[0])<<24)|(unsigned(code.endpoint.ip[1])<<16)|(unsigned(code.endpoint.ip[2])<<8)|code.endpoint.ip[3];
    *port=code.endpoint.port;return code.secret;
}

API unsigned mm_detail(void*peer,void*out){
    auto&p=*static_cast<Peer*>(peer);if(p.detailRead==p.detailWrite)return 0;
    std::memcpy(out,p.details[p.detailRead++%64],64);return 1;
}
API unsigned mm_detail_dropped(void*peer){return static_cast<Peer*>(peer)->detailDropped;}
API int mm_command(void*peer,unsigned id,unsigned operation){
    auto&p=*static_cast<Peer*>(peer);if(!p.host||!id||operation<1||operation>5)return 0;
    unsigned char body[16]={};MSRWrite32(body,0x4d4d5131u);MSRWrite32(body+4,id);MSRWrite32(body+8,operation);
    return LiveRaceSession::sendReliable(p.session,MSR_READY,body,16,0);
}
