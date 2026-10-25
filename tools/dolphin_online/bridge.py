#!/usr/bin/env python3
"""Windows/Linux companion for the bounded Moonshine Dolphin UDP mailbox."""
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
LINUX_DOLPHINS = ('dolphin-emu', 'dolphin-emu-nogui', 'dolphin-emu-qt2')


class MailboxNotFound(RuntimeError):
    pass


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


def route_address(target):
    # Query the route without sending a datagram or connecting the game socket.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(target)
            return probe.getsockname()[0]
    except OSError:
        return '0.0.0.0'


class ConnectionLog:
    """Bounded summaries; room secrets and packet payloads are never written."""
    LIMIT = 4 * 1024 * 1024

    def __init__(self, folder, clock=time.monotonic):
        self.clock, self.file, self.path, self.error = clock, None, None, None
        self.written, self.streams, self.last_state = 0, {}, None
        self.sample_at = self.flush_at = self.step_at = clock()
        self.max_step_gap = 0.0
        try:
            folder = Path(folder)
            folder.mkdir(parents=True, exist_ok=True)
            self.path = folder / f'connection_{time.strftime("%Y%m%d_%H%M%S")}_{secrets.token_hex(4)}.log'
            self.file = self.path.open('x', encoding='utf-8', newline='\n')
            self.write('Moonshine PR32 Dolphin connection log; clock=monotonic_seconds protocol=7')
        except OSError as exc:
            self.error = str(exc)

    def write(self, line):
        if not self.file:
            return
        line += '\n'
        if self.written + len(line.encode('utf-8')) > self.LIMIT:
            self.close()
            return
        try:
            self.file.write(line)
            self.written += len(line.encode('utf-8'))
        except OSError as exc:
            self.error = str(exc)
            self.close()

    def event(self, name, **fields):
        self.write(f'{self.clock():.6f} {name} ' + ' '.join(f'{k}={v}' for k, v in fields.items()))

    def packet(self, direction, peer, data):
        if not self.file or len(data) < 32 or data[:6] != b'MSR1\x00\x07':
            return
        kind, size = data[6], struct.unpack_from('>H', data, 8)[0]
        if size != len(data) - 32:
            return
        sequence, round_id = struct.unpack_from('>I', data, 12)[0], struct.unpack_from('>I', data, 24)[0]
        if kind not in (3, 11):
            names = {1: 'hello', 2: 'accept', 4: 'ping', 5: 'pong', 6: 'leave',
                     7: 'ready', 8: 'start', 9: 'result', 10: 'ack'}
            self.event(direction, peer=f'{peer[0]}:{peer[1]}', kind=names.get(kind, kind),
                       seq=sequence, round=round_id, bytes=len(data), kick=int(kind == 6 and data[32:] == b'\x01'))
            return
        key, now = (direction, peer), self.clock()
        if key not in self.streams:
            if len(self.streams) == 12:
                del self.streams[min(self.streams, key=lambda k: self.streams[k]['last'])]
            self.streams[key] = dict(count=0, last=now, gap=0.0)
        stream = self.streams[key]
        stream.update(count=stream['count'] + 1, gap=max(stream['gap'], now - stream['last']),
                      last=now, seq=sequence, kind=kind, poses=[])
        if kind == 3 and size in (48, 56):
            stream['poses'] = [(data[30], sequence, data[32:])]
        elif kind == 11 and size >= 4 and data[32] <= 3 and size == 4 + data[32] * 56:
            for at in range(36, len(data), 56):
                stream['poses'].append((data[at], struct.unpack_from('>I', data, at + 4)[0], data[at + 8:at + 56]))

    def sample(self, host):
        now = self.clock()
        self.max_step_gap = max(self.max_step_gap, now - self.step_at)
        self.step_at = now
        state = host.epoch, host.state, host.error
        if state != self.last_state:
            self.event('transport', epoch=host.epoch, state=host.state, error=host.error, region=host.region)
            self.last_state = state
        if now - self.sample_at < 1:
            return
        self.sample_at = now
        self.event('stats', tx=host.sent, rx=host.received, drop=host.dropped,
                   err_tx=host.send_errors, err_rx=host.receive_errors, tx_q=host.tx_queued,
                   rx_q=(host.rx_write - host.rx_consumed) & MASK, controls=len(host.rx_controls),
                   poses=len(host.rx_poses), replace_rx=host.rx_coalesced, ppc_rx=host.rx_consumed,
                   poll_gap_ms=round(self.max_step_gap * 1000), heartbeat_age_ms=round((now - host.game_seen) * 1000))
        self.max_step_gap = 0.0
        for (direction, peer), stream in self.streams.items():
            self.event('poses', direction=direction, peer=f'{peer[0]}:{peer[1]}', count=stream['count'],
                       seq=stream['seq'], kind=stream['kind'], max_gap_ms=round(stream['gap'] * 1000),
                       age_ms=round((now - stream['last']) * 1000))
            for player, sequence, pose in stream['poses']:
                self.event('member', direction=direction, peer_port=peer[1], player=player, seq=sequence,
                           remote_ms=struct.unpack_from('>I', pose, 4)[0], scene=struct.unpack_from('>I', pose, 8)[0],
                           area=pose[:4].hex(), visible=pose[37])
            stream['count'], stream['gap'] = 0, 0.0
        if self.file and now - self.flush_at >= 5:
            try:
                self.file.flush()
                self.flush_at = now
            except OSError as exc:
                self.error = str(exc)
                self.close()

    def close(self):
        file, self.file = self.file, None
        if file:
            try:
                file.close()
            except OSError as exc:
                self.error = str(exc)


class Bridge:
    """Ordered controls and one replaceable movement update per peer."""
    def __init__(self, memory, clock=time.monotonic, socket_factory=socket.socket, address_resolver=route_address, logger=None):
        self.logger = logger
        self.memory, self.clock, self.socket_factory = memory, clock, socket_factory
        self.address_resolver, self.local_address = address_resolver, '0.0.0.0'
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
        self.rx_consumed = self.rx_coalesced = self.tx_queued = 0
        self.rx_poses, self.rx_controls, self.rx_prefer_pose = {}, [], False
        self.sent = self.received = self.dropped = self.send_errors = self.receive_errors = 0
        self.allowed = set()
        self.host_heartbeat = 0
        self.last_heartbeat = -100.0
        self.closed = False
        self.publish_status()
        self.heartbeat()

    def flush_receive(self, indices):
        while ((self.rx_write - indices[4]) & MASK) < 4:
            if self.rx_poses and (self.rx_prefer_pose or not self.rx_controls):
                sender = next(iter(self.rx_poses))
                data = self.rx_poses.pop(sender)
                self.rx_prefer_pose = False
            elif self.rx_controls:
                sender, data = self.rx_controls.pop(0)
                self.rx_prefer_pose = True
            else:
                break
            out = struct.pack('>II4sHH4I', self.epoch, len(data), socket.inet_aton(sender[0]), sender[1], 0, 0, 0, 0, 0)
            self.write(RX + (self.rx_write & 3) * 288, out + data.ljust(256, b'\0'))
            if self.logger:
                self.logger.packet('deliver_rx', sender, data)
            self.rx_write = (self.rx_write + 1) & MASK

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
        if self.logger:
            self.logger.event('retire', epoch=self.epoch, error=error)
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
        self.rx_consumed = self.rx_coalesced = self.tx_queued = 0
        self.rx_poses, self.rx_controls, self.rx_prefer_pose = {}, [], False
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
            self.local_address = self.address_resolver(('1.1.1.1', 53))
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
        port = self.socket.getsockname()[1]
        counters = (min(self.sent, 65535) << 16) | min(self.received, 65535)
        flags = 0x01000000 | (min(self.dropped, 255) << 16) | (min(self.send_errors, 255) << 8) | min(self.receive_errors, 255)
        self.publish(INFO, struct.pack('>I4sHHIII', self.epoch, socket.inet_aton(self.local_address),
                                       port, 0, counters, flags, self.error & MASK))

    def send(self, target, data):
        if target not in self.allowed and len(self.allowed) >= 8:
            self.retire(-11001)
            return False
        try:
            if self.socket.sendto(data, target) != len(data):
                return False
            if target not in self.allowed:
                address = self.address_resolver(target)
                if address != '0.0.0.0' and not address.startswith('127.'):
                    self.local_address = address
            self.allowed.add(target)
            self.sent += 1
            if self.logger:
                self.logger.packet('socket_tx', target, data)
            return True
        except BlockingIOError:
            return False
        except OSError as exc:
            self.send_errors += 1
            self.error = -(exc.errno or 1)
            return False

    def step(self):
        try:
            self._step()
        finally:
            if self.logger:
                self.logger.sample(self)

    def _step(self):
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
        self.tx_queued = (indices[3] - self.tx_read) & MASK
        self.rx_consumed = indices[4]
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
        self.flush_receive(indices)
        for _ in range(32):
            try:
                data, sender = self.socket.recvfrom(257)
            except BlockingIOError:
                break
            except OSError as exc:
                self.receive_errors += 1
                self.error = -(exc.errno or 1)
                break
            if sender not in self.allowed or not 0 < len(data) <= 256:
                self.dropped += 1
                continue
            if self.logger:
                self.logger.packet('socket_rx', sender, data)
            movement = (len(data) >= 32 and data[:6] == b'MSR1\x00\x07' and
                        data[6] in (3, 11) and struct.unpack_from('>H', data, 8)[0] == len(data) - 32)
            if movement:
                if sender in self.rx_poses or len(self.rx_poses) < 3:
                    if sender in self.rx_poses:
                        self.rx_coalesced += 1
                    self.rx_poses[sender] = data
                else:
                    self.dropped += 1
            else:
                if len(self.rx_controls) == 4:
                    self.flush_receive(indices)
                if len(self.rx_controls) < 4:
                    self.rx_controls.append((sender, data))
                else:
                    self.dropped += 1
            self.received += 1
        self.flush_receive(indices)
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
            raise MailboxNotFound('No supported Moonshine online build found. Boot the matching Dolphin build first.')
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


def linux_mappings(text):
    """Only readable, writable views large enough for Dolphin's fake VMEM."""
    for row in text.splitlines():
        columns = row.split(None, 5)
        if len(columns) < 5 or columns[1][:2] != 'rw':
            continue
        try:
            start, end = (int(v, 16) for v in columns[0].split('-'))
        except ValueError:
            continue
        if 0 <= start < end and end - start >= 0x2000000:
            yield start, end


class LinuxMemory:
    def __init__(self, pid):
        if not sys.platform.startswith('linux') or C.sizeof(C.c_void_p) != 8:
            raise RuntimeError('Linux requires a 64-bit Python process')
        if pid <= 0:
            raise ValueError('Invalid Dolphin process ID')
        self.proc = self.handle = self.lock = None
        try:
            self.proc = os.open(f'/proc/{pid}', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            if os.fstat(self.proc).st_uid != os.getuid():
                raise PermissionError('Run the companion as the same user as Dolphin')
            executable = Path(os.readlink('exe', dir_fd=self.proc)).name
            if executable not in LINUX_DOLPHINS:
                raise ValueError(f'Selected PID runs {executable}, not a supported native Dolphin executable')
            self.acquire_lock(pid)
            # The open descriptor belongs to this address space, not a reused PID.
            try:
                self.handle = os.open('mem', os.O_RDWR | os.O_CLOEXEC, dir_fd=self.proc)
            except PermissionError as exc:
                raise PermissionError(
                    'Linux blocked access to Dolphin. Close Dolphin and start it through '
                    'the companion: bash start-linux.sh --launch dolphin-emu -e "/path/to/patched.iso". '
                    'Use the same user; no sudo or security-setting changes are needed '
                    'with the usual parent/child policy.') from exc
            self.base = self.find_mailbox()
        except BaseException:
            self.close()
            raise

    def acquire_lock(self, pid):
        import fcntl
        import stat
        folder = Path('/tmp') / f'moonshine-dolphin-{os.getuid()}'
        folder.mkdir(mode=0o700, exist_ok=True)
        directory = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            info = os.fstat(directory)
            if info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise PermissionError('Companion lock directory must belong to you and be private')
            self.lock = os.open(f'{pid}.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                                0o600, dir_fd=directory)
            info = os.fstat(self.lock)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
                raise PermissionError('Invalid companion lock file')
            try:
                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError('A companion is already attached to this Dolphin process') from exc
        finally:
            os.close(directory)
        # Keep the file after unlocking: unlinking allows two different lock inodes.

    def close(self):
        for name in ('handle', 'lock', 'proc'):
            descriptor = getattr(self, name, None)
            if descriptor is not None:
                os.close(descriptor)
                setattr(self, name, None)

    def raw_read(self, address, size, required=True):
        try:
            data = os.pread(self.handle, size, address)
            if len(data) == size:
                return data
        except OSError:
            if required:
                raise
        if required:
            raise RuntimeError('Dolphin memory is unavailable; reconnect after the game boots')
        return None

    def find_mailbox(self):
        descriptor = os.open('maps', os.O_RDONLY | os.O_CLOEXEC, dir_fd=self.proc)
        with os.fdopen(descriptor) as stream:
            mappings = list(linux_mappings(stream.read()))
        candidates = set()
        for start, end in mappings:
            candidate = start + BASE_OFFSET
            if candidate + SIZE > end:
                continue
            raw = self.raw_read(candidate, 32, False)
            if raw and raw[:4] == raw[4:8] and game_identity(raw):
                candidates.add(candidate)
        if not candidates:
            raise MailboxNotFound('No supported Moonshine online build found. Boot the matching Dolphin build first.')
        identities = [game_identity(self.raw_read(address, 32)) for address in candidates]
        if any(identity is None for identity in identities) or len({identity[:2] for identity in identities}) != 1:
            raise RuntimeError('Ambiguous Dolphin memory mapping; restart emulation')
        return min(candidates)

    def read(self, offset, length):
        checked_range(offset, length)
        return self.raw_read(self.base + offset, length)

    def write(self, offset, data):
        checked_range(offset, len(data), True)
        if os.pwrite(self.handle, data, self.base + offset) != len(data):
            raise RuntimeError('Dolphin networking mailbox write failed')


def dolphin_pids():
    if sys.platform.startswith('linux'):
        found = []
        for process in Path('/proc').iterdir():
            if not process.name.isdecimal():
                continue
            try:
                if process.stat().st_uid == os.getuid() and Path(os.readlink(process/'exe')).name in LINUX_DOLPHINS:
                    found.append(int(process.name))
            except OSError:
                continue
        return sorted(found)
    if os.name != 'nt':
        raise RuntimeError('This companion supports Windows and Linux')
    import subprocess
    output = subprocess.check_output(['tasklist', '/FO', 'CSV', '/NH'], text=True, creationflags=0x08000000)
    import csv
    return [int(row[1]) for row in csv.reader(output.splitlines())
            if row and row[0].lower() in ('dolphin.exe', 'dolphin-x64.exe', 'dolphinqt2.exe')]


def linux_launch_pids(root_pid):
    """Follow only this launch's children, including Flatpak/desktop wrappers."""
    pending, visited, found = [root_pid], set(), []
    while pending and len(visited) < 128:
        pid = pending.pop()
        if pid in visited:
            continue
        visited.add(pid)
        process = Path('/proc') / str(pid)
        try:
            if process.stat().st_uid != os.getuid():
                continue
            if Path(os.readlink(process/'exe')).name in LINUX_DOLPHINS:
                found.append(pid)
            for task in (process/'task').iterdir():
                pending.extend(int(p) for p in (task/'children').read_text().split())
        except (OSError, ValueError):
            continue
    return sorted(found)


def launch_linux(command):
    import subprocess
    if not sys.platform.startswith('linux'):
        raise ValueError('--launch is for native Linux Dolphin')
    if not command:
        raise ValueError('Example: --launch dolphin-emu -e "/path/to/patched.iso"')
    print('Starting Dolphin. Boot the matching Moonshine game; waiting up to three minutes...', flush=True)
    process = subprocess.Popen(command, start_new_session=True)
    deadline = time.monotonic() + 180
    while process.poll() is None and time.monotonic() < deadline:
        candidates = linux_launch_pids(process.pid)
        if len(candidates) > 1:
            raise RuntimeError('This launcher started multiple Dolphins; start only one game')
        if candidates:
            try:
                return LinuxMemory(candidates[0])
            except (MailboxNotFound, ProcessLookupError, FileNotFoundError):
                pass
            except PermissionError as exc:
                raise PermissionError(
                    'Found Dolphin, but Linux or its application sandbox blocked memory access. '
                    'Try a native distro Dolphin through --launch as the same user. '
                    'Do not use sudo or disable system security settings.') from exc
        time.sleep(0.5)
    raise RuntimeError('Launcher exited or no matching Moonshine game booted within three minutes. '
                       'Use the native Dolphin executable if the launcher hands off to another service.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--pid', type=int, help='Dolphin process ID; automatic when only one is running')
    selection.add_argument('--launch', nargs=argparse.REMAINDER,
                           help='Linux: start native Dolphin as a child, followed by its arguments')
    args = parser.parse_args()
    memory = bridge = logger = None
    try:
        if C.sizeof(C.c_void_p) != 8:
            raise RuntimeError('64-bit Python is required')
        if args.launch is not None:
            memory = launch_linux(args.launch)
        else:
            pids = [args.pid] if args.pid is not None else dolphin_pids()
            if len(pids) != 1:
                raise RuntimeError('Run one Dolphin instance, or select its PID with --pid NUMBER')
            memory = LinuxMemory(pids[0]) if sys.platform.startswith('linux') else WindowsMemory(pids[0])
        logger = ConnectionLog(Path(__file__).resolve().parent / 'connection-logs')
        bridge = Bridge(memory, logger=logger)
        if logger.file:
            print(f'Connection log: {logger.path}', flush=True)
        else:
            print(f'Connection logging unavailable: {logger.error}', file=sys.stderr)
        print(f'Connected to Moonshine ({("JP", "US", "PAL")[bridge.region - 1]}). Keep this window open.', flush=True)
        print('Create or Join room in Online, then exchange friend codes at BOTH ends.', flush=True)
        while True:
            bridge.step()
            time.sleep(0.005)
    except KeyboardInterrupt:
        print('\nDisconnected.')
    except (OSError, ValueError, RuntimeError, OverflowError) as exc:
        if logger:
            logger.event('stopped', error=str(exc))
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
        if logger:
            logger.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
