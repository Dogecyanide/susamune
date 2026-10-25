#!/usr/bin/env python3
"""Bounded two-player UDP relay. It never simulates the game or waits for inputs."""
from __future__ import annotations

import argparse
from collections import OrderedDict
from dataclasses import dataclass, field
import errno
import hmac
import logging
import secrets
import socket
import struct
import time

HEADER = struct.Struct('!4sBBBBIQ16sQHH')
OPEN, CHALLENGE, PROVE, WELCOME, KEEPALIVE, STATUS, DATA, LEAVE, ERROR = range(1, 10)
HOST, PEER_READY = 1, 2
NO_ROOM, ROOM_FULL, SERVER_BUSY, ROOM_CLOSED, PEER_LEFT, LOBBY_EXPIRED = range(3, 9)
ZERO_TOKEN = bytes(16)


@dataclass(frozen=True)
class Packet:
    kind: int
    flags: int
    room: int
    nonce: int
    token: bytes = ZERO_TOKEN
    generation: int = 0
    payload: bytes = b''

    def encode(self):
        return HEADER.pack(b'MSL1', 1, self.kind, self.flags, 0, self.room,
                           self.nonce, self.token, self.generation, len(self.payload), 0) + self.payload

    @staticmethod
    def decode(data):
        if not 48 <= len(data) <= 256:
            return None
        magic, version, kind, flags, reserved, room, nonce, token, generation, size, tail = HEADER.unpack_from(data)
        if (magic != b'MSL1' or version != 1 or not OPEN <= kind <= ERROR or
                flags & ~3 or reserved or tail or room > 999999 or not nonce or len(data) != 48 + size):
            return None
        return Packet(kind, flags, room, nonce, token, generation, data[48:])


@dataclass
class Bucket:
    credits: float
    updated: float

    def take(self, now, rate, capacity):
        self.credits = min(capacity, self.credits + max(0, now - self.updated) * rate)
        self.updated = now
        if self.credits < 1:
            return False
        self.credits -= 1
        return True


@dataclass
class Member:
    endpoint: tuple[str, int]
    nonce: int
    host: bool
    requested_room: int
    token: bytes
    room: int
    generation: int
    seen: float
    expires: float = 0
    error: int = 0
    traffic: Bucket = field(default_factory=lambda: Bucket(90, 0))


@dataclass
class Room:
    code: int
    generation: int
    created: float
    host: Member
    guest: Member | None = None


class Relay:
    MAX_ROOMS = 64
    MAX_MEMBERS = 256  # Includes short-lived tombstones for idempotent retries.
    MAX_IP_BUCKETS = 1024
    MEMBER_TIMEOUT = 15
    ROOM_LIFETIME = 30 * 60
    TOMBSTONE_SECONDS = 70  # Outlast both accepted challenge time buckets.

    def __init__(self, *, secret=None):
        self.secret = secret or secrets.token_bytes(32)
        self.rooms = {}
        self.members = {}
        self.ips = OrderedDict()
        self.global_traffic = Bucket(4000, 0)
        self.next_sweep = 0

    def _cookie(self, endpoint, p, bucket):
        identity = socket.inet_aton(endpoint[0]) + struct.pack('!HQBII', endpoint[1], p.nonce,
                                                             p.flags & HOST, p.room, bucket)
        return struct.pack('!I', bucket) + hmac.digest(self.secret, identity, 'sha256')[:12]

    def _proof(self, endpoint, p, now):
        bucket = struct.unpack_from('!I', p.token)[0]
        current = int(now // 30)
        return bucket in (current, current - 1) and hmac.compare_digest(p.token, self._cookie(endpoint, p, bucket))

    def _packet(self, member, kind, payload=b'', ready=False):
        return Packet(kind, (HOST if member.host else 0) | (PEER_READY if ready else 0),
                      member.room, member.nonce, member.token, member.generation, payload)

    def _close(self, room, now, error):
        self.rooms.pop(room.code, None)
        out = []
        for m in (room.host, room.guest):
            if m is not None:
                m.error = error
                m.expires = now + self.TOMBSTONE_SECONDS
                out.append((m.endpoint, self._packet(m, ERROR, struct.pack('!I', error)).encode()))
        return out

    def sweep(self, now):
        out = []
        if now < self.next_sweep:
            return out
        self.next_sweep = now + 1
        for room in list(self.rooms.values()):
            if room.guest is None and now - room.created >= self.ROOM_LIFETIME:
                out.extend(self._close(room, now, LOBBY_EXPIRED))
            elif any(m is not None and now - m.seen >= self.MEMBER_TIMEOUT for m in (room.host, room.guest)):
                out.extend(self._close(room, now, PEER_LEFT))
        for key, m in list(self.members.items()):
            if m.error and now >= m.expires:
                del self.members[key]
        return out

    def _rate(self, endpoint, now, opening):
        if not self.global_traffic.take(now, 2000, 4000):
            return False
        ip = endpoint[0]
        if ip not in self.ips:
            if len(self.ips) == self.MAX_IP_BUCKETS:
                self.ips.popitem(last=False)
            self.ips[ip] = (Bucket(180, now), Bucket(8, now))
        buckets = self.ips[ip]
        self.ips.move_to_end(ip)
        return buckets[0].take(now, 120, 180) and (not opening or buckets[1].take(now, 4, 8))

    def _error(self, endpoint, p, error):
        return [(endpoint, Packet(ERROR, p.flags & HOST, p.room, p.nonce, p.token,
                                  0, struct.pack('!I', error)).encode())]

    @staticmethod
    def _inner_valid(payload, host):
        if not 32 <= len(payload) <= 208 or payload[:4] != b'MSR1':
            return False
        return (payload[4:6] in (b'\x00\x01', b'\x00\x02', b'\x00\x03') and 1 <= payload[6] <= 10 and
                payload[7] == 0 and payload[10:12] == b'\x00\x00' and payload[31] == 0 and
                int.from_bytes(payload[8:10], 'big') == len(payload) - 32 and
                payload[28] < 3 and payload[29] == 1 and payload[30] == (0 if host else 1))

    def handle(self, data, endpoint, now):
        """Return at most four datagrams, never to an unproven third-party address."""
        p = Packet.decode(data)
        if p is None or p.flags & PEER_READY or not self._rate(endpoint, now, p.kind in (OPEN, PROVE)):
            return []
        host = bool(p.flags & HOST)
        if p.kind in (OPEN, PROVE):
            if p.payload or p.generation or (p.room != 0 if host else not 100000 <= p.room <= 999999):
                return []
            if p.kind == OPEN:
                if p.token != ZERO_TOKEN:
                    return []
                token = self._cookie(endpoint, p, int(now // 30))
                return [(endpoint, Packet(CHALLENGE, p.flags, p.room, p.nonce, token).encode())]
            if not self._proof(endpoint, p, now):
                return []
            key = (endpoint, p.nonce)
            m = self.members.get(key)
            retired = []
            if m is not None:
                if m.host != host or m.requested_room != p.room:
                    return []
                if m.error:
                    return self._error(endpoint, p, ROOM_CLOSED)
                # A duplicate proof must never allocate another room or identity.
                m.seen = now
                room = self.rooms[m.room]
            else:
                if len(self.members) >= self.MAX_MEMBERS:
                    return self._error(endpoint, p, SERVER_BUSY)
                # A fresh proof owns this endpoint even if its old LEAVE was lost.
                previous = next((x for x in self.members.values()
                                 if x.endpoint == endpoint and not x.error), None)
                if previous is not None:
                    retired = self._close(self.rooms[previous.room], now, PEER_LEFT)
                if host and len(self.rooms) >= self.MAX_ROOMS:
                    return retired + self._error(endpoint, p, SERVER_BUSY)
                room = None if host else self.rooms.get(p.room)
                if not host and room is None:
                    return retired + self._error(endpoint, p, NO_ROOM)
                if room is not None and room.guest is not None:
                    return retired + self._error(endpoint, p, ROOM_FULL)
                if host:
                    code = 100000 + secrets.randbelow(900000)
                    while code in self.rooms:
                        code = 100000 + secrets.randbelow(900000)
                    generation = secrets.randbits(64) or 1
                else:
                    code, generation = room.code, room.generation
                m = Member(endpoint, p.nonce, host, p.room, secrets.token_bytes(16), code, generation, now)
                m.traffic.updated = now
                self.members[key] = m
                if host:
                    room = Room(code, generation, now, m)
                    self.rooms[code] = room
                else:
                    room.guest = m
            ready = room.guest is not None
            out = retired + [(endpoint, self._packet(m, WELCOME, p.token, ready).encode())]
            if ready:
                other = room.guest if host else room.host
                out.append((other.endpoint, self._packet(other, STATUS, ready=True).encode()))
            return out

        if p.kind not in (KEEPALIVE, DATA, LEAVE):
            return []
        m = self.members.get((endpoint, p.nonce))
        if (m is None or m.host != host or m.room != p.room or m.generation != p.generation or
                not hmac.compare_digest(m.token, p.token)):
            return []
        if (p.kind == DATA and not self._inner_valid(p.payload, host)) or (p.kind != DATA and p.payload):
            return []
        if not m.traffic.take(now, 60, 90):
            return []
        if m.error:
            return [(endpoint, self._packet(m, ERROR, struct.pack('!I', m.error)).encode())]
        m.seen = now
        room = self.rooms[m.room]
        if p.kind == LEAVE:
            return self._close(room, now, PEER_LEFT)
        ready = room.guest is not None
        if p.kind == KEEPALIVE:
            return [(endpoint, self._packet(m, STATUS, ready=ready).encode())]
        if not ready:
            return []
        other = room.guest if host else room.host
        # Replace credentials, so neither console learns its peer's endpoint/token.
        return [(other.endpoint, self._packet(other, DATA, p.payload, ready=True).encode())]


class Diagnostics:
    INTERVAL = 5
    FIELDS = ('rx', 'malformed', 'open', 'prove', 'rx_data', 'tx',
              'challenge', 'welcome', 'error', 'tx_data', 'send_fail', 'recv_error')

    def __init__(self, enabled=False, now=0):
        self.enabled = enabled
        self.next_report = now + self.INTERVAL
        self.counts = dict.fromkeys(self.FIELDS, 0)

    def received(self, data):
        if not self.enabled:
            return
        self.counts['rx'] += 1
        packet = Packet.decode(data)
        if packet is None:
            self.counts['malformed'] += 1
        elif packet.kind in (OPEN, PROVE, DATA):
            self.counts[{OPEN: 'open', PROVE: 'prove', DATA: 'rx_data'}[packet.kind]] += 1

    def sent(self, payload):
        if not self.enabled:
            return
        self.counts['tx'] += 1
        kind = payload[5]
        if kind in (CHALLENGE, WELCOME, ERROR, DATA):
            self.counts[{CHALLENGE: 'challenge', WELCOME: 'welcome',
                         ERROR: 'error', DATA: 'tx_data'}[kind]] += 1

    def send_failed(self):
        if self.enabled:
            self.counts['send_fail'] += 1

    def receive_error(self, oversized=False):
        if self.enabled:
            self.counts['recv_error'] += 1
            if oversized:
                self.counts['rx'] += 1
                self.counts['malformed'] += 1

    def report(self, now, active_rooms):
        if not self.enabled or now < self.next_report:
            return
        # Fixed counters only; packet fields and endpoint identities never enter logs.
        logging.info('Relay diagnostics window=5s %s active_rooms=%d',
                     ' '.join(f'{name}={self.counts[name]}' for name in self.FIELDS), active_rooms)
        self.counts = dict.fromkeys(self.FIELDS, 0)
        self.next_report = now + self.INTERVAL


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind', default='0.0.0.0', help='IPv4 address to bind')
    parser.add_argument('--port', type=int, default=38400)
    parser.add_argument('--diagnostics', action='store_true',
                        help='log anonymous aggregate packet counters every five seconds')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be 1..65535')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    relay = Relay()
    diagnostics = Diagnostics(args.diagnostics, time.monotonic())
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 262144)
        sock.bind((args.bind, args.port))
        sock.settimeout(0.25)
        logging.info('Moonshine private relay listening on UDP %d; maximum %d rooms', args.port, relay.MAX_ROOMS)
        try:
            while True:
                now = time.monotonic()
                outgoing = relay.sweep(now)
                try:
                    data, endpoint = sock.recvfrom(257)
                except socket.timeout:
                    pass
                except (ConnectionResetError, ConnectionRefusedError):
                    # A UDP peer's unreachable port does not invalidate our socket.
                    diagnostics.receive_error()
                except OSError as error:
                    # Windows reports oversized datagrams instead of truncating them.
                    if error.errno not in (errno.EMSGSIZE, 10040):
                        raise
                    diagnostics.receive_error(oversized=True)
                else:
                    diagnostics.received(data)
                    outgoing.extend(relay.handle(data, endpoint, time.monotonic()))
                for destination, payload in outgoing:
                    try:
                        sock.sendto(payload, destination)
                        diagnostics.sent(payload)
                    except OSError:
                        # Client expiry handles transient network errors.
                        diagnostics.send_failed()
                diagnostics.report(time.monotonic(), len(relay.rooms))
        except KeyboardInterrupt:
            logging.info('Relay stopped')


if __name__ == '__main__':
    main()
