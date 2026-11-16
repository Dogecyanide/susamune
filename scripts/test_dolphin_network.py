"""Exercise the production native UDP/TCP stack with Ethernet frames, without sockets."""
import ctypes as C
import os
from pathlib import Path
import struct
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/test-dolphin-network'
MAC=b'\x02\x01\x02\x03\x04\x05'
ROUTER=b'\x02\x06\x07\x08\x09\x0a'
IP=b'\xc0\xa8\x02\x64'
SERVER=b'\xc0\xa8\x02\x01'

def check(data):
    if len(data)&1:data+=b'\0'
    n=sum(struct.unpack('>'+str(len(data)//2)+'H',data))
    while n>>16:n=(n&65535)+(n>>16)
    return (~n)&65535

def udp(payload,source=SERVER,destination=IP,sport=48222,dport=48222,fragment=0):
    u=struct.pack('>HHHH',sport,dport,len(payload)+8,0)+payload
    checksum=check(source+destination+struct.pack('>BBH',0,17,len(u))+u) or 65535
    u=u[:6]+struct.pack('>H',checksum)+u[8:]
    ip=struct.pack('>BBHHHBBH',0x45,0,len(u)+20,1,fragment,64,17,0)+source+destination
    ip=ip[:10]+struct.pack('>H',check(ip))+ip[12:]
    return MAC+ROUTER+b'\x08\x00'+ip+u

def tcp(payload=b'', source=SERVER, destination=IP, sport=443, dport=0,
        seq=1000, ack=0, flags=0x18, window=4096):
    t=struct.pack('>HHIIBBHHH',sport,dport,seq,ack,0x50,flags,window,0,0)+payload
    c=check(source+destination+struct.pack('>BBH',0,6,len(t))+t)
    t=t[:16]+struct.pack('>H',c)+t[18:]
    h=struct.pack('>BBHHHBBH',0x45,0,len(t)+20,1,0,64,6,0)+source+destination
    h=h[:10]+struct.pack('>H',check(h))+h[12:]
    return MAC+ROUTER+b'\x08\x00'+h+t

class NetworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ['PATH']='C:/msys64/mingw64/bin'+os.pathsep+os.environ.get('PATH','')
        OUT.mkdir(parents=True,exist_ok=True)
        source=(ROOT/'src/dolphin_network.cpp').read_text()
        source='\n'.join(l for l in source.splitlines() if not l.startswith('#include <Dolphin/'))
        source=source.replace('State &s=*reinterpret_cast<State *>(TW_DOLPHIN_LIVE_BASE);','State s;')
        source += '\n' + (ROOT/'src/dolphin_dns.cpp').read_text()
        tcp=(ROOT/'native/dolphin_https/tcp.cpp').read_text()
        tcp='\n'.join(l for l in tcp.splitlines() if not l.startswith('#include <Dolphin/'))
        tcp=tcp.replace('Work &s = *reinterpret_cast<Work *>(SUSAMUNE_DOLPHIN_TCP_STATE_PPC_BASE);','Work s;')
        source += '\n' + tcp + '\n' + '\n'.join(l for l in (ROOT/'src/dolphin_tcp.cpp').read_text().splitlines() if not l.startswith('#include <Dolphin/'))
        shim='''#include <cstring>
#define OS_BUS_CLOCK 162000000u
#define OS_TIMER_CLOCK OS_BUS_CLOCK / 4
static unsigned now=100;
static unsigned long long OSGetTime(){return (unsigned long long)now*OS_TIMER_CLOCK;}
static unsigned OSGetTick(){return (unsigned)OSGetTime();}
static unsigned char incoming[1536],outgoing[1536];
static unsigned inBytes,outBytes,frameCount;
static unsigned char sentFrames[128][1536];
static unsigned sentSizes[128];
extern "C" { alignas(32) unsigned char moonshine_tcp_heap[32768]; }
namespace DolphinBba {
bool init(unsigned char *p){const unsigned char m[]={2,1,2,3,4,5};memcpy(p,m,6);return true;}
bool send(const unsigned char *p,unsigned n){memcpy(outgoing,p,n);outBytes=n;if(frameCount<128){memcpy(sentFrames[frameCount],p,n);sentSizes[frameCount++]=n;}return true;}
unsigned receive(unsigned char *p,unsigned cap){unsigned n=inBytes;if(n>cap)return 0;memcpy(p,incoming,n);inBytes=0;return n;}
}
'''+source+'''
extern "C" {
__declspec(dllexport) void reset(){LiveTransport::stop();DolphinNetwork::initialized=false;now=100;inBytes=outBytes=frameCount=0;LiveTransport::poll();}
__declspec(dllexport) int start(){return LiveTransport::begin(48222);}
__declspec(dllexport) unsigned poll(){return LiveTransport::poll().state;}
__declspec(dllexport) void tick(unsigned n){now+=n;}
__declspec(dllexport) unsigned xid(){return DolphinNetwork::s.transaction;}
__declspec(dllexport) int resolve(const char *p){
 if(!DolphinNetwork::s.resolver)return false;
 const bool ok=DolphinNetwork::resolve(p,DolphinNetwork::s.resolver);
 if(ok)DolphinNetwork::s.dns.tcp=0;
 return ok;
}
__declspec(dllexport) int resolveTcp(const char *p){return DolphinNetwork::resolve(p,DolphinNetwork::s.resolver);}
__declspec(dllexport) int tcpConnect(unsigned ip,unsigned short port){return DolphinTcp::connect(ip,port);}
__declspec(dllexport) int tcpSend(const void *p,unsigned n){return DolphinTcp::send(p,n);}
__declspec(dllexport) int tcpRead(void *p,unsigned n){return DolphinTcp::read(p,n);}
__declspec(dllexport) unsigned tcpState(){return DolphinTcp::state();}
__declspec(dllexport) void clearFrames(){frameCount=0;}
__declspec(dllexport) unsigned frames(){return frameCount;}
__declspec(dllexport) unsigned frame(unsigned i,void *p){if(i>=frameCount)return 0;memcpy(p,sentFrames[i],sentSizes[i]);return sentSizes[i];}
__declspec(dllexport) unsigned dnsState(){return DolphinNetwork::dnsResult().state;}
__declspec(dllexport) unsigned dnsAddress(){return DolphinNetwork::dnsResult().address;}
__declspec(dllexport) int dnsError(){return DolphinNetwork::dnsResult().error;}
__declspec(dllexport) void dnsCancel(){DolphinNetwork::cancelResolve();}
__declspec(dllexport) unsigned dnsId(){return DolphinNetwork::s.dns.id;}
__declspec(dllexport) unsigned dnsPort(){return DolphinNetwork::s.dns.port;}
__declspec(dllexport) unsigned dnsQuery(const char *p,void *out){return DolphinDns::query((unsigned char *)out,272,p,123);}
__declspec(dllexport) unsigned dnsParse(const void *p,unsigned bytes){unsigned address=0;return DolphinDns::answer((const unsigned char *)p,bytes,"ghosts.example",123,&address);}
__declspec(dllexport) void stop(){LiveTransport::stop();}
__declspec(dllexport) void feed(const void *p,unsigned n){if(n<=sizeof(incoming)){memcpy(incoming,p,n);inBytes=n;}}
__declspec(dllexport) unsigned output(void *p){memcpy(p,outgoing,outBytes);return outBytes;}
__declspec(dllexport) unsigned take(void *p){LiveTransport::Packet packet;if(!LiveTransport::receive(packet))return 0;memcpy(p,packet.data,packet.bytes);return packet.bytes;}
__declspec(dllexport) int send(const void *p,unsigned n){LiveTransport::Endpoint e={{8,8,8,8},12345,0};return LiveTransport::sendControl(e,p,n);}
}
'''
        (OUT/'shim.cpp').write_text(shim)
        includes=['-I'+str(ROOT/p) for p in ('include','include/susamune/lwip_port','vendor/lwip/src/include')]
        defines=['-DIS_EMULATOR=1','-DTIMEWARP_LIVE_RACING=1','-DMOONSHINE_LWIP_HOST_TEST=1','-DMOONSHINE_LWIP_NATIVE_CORE=1']
        objects=[]
        for sourcefile in sorted((ROOT/'src').glob('dolphin_lwip_*.cpp')):
            obj=OUT/(sourcefile.stem+'.o')
            subprocess.run(['C:/msys64/mingw64/bin/gcc.exe','-x','c','-std=c99','-O2',*includes,*defines,
                '-c',str(sourcefile),'-o',str(obj)],check=True)
            objects.append(str(obj))
        subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-shared','-static','-O2','-std=c++17',
            *includes,*defines,str(OUT/'shim.cpp'),*objects,'-o',str(OUT/'test.dll')],check=True)
        cls.lib=C.CDLL(str(OUT/'test.dll'))
        cls.lib.xid.restype=C.c_uint
        cls.lib.resolve.argtypes=[C.c_char_p]
        cls.lib.resolveTcp.argtypes=[C.c_char_p]
        cls.lib.tcpConnect.argtypes=[C.c_uint,C.c_ushort]
        for name in ('tcpSend','tcpRead'):getattr(cls.lib,name).argtypes=[C.c_void_p,C.c_uint]
        cls.lib.frame.argtypes=[C.c_uint,C.c_void_p]
        cls.lib.dnsQuery.argtypes=[C.c_char_p,C.c_void_p]
        cls.lib.dnsParse.argtypes=[C.c_void_p,C.c_uint]
        cls.lib.dnsAddress.restype=C.c_uint
        for name in ('feed','send'):getattr(cls.lib,name).argtypes=[C.c_void_p,C.c_uint]
    def setUp(self):self.lib.reset()
    def feed(self,frame):self.lib.feed(bytes(frame),len(frame));return self.lib.poll()
    def output(self):
        out=C.create_string_buffer(1536);n=self.lib.output(out);return out.raw[:n]
    def reply(self,kind,extra=b''):
        p=bytearray(240);p[:3]=b'\x02\x01\x06';struct.pack_into('>I',p,4,self.lib.xid());p[16:20]=IP;p[28:34]=MAC
        p[236:]=b'\x63\x82\x53\x63'
        p.extend(bytes([53,1,kind,54,4])+SERVER+bytes([1,4,255,255,255,0,3,4])+SERVER+extra+b'\xff')
        return udp(p,sport=67,dport=68)
    def ready(self,dns=True):
        self.assertTrue(self.lib.start());self.assertEqual(self.lib.poll(),2)
        self.assertEqual(self.feed(self.reply(2)),2)
        self.assertEqual(self.feed(self.reply(5,bytes([6,4])+SERVER if dns else b'')),3)
    def test_dhcp_offer_ack_and_valid_udp(self):
        self.ready();self.feed(udp(b'hello'))
        out=C.create_string_buffer(256)
        self.assertEqual(self.lib.take(out),5);self.assertEqual(out.raw[:5],b'hello')
        self.assertEqual(self.lib.take(out),0)
    def test_wrong_dhcp_transaction_cannot_set_address(self):
        self.lib.start();self.lib.poll();p=bytearray(self.reply(2));p[46]^=1
        self.assertEqual(self.feed(p),2)
        self.assertEqual(self.feed(self.reply(5)),2)
        self.lib.tick(31);self.assertEqual(self.lib.poll(),5)
    def test_bad_checksums_fragments_and_oversized_payload_rejected(self):
        self.ready();out=C.create_string_buffer(256)
        bad=bytearray(udp(b'hello'));bad[-1]^=1
        for frame in (bad,udp(b'hello',fragment=0x2000),udp(b'hello',fragment=1),udp(b'x'*257),udp(b'',dport=1)):
            self.feed(bytes(frame));self.assertEqual(self.lib.take(out),0)
        self.feed(udp(b'x'*256));self.assertEqual(self.lib.take(out),256)
    def test_native_send_emits_valid_udp_with_same_bytes(self):
        self.ready();p=b'payload';self.assertTrue(self.lib.send(p,len(p)))
        frame=self.output();self.assertEqual(frame[:6],ROUTER);self.assertEqual(frame[42:49],p)
        self.assertEqual(check(frame[14:34]),0)
        self.assertEqual(check(frame[26:34]+b'\x00\x11'+frame[38:40]+frame[34:49]),0)
    def test_shared_bus_wait_does_not_replace_pending_packet(self):
        self.ready();self.feed(udp(b'first'));self.feed(udp(b'second'))
        out=C.create_string_buffer(256)
        self.assertEqual(self.lib.take(out),5);self.assertEqual(out.raw[:5],b'first')
        self.assertEqual(self.lib.take(out),6);self.assertEqual(out.raw[:6],b'second')

    def dns_ready(self):
        self.ready();self.assertTrue(self.lib.resolve(b'ghosts.example'))
        self.assertEqual(self.lib.dnsState(),1)
    def dns_reply(self,answers=None,question=b'\x06ghosts\x07example\x00',flags=0x8180,ident=None,count=None):
        if answers is None:answers=b'\xc0\x0c'+struct.pack('>HHIH',1,1,60,4)+b'\x08\x08\x04\x04'
        ident=self.lib.dnsId() if ident is None else ident
        return struct.pack('>HHHHHH',ident,flags,1,1 if count is None else count,0,0)+question+b'\x00\x01\x00\x01'+answers
    def dns_feed(self,payload,source=SERVER,dport=None,sport=53):
        return self.feed(udp(payload,source=source,sport=sport,dport=self.lib.dnsPort() if dport is None else dport))
    def test_dns_queries_dhcp_resolver_on_separate_port(self):
        self.dns_ready();f=self.output()
        self.assertEqual(f[30:34],SERVER)
        self.assertNotEqual(struct.unpack('>H',f[34:36])[0],48222)
        self.assertEqual(struct.unpack('>H',f[36:38])[0],53)
        self.assertEqual(f[54:74],b'\x06ghosts\x07example\x00\x00\x01\x00\x01')
        self.dns_feed(self.dns_reply())
        self.assertEqual(self.lib.dnsState(),2);self.assertEqual(self.lib.dnsAddress(),0x08080404)
    def test_dns_response_must_match_endpoint_id_and_question(self):
        self.dns_ready()
        for p,kwargs in [(self.dns_reply(),dict(source=b'\x08\x08\x08\x08')),
                (self.dns_reply(),dict(sport=54)),(self.dns_reply(),dict(dport=48222)),
                (self.dns_reply(ident=self.lib.dnsId()^1),{}),
                (self.dns_reply(question=b'\x05other\x07example\x00'),{})]:
            self.dns_feed(p,**kwargs)
            out=C.create_string_buffer(256);self.lib.take(out)
            self.assertEqual(self.lib.dnsState(),1)
        self.dns_feed(self.dns_reply());self.assertEqual(self.lib.dnsState(),2)
    def test_dns_unrelated_address_not_accepted(self):
        self.dns_ready()
        a=b'\x05other\xc0\x13'+struct.pack('>HHIH',1,1,60,4)+b'\x08\x08\x04\x04'
        self.dns_feed(self.dns_reply(a));self.assertEqual(self.lib.dnsState(),3)
        self.assertEqual(self.lib.dnsAddress(),0)
    def test_dns_compressed_alias_chain_and_out_of_order_records(self):
        self.dns_ready()
        target=b'\x04edge\xc0\x13'
        a=target+struct.pack('>HHIH',1,1,60,4)+b'\x08\x08\x04\x04'
        alias=b'\xc0\x0c'+struct.pack('>HHIH',5,1,60,len(target))+target
        self.dns_feed(self.dns_reply(a+alias,count=2))
        self.assertEqual(self.lib.dnsState(),2);self.assertEqual(self.lib.dnsAddress(),0x08080404)
    def test_dns_rejects_pointer_cycles_truncated_records_and_bad_addresses(self):
        self.dns_ready()
        for answer in [b'\xc0\x20', b'\xc0\xff', b'\xc0\x0c'+struct.pack('>HHIH',1,1,60,0xffff),
                       b'\xc0\x0c'+struct.pack('>HHIH',1,1,60,4)+b'\xe0\x00\x00\x01']:
            self.dns_feed(self.dns_reply(answer));self.assertEqual(self.lib.dnsState(),1)
        good=self.dns_reply()[32:]
        self.dns_feed(self.dns_reply(good+b'\xc0',count=2));self.assertEqual(self.lib.dnsState(),1)
        self.dns_feed(self.dns_reply());self.assertEqual(self.lib.dnsState(),2)
    def test_dns_timeout_cancel_and_reopen_do_not_close_online(self):
        self.dns_ready();old=self.dns_reply()
        self.lib.tick(12);self.assertEqual(self.lib.dnsState(),3);self.assertEqual(self.lib.poll(),3)
        self.assertTrue(self.lib.resolve(b'ghosts.example'));self.dns_feed(old)
        self.assertEqual(self.lib.dnsState(),1)
        self.lib.dnsCancel();self.assertEqual(self.lib.dnsState(),0);self.assertEqual(self.lib.poll(),3)
        self.feed(udp(b'still online'));out=C.create_string_buffer(256)
        self.assertEqual(self.lib.take(out),12)
        self.lib.stop();self.assertEqual(self.lib.dnsState(),0)
    def test_dns_no_resolver_and_bad_names_fail_without_query(self):
        self.ready(dns=False);self.assertFalse(self.lib.resolve(b'ghosts.example'))
        out=C.create_string_buffer(272)
        for name in [b'',b'-bad.example',b'bad-.example',b'a..b',b'.',b'x'*64+b'.example',b'a/b.example',b'x.'*127+b'x']:
            self.assertEqual(self.lib.dnsQuery(name,out),0,name)
        name=b'a'*63+b'.'+b'b'*63+b'.'+b'c'*63+b'.'+b'd'*61
        self.assertEqual(len(name),253);self.assertEqual(self.lib.dnsQuery(name,out),271)
    def test_dns_truncation_and_negative_reply_are_explicit(self):
        self.dns_ready();self.dns_feed(self.dns_reply(b'',flags=0x8380,count=0))
        self.assertEqual(self.lib.dnsError(),-3)
        self.assertTrue(self.lib.resolve(b'ghosts.example'))
        self.dns_feed(self.dns_reply(b'',flags=0x8183,count=0));self.assertEqual(self.lib.dnsError(),-2)
    def test_dns_malformed_response_corpus_is_bounded(self):
        import random
        rng=random.Random(44)
        packet=self.dns_reply(ident=123)
        for n in range(len(packet)):
            self.assertEqual(self.lib.dnsParse(packet[:n],n),0)
        for _ in range(5000):
            p=bytearray(packet)
            for _ in range(rng.randrange(1,8)):p[rng.randrange(len(p))]=rng.randrange(256)
            self.assertIn(self.lib.dnsParse(bytes(p),len(p)),range(4))

    def tcp_frames(self):
        frames=[]
        for i in range(self.lib.frames()):
            b=C.create_string_buffer(1536);n=self.lib.frame(i,b);f=b.raw[:n]
            if len(f)>=54 and f[12:14]==b'\x08\x00' and f[23]==6:
                frames.append(f[:14+int.from_bytes(f[16:18],'big')])
        return frames
    def tcp_handshake(self,port=443,connect=True):
        self.lib.clearFrames()
        if connect:self.assertTrue(self.lib.tcpConnect(int.from_bytes(SERVER,'big'),port))
        else:self.lib.poll()
        syn=next(f for f in self.tcp_frames() if f[47]&2)
        self.localport=struct.unpack_from('>H',syn,34)[0];self.remoteport=port
        self.localnext=struct.unpack_from('>I',syn,38)[0]+1;self.remotenext=1001
        self.feed(tcp(sport=port,dport=self.localport,seq=1000,ack=self.localnext,flags=0x12))
        self.assertEqual(self.lib.tcpState(),2)
        return syn
    def tcp_packet(self,payload=b'',**kwargs):
        defaults=dict(sport=self.remoteport,dport=self.localport,seq=self.remotenext,ack=self.localnext)
        defaults.update(kwargs)
        return tcp(payload,**defaults)
    def test_tcp_sends_valid_checksums_and_handles_partial_reads(self):
        self.ready();self.tcp_handshake();self.lib.clearFrames()
        p=b'GET / HTTP/1.0\r\n\r\n';self.assertEqual(self.lib.tcpSend(p,len(p)),len(p))
        self.localnext+=len(p)
        f=next(f for f in self.tcp_frames() if len(f)>54)
        self.assertEqual(check(f[14:34]),0)
        self.assertEqual(check(f[26:34]+struct.pack('>BBH',0,6,len(f)-34)+f[34:]),0)
        self.assertEqual(f[54:],p)
        self.feed(self.tcp_packet(b'abcdef'))
        out=C.create_string_buffer(32)
        self.assertEqual(self.lib.tcpRead(out,2),2);self.assertEqual(out.raw[:2],b'ab')
        self.assertEqual(self.lib.tcpRead(out,32),4);self.assertEqual(out.raw[:4],b'cdef')
        self.assertEqual(self.lib.tcpRead(out,32),0)
    def test_tcp_out_of_order_duplicate_and_corrupt_packets(self):
        self.ready();self.tcp_handshake();out=C.create_string_buffer(32)
        self.feed(self.tcp_packet(b'def',seq=self.remotenext+3))
        self.assertEqual(self.lib.tcpRead(out,32),0)
        corrupt=bytearray(self.tcp_packet(b'abc'));corrupt[-1]^=1
        self.feed(corrupt);self.assertEqual(self.lib.tcpRead(out,32),0)
        self.feed(self.tcp_packet(b'abc',source=b'\x08\x08\x08\x08'))
        self.assertEqual(self.lib.tcpRead(out,32),0)
        self.feed(self.tcp_packet(b'abc'))
        self.assertEqual(self.lib.tcpRead(out,32),6);self.assertEqual(out.raw[:6],b'abcdef')
        self.feed(self.tcp_packet(b'abc'));self.assertEqual(self.lib.tcpRead(out,32),0)
    def test_tcp_fin_preserves_tail_and_can_reopen(self):
        self.ready();self.tcp_handshake()
        self.feed(self.tcp_packet(b'last',flags=0x19))
        self.assertEqual(self.lib.tcpState(),3);out=C.create_string_buffer(32)
        self.assertEqual(self.lib.tcpRead(out,32),4);self.assertEqual(out.raw[:4],b'last')
        self.assertEqual(self.lib.tcpRead(out,32),-1)
        self.tcp_handshake();self.feed(self.tcp_packet(b'new'))
        self.assertEqual(self.lib.tcpRead(out,32),3)
    def test_tcp_progresses_while_udp_packet_is_pending(self):
        self.ready();self.tcp_handshake();out=C.create_string_buffer(32)
        self.feed(udp(b'online'));self.feed(self.tcp_packet(b'web'))
        self.assertEqual(self.lib.tcpRead(out,32),3);self.assertEqual(out.raw[:3],b'web')
        self.assertEqual(self.lib.take(out),6);self.assertEqual(out.raw[:6],b'online')
    def test_tcp_send_window_bounds_memory(self):
        self.ready();self.tcp_handshake();p=b'x'*8192
        self.assertEqual(self.lib.tcpSend(p,len(p)),4096)
        self.assertEqual(self.lib.tcpSend(p,len(p)),0)
        self.localnext=max(int.from_bytes(f[38:42],'big')+len(f)-34-(f[46]>>4)*4
                           for f in self.tcp_frames() if len(f)>54 and not f[47]&2)
        self.feed(self.tcp_packet(flags=0x10))
        self.assertEqual(self.lib.tcpSend(p,16),16)
    def dns_tcp_start(self):
        self.assertTrue(self.lib.resolveTcp(b'ghosts.example'))
        self.tcp_handshake(53,False)
        self.lib.poll()
        query=next(f[54:] for f in self.tcp_frames() if len(f)>54 and not f[47]&2)
        self.assertEqual(int.from_bytes(query[:2],'big'),len(query)-2)
        self.localnext+=len(query)
    def test_dns_tcp_split_prefix_body_and_fin_then_reopen(self):
        self.ready()
        for _ in range(3):
            self.dns_tcp_start();answer=self.dns_reply();p=struct.pack('>H',len(answer))+answer
            for part in (p[:1],p[1:9],p[9:]):
                self.feed(self.tcp_packet(part,flags=0x19 if part==p[9:] else 0x18))
                self.remotenext+=len(part)
            self.assertEqual(self.lib.dnsState(),2);self.assertEqual(self.lib.dnsAddress(),0x08080404)
            self.assertEqual(self.lib.tcpState(),0);self.assertEqual(self.lib.poll(),3)
    def test_dns_tcp_refuses_oversized_body_and_timeout(self):
        self.ready();self.dns_tcp_start();self.feed(self.tcp_packet(b'\x02\x01'))
        self.assertEqual(self.lib.dnsState(),3);self.assertEqual(self.lib.tcpState(),0)
        self.dns_tcp_start();self.lib.tick(12);self.lib.poll()
        self.assertEqual(self.lib.dnsState(),3);self.assertEqual(self.lib.tcpState(),0)

if __name__=='__main__':unittest.main()
