"""Two actual session engines over a bounded fake datagram wire; no sockets."""
import ctypes as C
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
#define TIMEWARP_LIVE_RACING 1
#include "susamune/live_race_session.hxx"
extern "C" void *memcpy(void*d,const void*s,__SIZE_TYPE__ n){unsigned char*a=(unsigned char*)d;const unsigned char*b=(const unsigned char*)s;while(n--)*a++=*b++;return d;}
extern "C" void *memset(void*d,int c,__SIZE_TYPE__ n){unsigned char*a=(unsigned char*)d;while(n--)*a++=(unsigned char)c;return d;}
using namespace LiveRaceSession;
struct Node {Session session;unsigned id,block,poseBlock,controls,poses,lastKind,lastRound,lastSequence,lastBytes,lastPoseX;unsigned char lastData[64];};
struct Datagram {unsigned from,to,bytes;unsigned char data[96];};
static Node nodes[2];static Datagram packets[64];static unsigned count,violation;
static Endpoint endpoint(unsigned id){Endpoint p={{10,0,0,(unsigned char)(id+1)},(unsigned short)(3001+id),0};return p;}
static bool queue(Node*n,const Endpoint&to,const void*data,unsigned bytes,bool pose){
 if((pose?n->poseBlock:n->block)||count==64)return false;
 Endpoint expected=endpoint(1-n->id);
 if(bytes>96||to.port!=expected.port||to.ip[3]!=expected.ip[3]){++violation;return false;}
 Datagram&p=packets[count++];p.from=n->id;p.to=1-n->id;p.bytes=bytes;memcpy(p.data,data,bytes);return true;}
static bool control(void*c,const Endpoint&p,const void*d,unsigned n){return queue((Node*)c,p,d,n,false);}
static bool pose(void*c,const Endpoint&p,const void*d,unsigned n){return queue((Node*)c,p,d,n,true);}
static void receivedControl(void*c,const MSRHeader&h,const void*d,unsigned n){Node*x=(Node*)c;
 ++x->controls;x->lastKind=h.kind;x->lastRound=h.round;x->lastSequence=h.sequence;x->lastBytes=n;
 if(n>64){++violation;return;}memcpy(x->lastData,d,n);}
static void receivedPose(void*c,const MSRHeader&h,const MSRPose&p,unsigned now){(void)now;Node*x=(Node*)c;
 ++x->poses;x->lastSequence=h.sequence;x->lastRound=h.round;x->lastPoseX=(unsigned)p.x;}
#define API extern "C" __declspec(dllexport)
API void reset(unsigned hostRegion,unsigned guestRegion,unsigned hostPin,unsigned guestPin){
 memset(nodes,0,sizeof(nodes));count=violation=0;
 for(unsigned i=0;i<2;i++){Node&n=nodes[i];n.id=i;Config c={};
  const char*name=i?"PAL Guest":"JP Host";for(unsigned j=0;name[j];j++)c.name[j]=name[j];
  c.region=(unsigned char)(i?guestRegion:hostRegion);c.timing=1;c.pin=i?guestPin:hostPin;
  c.nonceHigh=0x11223344+i;c.nonceLow=0x55667788+i;
  Callbacks cb={&n,control,pose,receivedPose,receivedControl};init(n.session,c,cb);}}
API int start(unsigned now){Endpoint any={};return startHost(nodes[0].session,any,now)&&startGuest(nodes[1].session,endpoint(0),now);}
API void tickNode(unsigned id,unsigned now){tick(nodes[id].session,now);}
API void stopNode(unsigned id){stop(nodes[id].session);}
API void kickNode(unsigned id){kick(nodes[id].session);}
API unsigned wireCount(void){return count;}
API unsigned wireFrom(unsigned i){return packets[i].from;}
API unsigned wireBytes(unsigned i){return packets[i].bytes;}
API const void*wireData(unsigned i){return packets[i].data;}
API void drop(unsigned i){if(i>=count){++violation;return;}for(unsigned j=i+1;j<count;j++)packets[j-1]=packets[j];--count;}
API int inject(unsigned to,unsigned from,const void*d,unsigned bytes,unsigned now){return receivePacket(nodes[to].session,endpoint(from),d,bytes,now);}
API int deliver(unsigned i,unsigned now){if(i>=count){++violation;return 0;}Datagram p=packets[i];drop(i);return inject(p.to,p.from,p.data,p.bytes,now);}
API unsigned get(unsigned id,unsigned field){const Node&n=nodes[id];const Status&s=n.session.info;
 switch(field){case 0:return s.state;case 1:return s.error;case 2:return s.connected;
 case 3:return s.pending;case 4:return s.pingMs;case 5:return n.controls;case 6:return n.poses;
 case 7:return n.lastKind;case 8:return n.lastRound;case 9:return n.lastSequence;
 case 10:return n.session.sendSequence;case 11:return n.session.receiveSequence;
 case 12:return n.lastPoseX;case 13:return s.remoteRegion;case 14:return sizeof(Session);
 default:return violation;}}
API const char*name(unsigned id){return nodes[id].session.info.remoteName;}
API const void*lastData(unsigned id){return nodes[id].lastData;}
API void block(unsigned id,unsigned controls,unsigned poses){nodes[id].block=controls;nodes[id].poseBlock=poses;}
API int reliable(unsigned id,unsigned kind,const void*p,unsigned bytes,unsigned round){return sendReliable(nodes[id].session,kind,p,bytes,round);}
API int sendPose(unsigned id,int x,unsigned round){MSRPose p={};p.x=x;p.flags=1;p.area=2;p.episode=0;p.remoteMs=nodes[id].session.nowMs;
 return publishPose(nodes[id].session,p,round);}
API void seed(unsigned id,unsigned field,unsigned value){Session&s=nodes[id].session;
 switch(field){case 0:s.sendSequence=value;break;case 1:s.receiveSequence=value;break;case 2:s.poseSendSequence=value;break;}}
API int invalidConfig(unsigned field){Config c=nodes[0].session.config;Callbacks cb=nodes[0].session.callbacks;
 switch(field){case 0:c.name[0]='\n';break;case 1:c.name[3]=0;c.name[4]='x';break;case 2:c.region=3;break;
 case 3:c.timing=0;break;case 4:c.pin=1000000;break;case 5:c.nonceHigh=c.nonceLow=0;break;case 6:cb.sendControl=0;break;}
 return init(nodes[0].session,c,cb);}
'''


class LiveRaceSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / 'toolchain/clang++.exe'
        if not compiler.exists():
            raise unittest.SkipTest('Bundled native compiler required')
        output = ROOT / 'build/timewarp-session-spike-1'
        output.mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(prefix='host-', dir=output)
        cls.addClassCleanup(cls.temp.cleanup)
        path = Path(cls.temp.name)
        (path / 'harness.cpp').write_text(HARNESS)
        result = subprocess.run([str(compiler), '--target=x86_64-pc-windows-msvc', '-std=c++17',
            '-shared', '-O2', '-fno-builtin', '-fno-exceptions', '-fno-rtti', '-nostdlib',
            '-DTIMEWARP_LIVE_RACING=1', '-fuse-ld=lld', '-Xlinker', '/noentry',
            '-I', str(ROOT / 'include'), str(path / 'harness.cpp'),
            str(ROOT / 'src/live_race_session.cpp'), '-o', str(path / 'test.dll')],
            text=True, capture_output=True, env={**os.environ, 'TEMP': str(path), 'TMP': str(path)})
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        cls.lib = C.CDLL(str(path / 'test.dll'))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.wireData.restype = cls.lib.lastData.restype = C.c_void_p
        cls.lib.name.restype = C.c_char_p
        cls.lib.get.restype = C.c_uint
        cls.lib.inject.argtypes = [C.c_uint, C.c_uint, C.c_char_p, C.c_uint, C.c_uint]
        cls.lib.reliable.argtypes = [C.c_uint, C.c_uint, C.c_char_p, C.c_uint, C.c_uint]

    def setUp(self):
        self.lib.reset(0, 2, 123456, 123456)

    def tearDown(self):
        self.assertEqual(self.lib.get(0, 99), 0)

    def packet(self, i):
        return C.string_at(self.lib.wireData(i), self.lib.wireBytes(i))

    def inject(self, to, sender, data, now=1):
        return self.lib.inject(to, sender, data, len(data), now)

    def find(self, kind, sender=None):
        for i in range(self.lib.wireCount()):
            if self.packet(i)[6] == kind and (sender is None or self.lib.wireFrom(i) == sender):
                return i
        self.fail(f'No queued kind {kind}, sender {sender}')

    def pump(self, now=1):
        for _ in range(64):
            if not self.lib.wireCount():
                return
            self.lib.deliver(0, now)
        self.fail('Unbounded fake wire exchange')

    def connect(self, now=0):
        self.assertEqual(self.lib.start(now), 1)
        self.pump(now)
        self.assertEqual((self.lib.get(0, 2), self.lib.get(1, 2)), (1, 1))

    def reliable(self, sender=0, kind=7, data=b'ready', round=4):
        return self.lib.reliable(sender, kind, data, len(data), round)

    def test_jp_pal_handshake_nonce_binding_names_ping_and_budget(self):
        self.connect()
        self.assertEqual((self.lib.get(0, 13), self.lib.get(1, 13)), (2, 0))
        self.assertEqual(self.lib.name(0), b'PAL Guest')
        self.assertEqual(self.lib.name(1), b'JP Host')
        self.assertLess(self.lib.get(0, 14), 2048)
        self.lib.tickNode(0, 100)
        ping = self.find(4, 0)
        self.assertEqual(self.lib.deliver(ping, 140), 1)
        pong = self.find(5, 1)
        self.assertEqual(self.lib.deliver(pong, 180), 1)
        self.assertEqual(self.lib.get(0, 4), 80)

    def test_lost_probe_does_not_add_retry_time_to_ping(self):
        self.connect()
        self.lib.tickNode(0, 100)
        self.lib.drop(self.find(4, 0))
        self.lib.tickNode(0, 1100)
        self.assertEqual(self.lib.deliver(self.find(4, 0), 1140), 1)
        self.assertEqual(self.lib.deliver(self.find(5, 1), 1180), 1)
        self.assertEqual(self.lib.get(0, 4), 80)

    def test_delayed_probe_still_measures_rtt_and_older_reply_cannot_overwrite_it(self):
        self.connect()
        self.lib.tickNode(0, 100)
        old = self.packet(self.find(4, 0))
        self.lib.drop(self.find(4, 0))
        self.lib.tickNode(0, 1100)
        self.assertEqual(self.inject(1, 0, old, 1200), 1)
        self.assertEqual(self.lib.deliver(self.find(5, 1), 1300), 1)
        self.assertEqual(self.lib.get(0, 4), 1200)
        self.assertEqual(self.lib.deliver(self.find(4, 0), 1320), 1)
        self.assertEqual(self.lib.deliver(self.find(5, 1), 1340), 1)
        self.assertEqual(self.lib.get(0, 4), 240)
        self.assertEqual(self.inject(1, 0, old, 1400), 1)
        self.assertEqual(self.lib.deliver(self.find(5, 1), 1420), 0)
        self.assertEqual(self.lib.get(0, 4), 240)

    def test_handshake_rejects_wrong_pin_region_timing_role_endpoint_and_nonce(self):
        self.assertEqual(self.lib.start(0), 1)
        hello = self.packet(0)
        for offset in (5, 28, 29, 30, 32):
            bad = bytearray(hello)
            bad[offset] = 3 if offset == 28 else bad[offset] ^ 1
            self.assertEqual(self.inject(0, 1, bytes(bad)), 0)
        self.assertEqual(self.lib.get(0, 0), 1)
        self.assertEqual(self.lib.deliver(0, 1), 1)
        offer = self.packet(self.find(2, 0))
        self.assertEqual(self.inject(1, 2, offer), 0)
        bad = bytearray(offer); bad[32] ^= 1
        self.assertEqual(self.inject(1, 0, bytes(bad)), 0)
        self.assertEqual(self.lib.get(1, 2), 0)
        self.pump()
        self.assertEqual(self.lib.get(0, 2), 1)
        for field in range(7):
            self.lib.reset(0, 2, 123456, 123456)
            self.assertEqual(self.lib.invalidConfig(field), 0)
            self.assertEqual(self.lib.get(0, 1), 1)

    def test_lost_handshake_ack_recovers_without_early_host_pose_acceptance(self):
        self.assertEqual(self.lib.start(0), 1)
        self.lib.deliver(0, 1)
        self.lib.deliver(0, 2)
        self.lib.drop(self.find(10, 1))
        self.assertEqual(self.lib.get(0, 2), 0)
        self.assertEqual(self.lib.sendPose(1, 80, 0), 1)
        self.assertEqual(self.lib.deliver(self.find(3, 1), 3), 0)
        self.lib.tickNode(0, 1001)
        self.pump(1001)
        self.assertEqual(self.lib.get(0, 2), 1)
        self.assertEqual(self.lib.sendPose(1, 88, 0), 1)
        self.pump(1002)
        self.assertEqual(self.lib.get(0, 6), 1)

    def test_reliable_controls_deliver_once_with_lost_duplicate_and_reordered_acks(self):
        self.connect()
        self.assertEqual(self.reliable(), 1)
        first = self.packet(self.find(7, 0))
        self.lib.deliver(self.find(7, 0), 10)
        old_ack = self.packet(self.find(10, 1))
        self.lib.drop(self.find(10, 1))
        self.assertEqual(self.reliable(kind=8), 0)
        self.lib.tickNode(0, 260)
        self.lib.deliver(self.find(7, 0), 261)
        self.assertEqual(self.inject(1, 0, first, 262), 1)
        self.assertEqual(self.lib.get(1, 5), 1)
        self.lib.deliver(self.find(10, 1), 263)
        self.assertEqual(self.lib.get(0, 3), 0)
        self.assertEqual(self.reliable(kind=9, data=b'finish', round=5), 1)
        self.assertEqual(self.inject(0, 1, old_ack, 264), 0)
        self.assertEqual(self.lib.get(0, 3), 1)
        self.pump(265)
        self.assertEqual(self.lib.get(1, 5), 2)
        self.assertEqual((self.lib.get(1, 7), self.lib.get(1, 8)), (9, 5))
        self.assertEqual(C.string_at(self.lib.lastData(1), 6), b'finish')
        self.assertEqual(self.lib.get(0, 3), 0)

    def test_queue_full_does_not_advance_sender_and_delayed_ack_is_retried(self):
        self.connect()
        self.lib.block(0, 1, 1)
        self.assertEqual(self.reliable(), 0)
        self.assertEqual((self.lib.get(0, 3), self.lib.get(0, 10)), (0, 1))
        self.assertEqual(self.lib.sendPose(0, 10, 0), 0)
        self.lib.block(0, 0, 0)
        self.assertEqual(self.reliable(), 1)
        self.lib.block(1, 1, 0)
        self.lib.deliver(self.find(7, 0), 1)
        self.assertEqual(self.lib.get(1, 5), 1)
        self.assertEqual(self.lib.get(0, 3), 1)
        self.lib.tickNode(0, 250)
        self.lib.deliver(self.find(7, 0), 251)
        self.assertEqual(self.lib.get(1, 5), 1)
        self.lib.block(1, 0, 0)
        self.lib.tickNode(1, 252)
        self.pump(253)
        self.assertEqual(self.lib.get(0, 3), 0)
        self.assertEqual(self.reliable(0, 8, b'host'), 1)
        self.assertEqual(self.reliable(1, 7, b'guest'), 1)
        self.pump(254)
        self.assertEqual((self.lib.get(0, 5), self.lib.get(1, 5)), (1, 2))

    def test_independent_pose_and_control_sequence_wrap_and_session_validation(self):
        self.connect()
        self.lib.seed(0, 0, 0xffffffff)
        self.lib.seed(1, 1, 0xffffffff)
        for sequence in (0xffffffff, 0):
            self.assertEqual(self.reliable(), 1)
            self.pump()
            self.assertEqual(self.lib.get(1, 9), sequence)
        self.lib.seed(0, 2, 0xfffffffe)
        last = None
        for x, sequence in zip((16, 24, 32), (0xfffffffe, 0xffffffff, 0)):
            self.assertEqual(self.lib.sendPose(0, x, 7), 1)
            i = self.find(3, 0)
            last = self.packet(i)
            self.lib.deliver(i, 2)
            self.assertEqual(self.lib.get(1, 9), sequence)
        self.assertEqual(self.inject(1, 0, last, 3), 0)
        self.assertEqual(self.lib.get(1, 6), 3)
        self.assertEqual(self.lib.sendPose(0, 40, 7), 1)
        fresh = self.packet(self.find(3, 0))
        for offset in (16, 28, 29, 30, 32 + 26):
            bad = bytearray(fresh); bad[offset] ^= 0x80
            self.assertEqual(self.inject(1, 0, bytes(bad), 4), 0)
        self.assertEqual(self.inject(1, 2, fresh, 4), 0)
        self.assertEqual(self.inject(1, 0, fresh, 4), 1)
        self.assertEqual(self.lib.get(1, 12), 40)

    def test_host_kick_retries_loss_and_guest_cannot_kick_host(self):
        self.connect()
        self.lib.kickNode(1)
        self.assertEqual(self.lib.get(1, 2), 1)
        self.lib.kickNode(0)
        first = self.find(6, 0)
        self.assertEqual(self.packet(first)[32:], b'\x01')
        self.lib.drop(first)
        self.lib.tickNode(0, 300)
        self.lib.deliver(self.find(6, 0), 301)
        self.assertEqual((self.lib.get(1, 1), self.lib.get(1, 2)), (6, 0))
        self.lib.tickNode(0, 3100)
        self.assertEqual(self.lib.get(0, 0), 0)

    def test_handshake_peer_and_reliable_timeouts_across_clock_wrap(self):
        self.lib.reset(0, 2, 123456, 999999)
        self.assertEqual(self.lib.start(0xfffff000), 1)
        self.pump(0xfffff000)
        self.lib.tickNode(0, (0xfffff000 + 30000) & 0xffffffff)
        self.lib.tickNode(1, (0xfffff000 + 30000) & 0xffffffff)
        self.assertEqual((self.lib.get(0, 1), self.lib.get(1, 1)), (2, 2))
        self.lib.reset(0, 2, 123456, 123456)
        self.connect(0xfffff000)
        # The peer timeout is 15 s so a long load on the other Wii does not drop the link.
        self.lib.tickNode(0, (0xfffff000 + 14999) & 0xffffffff)
        self.assertNotEqual(self.lib.get(0, 1), 3)
        self.lib.tickNode(0, (0xfffff000 + 15000) & 0xffffffff)
        self.assertEqual(self.lib.get(0, 1), 3)
        self.lib.reset(0, 2, 123456, 123456)
        self.connect()
        self.assertEqual(self.reliable(), 1)
        for now in range(1000, 15001, 1000):
            self.lib.tickNode(1, now)
            while self.lib.wireCount():
                i = 0
                if self.packet(i)[6] in (7, 10):
                    self.lib.drop(i)
                else:
                    self.lib.deliver(i, now)
            self.lib.tickNode(0, now)
        self.assertEqual(self.lib.get(0, 1), 4)
        self.assertEqual(self.lib.get(0, 2), 0)


if __name__ == '__main__':
    unittest.main()
