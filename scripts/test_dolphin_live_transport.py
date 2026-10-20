"""Companion ownership/lifecycle and real loopback UDP with native JP/PAL clients."""
import ctypes as C
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
        words = bridge.WORDS.unpack(self.read(bridge.INDICES, 32))
        write, read = words[3:5]
        if read == host.rx_write:
            return None
        _, data = bridge.packet(self.read(bridge.RX + (read & 3) * 288, 288), host.epoch)
        self.publish(bridge.INDICES, (host.epoch, write, (read + 1) & bridge.MASK, 0, 0, 0))
        return data


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


class NativeRelaySocketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_live_relay
        cls.native = test_live_relay
        test_live_relay.RelayTests.setUpClass.__func__(cls)

    def test_jp_pal_native_handshake_poses_and_old_session_rejection(self):
        relay = self.native.relay
        self.lib.reset()
        server = relay.Relay(secret=b'loopback-fixture')
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(('127.0.0.1', 0))
            sock.setblocking(False)
            memories = [Memory(1), Memory(3)]
            hosts = [bridge.Bridge(m) for m in memories]
            for host in hosts:
                self.addCleanup(host.close)
            for memory, host in zip(memories, hosts):
                memory.begin(host)
            target = sock.getsockname()
            now = 100
            old_response = None

            def pump():
                nonlocal old_response
                for _ in range(20):
                    while self.lib.queued():
                        node = getattr(self.lib, 'from')(0)
                        data = C.string_at(self.lib.data(0), self.lib.bytes(0))
                        memories[node].tx(hosts[node], target, data)
                        self.lib.drop(0)
                        hosts[node].step()
                    for host in hosts:
                        host.step()
                    while True:
                        try:
                            data, sender = sock.recvfrom(257)
                        except BlockingIOError:
                            break
                        for endpoint, reply in server.handle(data, sender, now / 1000):
                            if relay.Packet.decode(reply).kind == relay.DATA:
                                old_response = reply
                            sock.sendto(reply, endpoint)
                    for i, host in enumerate(hosts):
                        host.step()
                        while (data := memories[i].receive(host)) is not None:
                            self.lib.inject(i, data, len(data), now, 0)
                    time.sleep(0.001)

            self.assertTrue(self.lib.start(0, 0, now))
            pump()
            code = self.lib.get(0, 2)
            self.assertTrue(100000 <= code <= 999999)
            self.assertTrue(self.lib.start(1, code, now))
            pump()
            for i in range(2):
                self.lib.tick(i, now + 1)
            pump()
            self.assertEqual([self.lib.get(i, 4) for i in range(2)], [1, 1])
            self.assertEqual([self.lib.get(i, 5) for i in range(2)], [2, 0])
            for i in range(2):
                self.assertTrue(self.lib.sendPose(i))
            pump()
            self.assertEqual([self.lib.get(i, 6) for i in range(2)], [1, 1])
            self.lib.stop(1)
            pump()
            self.assertNotIn(code, server.rooms)
            self.assertIsNotNone(old_response)
            self.assertFalse(self.lib.inject(0, old_response, len(old_response), now, 0))


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
