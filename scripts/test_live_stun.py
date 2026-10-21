"""Check the phase-0 STUN codec and probe driver from src/live_transport.cpp."""
import ctypes as C
import _ctypes
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
COOKIE = 0x2112A442
SERVERS = (("74.125.250.129", 19302), ("162.159.207.0", 3478))


def block(source, name):
    begin, end = f"// STUN {name} begin", f"// STUN {name} end"
    return source[source.index(begin):source.index(end)]


def response(transaction, ip, port, before=b"", kind=0x0101, family=1, cookie=COOKIE):
    xip = bytes(a ^ b for a, b in zip(socket.inet_aton(ip), struct.pack(">I", COOKIE)))
    value = struct.pack(">BBH", 0, family, port ^ (COOKIE >> 16)) + xip
    body = before + struct.pack(">HH", 0x0020, len(value)) + value
    return struct.pack(">HHI", kind, len(body), cookie) + transaction + body


def attribute(kind, value):
    return struct.pack(">HH", kind, len(value)) + value + b"\0" * (-len(value) % 4)


class Endpoint(C.Structure):
    _fields_ = [("ip", C.c_ubyte * 4), ("port", C.c_ushort), ("reserved", C.c_ushort)]


class LiveStunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-stun-", dir=ROOT / "build")
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name)
        source = (ROOT / "src/live_transport.cpp").read_text()
        code = r'''
#include "susamune/live_transport.hxx"
#define API extern "C" __declspec(dllexport)
extern "C" void *memcpy(void *d, const void *s, unsigned long long n) {
    for (unsigned long long i = 0; i < n; ++i) static_cast<char *>(d)[i] = static_cast<const char *>(s)[i];
    return d;
}
extern "C" void *memset(void *d, int v, unsigned long long n) {
    for (unsigned long long i = 0; i < n; ++i) static_cast<char *>(d)[i] = static_cast<char>(v);
    return d;
}
typedef long long OSTime;
unsigned gTick;
OSTime OSGetTime() { return 0x0123456789abcdefll + gTick; }
unsigned OSGetTick() { return gTick; }
#define OSMillisecondsToTicks(ms) ((ms) * 10u)
namespace LiveTransport {
Status gStatus; bool gBegun, gStopped, gSendOk = true;
Packet gTx[64]; unsigned gTxCount;
Packet gRx[8]; unsigned gRxCount, gRxRead;
bool begin(unsigned short port) { if (gBegun) return false; gBegun = true; gTx[63].bytes = port; return true; }
Status poll() { return gStatus; }
bool sendControl(const Endpoint &to, const void *data, unsigned bytes) {
    if (!gSendOk || gTxCount == 63) return false;
    Packet &p = gTx[gTxCount++]; p.endpoint = to; p.bytes = bytes;
    for (unsigned i = 0; i < bytes; ++i) p.data[i] = static_cast<const unsigned char *>(data)[i];
    return true;
}
bool receive(Packet &packet) { if (gRxRead == gRxCount) return false; packet = gRx[gRxRead++]; return true; }
void stop() { gStopped = true; }
}
'''
        code += block(source, "codec") + block(source, "probe")
        code += r'''
using namespace LiveTransport;
API void request(unsigned char *out, const unsigned char *id) { LiveStun::request(out, id); }
API bool mapped(const void *data, unsigned bytes, const unsigned char *id, TWLiveEndpoint *out) {
    return LiveStun::mapped(data, bytes, id, out);
}
API void reset() { LiveStun::sResult = LiveStun::Result{}; gStatus = Status{}; gBegun = gStopped = false; gSendOk = true; gTxCount = gRxCount = gRxRead = 0; gTick = 1000; }
API void setState(unsigned state, int error) { gStatus.state = state; gStatus.error = error; }
API void setSendOk(bool ok) { gSendOk = ok; }
API bool start(unsigned short port) { return LiveStun::start(port); }
API void update(unsigned advance) { gTick += advance; LiveStun::update(); }
API unsigned sent() { return gTxCount; }
API unsigned lastPort() { return gTx[63].bytes; }
API const Packet *sentPacket(unsigned i) { return &gTx[i]; }
API void inject(const TWLiveEndpoint *from, const void *data, unsigned bytes) {
    Packet &p = gRx[gRxCount++]; p = Packet{}; p.endpoint = *from; p.bytes = bytes;
    for (unsigned i = 0; i < bytes; ++i) p.data[i] = static_cast<const unsigned char *>(data)[i];
}
API bool stopped() { return gStopped; }
API const LiveStun::Result *result() { return &LiveStun::result(); }
API bool startShared() { return LiveStun::startShared(); }
API bool accept(const TWLiveEndpoint *from, const void *data, unsigned bytes) {
    Packet p = Packet{}; p.endpoint = *from; p.bytes = bytes;
    for (unsigned i = 0; i < bytes; ++i) p.data[i] = static_cast<const unsigned char *>(data)[i];
    return LiveStun::accept(p);
}
API void cancel() { LiveStun::cancel(); }
API unsigned rxRead() { return gRxRead; }
'''
        cpp = folder / "fixture.cpp"
        cpp.write_text(code)
        dll = cpp.with_suffix(".dll")
        subprocess.run([str(ROOT / "toolchain/clang++.exe"), "--target=x86_64-pc-windows-msvc",
                        "-shared", "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-fno-builtin",
                        "-O2", "-I", str(ROOT / "include"), str(cpp), "-o", str(dll)],
                       check=True, text=True, env={**os.environ, "TEMP": str(folder), "TMP": str(folder)})
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: _ctypes.FreeLibrary(cls.lib._handle))
        lib = cls.lib
        lib.mapped.argtypes = [C.c_char_p, C.c_uint, C.c_char_p, C.POINTER(Endpoint)]
        lib.mapped.restype = C.c_bool
        lib.request.argtypes = [C.c_void_p, C.c_char_p]
        lib.start.argtypes = [C.c_ushort]
        lib.start.restype = C.c_bool
        lib.stopped.restype = C.c_bool
        lib.setSendOk.argtypes = [C.c_bool]
        lib.setState.argtypes = [C.c_uint, C.c_int]
        lib.update.argtypes = [C.c_uint]
        lib.sentPacket.restype = C.c_void_p
        lib.result.restype = C.c_void_p
        lib.inject.argtypes = [C.POINTER(Endpoint), C.c_char_p, C.c_uint]
        lib.startShared.restype = C.c_bool
        lib.accept.argtypes = [C.POINTER(Endpoint), C.c_char_p, C.c_uint]
        lib.accept.restype = C.c_bool

    def parse(self, data, transaction):
        out = Endpoint()
        if not self.lib.mapped(data, len(data), transaction, C.byref(out)):
            return None
        return socket.inet_ntoa(bytes(out.ip)), out.port

    def test_request_is_a_bare_rfc5389_binding_request(self):
        transaction = bytes(range(1, 13))
        out = (C.c_ubyte * 20)()
        self.lib.request(out, transaction)
        self.assertEqual(bytes(out), struct.pack(">HHI", 1, 0, COOKIE) + transaction)

    def test_xor_mapped_address_after_other_padded_attributes(self):
        transaction = os.urandom(12)
        before = attribute(0x0001, b"\0\1\x12\x34\1\2\3\4") + attribute(0x8022, b"abcde")
        self.assertEqual(self.parse(response(transaction, "84.83.141.41", 48222, before), transaction),
                         ("84.83.141.41", 48222))
        self.assertEqual(self.parse(response(transaction, "255.0.1.2", 65535), transaction), ("255.0.1.2", 65535))

    def test_rejects_wrong_transaction_type_cookie_family_port_and_lengths(self):
        transaction = os.urandom(12)
        good = response(transaction, "1.2.3.4", 5000)
        self.assertIsNotNone(self.parse(good, transaction))
        other = bytes(transaction[:-1]) + bytes([transaction[-1] ^ 1])
        self.assertIsNone(self.parse(good, other))
        self.assertIsNone(self.parse(response(transaction, "1.2.3.4", 5000, kind=0x0111), transaction))
        self.assertIsNone(self.parse(response(transaction, "1.2.3.4", 5000, cookie=COOKIE ^ 1), transaction))
        self.assertIsNone(self.parse(response(transaction, "1.2.3.4", 5000, family=2), transaction))
        self.assertIsNone(self.parse(response(transaction, "1.2.3.4", 0), transaction))
        for cut in range(len(good)):
            self.assertIsNone(self.parse(good[:cut], transaction), cut)
        overlong = bytearray(good)
        overlong[22:24] = struct.pack(">H", 200)
        self.assertIsNone(self.parse(bytes(overlong), transaction))
        self.assertIsNone(self.parse(struct.pack(">HHI", 0x0101, 0, COOKIE) + transaction, transaction))

    def endpoint(self, ip, port):
        return Endpoint((C.c_ubyte * 4)(*socket.inet_aton(ip)), port, 0)

    def requests(self):
        out = []
        for i in range(self.lib.sent()):
            base = self.lib.sentPacket(i)
            packet = C.cast(base, C.POINTER(C.c_ubyte * (8 + 8 + 16 + 256))).contents
            endpoint = Endpoint.from_address(base + 8)
            size = struct.unpack("<I", bytes(packet[4:8]))[0]
            out.append(((socket.inet_ntoa(bytes(endpoint.ip)), endpoint.port), bytes(packet[32:32 + size])))
        return out

    def result(self):
        raw = C.string_at(self.lib.result(), 24)
        state, verdict, attempts, answered, error = struct.unpack("<BBBBi", raw[:8])
        mapped = [(socket.inet_ntoa(raw[8 + i * 8:12 + i * 8]), struct.unpack("<H", raw[12 + i * 8:14 + i * 8])[0])
                  for i in range(2)]
        return dict(state=state, verdict=verdict, attempts=attempts, answered=answered, error=error, mapped=mapped)

    def run_probe(self, replies, failure=None):
        self.lib.reset()
        self.assertTrue(self.lib.start(48222))
        self.assertEqual(self.lib.lastPort(), 48222)
        self.assertFalse(self.lib.start(48222))
        self.lib.update(1)
        self.assertEqual(self.lib.sent(), 0)  # Still opening.
        self.lib.setState(3, 0)
        for step in range(20):
            self.lib.update(5000 if step else 1)
            if failure is not None and step == 1:
                self.lib.setState(*failure)
            for (server, data) in self.requests()[-2:]:
                if server in replies and step == 0:
                    ip, port = replies[server]
                    transaction = data[8:20]
                    self.lib.inject(self.endpoint(*server), response(transaction, ip, port), 32)
            if self.result()["state"] != 1:
                break
        return self.result()

    def test_same_mapping_means_endpoint_independent(self):
        result = self.run_probe({SERVERS[0]: ("84.83.141.41", 48222), SERVERS[1]: ("84.83.141.41", 48222)})
        self.assertEqual((result["state"], result["verdict"], result["answered"]), (2, 2, 3))
        self.assertEqual(result["mapped"], [("84.83.141.41", 48222)] * 2)
        self.assertTrue(self.lib.stopped())
        sent = self.requests()
        self.assertEqual([s for s, _ in sent], list(SERVERS))
        self.assertNotEqual(sent[0][1][8:20], sent[1][1][8:20])

    def test_different_ports_mean_symmetric(self):
        result = self.run_probe({SERVERS[0]: ("84.83.141.41", 40001), SERVERS[1]: ("84.83.141.41", 40002)})
        self.assertEqual((result["state"], result["verdict"]), (2, 3))

    def test_one_reply_retries_only_the_silent_server_six_times(self):
        result = self.run_probe({SERVERS[1]: ("84.83.141.41", 48222)})
        self.assertEqual((result["state"], result["verdict"], result["answered"], result["attempts"]), (2, 1, 2, 6))
        self.assertEqual([s for s, _ in self.requests()], list(SERVERS) + [SERVERS[0]] * 5)

    def test_reply_from_wrong_source_or_transaction_is_ignored(self):
        self.lib.reset()
        self.assertTrue(self.lib.start(1))
        self.lib.setState(3, 0)
        self.lib.update(1)
        (first, data), (second, other) = self.requests()
        self.lib.inject(self.endpoint("9.9.9.9", first[1]), response(data[8:20], "1.1.1.1", 1), 32)
        self.lib.inject(self.endpoint(*first), response(other[8:20], "1.1.1.1", 1), 32)
        self.lib.update(1)
        self.assertEqual(self.result()["answered"], 0)

    def test_transport_failure_without_replies_fails(self):
        result = self.run_probe({}, failure=(5, -116))
        self.assertEqual((result["state"], result["error"]), (3, -116))
        self.assertTrue(self.lib.stopped())

    def test_standalone_probe_waits_for_the_address(self):
        lib = self.lib
        lib.reset()
        self.assertTrue(lib.start(48222))
        lib.setState(1, 0)  # The ARM side has not taken BEGIN yet.
        lib.update(5000)
        lib.setState(2, 0)  # Opening: KD, DHCP and the socket can take many seconds.
        lib.update(200000)
        self.assertEqual((self.result()["state"], lib.sent()), (1, 0))
        lib.setState(3, 0)
        lib.update(1)
        self.assertEqual(lib.sent(), 2)  # The probe's clock starts at READY.
        for _ in range(10):
            lib.update(5000)
        result = self.result()
        self.assertEqual((result["state"], result["verdict"], result["attempts"]), (2, 0, 6))
        self.assertTrue(lib.stopped())
        lib.reset()
        self.assertTrue(lib.start(48222))
        lib.setState(2, 0)
        lib.update(300000)
        self.assertEqual(self.result()["state"], 1)
        lib.update(1)
        self.assertEqual((self.result()["state"], self.result()["error"]), (3, -1))
        lib.reset()
        self.assertTrue(lib.start(48222))
        lib.setState(3, 0)
        lib.update(1)
        lib.setState(1, 0)  # IDLE after READY: the transport went away.
        lib.update(1)
        self.assertEqual(self.result()["state"], 3)

    def test_shared_probe_uses_the_owners_transport_and_packets(self):
        lib = self.lib
        lib.reset()
        self.assertTrue(lib.startShared())
        self.assertFalse(lib.startShared())
        self.assertFalse(lib.start(48222))
        lib.update(1)  # No READY needed: the online session already polls the transport.
        sent = self.requests()
        self.assertEqual([s for s, _ in sent], list(SERVERS))
        lib.inject(self.endpoint(*SERVERS[0]), response(sent[0][1][8:20], "84.83.141.41", 48222), 32)
        self.assertFalse(lib.accept(self.endpoint("9.9.9.9", 3478), b"\0" * 32, 32))
        for (server, data) in sent:
            reply = response(data[8:20], "84.83.141.41", 48222)
            self.assertTrue(lib.accept(self.endpoint(*server), reply, len(reply)))
        lib.update(1)
        result = self.result()
        self.assertEqual((result["state"], result["verdict"], result["answered"]), (2, 2, 3))
        self.assertEqual(lib.rxRead(), 0)
        self.assertFalse(lib.stopped())
        self.assertFalse(lib.accept(self.endpoint(*SERVERS[0]), reply, len(reply)))

    def test_shared_probe_cancel_and_time_limit(self):
        lib = self.lib
        lib.reset()
        self.assertTrue(lib.startShared())
        lib.update(1)
        lib.cancel()
        self.assertEqual((self.result()["state"], self.result()["error"]), (3, -1))
        self.assertFalse(lib.stopped())
        lib.reset()
        lib.setSendOk(False)
        self.assertTrue(lib.startShared())
        for _ in range(40):
            lib.update(5000)
        result = self.result()
        self.assertEqual((result["state"], result["verdict"], result["attempts"]), (2, 0, 0))
        self.assertFalse(lib.stopped())

    @unittest.skipUnless(os.environ.get("MOONSHINE_STUN_LIVE"), "set MOONSHINE_STUN_LIVE=1 for real servers")
    def test_codec_against_real_servers(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", 0))
        sock.settimeout(2)
        seen = []
        for server in SERVERS:
            transaction = os.urandom(12)
            out = (C.c_ubyte * 20)()
            self.lib.request(out, transaction)
            sock.sendto(bytes(out), server)
            data, source = sock.recvfrom(2048)
            self.assertEqual(source, server)
            seen.append(self.parse(data, transaction))
            self.assertIsNotNone(seen[-1])
        print("real STUN mappings", seen)
        sock.close()


if __name__ == "__main__":
    unittest.main()
