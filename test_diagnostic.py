import os
import stat
import subprocess
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import diagnostic as d


class TestToolkit(unittest.TestCase):
    @patch('diagnostic.subprocess.run')
    def test_run_command_success(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(['a'], 0, stdout='ok\n', stderr='')
        self.assertEqual(d.run_command(['a']), (True, 'ok'))

    @patch('diagnostic.subprocess.run', side_effect=FileNotFoundError())
    def test_missing_command_graceful(self, _):
        self.assertEqual(d.run_command(['absent'])[0], False)

    @patch('diagnostic.subprocess.run', side_effect=subprocess.TimeoutExpired(cmd=['ping'], timeout=5))
    def test_timeout_graceful(self, _):
        self.assertEqual(d.run_command(['ping'])[0], False)

    @patch('diagnostic.run_command', return_value=(True, '2 received\n'))
    def test_ping_success(self, _):
        self.assertTrue(d.check_ping().startswith('OK'))

    @patch('diagnostic.run_command', return_value=(False, 'Command not found: ping'))
    def test_ping_unavailable(self, _):
        self.assertIn('Command not found', d.check_ping())

    @patch('diagnostic.run_command', return_value=(True, 'active'))
    def test_service_active(self, _):
        self.assertEqual(d.check_service('nginx'), 'nginx: active')

    @patch('diagnostic.run_command', return_value=(False, 'inactive'))
    def test_service_inactive(self, _):
        self.assertEqual(d.check_service('nginx'), 'nginx: inactive')

    @patch('diagnostic.run_command', return_value=(False, 'systemd unavailable'))
    def test_service_unavailable(self, _):
        self.assertEqual(d.check_service('nginx'), 'nginx: systemd unavailable')

    @patch('diagnostic.socket.gethostbyname', side_effect=OSError('DNS lookup failed'))
    def test_dns_failure_does_not_crash(self, _):
        self.assertTrue(d.check_dns().startswith('FAILED'))

    @patch('diagnostic.socket.gethostbyname', return_value='192.0.2.1')
    def test_dns_success(self, _):
        self.assertTrue(d.check_dns().startswith('OK'))

    @patch('diagnostic.check_ping', return_value='FAILED (ICMP blocked)')
    @patch('diagnostic.check_dns', return_value='OK (github.com -> 192.0.2.1)')
    @patch('diagnostic.read_ip_addresses', return_value=['192.0.2.10'])
    @patch('diagnostic.read_default_gateway', return_value='default via 192.0.2.1')
    @patch('diagnostic.read_dns_servers', return_value=['192.0.2.1'])
    def test_report_distinguishes_icmp_from_internet(self, *mocks):
        report = d.build_report([])
        self.assertIn('DNS resolution: OK', report)
        self.assertIn('ICMP reachability (1.1.1.1): FAILED (ICMP blocked)', report)
        self.assertNotIn('Internet connectivity:', report)

    def test_disk_and_memory_functions(self):
        self.assertTrue(d.read_disk_usage().strip())
        self.assertTrue(d.read_memory_usage().strip())

    @patch('diagnostic.build_report', return_value='example report\n')
    @patch('diagnostic.save_report_private', side_effect=PermissionError('permission denied'))
    def test_report_save_permission_error(self, mock_save, mock_report):
        with patch.object(sys, 'argv', ['diagnostic.py', '--output', 'reports/report.txt']):
            with patch('sys.stderr', new_callable=StringIO) as stderr:
                with patch('builtins.print'):
                    with self.assertRaises(SystemExit) as raised:
                        d.main()
        self.assertEqual(raised.exception.code, 1)
        self.assertIn('Error saving report', stderr.getvalue())
        self.assertIn('permission denied', stderr.getvalue())
        mock_save.assert_called_once()

    @patch('diagnostic.socket.gethostname', return_value='secret-host')
    @patch('diagnostic.read_ip_addresses', return_value=['192.168.77.5', '10.8.0.1', 'fd00::1234', 'fe80::1%eth0'])
    @patch('diagnostic.read_default_gateway', return_value='default via 192.168.77.1 dev eth0')
    @patch('diagnostic.read_dns_servers', return_value=['10.8.0.53', 'fd00::53'])
    @patch('diagnostic.check_dns', return_value='OK (intranet.customer.local -> 10.8.0.53)')
    @patch('diagnostic.check_ping', return_value='FAILED (secret-host/192.168.77.5 unreachable)')
    @patch('diagnostic.check_service', return_value='billing-secret.service: inactive')
    def test_redacted_report_does_not_leak_identifiers(self, *mocks):
        report = d.build_report(['billing-secret.service'], redact=True)
        for secret in ['secret-host', '192.168.77.', '10.8.0.', 'fd00:', 'fe80:',
                       'intranet.customer.local', 'billing-secret', 'eth0', 'customer.local']:
            self.assertNotIn(secret, report)
        self.assertIn('Hostname: [REDACTED]', report)
        self.assertIn('IPv4=2, IPv6=2', report)
        self.assertIn('DNS servers: 2 configured', report)
        self.assertIn('service-1: inactive', report)
        self.assertIn('ICMP reachability: FAILED', report)

    @patch('diagnostic.read_ip_addresses', return_value=['192.0.2.5'])
    @patch('diagnostic.read_default_gateway', return_value='not detected')
    @patch('diagnostic.read_dns_servers', return_value=[])
    @patch('diagnostic.check_dns', return_value='FAILED (private exception 10.3.4.5)')
    @patch('diagnostic.check_ping', return_value='OK (10.3.4.5)')
    def test_redacted_report_strips_command_errors(self, *mocks):
        report = d.build_report([], redact=True)
        self.assertNotIn('10.3.4.5', report)
        self.assertIn('DNS resolution: FAILED', report)
        self.assertIn('ICMP reachability: OK', report)
        self.assertIn('Default gateway: not detected', report)

    @patch('diagnostic.check_service', return_value='sensitive@customer.service: error host 192.0.2.3')
    def test_redacted_unrecognized_service_error_is_hidden(self, _):
        self.assertEqual(d._service_status_only('sensitive@customer.service'), 'unknown')

    def test_redacted_service_allowed_states(self):
        for state in ['active', 'inactive', 'failed', 'activating']:
            with patch('diagnostic.check_service', return_value=f'srv: {state}'):
                self.assertEqual(d._service_status_only('srv'), state)

    def test_ip_version_count_handles_zone_ids_and_bad_values(self):
        self.assertEqual(d._ip_version_counts(['192.0.2.3', 'fd00::1', 'fe80::1%eth0', 'bad']), (1, 2, 1))

    def test_private_report_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'private' / 'report.txt'
            d.save_report_private(target, 'hello\n')
            self.assertEqual(target.read_text(encoding='utf-8'), 'hello\n')
            self.assertEqual(list(target.parent.glob('.diagnostic-*.tmp')), [])
            if os.name == 'posix':
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(target.parent.stat().st_mode), 0o700)

    def test_private_replace_fixes_world_readable_existing_file(self):
        if os.name != 'posix':
            self.skipTest('POSIX permissions')
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'report.txt'
            target.write_text('old')
            target.chmod(0o644)
            d.save_report_private(target, 'private')
            self.assertEqual(target.read_text(), 'private')
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)

    def test_private_report_replaces_symlink_not_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'destination.txt'
            dest.write_text('do not change')
            target = Path(tmp) / 'report.txt'
            try:
                target.symlink_to(dest)
            except (OSError, NotImplementedError):
                self.skipTest('Cannot create symlinks')
            d.save_report_private(target, 'new report')
            self.assertEqual(dest.read_text(), 'do not change')
            self.assertFalse(target.is_symlink())
            self.assertEqual(target.read_text(), 'new report')

    def test_redacted_and_full_report_are_different(self):
        with patch('diagnostic.read_ip_addresses', return_value=['192.0.2.3']):
            with patch('diagnostic.check_dns', return_value='OK (github.com -> 192.0.2.2)'):
                full = d.build_report([])
                redacted = d.build_report([], redact=True)
        self.assertIn('192.0.2.3', full)
        self.assertNotIn('192.0.2.3', redacted)

    @patch('diagnostic.build_report', return_value='sanitized')
    @patch('diagnostic.save_report_private')
    def test_cli_redact_parameter(self, save_mock, build_mock):
        with patch.object(sys, 'argv', ['diagnostic.py', '--redact', '--output', 'test.txt']):
            with patch('builtins.print'):
                self.assertEqual(d.main(), 0)
        self.assertEqual(build_mock.call_args.kwargs, {'redact': True})
        save_mock.assert_called_once_with(Path('test.txt'), 'sanitized')


if __name__ == '__main__':
    unittest.main()
