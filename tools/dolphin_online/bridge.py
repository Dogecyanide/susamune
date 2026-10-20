#!/usr/bin/env python3
"""Windows companion for the bounded Moonshine Dolphin UDP mailbox."""
from __future__ import annotations

import argparse
import ctypes as C
import os
from pathlib import Path
import secrets
import socket
import struct
import sys
import time

BASE_OFFSET = 0x1901000
SIZE = 2784
MAGIC, ABI = 0x4D444C31, 1
GAME, HOST, COMMAND, INDICES, STATUS = 0, 32, 64, 96, 128
TX, RX, POSE, INFO = 160, 1312, 2464, 2752
WORDS = struct.Struct('>8I')
IDLE, OPENING, READY, RETIRING, FAILED = range(1, 6)
MASK = 0xFFFFFFFF
HOST_RANGES = ((HOST, 64), (STATUS, 160), (RX, 2464), (INFO, SIZE))


def checked_range(offset, length, writable=False):
    if offset < 0 or length < 0 or offset + length > SIZE:
        raise ValueError('Address outside Moonshine networking mailbox')
    if writable and not any(start <= offset and offset + length <= end for start, end in HOST_RANGES):
        raise ValueError('Companion cannot write a game-owned mailbox line')


def publication(memory, offset, size=32):
    first = memory.read(offset, 8)
    generation, issued = struct.unpack('>II', first)
    if not generation or generation != issued:
        return None
    data = memory.read(offset, size)
    return data if data[:8] == first and memory.read(offset, 8) == first else None


def game_identity(raw):
    if raw is None:
        return None
    generation, issued, magic, abi, region, instance, heartbeat, size = WORDS.unpack(raw)
    if (magic, abi, size) != (MAGIC, ABI, SIZE) or region not in (1, 2, 3) or not instance or not heartbeat:
        return None
    return region, instance, heartbeat


def host_identity(raw):
    words = WORDS.unpack(raw)
    return words[0], words[2], words[3]


def endpoint(raw):
    ip, port, reserved = struct.unpack('>4sHH', raw)
    if not port or reserved or not any(ip):
        raise ValueError('Invalid UDP endpoint')
    return socket.inet_ntoa(ip), port


def packet(raw, epoch, pose=False):
    words = struct.unpack_from('>4I', raw)
    found, length = words[2:4] if pose else words[:2]
    address = raw[16:24] if pose else raw[8:16]
    reserved = raw[24:32] if pose else raw[16:32]
    if found != epoch or not 0 < length <= 256 or any(reserved):
        raise ValueError('Invalid UDP mailbox packet')
    return endpoint(address), raw[32:32 + length]


class Bridge:
    """The only queues are the game's four slots and a replaceable latest pose."""
    def __init__(self, memory, clock=time.monotonic, socket_factory=socket.socket):
        self.memory, self.clock, self.socket_factory = memory, clock, socket_factory
        raw = publication(memory, GAME)
        identity = game_identity(raw)
        if identity is None:
            raise ValueError('No supported Moonshine Dolphin build is running')
        self.region, self.instance, self.game_heartbeat = identity
        self.game_seen = self.clock()
        self.generations = {offset: max(struct.unpack('>II', memory.read(offset, 8)))
                            for offset in (HOST, STATUS, INFO)}
        prior_epoch = WORDS.unpack(memory.read(HOST, 32))[3]
        self.epoch = secrets.randbelow(MASK - 1) + 1
        if self.epoch == prior_epoch:
            self.epoch = self.epoch % (MASK - 1) + 1
        self.state, self.ack, self.tx_read, self.rx_write, self.error = IDLE, 0, 0, 0, 0
        self.socket = None
        self.seen_generations = {}
        self.pose_seen = 0
        self.sent = self.received = self.dropped = self.send_errors = self.receive_errors = 0
        self.allowed = set()
        self.host_heartbeat = 0
        self.last_heartbeat = -100.0
        self.closed = False
        self.publish_status()
        self.heartbeat()

    def publish(self, offset, tail):
        current = self.generations[offset]
        if current == MASK:
            raise OverflowError('Mailbox generation exhausted; restart Dolphin')
        current += 1
        self.generations[offset] = current
        self.write(offset, struct.pack('>II', 0, current))
        self.write(offset + 8, tail)
        self.write(offset, struct.pack('>I', current))

    def write(self, offset, data):
        checked_range(offset, len(data), True)
        # Identity fields are immutable even while the heartbeat is withdrawn.
        identity = game_identity(self.memory.read(GAME, 32))
        if identity is None or identity[:2] != (self.region, self.instance):
            raise RuntimeError('Dolphin restarted; reconnect the companion')
        self.memory.write(offset, data)

    def publish_status(self):
        self.publish(STATUS, struct.pack('>6I', self.epoch, self.state, self.ack,
                                        self.tx_read, self.rx_write, self.error & MASK))

    def heartbeat(self):
        if self.host_heartbeat == MASK:
            raise OverflowError('Companion heartbeat exhausted; reconnect the companion')
        self.host_heartbeat += 1
        self.publish(HOST, struct.pack('>6I', self.instance, self.epoch, self.host_heartbeat, 0, 0, 0))
        self.last_heartbeat = self.clock()

    def retire(self, error=0):
        if self.socket:
            self.socket.close()
        self.socket = None
        self.allowed.clear()
        self.epoch += 1
        if self.epoch > MASK:
            raise OverflowError('Network epoch exhausted; restart companion')
        self.state, self.ack, self.tx_read, self.rx_write = IDLE, 0, 0, 0
        self.error = error
        self.pose_seen = 0
        self.write(INFO, bytes(4))
        self.publish_status()
        self.heartbeat()

    def close(self):
        if not self.closed:
            self.closed = True
            try:
                self.retire()
                self.write(HOST, bytes(4))
            finally:
                if self.socket:
                    self.socket.close()

    def read_game(self, offset, size=32):
        raw = publication(self.memory, offset, size)
        if raw is None:
            return None
        generation = struct.unpack_from('>I', raw)[0]
        previous = self.seen_generations.get(offset, 0)
        if generation < previous:
            self.seen_generations.clear()
            self.retire(-11003)
            return None
        self.seen_generations[offset] = generation
        return raw

    def open_socket(self, command):
        self.state, self.ack = OPENING, command[4]
        self.publish_status()
        try:
            self.socket = self.socket_factory(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setblocking(False)
            # Windows can surface an old ICMP error on the next unrelated recv.
            if hasattr(socket, 'SIO_UDP_CONNRESET'):
                self.socket.ioctl(socket.SIO_UDP_CONNRESET, False)
            self.socket.bind(('0.0.0.0', command[5]))
        except OSError as exc:
            if self.socket:
                self.socket.close()
            self.socket = None
            self.state, self.error = FAILED, -(exc.errno or 1)
            self.publish_status()
            return
        self.sent = self.received = self.dropped = self.send_errors = self.receive_errors = 0
        self.state, self.error = READY, 0
        self.publish_info()
        self.publish_status()

    def publish_info(self):
        # A relay client needs a source port, not a LAN address announcement.
        port = self.socket.getsockname()[1]
        counters = (min(self.sent, 65535) << 16) | min(self.received, 65535)
        flags = 0x01000000 | (min(self.dropped, 255) << 16) | (min(self.send_errors, 255) << 8) | min(self.receive_errors, 255)
        self.publish(INFO, struct.pack('>I4sHHIII', self.epoch, socket.inet_aton('127.0.0.1'),
                                       port, 0, counters, flags, self.error & MASK))

    def send(self, target, data):
        if target not in self.allowed and len(self.allowed) >= 8:
            self.retire(-11001)
            return False
        try:
            if self.socket.sendto(data, target) != len(data):
                return False
            self.allowed.add(target)
            self.sent += 1
            return True
        except BlockingIOError:
            return False
        except OSError as exc:
            self.send_errors += 1
            self.error = -(exc.errno or 1)
            return False

    def step(self):
        identity = game_identity(publication(self.memory, GAME))
        if identity is None:
            if self.clock() - self.game_seen > 3:
                raise RuntimeError('Game mailbox stopped; reconnect after the game boots')
            return  # A PPC publication can be withdrawn for this bounded poll.
        region, instance, heartbeat = identity
        if (region, instance) != (self.region, self.instance):
            raise RuntimeError('Dolphin restarted; reconnect the companion')
        now = self.clock()
        own = publication(self.memory, HOST)
        if own is None or host_identity(own) != (self.generations[HOST], self.instance, self.epoch):
            self.seen_generations.clear()
            self.retire(-11003)
            return
        if heartbeat < self.game_heartbeat:
            self.seen_generations.clear()
            self.retire(-11003)
        if heartbeat != self.game_heartbeat:
            self.game_heartbeat, self.game_seen = heartbeat, now
        if now - self.game_seen > 3:
            if self.state != IDLE:
                self.retire(-11004)
            return
        if now - self.last_heartbeat >= 0.1:
            self.heartbeat()
        raw_command = self.read_game(COMMAND)
        raw_indices = self.read_game(INDICES)
        if raw_command:
            command = WORDS.unpack(raw_command)
            if command[2] == self.epoch and command[4] != self.ack:
                if not command[4] or command[4] < self.ack or command[5] > 65535 or any(command[6:]):
                    self.retire(-11001)
                    return
                if command[3] == 2:
                    self.retire()
                    return
                if command[3] != 1 or self.state != IDLE:
                    self.retire(-11001)
                    return
                if not raw_indices:
                    return
                indices = WORDS.unpack(raw_indices)
                if indices[2] != self.epoch or any(indices[3:]):
                    self.retire(-11001)
                    return
                self.open_socket(command)
        if self.state != READY or not raw_indices:
            return
        indices = WORDS.unpack(raw_indices)
        if (indices[2] != self.epoch or any(indices[5:]) or
                (indices[3] - self.tx_read) & MASK > 4 or (self.rx_write - indices[4]) & MASK > 4):
            self.retire(-11001)
            return
        try:
            for _ in range(4):
                if self.tx_read == indices[3]:
                    break
                target, data = packet(self.memory.read(TX + (self.tx_read & 3) * 288, 288), self.epoch)
                if not self.send(target, data):
                    break
                self.tx_read = (self.tx_read + 1) & MASK
            if self.state != READY:
                return
            pose = self.read_game(POSE, 288)
            if pose and struct.unpack_from('>I', pose, 8)[0] == self.epoch:
                generation = struct.unpack_from('>I', pose)[0]
                if generation != self.pose_seen:
                    target, data = packet(pose, self.epoch, pose=True)
                    if self.send(target, data):
                        self.pose_seen = generation
        except ValueError:
            self.retire(-11001)
            return
        if self.state != READY:
            return
        for _ in range(16):
            try:
                data, sender = self.socket.recvfrom(257)
            except BlockingIOError:
                break
            except OSError as exc:
                self.receive_errors += 1
                self.error = -(exc.errno or 1)
                break
            if sender not in self.allowed or not 0 < len(data) <= 256 or (self.rx_write - indices[4]) & MASK == 4:
                self.dropped += 1
                continue
            out = struct.pack('>II4sHH4I', self.epoch, len(data), socket.inet_aton(sender[0]), sender[1], 0, 0, 0, 0, 0)
            self.write(RX + (self.rx_write & 3) * 288, out + data.ljust(256, b'\0'))
            self.rx_write = (self.rx_write + 1) & MASK
            self.received += 1
        self.publish_info()
        self.publish_status()


class WindowsMemory:
    def __init__(self, pid):
        if os.name != 'nt' or C.sizeof(C.c_void_p) != 8:
            raise RuntimeError('This prototype needs 64-bit Python on Windows')
        self.kernel = C.WinDLL('kernel32', use_last_error=True)
        self.kernel.OpenProcess.argtypes = [C.c_ulong, C.c_bool, C.c_ulong]
        self.kernel.OpenProcess.restype = C.c_void_p
        self.kernel.CloseHandle.argtypes = [C.c_void_p]
        self.kernel.ReadProcessMemory.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_size_t, C.c_void_p]
        self.kernel.WriteProcessMemory.argtypes = self.kernel.ReadProcessMemory.argtypes
        self.kernel.VirtualQueryEx.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_size_t]
        self.kernel.VirtualQueryEx.restype = C.c_size_t
        self.kernel.QueryFullProcessImageNameW.argtypes = [C.c_void_p, C.c_ulong, C.c_wchar_p, C.POINTER(C.c_ulong)]
        self.kernel.CreateMutexW.argtypes = [C.c_void_p, C.c_bool, C.c_wchar_p]
        self.kernel.CreateMutexW.restype = C.c_void_p
        self.handle = self.kernel.OpenProcess(0x438 | 0x1000, False, pid)
        self.lock = None
        if not self.handle:
            raise OSError(C.get_last_error(), 'Cannot open the selected Dolphin process')
        try:
            path, length = C.create_unicode_buffer(32768), C.c_ulong(32768)
            if not self.kernel.QueryFullProcessImageNameW(self.handle, 0, path, C.byref(length)):
                raise OSError(C.get_last_error(), 'Cannot verify Dolphin executable')
            if Path(path.value).name.lower() not in ('dolphin.exe', 'dolphin-x64.exe', 'dolphinqt2.exe'):
                raise ValueError('Selected PID is not a supported Dolphin executable')
            self.lock = self.kernel.CreateMutexW(None, False, f'Local\\MoonshineDolphinOnline-{pid}')
            if not self.lock or C.get_last_error() == 183:
                raise RuntimeError('A companion is already attached to this Dolphin process')
            self.base = self.find_mailbox()
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
        if self.lock:
            self.kernel.CloseHandle(self.lock)
            self.lock = None

    def raw_read(self, address, size, required=True):
        buffer, received = C.create_string_buffer(size), C.c_size_t()
        if not self.kernel.ReadProcessMemory(self.handle, address, buffer, size, C.byref(received)) or received.value != size:
            if required:
                raise OSError(C.get_last_error(), 'Dolphin memory is unavailable; restart companion after the game boots')
            return None
        return buffer.raw

    def find_mailbox(self):
        class Info(C.Structure):
            _fields_ = [('base', C.c_void_p), ('allocation', C.c_void_p), ('aprotect', C.c_ulong),
                        ('size', C.c_size_t), ('state', C.c_ulong), ('protect', C.c_ulong), ('kind', C.c_ulong)]
        address = 0
        candidates = set()
        while address < 0x7FFFFFFFFFFF:
            info = Info()
            if not self.kernel.VirtualQueryEx(self.handle, address, C.byref(info), C.sizeof(info)):
                break
            base = int(info.base or 0)
            if info.state == 0x1000 and info.protect & 0xFF in (4, 8, 0x40, 0x80) and info.size >= 0x2000000:
                candidate = base + BASE_OFFSET
                raw = self.raw_read(candidate, 32, False)
                if raw and raw[:4] == raw[4:8] and game_identity(raw):
                    candidates.add(candidate)
            address = base + info.size
        if not candidates:
            raise RuntimeError('No supported Moonshine online build found. Boot the matching Dolphin build first.')
        # Dolphin may map the same fake-VMEM backing more than once.
        first = min(candidates)
        identities = [game_identity(self.raw_read(other, 32)) for other in candidates]
        if any(identity is None for identity in identities) or len({identity[:2] for identity in identities}) != 1:
            raise RuntimeError('Ambiguous Dolphin memory mapping; stop other emulation sessions')
        return first

    def read(self, offset, length):
        checked_range(offset, length)
        return self.raw_read(self.base + offset, length)

    def write(self, offset, data):
        checked_range(offset, len(data), True)
        written = C.c_size_t()
        if not self.kernel.WriteProcessMemory(self.handle, self.base + offset, data, len(data), C.byref(written)) or written.value != len(data):
            raise OSError(C.get_last_error(), 'Dolphin networking mailbox write failed')


def dolphin_pids():
    import subprocess
    output = subprocess.check_output(['tasklist', '/FO', 'CSV', '/NH'], text=True, creationflags=0x08000000)
    import csv
    return [int(row[1]) for row in csv.reader(output.splitlines())
            if row and row[0].lower() in ('dolphin.exe', 'dolphin-x64.exe', 'dolphinqt2.exe')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, help='Dolphin process ID; automatic when only one is running')
    args = parser.parse_args()
    memory = bridge = None
    try:
        pids = [args.pid] if args.pid else dolphin_pids()
        if len(pids) != 1:
            raise RuntimeError('Run one Dolphin instance, or select its PID with --pid NUMBER')
        memory = WindowsMemory(pids[0])
        bridge = Bridge(memory)
        print(f'Connected to Moonshine ({("JP", "US", "PAL")[bridge.region - 1]}). Keep this window open.', flush=True)
        print('Enter the same relay server address/port as your Wii friend, then Create or Join room.', flush=True)
        while True:
            bridge.step()
            time.sleep(0.005)
    except KeyboardInterrupt:
        print('\nDisconnected.')
    except (OSError, ValueError, RuntimeError, OverflowError) as exc:
        print(f'Connection stopped: {exc}', file=sys.stderr)
        return 1
    finally:
        if bridge:
            try:
                bridge.close()
            except (OSError, RuntimeError, OverflowError):
                pass
        if memory:
            memory.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
