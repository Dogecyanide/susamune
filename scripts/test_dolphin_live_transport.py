"""Companion ownership/lifecycle and real loopback UDP with native JP/PAL clients."""
import ctypes as C
import _ctypes
import os
import importlib.util
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('dolphin_bridge', ROOT / 'tools/dolphin_online/bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class Memory:
    def __init__(self, region=1):
        self.data = bytearray(bridge.SIZE)
        self.generations = {}
        self.writes = []
        self.game(region, 123, 1)

    def game(self, region, instance, heartbeat):
        self.publish(bridge.GAME, (bridge.MAGIC, bridge.ABI, region, instance, heartbeat, bridge.SIZE))

    def publish(self, offset, tail):
        generation = self.generations.get(offset, 0) + 1
        self.generations[offset] = generation
        raw = struct.pack('>II', generation, generation)
        raw += struct.pack('>6I', *tail) if isinstance(tail, tuple) else tail
        self.data[offset:offset + len(raw)] = raw

    def read(self, offset, length):
        bridge.checked_range(offset, length)
        return bytes(self.data[offset:offset + length])

    def write(self, offset, data):
        bridge.checked_range(offset, len(data), True)
        self.writes.append((offset, len(data)))
        self.data[offset:offset + len(data)] = data

    def begin(self, host):
        self.publish(bridge.INDICES, (host.epoch, 0, 0, 0, 0, 0))
        self.publish(bridge.COMMAND, (host.epoch, 1, 1, 0, 0, 0))
        host.step()

    def tx(self, host, target, data):
        words = bridge.WORDS.unpack(self.read(bridge.INDICES, 32))
        write, read = words[3:5]
        packet = struct.pack('>II4sHH4I', host.epoch, len(data), socket.inet_aton(target[0]), target[1], 0, 0, 0, 0, 0)
        at = bridge.TX + (write & 3) * 288
        self.data[at:at + 288] = packet + data.ljust(256, b'\0')
        self.publish(bridge.INDICES, (host.epoch, (write + 1) & bridge.MASK, read, 0, 0, 0))

    def receive(self, host):
        received = self.receive_from(host)
        return None if received is None else received[1]

    def receive_from(self, host):
        words = bridge.WORDS.unpack(self.read(bridge.INDICES, 32))
        write, read = words[3:5]
        if read == host.rx_write:
            return None
        sender, data = bridge.packet(self.read(bridge.RX + (read & 3) * 288, 288), host.epoch)
        self.publish(bridge.INDICES, (host.epoch, write, (read + 1) & bridge.MASK, 0, 0, 0))
        return sender, data


class MailboxTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.memory = Memory()
        self.host = bridge.Bridge(self.memory, clock=lambda: self.now)
        self.addCleanup(self.host.close)

    def test_owned_ranges_and_packet_validation(self):
        for start, end in bridge.HOST_RANGES:
            bridge.checked_range(start, end - start, True)
        for offset, size in ((0, 4), (64, 4), (159, 2), (2464, 4), (-1, 1), (bridge.SIZE, 1)):
            with self.assertRaises(ValueError):
                bridge.checked_range(offset, size, True)
        self.memory.begin(self.host)
        self.assertEqual(self.host.state, bridge.READY)
        self.memory.tx(self.host, ('127.0.0.1', 9), b'x')
        self.memory.data[bridge.TX + 16] = 1
        old = self.host.epoch
        self.host.step()
        self.assertEqual((self.host.state, self.host.epoch, self.host.sent), (bridge.IDLE, old + 1, 0))

    def test_stop_reconnect_and_stale_epoch(self):
        self.memory.begin(self.host)
        old_socket, old = self.host.socket, self.host.epoch
        self.memory.publish(bridge.COMMAND, (old, 2, 2, 0, 0, 0))
        self.host.step()
        self.assertEqual(old_socket.fileno(), -1)
        self.assertEqual(self.host.epoch, old + 1)
        self.host.step()
        self.assertEqual(self.host.state, bridge.IDLE)
        self.memory.begin(self.host)
        self.assertEqual(self.host.state, bridge.READY)

    def test_heartbeat_timeout_and_game_rollback(self):
        self.memory.game(1, 123, 10)
        self.memory.begin(self.host)
        old = self.host.epoch
        self.now = 4
        self.host.step()
        self.assertEqual((self.host.state, self.host.epoch), (bridge.IDLE, old + 1))
        self.memory.game(1, 123, 2)
        self.host.step()
        self.assertEqual(self.host.epoch, old + 2)

    def test_restart_rejects_every_host_write(self):
        self.memory.begin(self.host)
        before = len(self.memory.writes)
        self.memory.game(1, 456, 1)
        with self.assertRaises(RuntimeError):
            self.host.publish_status()
        self.assertEqual(len(self.memory.writes), before)
        with self.assertRaises(RuntimeError):
            self.host.close()
        self.assertIsNone(self.host.socket)

    def test_torn_publications_and_exhausted_generation(self):
        self.memory.data[bridge.COMMAND:bridge.COMMAND + 8] = struct.pack('>II', 0, 9)
        self.assertIsNone(bridge.publication(self.memory, bridge.COMMAND))
        self.memory.data[bridge.COMMAND:bridge.COMMAND + 8] = struct.pack('>II', 8, 9)
        self.assertIsNone(bridge.publication(self.memory, bridge.COMMAND))
        self.host.generations[bridge.STATUS] = bridge.MASK
        with self.assertRaises(OverflowError):
            self.host.publish_status()
        self.host.generations[bridge.STATUS] = 100

    def test_same_clock_boot_clearing_host_line_retires_old_socket(self):
        self.memory.begin(self.host)
        old_socket, old = self.host.socket, self.host.epoch
        self.memory.data[bridge.HOST:bridge.HOST + 32] = bytes(32)
        self.host.step()
        self.assertEqual(old_socket.fileno(), -1)
        self.assertEqual((self.host.state, self.host.epoch), (bridge.IDLE, old + 1))

    def test_counter_bounds_and_backward_publication(self):
        self.memory.begin(self.host)
        old = self.host.epoch
        self.memory.publish(bridge.INDICES, (old, 5, 0, 0, 0, 0))
        self.host.step()
        self.assertEqual(self.host.epoch, old + 1)
        self.memory.begin(self.host)
        self.memory.generations[bridge.INDICES] = 0
        self.memory.publish(bridge.INDICES, (self.host.epoch, 0, 0, 0, 0, 0))
        self.host.step()
        self.assertEqual(self.host.epoch, old + 2)

    def test_latest_pose_replaces_unsent_pose_and_foreign_sender_is_dropped(self):
        self.memory.begin(self.host)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as remote, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as foreign:
            remote.bind(('127.0.0.1', 0))
            remote.settimeout(1)
            target = remote.getsockname()
            for value in (b'old', b'new'):
                tail = struct.pack('>II4sHHII', self.host.epoch, len(value), socket.inet_aton(target[0]), target[1], 0, 0, 0)
                self.memory.publish(bridge.POSE, tail + value.ljust(256, b'\0'))
            self.host.step()
            data, sender = remote.recvfrom(256)
            self.assertEqual(data, b'new')
            foreign.sendto(b'foreign', sender)
            remote.sendto(b'reply', sender)
            remote.sendto(bytes(257), sender)
            for _ in range(100):
                self.host.step()
                if self.host.received and self.host.dropped == 2:
                    break
                time.sleep(0.001)
            self.assertEqual(self.memory.receive(self.host), b'reply')
            self.assertEqual((self.host.sent, self.host.received, self.host.dropped), (1, 1, 2))


P2P_HARNESS = r"""
#define TIMEWARP_LIVE_RACING 1
#include "susamune/live_p2p.hxx"
#include "susamune/live_race_session.hxx"
extern "C" void *memcpy(void*d,const void*s,__SIZE_TYPE__ n){unsigned char*a=(unsigned char*)d;const unsigned char*b=(const unsigned char*)s;while(n--)*a++=*b++;return d;}
extern "C" void *memset(void*d,int c,__SIZE_TYPE__ n){unsigned char*a=(unsigned char*)d;while(n--)*a++=(unsigned char)c;return d;}
struct Node {LiveP2P::Punch punch;LiveRaceSession::Session session;unsigned id,poses;};
struct Datagram {unsigned from,bytes;TWLiveEndpoint to;unsigned char data[256];};
static Node nodes[2];static Datagram packets[256];static unsigned count;
static bool queue(void*context,const TWLiveEndpoint&e,const void*data,unsigned bytes){
 if(count==256||bytes>256)return false;Datagram&p=packets[count++];
 p.from=((Node*)context)->id;p.to=e;p.bytes=bytes;memcpy(p.data,data,bytes);return true;}
static void onPose(void*context,const MSRHeader&,const MSRPose&,unsigned){++((Node*)context)->poses;}
static TWLiveEndpoint loopback(unsigned port){TWLiveEndpoint e={{127,0,0,1},(unsigned short)port,0};return e;}
#define API extern "C" __declspec(dllexport)
API void reset(){memset(nodes,0,sizeof(nodes));count=0;}
// The joiner always has the host's code; the host has the joiner's only when peerPort is set.
API int start(unsigned id,unsigned pin,unsigned peerPort,unsigned now){
 Node&n=nodes[id];n.id=id;LiveRaceSession::Config config={};config.name[0]=id?'J':'H';config.pin=pin;
 config.region=id?2:0;config.timing=MSR_TIMING_60HZ;config.nonceHigh=0xabcdef00+id;config.nonceLow=0x12345678;
 LiveRaceSession::Callbacks cb={&n,queue,queue,onPose,nullptr};
 if(!LiveRaceSession::init(n.session,config,cb))return 0;
 LiveP2P::reset(n.punch,pin,(unsigned char)id);
 if(peerPort)LiveP2P::add(n.punch,loopback(peerPort),(unsigned char)(id^1));
 const TWLiveEndpoint anyone={};
 return id?LiveRaceSession::startGuest(n.session,loopback(peerPort),now):LiveRaceSession::startHost(n.session,anyone,now);}
API void tick(unsigned id,unsigned now){Node&n=nodes[id];unsigned char punch[LiveP2P::PUNCH_BYTES];
 if(!n.session.info.connected)for(unsigned i=0;i<LiveP2P::MAX_PEERS-1;++i){
  const unsigned bytes=LiveP2P::due(n.punch,i,now,punch);if(bytes)queue(&n,n.punch.peers[i].endpoint,punch,bytes);}
 LiveRaceSession::tick(n.session,now);}
API void inject(unsigned id,unsigned port,const void*data,unsigned bytes,unsigned now){
 Node&n=nodes[id];if(!LiveP2P::receive(n.punch,loopback(port),data,bytes,now,id==0))
  LiveRaceSession::receivePacket(n.session,loopback(port),data,bytes,now);}
API unsigned queued(){return count;}
API unsigned from(unsigned i){return packets[i].from;}
API unsigned toPort(unsigned i){return packets[i].to.port;}
API unsigned bytes(unsigned i){return packets[i].bytes;}
API const void*data(unsigned i){return packets[i].data;}
API void drop(unsigned i){for(unsigned j=i+1;j<count;j++)packets[j-1]=packets[j];--count;}
API int connected(unsigned id){return nodes[id].session.info.connected;}
API int open(unsigned id){return LiveP2P::open(nodes[id].punch);}
API unsigned poses(unsigned id){return nodes[id].poses;}
API int sendPose(unsigned id){MSRPose p={};p.flags=1;p.x=80;return LiveRaceSession::publishPose(nodes[id].session,p,1);}
"""


class NativeP2PSocketTests(unittest.TestCase):
    """Production punching and session code through two Dolphin companions on loopback.
    The companion only admits senders it has sent to, like a port-restricted NAT."""
    @classmethod
    def setUpClass(cls):
        if sys.platform != 'win32':
            raise unittest.SkipTest('Bundled Windows compiler required')
        cls.temp = tempfile.TemporaryDirectory(prefix='dolphin-p2p-', dir=ROOT / 'build')
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        session = (ROOT / 'src/live_race_session.cpp').read_text()
        code = P2P_HARNESS + session[session.index('namespace LiveRaceSession {'):session.rindex('#endif')]
        cpp, dll = work / 'p2p.cpp', work / 'p2p.dll'
        cpp.write_text(code)
        result = subprocess.run([str(ROOT / 'toolchain/clang++.exe'),
            '--target=x86_64-pc-windows-msvc', '-std=c++17', '-shared', '-nostdlib', '-fno-builtin',
            '-fno-exceptions', '-fno-rtti', '-fuse-ld=lld', '-Wl,/noentry', '-O2',
            '-I', str(ROOT / 'include'), str(cpp), '-o', str(dll)],
            capture_output=True, text=True, env={**os.environ, 'TEMP': str(work), 'TMP': str(work)})
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: _ctypes.FreeLibrary(cls.lib._handle))
        cls.lib.data.restype = C.c_void_p

    def run_pair(self, swap):
        lib = self.lib
        lib.reset()
        memories = [Memory(1), Memory(3)]
        hosts = [bridge.Bridge(m) for m in memories]
        for host in hosts:
            self.addCleanup(host.close)
        for memory, host in zip(memories, hosts):
            memory.begin(host)
        ports = [host.socket.getsockname()[1] for host in hosts]
        now = 100
        self.assertTrue(lib.start(0, 4242, ports[1] if swap else 0, now))
        self.assertTrue(lib.start(1, 4242, ports[0], now))
        for _ in range(200):
            now += 50
            for i in range(2):
                lib.tick(i, now)
            while lib.queued():
                node = getattr(lib, 'from')(0)
                data = C.string_at(lib.data(0), lib.bytes(0))
                memories[node].tx(hosts[node], ('127.0.0.1', lib.toPort(0)), data)
                lib.drop(0)
                hosts[node].step()
            time.sleep(0.001)
            for i, host in enumerate(hosts):
                host.step()
                while (received := memories[i].receive_from(host)) is not None:
                    sender, data = received
                    lib.inject(i, sender[1], data, len(data), now)
            if lib.connected(0) and lib.connected(1):
                break
        return hosts

    def test_swapped_codes_punch_through_and_race(self):
        self.run_pair(swap=True)
        self.assertEqual([self.lib.connected(i) for i in range(2)], [1, 1])
        self.assertEqual([self.lib.open(i) for i in range(2)], [1, 1])
        for i in range(2):
            self.assertTrue(self.lib.sendPose(i))
        self.assertGreaterEqual(self.lib.queued(), 2)

    def test_restricted_host_needs_the_joiners_code(self):
        hosts = self.run_pair(swap=False)
        self.assertEqual([self.lib.connected(i) for i in range(2)], [0, 0])
        self.assertGreater(hosts[0].dropped, 0)


class PpcHeartbeatTests(unittest.TestCase):
    def test_actual_client_survives_torn_heartbeat_but_retires_stale_host(self):
        from test_native_timer_creation import function
        source = (ROOT / 'src/live_transport.cpp').read_text()
        code = r'''
#define IS_EMULATOR 1
#include "susamune/dolphin_live_transport.h"
#include "susamune/live_transport.hxx"
typedef unsigned long long OSTime;
static unsigned now=1000;
unsigned OSGetTick(){return now;} OSTime OSGetTime(){return 1234;}
unsigned OSMillisecondsToTicks(unsigned n){return n;}
unsigned OSSecondsToTicks(unsigned n){return 1000*n;}
static const unsigned SUSAMUNE_GAME_VERSION=3;
void flush(volatile void*,unsigned){} void invalidate(const volatile void*,unsigned){}
void barrier(){} const TWLiveIo kIo={flush,invalidate,barrier};
static TWDolphinLive memory;
static volatile TWDolphinLive *const kEmulator=&memory;
static TWDolphinGame sGame;
static unsigned sGameGeneration,sGameTick,sHostGeneration,sHostTick,sHostEpoch,sSession;
static bool sStopping;static volatile TWLiveMailbox*sWire=&memory.wire;
bool discover(){return true;}
using LiveTransport::Status;
'''
        code += function(source, 'emulatorPresent') + '\n' + function(source, 'poll')
        code += r'''
#define CHECK(x) do{if(!(x))return __LINE__;}while(0)
extern "C" __declspec(dllexport) int run(){
 CHECK(!emulatorPresent());CHECK(memory.game.magic==TW_DOLPHIN_LIVE_MAGIC);
 TWDolphinHost host={};host.instance=sGame.instance;host.epoch=17;host.heartbeat=1;
 unsigned hostGeneration=0,statusGeneration=0;
 TWLivePublish(&memory.host,&host,sizeof(host),&hostGeneration,&kIo);
 Status status={};status.epoch=17;status.state=TW_LIVE_READY;
 TWLivePublish(&memory.wire.status,&status,sizeof(status),&statusGeneration,&kIo);
 CHECK(poll().state==TW_LIVE_READY);sSession=17;
 memory.host.generation=0;now+=1500;
 CHECK(poll().state==TW_LIVE_READY&&sSession==17);
 now+=1501;CHECK(poll().state==TW_LIVE_UNAVAILABLE&&!sSession);
 host.epoch=18;host.heartbeat=2;
 TWLivePublish(&memory.host,&host,sizeof(host),&hostGeneration,&kIo);
 CHECK(poll().state==TW_LIVE_UNAVAILABLE);
 status.epoch=18;TWLivePublish(&memory.wire.status,&status,sizeof(status),&statusGeneration,&kIo);
 CHECK(poll().state==TW_LIVE_READY);sSession=18;
 host.instance++;TWLivePublish(&memory.host,&host,sizeof(host),&hostGeneration,&kIo);
 CHECK(poll().state==TW_LIVE_UNAVAILABLE&&!sSession);
 return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='dolphin-heartbeat-', dir=ROOT / 'build') as folder:
            folder = Path(folder)
            cpp, dll = folder / 'test.cpp', folder / 'test.dll'
            cpp.write_text(code)
            result = subprocess.run([str(ROOT / 'toolchain/clang++.exe'), '--target=x86_64-pc-windows-msvc',
                '-shared', '-O2', '-nostdlib', '-fno-builtin', '-fuse-ld=lld', '-Wl,/noentry',
                '-std=c++17', '-I', str(ROOT / 'include'), str(cpp), '-o', str(dll)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            library = C.CDLL(str(dll))
            try:
                self.assertEqual(library.run(), 0, 'actual client assertion line')
            finally:
                C.windll.kernel32.FreeLibrary(C.c_void_p(library._handle))


if __name__ == '__main__':
    unittest.main()
