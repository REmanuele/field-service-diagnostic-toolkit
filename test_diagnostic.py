import unittest
from unittest.mock import patch
import subprocess
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
    @patch('diagnostic.run_command',return_value=(True,'2 received\n'))
    def test_ping_success(self, _):
        self.assertTrue(d.check_ping().startswith('OK'))
    @patch('diagnostic.run_command',return_value=(False,'Command not found: ping'))
    def test_ping_unavailable(self, _):
        self.assertIn('Command not found', d.check_ping())
    @patch('diagnostic.run_command',return_value=(True,'active'))
    def test_service_active(self, _):
        self.assertEqual(d.check_service('nginx'), 'nginx: active')
    @patch('diagnostic.run_command',return_value=(False,'inactive'))
    def test_service_inactive(self, _):
        self.assertEqual(d.check_service('nginx'), 'nginx: inactive')
    @patch('diagnostic.run_command',return_value=(False,'systemd unavailable'))
    def test_service_unavailable(self, _):
        self.assertEqual(d.check_service('nginx'), 'nginx: systemd unavailable')
    @patch('diagnostic.socket.gethostbyname',side_effect=OSError('DNS lookup failed'))
    def test_dns_failure_does_not_crash(self, _):
        self.assertTrue(d.check_dns().startswith('FAILED'))
    @patch('diagnostic.socket.gethostbyname',return_value='192.0.2.1')
    def test_dns_success(self, _):
        self.assertTrue(d.check_dns().startswith('OK'))
    @patch('diagnostic.check_ping',return_value='FAILED (ICMP blocked)')
    @patch('diagnostic.check_dns',return_value='OK (github.com -> 192.0.2.1)')
    @patch('diagnostic.read_ip_addresses',return_value=['192.0.2.10'])
    @patch('diagnostic.read_default_gateway',return_value='default via 192.0.2.1')
    @patch('diagnostic.read_dns_servers',return_value=['192.0.2.1'])
    def test_report_distinguishes_icmp_from_internet(self,*mocks):
        report=d.build_report([])
        self.assertIn('DNS resolution: OK',report)
        self.assertIn('ICMP reachability (1.1.1.1): FAILED (ICMP blocked)', report)
        self.assertNotIn('Internet connectivity:', report)
    def test_disk_and_memory_functions(self):
        self.assertTrue(d.read_disk_usage().strip())
        self.assertTrue(d.read_memory_usage().strip())

    @patch('diagnostic.build_report', return_value='example report\n')
    @patch('diagnostic.Path.mkdir')
    @patch('diagnostic.Path.write_text', side_effect=PermissionError('permission denied'))
    def test_report_save_permission_error(self, mock_write, mock_mkdir, mock_report):
        from io import StringIO
        with patch('sys.argv', ['diagnostic.py', '--output', 'reports/report.txt']):
            with patch('sys.stderr', new_callable=StringIO) as stderr:
                with patch('builtins.print'):
                    with self.assertRaises(SystemExit) as raised:
                        d.main()
        self.assertEqual(raised.exception.code, 1)
        self.assertIn('Error saving report', stderr.getvalue())
        self.assertIn('permission denied', stderr.getvalue())
        mock_write.assert_called_once()

if __name__ == '__main__': unittest.main()
