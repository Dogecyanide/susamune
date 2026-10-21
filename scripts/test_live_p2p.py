"""Room codes and UDP hole punching for serverless online play."""
import ctypes as C
import _ctypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"

HARNESS = r'''
#define TIMEWARP_LIVE_RACING 1
#include "susamune/live_p2p.hxx"
#define API extern "C" __declspec(dllexport)
static LiveP2P::Punch nodes[4];
static TWLiveEndpoint endpoint(unsigned ip, unsigned port) {
    TWLiveEndpoint e = {{(unsigned char)(ip >> 24), (unsigned char)(ip >> 16), (unsigned char)(ip >> 8), (unsigned char)ip},
                        (unsigned short)port, 0};
    return e;
}
API int encode(unsigned ip, unsigned port, unsigned secret, unsigned role, char *out) {
    LiveP2P::Code code = {endpoint(ip, port), secret, (unsigned char)role};
    return LiveP2P::encode(code, out);
}
API int decode(const char *text, unsigned *ip, unsigned *port, unsigned *secret, unsigned *role) {
    LiveP2P::Code code;
    if (!LiveP2P::decode(text, &code)) return 0;
    *ip = (unsigned)code.endpoint.ip[0] << 24 | code.endpoint.ip[1] << 16 | code.endpoint.ip[2] << 8 | code.endpoint.ip[3];
    *port = code.endpoint.port; *secret = code.secret; *role = code.role;
    return 1;
}
API void format(const char *code, char *out) { LiveP2P::format(code, out); }
API void reset(unsigned node, unsigned pin, unsigned self) { LiveP2P::reset(nodes[node], pin, (unsigned char)self); }
API int add(unsigned node, unsigned ip, unsigned port, unsigned participant) {
    return LiveP2P::add(nodes[node], endpoint(ip, port), (unsigned char)participant);
}
API unsigned due(unsigned node, unsigned index, unsigned now, unsigned char *packet) {
    return LiveP2P::due(nodes[node], index, now, packet);
}
API int receive(unsigned node, unsigned ip, unsigned port, const void *data, unsigned bytes, unsigned now, int adopt) {
    return LiveP2P::receive(nodes[node], endpoint(ip, port), data, bytes, now, adopt != 0);
}
API unsigned state(unsigned node, unsigned index) { return nodes[node].peers[index].state; }
API unsigned peerPort(unsigned node, unsigned index) { return nodes[node].peers[index].endpoint.port; }
API unsigned peerIp(unsigned node, unsigned index) {
    const unsigned char *a = nodes[node].peers[index].endpoint.ip;
    return (unsigned)a[0] << 24 | a[1] << 16 | a[2] << 8 | a[3];
}
API unsigned participant(unsigned node, unsigned index) { return nodes[node].peers[index].participant; }
API int open(unsigned node) { return LiveP2P::open(nodes[node]); }
API unsigned roster(unsigned node, unsigned index, unsigned char *packet) { return LiveP2P::roster(nodes[node], index, packet); }
API unsigned maxPeers() { return LiveP2P::MAX_PEERS; }
'''


def ip(text):
    a, b, c, d = (int(x) for x in text.split('.'))
    return a << 24 | b << 16 | c << 8 | d


class LiveP2PTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "win32":
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="live-p2p-", dir=ROOT / "build")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        session = (ROOT / "src/live_race_session.cpp").read_text()
        code = HARNESS + session[session.index("// P2P codec begin"):session.index("// P2P codec end")]
        cls.lib = cls.compile(work, code, "p2p", [])
        # The same source built for a four-player room, as a later build would set it.
        cls.lib4 = cls.compile(work, code, "p2p4", ["-DLIVE_P2P_MAX_PEERS=4"])

    @classmethod
    def compile(cls, work, code, name, flags):
        cpp, dll = work / (name + ".cpp"), work / (name + ".dll")
        cpp.write_text(code)
        result = subprocess.run([str(ROOT / "toolchain/clang++.exe"),
            "--target=x86_64-pc-windows-msvc", "-std=c++17", "-shared", "-nostdlib", "-fno-builtin",
            "-fno-exceptions", "-fno-rtti", "-fuse-ld=lld", "-Wl,/noentry", "-O2", "-Wall", "-Werror", *flags,
            "-I", str(ROOT / "include"), str(cpp), "-o", str(dll)],
            capture_output=True, text=True, env={**os.environ, "TEMP": str(work), "TMP": str(work)})
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: _ctypes.FreeLibrary(lib._handle))
        for name in ("encode", "decode", "reset", "add", "due", "receive", "state", "peerPort", "peerIp",
                     "participant", "open", "roster"):
            getattr(lib, name).restype = C.c_int if name in ("encode", "decode", "add", "receive", "open") else C.c_uint
        return lib

    def encode(self, address, port, secret, role):
        out = C.create_string_buffer(17)
        ok = self.lib.encode(ip(address), port, secret, role, out)
        return out.value.decode() if ok else None

    def decode(self, text):
        values = [C.c_uint() for _ in range(4)]
        if not self.lib.decode(text.encode(), *(C.byref(v) for v in values)):
            return None
        a, port, secret, role = (v.value for v in values)
        return ('.'.join(str(a >> s & 255) for s in (24, 16, 8, 0)), port, secret, role)

    def display(self, code):
        out = C.create_string_buffer(20)
        self.lib.format(code.encode(), out)
        return out.value.decode()

    def test_codes_round_trip_in_an_unambiguous_alphabet(self):
        cases = [("86.81.7.200", 48222, 123456, 0), ("1.2.3.4", 1, 1, 1),
                 ("223.255.255.255", 65535, 999999, 1), ("100.64.0.9", 50123, 500000, 0)]
        for case in cases:
            code = self.encode(*case)
            self.assertEqual(len(code), 16)
            self.assertTrue(set(code) <= set(ALPHABET), code)
            self.assertFalse(set(code) & set("01OI"))
            shown = self.display(code)
            self.assertEqual(shown, "-".join(code[i:i + 4] for i in range(0, 16, 4)))
            for text in (code, shown, shown.lower(), " ".join(shown.split("-"))):
                self.assertEqual(self.decode(text), case)

    def test_the_address_is_not_readable_from_the_code(self):
        first = self.encode("86.81.7.200", 48222, 123456, 0)
        second = self.encode("86.81.7.200", 48222, 123457, 0)
        # The endpoint characters change with the secret, so equal IPs do not share a prefix.
        self.assertNotEqual(first[:9], second[:9])
        self.assertNotEqual(self.encode("86.81.7.200", 48222, 123456, 1), first)

    def test_invalid_codes_and_values_are_refused(self):
        code = self.encode("86.81.7.200", 48222, 123456, 0)
        for text in ("", code[:15], code + "2", code[:15] + "0", code[:15] + "O", code[:15] + "I",
                     code[:15] + "1", code[:15] + "!"):
            self.assertIsNone(self.decode(text), text)
        for args in (("86.81.7.200", 48222, 0, 0), ("86.81.7.200", 48222, 1000000, 0),
                     ("86.81.7.200", 0, 5, 0), ("0.1.2.3", 1, 5, 0), ("224.0.0.1", 1, 5, 0),
                     ("86.81.7.200", 1, 5, 2)):
            self.assertIsNone(self.encode(*args), args)

    def test_single_character_typos_are_caught(self):
        accepted = total = 0
        for case in [("86.81.7.200", 48222, 123456, 0), ("203.0.113.7", 50123, 4242, 1),
                     ("192.0.2.1", 48222, 999999, 0)]:
            code = self.encode(*case)
            for position in range(16):
                for symbol in ALPHABET:
                    if symbol == code[position]:
                        continue
                    total += 1
                    accepted += self.decode(code[:position] + symbol + code[position + 1:]) is not None
        self.assertLess(accepted / total, 0.005, (accepted, total))

    def test_punch_table_is_sized_by_max_peers(self):
        lib = self.lib
        self.assertEqual(lib.maxPeers(), 2)
        lib.reset(0, 4242, 0)
        self.assertEqual(lib.add(0, ip("198.51.100.9"), 50123, 1), 0)
        self.assertEqual(lib.add(0, ip("198.51.100.9"), 50123, 1), 0)
        self.assertEqual(lib.add(0, ip("198.51.100.10"), 50123, 1), -1)
        lib.reset(0, 4242, 0)
        self.assertEqual(lib.add(0, ip("198.51.100.9"), 50123, 0), -1)  # own participant
        self.assertEqual(lib.add(0, ip("198.51.100.9"), 50123, 2), -1)  # beyond MAX_PEERS

    def test_punch_packets_and_timing(self):
        lib = self.lib
        lib.reset(0, 4242, 1)
        packet = (C.c_ubyte * 16)()
        self.assertEqual(lib.due(0, 0, 0, packet), 0)  # empty slot
        lib.add(0, ip("203.0.113.7"), 48222, 0)
        self.assertEqual(lib.due(0, 0, 5000, packet), 12)
        self.assertEqual(bytes(packet[:12]), b"MSP1" + (4242).to_bytes(4, "big") + bytes((1, 0, 0, 0)))
        self.assertEqual(lib.due(0, 0, 5199, packet), 0)
        self.assertEqual(lib.due(0, 0, 5200, packet), 12)
        self.assertEqual(lib.due(0, 1, 5200, packet), 0)  # out of range

    def test_receive_opens_only_with_the_room_pin(self):
        lib = self.lib
        host, joiner = ip("203.0.113.7"), ip("198.51.100.9")
        lib.reset(1, 4242, 1)
        lib.add(1, host, 48222, 0)
        packet = (C.c_ubyte * 12)()
        lib.reset(0, 4242, 0)
        lib.add(0, joiner, 50123, 1)
        lib.due(0, 0, 0, packet)
        self.assertEqual(lib.receive(1, host, 48222, packet, 12, 10, 0), 1)
        self.assertEqual(lib.state(1, 0), 2)
        self.assertTrue(lib.open(1))
        # The reply now says "I hear you".
        reply = (C.c_ubyte * 12)()
        lib.due(1, 0, 10, reply)
        self.assertEqual(reply[9], 1)
        # Wrong PIN, other sender, bad flags and non-punch data.
        lib.reset(1, 4243, 1)
        lib.add(1, host, 48222, 0)
        self.assertEqual(lib.receive(1, host, 48222, packet, 12, 10, 1), 1)
        self.assertEqual(lib.state(1, 0), 1)
        lib.reset(1, 4242, 1)
        self.assertEqual(lib.receive(1, host, 48222, packet, 12, 10, 0), 1)
        self.assertEqual(lib.state(1, 0), 0)
        bad = (C.c_ubyte * 12)(*packet)
        bad[9] = 2
        self.assertEqual(lib.receive(1, host, 48222, bad, 12, 10, 1), 1)
        self.assertEqual(lib.state(1, 0), 0)
        msr = (C.c_ubyte * 32)(0x4d, 0x53, 0x52, 0x31)
        self.assertEqual(lib.receive(1, host, 48222, msr, 32, 10, 1), 0)
        self.assertEqual(lib.receive(1, host, 48222, packet, 11, 10, 1), 0)
        # Adoption: an unknown sender with the PIN becomes a peer.
        self.assertEqual(lib.receive(1, host, 48222, packet, 12, 10, 1), 1)
        self.assertEqual((lib.state(1, 0), lib.peerPort(1, 0), lib.participant(1, 0)), (2, 48222, 0))

    def run_nat(self, host_nat, joiner_nat, swap=True, seconds=5):
        """Two players behind NATs. 'cone' keeps one public port for every destination;
        'symmetric' maps each destination to a new port. A public port admits a source only
        after the inside player sent to that source from it, except 'fullcone', which admits anyone."""
        lib = self.lib
        public_ip = [ip("203.0.113.7"), ip("198.51.100.9")]
        nat = [host_nat, joiner_nat]
        mappings = [{}, {}]
        allowed = [set(), set()]

        def public(node, destination):
            key = destination if nat[node] == "symmetric" else None
            if key not in mappings[node]:
                mappings[node][key] = 40000 + 1000 * node + len(mappings[node])
            return public_ip[node], mappings[node][key]

        stun = [public(node, ("stun", 3478)) for node in (0, 1)]
        lib.reset(0, 777, 0)
        lib.reset(1, 777, 1)
        lib.add(1, *stun[0], 0)            # the joiner entered the host's code
        if swap:
            lib.add(0, *stun[1], 1)        # the host entered the joiner's code
        packet = (C.c_ubyte * 12)()
        for now in range(0, seconds * 1000, 50):
            for node in (0, 1):
                if not lib.state(node, 0) or not lib.due(node, 0, now, packet):
                    continue
                target = (lib.peerIp(node, 0), lib.peerPort(node, 0))
                source = public(node, target)
                allowed[node].add((source[1], target))
                other = 1 - node
                if target[0] != public_ip[other] or target[1] not in mappings[other].values():
                    continue
                if nat[other] != "fullcone" and (target[1], source) not in allowed[other]:
                    continue
                lib.receive(other, *source, packet, 12, now, int(other == 0))
            if lib.open(0) and lib.open(1):
                return now
        return None

    def test_hole_punching_needs_endpoint_independent_mapping(self):
        self.assertIsNotNone(self.run_nat("cone", "cone"))
        # A full-cone host learns a symmetric joiner's real port from its punch.
        self.assertIsNotNone(self.run_nat("fullcone", "symmetric"))
        self.assertIsNone(self.run_nat("cone", "symmetric"))
        self.assertIsNone(self.run_nat("symmetric", "cone"))
        self.assertIsNone(self.run_nat("symmetric", "symmetric"))

    def test_two_player_host_has_nobody_to_forward(self):
        lib = self.lib
        lib.reset(0, 9, 0)
        lib.add(0, ip("198.51.100.9"), 50123, 1)
        packet = (C.c_ubyte * 64)()
        lib.due(0, 0, 0, packet)
        lib.reset(1, 9, 1)
        lib.add(1, ip("203.0.113.7"), 48222, 0)
        hello = (C.c_ubyte * 12)()
        lib.due(1, 0, 0, hello)
        lib.receive(0, ip("198.51.100.9"), 50123, hello, 12, 0, 1)
        self.assertEqual(lib.state(0, 0), 2)
        self.assertEqual(lib.roster(0, 0, packet), 0)

    def test_four_player_host_collects_joiners_and_forwards_them(self):
        lib = self.lib4
        self.assertEqual(lib.maxPeers(), 4)
        host = ip("203.0.113.7")
        joiners = [(ip("198.51.100.%d" % n), 50000 + n) for n in (1, 2, 3)]
        lib.reset(0, 31337, 0)
        punch = (C.c_ubyte * 12)()
        for number, (address, port) in enumerate(joiners, 1):
            lib.reset(number, 31337, number)
            lib.add(number, host, 48222, 0)
            lib.due(number, 0, 0, punch)
            self.assertEqual(lib.receive(0, address, port, punch, 12, 0, 1), 1)  # one-code adoption
        self.assertEqual([lib.state(0, i) for i in range(3)], [2, 2, 2])
        self.assertEqual([lib.participant(0, i) for i in range(3)], [1, 2, 3])
        self.assertEqual(lib.add(0, ip("192.0.2.99"), 1, 1), -1)  # room full
        roster = (C.c_ubyte * 64)()
        size = lib.roster(0, 0, roster)
        self.assertEqual(size, 12 + 2 * 8)
        self.assertEqual(bytes(roster[:12]), b"MSP1" + (31337).to_bytes(4, "big") + bytes((0, 2, 2, 0)))
        self.assertEqual(bytes(roster[12:20]), bytes((198, 51, 100, 2)) + (50002).to_bytes(2, "big") + bytes((2, 0)))
        # Joiner 1 only trusts the roster once the host path is open.
        self.assertEqual(lib.receive(1, host, 48222, roster, size, 0, 0), 1)
        self.assertEqual([lib.state(1, i) for i in range(3)], [1, 0, 0])
        reply = (C.c_ubyte * 12)()
        lib.reset(0 + 3, 31337, 0)  # a stand-in host table for the reply
        lib.add(3, joiners[0][0], joiners[0][1], 1)
        lib.due(3, 0, 0, reply)
        lib.receive(1, host, 48222, reply, 12, 0, 0)
        self.assertEqual(lib.state(1, 0), 2)
        self.assertEqual(lib.receive(1, ip("192.0.2.1"), 48222, roster, size, 0, 0), 1)  # stranger
        self.assertEqual([lib.state(1, i) for i in range(3)], [2, 0, 0])
        self.assertEqual(lib.receive(1, host, 48222, roster, size - 1, 0, 0), 1)  # torn
        self.assertEqual([lib.state(1, i) for i in range(3)], [2, 0, 0])
        self.assertEqual(lib.receive(1, host, 48222, roster, size, 0, 0), 1)
        self.assertEqual([lib.state(1, i) for i in range(3)], [2, 1, 1])
        self.assertEqual([(lib.peerPort(1, i), lib.participant(1, i)) for i in (1, 2)], [(50002, 2), (50003, 3)])

    def test_one_code_join_needs_an_open_host_filter(self):
        # The host adopts the joiner's punch; without that, filtering needs both codes.
        self.assertIsNotNone(self.run_nat("fullcone", "cone", swap=False))
        self.assertIsNone(self.run_nat("cone", "cone", swap=False))

if __name__ == "__main__":
    unittest.main()
