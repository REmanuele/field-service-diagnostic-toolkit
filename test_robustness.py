"""Regression tests for v0.3 error handling (no external dependencies)."""

import subprocess
import unittest
from unittest.mock import patch

import diagnostic as d


class RobustnessTests(unittest.TestCase):
    @patch("diagnostic.subprocess.run", side_effect=PermissionError(13, "Permission denied"))
    def test_command_permission_denied_returns_failure(self, _):
        ok, message = d.run_command(["ping"])
        self.assertFalse(ok)
        self.assertIn("Could not execute ping", message)

    @patch("diagnostic.subprocess.run", side_effect=UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid byte"))
    def test_command_undecodable_output_returns_failure(self, _):
        ok, message = d.run_command(["hostname"])
        self.assertFalse(ok)
        self.assertIn("Unable to decode", message)

    @patch("diagnostic.Path.read_text", side_effect=FileNotFoundError("missing resolv.conf"))
    def test_missing_resolver_config_returns_empty_list(self, _):
        self.assertEqual(d.read_dns_servers(), [])

    @patch("diagnostic.Path.read_text", side_effect=PermissionError("permission denied"))
    def test_unreadable_resolver_config_returns_empty_list(self, _):
        self.assertEqual(d.read_dns_servers(), [])

    @patch("diagnostic.Path.read_text", side_effect=UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid byte"))
    def test_undecodable_resolver_config_returns_empty_list(self, _):
        self.assertEqual(d.read_dns_servers(), [])

    @patch("diagnostic.Path.read_text", return_value=(
        "# comment\n nameserver 192.0.2.53\n"
        "nameserverx 198.51.100.1\n"
        "nameserver fd00::53\n"
        "search example.test\n"
        "nameserver\n"
    ))
    def test_resolver_parser_ignores_other_directives(self, _):
        self.assertEqual(d.read_dns_servers(), ["192.0.2.53", "fd00::53"])

    @patch("diagnostic.Path.read_text", return_value="MemTotal: 4096 kB\n")
    def test_missing_memavailable_returns_unknown(self, _):
        self.assertEqual(d.read_memory_usage(), "unknown")

    @patch("diagnostic.Path.read_text", return_value="MemTotal: 4096 kB\nMemAvailable: 8192 kB\n")
    def test_impossible_memory_values_return_unknown(self, _):
        self.assertEqual(d.read_memory_usage(), "unknown")

    @patch("diagnostic.Path.read_text", return_value="MemTotal: 4096 kB\nMemAvailable: 2048 kB\n")
    def test_valid_memory_values_still_calculate(self, _):
        self.assertIn("50.0%", d.read_memory_usage())

    @patch("diagnostic.read_ip_addresses", return_value=["192.0.2.10"])
    @patch("diagnostic.read_default_gateway", return_value="not detected")
    @patch("diagnostic.check_dns", return_value="FAILED (private hostname)")
    @patch("diagnostic.check_ping", return_value="FAILED (private network)")
    @patch("diagnostic.Path.read_text", side_effect=PermissionError("denied"))
    @patch("diagnostic.run_command", return_value=(False, "unavailable"))
    def test_redacted_report_survives_unreadable_resolver(self, *_):
        report = d.build_report([], redact=True)
        self.assertIn("DNS servers: 0 configured", report)
        self.assertIn("Hostname: [REDACTED]", report)
        self.assertNotIn("private hostname", report)
        self.assertNotIn("192.0.2.10", report)


if __name__ == "__main__":
    unittest.main()
