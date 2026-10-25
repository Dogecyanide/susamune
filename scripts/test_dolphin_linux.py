"""Native Linux process access using a mailbox fixture, without pretending it is Dolphin."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('linux_bridge', ROOT/'tools/dolphin_online/bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class MappingTests(unittest.TestCase):
    def test_only_complete_writable_views_are_candidates(self):
        text = '\n'.join((
            '10000000-12000000 rw-s 02040000 00:01 1 /memfd:dolphin-emu (deleted)',
            '20000000-22000000 r--s 02040000 00:01 1 /memfd:dolphin-emu (deleted)',
            '30000000-31000000 rw-p 00000000 00:00 0',
            '40000000-42000000 ---p 00000000 00:00 0',
            'broken rw-p 0 00:00 0'))
        self.assertEqual(list(bridge.linux_mappings(text)), [(0x10000000, 0x12000000)])

    def test_launch_keeps_arguments_separate_and_does_not_kill_dolphin_on_ctrl_c(self):
        class Process:
            pid = 123
            def poll(self): return None
        command = ['dolphin-emu', '-e', '/folder with spaces/test.iso']
        with patch.object(bridge.sys, 'platform', 'linux'), \
                patch('subprocess.Popen', return_value=Process()) as popen, \
                patch.object(bridge, 'linux_launch_pids', return_value=[123]), \
                patch.object(bridge, 'LinuxMemory', return_value='attached') as memory:
            self.assertEqual(bridge.launch_linux(command), 'attached')
            popen.assert_called_once_with(command, start_new_session=True)
            memory.assert_called_once_with(123)

    def test_waits_for_wrapper_to_start_dolphin_child(self):
        class Process:
            pid = 123
            def poll(self): return None
        with patch.object(bridge.sys, 'platform', 'linux'), \
                patch('subprocess.Popen', return_value=Process()), \
                patch.object(bridge, 'linux_launch_pids', side_effect=[[], [456]]), \
                patch.object(bridge.time, 'sleep'), \
                patch.object(bridge, 'LinuxMemory', return_value='attached') as memory:
            self.assertEqual(bridge.launch_linux(['flatpak', 'run', 'org.DolphinEmu.dolphin-emu']), 'attached')
            memory.assert_called_once_with(456)

    def test_multiple_children_and_sandbox_denial_are_explicit(self):
        class Process:
            pid = 123
            def poll(self): return None
        with patch.object(bridge.sys, 'platform', 'linux'), \
                patch('subprocess.Popen', return_value=Process()), \
                patch.object(bridge, 'linux_launch_pids', return_value=[456,789]), \
                patch.object(bridge, 'LinuxMemory') as memory:
            with self.assertRaisesRegex(RuntimeError, 'multiple Dolphins'):
                bridge.launch_linux(['launcher'])
            memory.assert_not_called()
        with patch.object(bridge.sys, 'platform', 'linux'), \
                patch('subprocess.Popen', return_value=Process()), \
                patch.object(bridge, 'linux_launch_pids', return_value=[456]), \
                patch.object(bridge, 'LinuxMemory', side_effect=PermissionError('sandbox')):
            with self.assertRaisesRegex(PermissionError, 'application sandbox'):
                bridge.launch_linux(['launcher'])


CHILD = r'''
import json, mmap, struct, sys, tempfile
offset, size = 0x1901000, 2784
backing = tempfile.TemporaryFile()
backing.truncate(0x4040000)
views = [mmap.mmap(backing.fileno(), 0x2000000, offset=0x2040000) for _ in range(2)]
mem = views[0]
mem[offset:offset+32] = struct.pack('>8I', 1, 1, 0x4D444C31, 1, 1, 123, 1, size)
print('ready', flush=True)
for line in sys.stdin:
    command = json.loads(line)
    if command['op'] == 'read':
        result = mem[offset+command['at']:offset+command['at']+command['size']].hex()
    elif command['op'] == 'write':
        data = bytes.fromhex(command['hex'])
        mem[offset+command['at']:offset+command['at']+len(data)] = data
        result = True
    elif command['op'] == 'ambiguous':
        different = mmap.mmap(-1, 0x2000000)
        different[offset:offset+32] = struct.pack('>8I', 1, 1, 0x4D444C31, 1, 1, 999, 1, size)
        views.append(different)
        result = True
    print(json.dumps(result), flush=True)
'''


@unittest.skipUnless(sys.platform.startswith('linux'), 'Requires the Linux kernel')
class NativeLinuxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='moonshine-linux-test-')
        self.addCleanup(self.temp.cleanup)
        self.executable = Path(self.temp.name)/'dolphin-emu'
        # The filename exercises process admission; this is only a synthetic mailbox.
        shutil.copy2(Path(sys.executable).resolve(), self.executable)
        self.executable.chmod(0o700)
        self.child = subprocess.Popen([str(self.executable), '-u', '-c', CHILD],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.stop_child)
        self.assertEqual(self.child.stdout.readline().strip(), 'ready')

    def stop_child(self):
        if self.child.poll() is None:
            self.child.terminate()
        self.child.communicate(timeout=5)

    def command(self, op, **values):
        self.child.stdin.write(json.dumps(dict(op=op, **values))+'\n')
        self.child.stdin.flush()
        return json.loads(self.child.stdout.readline())

    def memory(self):
        memory = bridge.LinuxMemory(self.child.pid)
        self.addCleanup(memory.close)
        return memory

    def publish(self, offset, generation, tail):
        data = struct.pack('>8I', generation, generation, *tail)
        self.command('write', at=offset, hex=data.hex())

    def test_detect_aliases_and_read_write_only_owned_ranges(self):
        self.assertIn(self.child.pid, bridge.dolphin_pids())
        memory = self.memory()
        self.assertEqual(bridge.game_identity(memory.read(0, 32)), (1, 123, 1))
        memory.write(bridge.STATUS, b'test')
        self.assertEqual(self.command('read', at=bridge.STATUS, size=4), b'test'.hex())
        for at in (bridge.GAME, bridge.COMMAND, bridge.TX, bridge.POSE, bridge.SIZE):
            with self.assertRaises(ValueError): memory.write(at, b'no')
        with self.assertRaises(ValueError): memory.read(-1, 32)

    def test_duplicate_lock_and_reconnect(self):
        memory = self.memory()
        with self.assertRaisesRegex(RuntimeError, 'already attached'):
            bridge.LinuxMemory(self.child.pid)
        memory.close()
        self.assertEqual(self.memory().read(0, 4), struct.pack('>I', 1))

    def test_wrong_executable_rejected(self):
        with self.assertRaisesRegex(ValueError, 'executable'):
            bridge.LinuxMemory(os.getpid())

    def test_restricted_sibling_gets_launch_instructions(self):
        policy = Path('/proc/sys/kernel/yama/ptrace_scope')
        if not policy.exists() or policy.read_text().strip() != '1' or os.getuid() == 0:
            self.skipTest('Requires unprivileged Yama parent/child policy')
        program = ('import sys; sys.path.insert(0, sys.argv[1]); import bridge\n'
                   'try: bridge.LinuxMemory(int(sys.argv[2]))\n'
                   'except PermissionError as e: print(e)\n'
                   'else: raise SystemExit(7)\n')
        result = subprocess.run([sys.executable, '-c', program,
                                 str(ROOT/'tools/dolphin_online'), str(self.child.pid)],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('start-linux.sh --launch', result.stdout)

    def test_real_launcher_waits_for_a_child_mailbox(self):
        processes = []
        real_popen = subprocess.Popen
        def start(*args, **kwargs):
            process = real_popen(*args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **kwargs)
            processes.append(process)
            return process
        code = 'import time; time.sleep(.2)\n' + CHILD.split('for line in sys.stdin:')[0] + '\ntime.sleep(30)\n'
        try:
            with patch('subprocess.Popen', side_effect=start):
                memory = bridge.launch_linux([str(self.executable), '-u', '-c', code])
            self.addCleanup(memory.close)
            self.assertEqual(bridge.game_identity(memory.read(0, 32)), (1, 123, 1))
        finally:
            for process in processes:
                process.terminate()
                process.communicate(timeout=5)

    def test_wrapper_launch_finds_grandchild_and_ignores_other_dolphin(self):
        processes = []
        real_popen = subprocess.Popen
        def start(*args, **kwargs):
            process = real_popen(*args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **kwargs)
            processes.append(process)
            return process
        code = CHILD.split('for line in sys.stdin:')[0] + '\nimport time; time.sleep(30)\n'
        command = ['/bin/sh', '-c', 'sleep .15; "$@" & wait', 'wrapper',
                   str(self.executable), '-u', '-c', code]
        try:
            with patch('subprocess.Popen', side_effect=start):
                memory = bridge.launch_linux(command)
            self.addCleanup(memory.close)
            found = bridge.linux_launch_pids(processes[0].pid)
            self.assertEqual(len(found), 1)
            self.assertNotIn(self.child.pid, found)
            self.assertEqual(bridge.game_identity(memory.read(0, 32)), (1, 123, 1))
        finally:
            for process in processes:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                process.communicate(timeout=5)

    def test_missing_and_ambiguous_mailboxes_fail_closed(self):
        self.command('write', at=0, hex=bytes(32).hex())
        with self.assertRaises(bridge.MailboxNotFound): self.memory()
        self.publish(0, 1, (bridge.MAGIC, bridge.ABI, 1, 123, 1, bridge.SIZE))
        self.command('ambiguous')
        with self.assertRaisesRegex(RuntimeError, 'Ambiguous'): self.memory()

    def test_process_exit_and_restarted_game_cannot_receive_writes(self):
        memory = self.memory()
        host = bridge.Bridge(memory)
        self.publish(0, 2, (bridge.MAGIC, bridge.ABI, 1, 456, 1, bridge.SIZE))
        before = self.command('read', at=bridge.HOST, size=32)
        with self.assertRaisesRegex(RuntimeError, 'restarted'): host.heartbeat()
        self.assertEqual(self.command('read', at=bridge.HOST, size=32), before)
        self.stop_child()
        with self.assertRaises((RuntimeError, OSError)): memory.read(0, 32)

    def test_udp_roundtrip_through_real_process_memory(self):
        memory = self.memory()
        host = bridge.Bridge(memory, address_resolver=lambda target: '127.0.0.1')
        self.addCleanup(host.close)
        self.publish(bridge.INDICES, 1, (host.epoch, 0, 0, 0, 0, 0))
        self.publish(bridge.COMMAND, 1, (host.epoch, 1, 1, 0, 0, 0))
        host.step()
        self.assertEqual(host.state, bridge.READY)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as remote:
            remote.bind(('127.0.0.1', 0))
            remote.settimeout(1)
            address = remote.getsockname()
            body = b'Linux to peer'
            packet = struct.pack('>II4sHH4I', host.epoch, len(body),
                                 socket.inet_aton(address[0]), address[1], 0, 0, 0, 0, 0)
            self.command('write', at=bridge.TX, hex=(packet+body.ljust(256, b'\0')).hex())
            self.publish(bridge.INDICES, 2, (host.epoch, 1, 0, 0, 0, 0))
            host.step()
            data, sender = remote.recvfrom(256)
            self.assertEqual(data, body)
            remote.sendto(b'peer to Linux', sender)
            for _ in range(100):
                host.step()
                if host.received: break
                time.sleep(.001)
            received = bytes.fromhex(self.command('read', at=bridge.RX, size=288))
            self.assertEqual(bridge.packet(received, host.epoch), (address, b'peer to Linux'))


if __name__ == '__main__':
    unittest.main()
