"""Actual heapless relay/session clients against the deployable Python relay."""
import ctypes as C
import importlib.util
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('moonshine_relay', ROOT / 'tools/live_relay/server.py')
relay = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = relay
spec.loader.exec_module(relay)

HARNESS = r'''
#define TIMEWARP_LIVE_RACING 1
#include "susamune/live_relay.hxx"
#include "susamune/live_race_session.hxx"
extern "C" void *memcpy(void*d,const void*s,__SIZE_TYPE__ n){unsigned char*a=(unsigned char*)d;const unsigned char*b=(const unsigned char*)s;while(n--)*a++=*b++;return d;}
extern "C" void *memset(void*d,int c,__SIZE_TYPE__ n){unsigned char*a=(unsigned char*)d;while(n--)*a++=(unsigned char)c;return d;}
typedef TWLiveEndpoint Endpoint;
struct Node {LiveRelay::Client relay;LiveRaceSession::Session session;unsigned id,poses,now,started;};
struct Datagram {unsigned from,bytes;unsigned char data[256];};
static Node nodes[2];static Datagram packets[256];static unsigned count,violations;
static Endpoint server={{192,0,2,1},38400,0};
static bool queue(void*context,const Endpoint&e,const void*data,unsigned bytes){
 Node*n=(Node*)context;if(count==256)return false;
 if(bytes>256||e.port!=38400||e.ip[0]!=192||e.ip[3]!=1){++violations;return false;}
 Datagram&p=packets[count++];p.from=n->id;p.bytes=bytes;memcpy(p.data,data,bytes);return true;}
static bool control(void*context,const Endpoint&,const void*d,unsigned bytes){return LiveRelay::sendControl(((Node*)context)->relay,d,bytes);}
static bool pose(void*context,const Endpoint&,const void*d,unsigned bytes){return LiveRelay::sendPose(((Node*)context)->relay,d,bytes);}
static void onPose(void*context,const MSRHeader&,const MSRPose&,unsigned){++((Node*)context)->poses;}
static void onControl(void*,const MSRHeader&,const void*,unsigned){}
static void ensure(Node&n){if(n.started||!n.relay.info.peerReady)return;
 LiveRaceSession::Config config={};config.name[0]=n.id?'P':'J';config.pin=n.relay.info.roomCode;
 config.region=n.id?2:0;config.timing=1;config.nonceHigh=0xabcdef00+n.id;config.nonceLow=0x12345678;
 LiveRaceSession::Callbacks cb={&n,control,pose,onPose,onControl};LiveRaceSession::init(n.session,config,cb);
 n.started=1;if(n.id)LiveRaceSession::startGuest(n.session,server,n.now);else LiveRaceSession::startHost(n.session,server,n.now);}
static void incoming(void*context,const void*d,unsigned bytes,unsigned now){Node&n=*(Node*)context;n.now=now;ensure(n);
 if(!n.relay.info.peerReady||!n.started){++violations;return;}LiveRaceSession::receivePacket(n.session,server,d,bytes,now);}
#define API extern "C" __declspec(dllexport)
API void reset(){memset(nodes,0,sizeof(nodes));count=violations=0;}
API int start(unsigned id,unsigned room,unsigned now){Node&n=nodes[id];n.id=id;n.now=now;
 LiveRelay::Callbacks cb={&n,queue,queue,incoming};LiveRelay::init(n.relay,cb);
 return LiveRelay::begin(n.relay,id==0,room,0x11223344,0x12340000+id,server,now);}
API void tick(unsigned id,unsigned now){Node&n=nodes[id];n.now=now;LiveRelay::tick(n.relay,now);ensure(n);if(n.started)LiveRaceSession::tick(n.session,now);}
API int inject(unsigned id,const void*d,unsigned bytes,unsigned now,unsigned wrongEndpoint){
 Node&n=nodes[id];n.now=now;Endpoint e=server;if(wrongEndpoint)e.port++;
 bool ok=LiveRelay::receive(n.relay,e,d,bytes,now);ensure(n);return ok;}
API unsigned queued(){return count;}
API unsigned from(unsigned i){return packets[i].from;}
API unsigned bytes(unsigned i){return packets[i].bytes;}
API const void*data(unsigned i){return packets[i].data;}
API void drop(unsigned i){for(unsigned j=i+1;j<count;j++)packets[j-1]=packets[j];--count;}
API void stop(unsigned id){LiveRelay::stop(nodes[id].relay);}
API int sendPose(unsigned id){MSRPose p={};p.flags=1;p.x=80;p.remoteMs=nodes[id].now;
 return LiveRaceSession::publishPose(nodes[id].session,p,1);}
API unsigned get(unsigned id,unsigned field){Node&n=nodes[id];switch(field){
 case 0:return n.relay.info.state;case 1:return n.relay.info.error;case 2:return n.relay.info.roomCode;
 case 3:return n.relay.info.peerReady;case 4:return n.session.info.connected;
 case 5:return n.session.info.remoteRegion;case 6:return n.poses;case 7:return sizeof(LiveRelay::Client);
 default:return violations;}}
'''


class RelayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        output = ROOT / 'build/timewarp-live-relay-1'
        output.mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(prefix='host-', dir=output)
        cls.addClassCleanup(cls.temp.cleanup)
        path = Path(cls.temp.name)
        (path / 'harness.cpp').write_text(HARNESS)
        result = subprocess.run([str(ROOT / 'toolchain/clang++.exe'), '--target=x86_64-pc-windows-msvc',
            '-std=c++17', '-shared', '-O2', '-fno-builtin', '-fno-exceptions', '-fno-rtti', '-nostdlib',
            '-DTIMEWARP_LIVE_RACING=1', '-fuse-ld=lld', '-Xlinker', '/noentry', '-I', str(ROOT / 'include'),
            str(path / 'harness.cpp'), str(ROOT / 'src/live_relay.cpp'), str(ROOT / 'src/live_race_session.cpp'),
            '-o', str(path / 'test.dll')], text=True, capture_output=True,
            env={**os.environ, 'TEMP': str(path), 'TMP': str(path)})
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        cls.lib = C.CDLL(str(path / 'test.dll'))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.data.restype = C.c_void_p
        cls.lib.inject.argtypes = [C.c_uint, C.c_char_p, C.c_uint, C.c_uint, C.c_uint]

    def setUp(self):
        self.lib.reset()
        self.server = relay.Relay(secret=b'x' * 32)
        self.endpoints = [('198.51.100.1', 31000), ('203.0.113.1', 32000)]
        self.now = 100

    def tearDown(self):
        self.assertEqual(self.lib.get(0, 99), 0)

    def take(self, index=0):
        item = (getattr(self.lib, 'from')(index),
                C.string_at(self.lib.data(index), self.lib.bytes(index)))
        self.lib.drop(index)
        return item

    def deliver(self, response, wrong=0):
        endpoint, data = response
        return self.lib.inject(self.endpoints.index(endpoint), data, len(data), self.now, wrong)

    def pump(self, drop_kind=None):
        for _ in range(100):
            if not self.lib.queued():
                return
            sender, data = self.take()
            for response in self.server.handle(data, self.endpoints[sender], self.now / 1000):
                if relay.Packet.decode(response[1]).kind != drop_kind:
                    self.deliver(response)
        self.fail('unexpected protocol loop')

    def advance(self, ms):
        self.now += ms
        for i in range(2):
            self.lib.tick(i, self.now)
        for response in self.server.sweep(self.now / 1000):
            self.deliver(response)
        self.pump()

    def connect(self):
        self.assertTrue(self.lib.start(0, 0, self.now))
        self.pump()
        code = self.lib.get(0, 2)
        self.assertTrue(100000 <= code <= 999999)
        self.assertEqual(self.lib.get(0, 0), 3)
        self.assertTrue(self.lib.start(1, code, self.now))
        self.pump()
        self.advance(1)
        self.assertTrue(self.lib.get(0, 4) and self.lib.get(1, 4))
        return code

    def test_actual_jp_pal_sessions_and_latest_pose(self):
        self.connect()
        self.assertEqual(self.lib.get(0, 5), 2)
        self.assertEqual(self.lib.get(1, 5), 0)
        for i in range(2):
            self.assertTrue(self.lib.sendPose(i))
        self.pump()
        self.assertEqual([self.lib.get(i, 6) for i in range(2)], [1, 1])
        self.assertLessEqual(self.lib.get(0, 7), 192)

    def test_lost_welcome_duplicate_proof_and_long_lobby(self):
        self.lib.start(0, 0, self.now)
        self.pump(drop_kind=relay.WELCOME)
        original = next(iter(self.server.rooms))
        self.assertEqual(self.lib.get(0, 0), 2)
        self.advance(500)
        self.assertEqual(self.lib.get(0, 2), original)
        self.assertEqual(len(self.server.rooms), 1)
        for _ in range(125):
            self.advance(1000)
        self.assertEqual(self.lib.get(0, 0), 3)
        self.assertEqual(len(self.server.members), 1)

    def test_ready_reordering_data_before_status_and_stale_waiting(self):
        self.lib.start(0, 0, self.now)
        self.pump()
        host = next(iter(self.server.members.values()))
        stale = (host.endpoint, self.server._packet(host, relay.STATUS).encode())
        self.lib.start(1, host.room, self.now)
        # Hold the host's readiness notification; the guest's HELLO must promote it.
        self.pump(drop_kind=relay.STATUS)
        self.assertTrue(self.lib.get(0, 3))
        self.assertTrue(self.lib.get(0, 4) and self.lib.get(1, 4))
        self.deliver(stale)
        self.assertEqual(self.lib.get(0, 0), 4)

    def test_wrong_room_and_proof_cannot_reflect_to_third_party(self):
        self.lib.start(1, 123456, self.now)
        sender, opening = self.take()
        challenge = self.server.handle(opening, self.endpoints[sender], self.now / 1000)[0]
        self.assertEqual(len(challenge[1]), len(opening))
        self.deliver(challenge)
        _, proof = self.take()
        self.assertEqual(self.server.handle(proof, ('203.0.113.99', 40000), self.now / 1000), [])
        self.assertEqual(len(self.server.members), 0)
        for response in self.server.handle(proof, self.endpoints[1], self.now / 1000):
            self.deliver(response)
        self.assertEqual(self.lib.get(1, 1), relay.NO_ROOM)

    def test_credentials_generation_endpoint_and_lengths_checked(self):
        self.connect()
        self.lib.sendPose(0)
        _, packet = self.take()
        for offset in (7, 20, 36, 46, 48 + 30):
            forged = bytearray(packet)
            forged[offset] ^= 1
            self.assertEqual(self.server.handle(bytes(forged), self.endpoints[0], self.now / 1000), [])
        self.assertEqual(self.server.handle(packet, self.endpoints[1], self.now / 1000), [])
        response = self.server.handle(packet, self.endpoints[0], self.now / 1000)[0]
        self.assertFalse(self.deliver(response, wrong=1))
        for size in (0, 47, len(response[1]) - 1):
            self.assertFalse(self.deliver((response[0], response[1][:size])))
        self.assertTrue(self.deliver(response))

    def test_disconnect_terminal_room_and_old_proof(self):
        code = self.connect()
        host = next(m for m in self.server.members.values() if m.host)
        request = relay.Packet(relay.PROVE, relay.HOST, 0, host.nonce)
        proof = relay.Packet(relay.PROVE, relay.HOST, 0, host.nonce,
                             self.server._cookie(host.endpoint, request, 0)).encode()
        self.lib.stop(1)
        self.pump()
        self.assertEqual(self.lib.get(0, 1), relay.PEER_LEFT)
        self.assertNotIn(code, self.server.rooms)
        retry = self.server.handle(proof, host.endpoint, self.now / 1000)
        self.assertEqual(relay.Packet.decode(retry[0][1]).payload, struct.pack('!I', relay.ROOM_CLOSED))
        self.assertEqual(len(self.server.rooms), 0)

    def test_timeout_and_bounded_server(self):
        self.connect()
        self.now += 15000
        self.lib.tick(0, self.now)
        self.assertEqual(self.lib.get(0, 1), 2)
        closed = self.server.sweep(self.now / 1000)
        self.assertEqual(len(closed), 2)
        self.assertEqual(len(self.server.rooms), 0)
        self.server.MAX_ROOMS = 0
        p = relay.Packet(relay.PROVE, relay.HOST, 0, 999)
        p = relay.Packet(relay.PROVE, relay.HOST, 0, 999,
                         self.server._cookie(self.endpoints[0], p, 0))
        out = self.server.handle(p.encode(), self.endpoints[0], self.now / 1000)
        self.assertEqual(relay.Packet.decode(out[0][1]).payload, struct.pack('!I', relay.SERVER_BUSY))

    def test_full_room_and_paired_match_survives_lobby_deadline(self):
        code = self.connect()
        room = self.server.rooms[code]
        room.created -= self.server.ROOM_LIFETIME + 1
        self.server.next_sweep = 0
        self.assertEqual(self.server.sweep(self.now / 1000), [])
        third = ('192.0.2.55', 33000)
        p = relay.Packet(relay.PROVE, 0, code, 999)
        p = relay.Packet(relay.PROVE, 0, code, 999, self.server._cookie(third, p, 0))
        out = self.server.handle(p.encode(), third, self.now / 1000)
        self.assertEqual(relay.Packet.decode(out[0][1]).payload, struct.pack('!I', relay.ROOM_FULL))
        self.assertEqual(len(self.server.members), 2)

    def test_waiting_lobby_expiry_and_opening_retry(self):
        self.lib.start(0, 0, self.now)
        self.pump(drop_kind=relay.CHALLENGE)
        self.assertEqual(self.lib.get(0, 0), 1)
        self.advance(500)
        self.assertEqual(self.lib.get(0, 0), 3)
        room = next(iter(self.server.rooms.values()))
        room.created -= self.server.ROOM_LIFETIME + 1
        self.server.next_sweep = 0
        for response in self.server.sweep(self.now / 1000):
            self.deliver(response)
        self.assertEqual(self.lib.get(0, 1), relay.LOBBY_EXPIRED)
        self.assertEqual(len(self.server.rooms), 0)

    def test_fresh_endpoint_proof_reconnects_when_leave_was_lost(self):
        old_code = self.connect()
        old_host = self.server.rooms[old_code].host
        def proof(nonce, room=0):
            p = relay.Packet(relay.PROVE, relay.HOST if not room else 0, room, nonce)
            return relay.Packet(p.kind, p.flags, room, nonce,
                                self.server._cookie(old_host.endpoint, p, 0)).encode()
        out = self.server.handle(proof(991), old_host.endpoint, self.now / 1000)
        self.assertEqual(len(out), 3)
        self.assertNotIn(old_code, self.server.rooms)
        self.assertEqual(len(self.server.rooms), 1)
        self.assertEqual(relay.Packet.decode(out[-1][1]).kind, relay.WELCOME)
        old_retry = self.server.handle(proof(old_host.nonce), old_host.endpoint, self.now / 1000)
        self.assertEqual(relay.Packet.decode(old_retry[0][1]).payload,
                         struct.pack('!I', relay.ROOM_CLOSED))
        new_code = next(iter(self.server.rooms))
        self_join = self.server.handle(proof(992, new_code), old_host.endpoint, self.now / 1000)
        self.assertEqual(relay.Packet.decode(self_join[-1][1]).payload,
                         struct.pack('!I', relay.NO_ROOM))
        self.assertEqual(len(self.server.rooms), 0)

    def test_unproven_requests_are_rate_bounded_without_room_allocation(self):
        p = relay.Packet(relay.OPEN, relay.HOST, 0, 123).encode()
        answers = sum(bool(self.server.handle(p, self.endpoints[0], 0)) for _ in range(100))
        self.assertEqual(answers, 8)
        self.assertEqual(len(self.server.rooms), 0)
        self.assertEqual(len(self.server.members), 0)


if __name__ == '__main__':
    unittest.main()
