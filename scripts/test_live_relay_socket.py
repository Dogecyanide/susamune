"""Focused relay receive-loop checks for peer-generated UDP errors."""
import errno
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('moonshine_relay_socket', ROOT / 'tools/live_relay/server.py')
relay = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = relay
spec.loader.exec_module(relay)


class RelaySocketTests(unittest.TestCase):
    def test_diagnostics_are_aggregate_private_and_rate_bounded(self):
        diagnostics = relay.Diagnostics(True, 0)
        token = b'private-token!!!'
        nonce = 0xfedcba9876543210
        diagnostics.received(b'private malformed payload')
        for kind in (relay.OPEN, relay.PROVE, relay.DATA):
            diagnostics.received(relay.Packet(kind, relay.HOST, 765432, nonce, token).encode())
        for kind in (relay.CHALLENGE, relay.WELCOME, relay.ERROR, relay.DATA):
            diagnostics.sent(relay.Packet(kind, relay.HOST, 765432, nonce, token).encode())
        diagnostics.send_failed()
        diagnostics.receive_error(oversized=True)
        with patch.object(relay.logging, 'info') as log:
            for now in (0, 1, 4.99):
                diagnostics.report(now, 2)
            log.assert_not_called()
            diagnostics.report(5, 2)
            for now in (5, 5.1, 6, 9.99):
                diagnostics.report(now, 2)
            self.assertEqual(log.call_count, 1)
            first = log.call_args.args[0] % log.call_args.args[1:]
            for expected in ('rx=5', 'malformed=2', 'open=1', 'prove=1', 'rx_data=1',
                             'tx=4', 'challenge=1', 'welcome=1', 'error=1', 'tx_data=1',
                             'send_fail=1', 'recv_error=1', 'active_rooms=2'):
                self.assertIn(expected, first)
            for sensitive in ('private', '765432', str(nonce), token.hex()):
                self.assertNotIn(sensitive, first)
            diagnostics.report(10, 0)
            self.assertEqual(log.call_count, 2)
            idle = log.call_args.args[0] % log.call_args.args[1:]
            self.assertIn('rx=0 malformed=0 open=0 prove=0', idle)

    def test_diagnostics_socket_loop_counts_failures_and_idle_windows(self):
        endpoint = ('192.0.2.77', 41000)
        request = relay.Packet(relay.OPEN, relay.HOST, 0, 0x1122334455667788).encode()
        sock = MagicMock()
        sock.__enter__.return_value = sock
        sock.recvfrom.side_effect = [ConnectionResetError(10054, 'UDP reset'),
            (b'malformed secret', endpoint), (request, endpoint), (request, endpoint),
            relay.socket.timeout(), KeyboardInterrupt()]
        sock.sendto.side_effect = [OSError(errno.EHOSTUNREACH, 'Peer unreachable'), None]
        times = [0, 0, 1, 1, 2, 2, 2, 3, 3, 3, 4, 5, 5, 10, 10]
        with patch.object(sys, 'argv', ['server.py', '--diagnostics']), \
             patch.object(relay.socket, 'socket', return_value=sock), \
             patch.object(relay.time, 'monotonic', side_effect=times), \
             patch.object(relay.logging, 'basicConfig'), patch.object(relay.logging, 'info') as log:
            relay.main()
        lines = [call.args[0] % call.args[1:] for call in log.call_args_list
                 if call.args[0].startswith('Relay diagnostics')]
        self.assertEqual(len(lines), 2)
        for expected in ('rx=3', 'malformed=1', 'open=2', 'tx=1', 'challenge=1',
                         'send_fail=1', 'recv_error=1'):
            self.assertIn(expected, lines[0])
        self.assertIn('rx=0 malformed=0 open=0 prove=0', lines[1])
        for line in lines:
            self.assertNotIn(endpoint[0], line)
            self.assertNotIn(str(endpoint[1]), line)
            self.assertNotIn(str(0x1122334455667788), line)
            self.assertNotIn('secret', line)

    def test_disabled_diagnostics_skip_packet_inspection_and_logging(self):
        diagnostics = relay.Diagnostics()
        with patch.object(relay.Packet, 'decode') as decode, patch.object(relay.logging, 'info') as log:
            diagnostics.received(b'ignored')
            diagnostics.sent(b'ignored')
            diagnostics.send_failed()
            diagnostics.receive_error(oversized=True)
            diagnostics.report(100, 2)
            decode.assert_not_called()
            log.assert_not_called()

    def test_peer_errors_do_not_stop_the_next_valid_handshake(self):
        endpoint = ('127.0.0.1', 41000)
        request = relay.Packet(relay.OPEN, relay.HOST, 0, 123).encode()
        for error in (ConnectionResetError(10054, 'UDP reset'),
                      ConnectionRefusedError(errno.ECONNREFUSED, 'Port unreachable'),
                      OSError(10040, 'Windows oversized UDP'),
                      OSError(errno.EMSGSIZE, 'Oversized UDP')):
            with self.subTest(error=error):
                sock = MagicMock()
                sock.__enter__.return_value = sock
                sock.recvfrom.side_effect = [error, (request, endpoint), KeyboardInterrupt()]
                with patch.object(sys, 'argv', ['server.py']), \
                     patch.object(relay.socket, 'socket', return_value=sock), \
                     patch.object(relay.logging, 'basicConfig'), patch.object(relay.logging, 'info'):
                    relay.main()
                sock.sendto.assert_called_once()
                payload, destination = sock.sendto.call_args.args
                response = relay.Packet.decode(payload)
                self.assertEqual(destination, endpoint)
                self.assertEqual(response.kind, relay.CHALLENGE)
                self.assertEqual(response.nonce, 123)

    def test_local_socket_failure_is_not_hidden(self):
        sock = MagicMock()
        sock.__enter__.return_value = sock
        sock.recvfrom.side_effect = OSError(errno.EBADF, 'Local socket closed')
        with patch.object(sys, 'argv', ['server.py']), \
             patch.object(relay.socket, 'socket', return_value=sock), \
             patch.object(relay.logging, 'basicConfig'), patch.object(relay.logging, 'info'):
            with self.assertRaises(OSError) as failure:
                relay.main()
        self.assertEqual(failure.exception.errno, errno.EBADF)


if __name__ == '__main__':
    unittest.main()
