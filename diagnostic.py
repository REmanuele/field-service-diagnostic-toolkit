#!/usr/bin/env python3
"""Field Service Diagnostic Toolkit.

Read-only Linux host/network diagnostics with optional privacy-preserving reports.
No third-party Python dependencies.
"""

from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import os
import platform
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable


def run_command(command: list[str], timeout: int = 5) -> tuple[bool, str]:
    """Run a command and return success flag plus output."""
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = (completed.stdout or completed.stderr).strip()
        return completed.returncode == 0, output
    except FileNotFoundError:
        return False, f"Command not found: {command[0]}"
    except subprocess.TimeoutExpired:
        return False, f"Command timed out: {' '.join(command)}"
    except OSError as exc:
        # A present executable can still fail to start (e.g. permission denied).
        detail = exc.strerror or type(exc).__name__
        return False, f"Could not execute {command[0]}: {detail}"
    except UnicodeError:
        # subprocess.run(text=True) may be unable to decode a command's output.
        return False, f"Unable to decode command output: {command[0]}"


def read_uptime() -> str:
    try:
        seconds = float(Path("/proc/uptime").read_text().split()[0])
        return str(dt.timedelta(seconds=int(seconds)))
    except Exception:
        ok, output = run_command(["uptime", "-p"])
        return output if ok else "unknown"


def read_memory_usage() -> str:
    try:
        meminfo: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            meminfo[key] = int(value.strip().split()[0])
        total = meminfo.get("MemTotal", 0)
        available = meminfo.get("MemAvailable")
        if total <= 0 or available is None or not 0 <= available <= total:
            return "unknown"
        used_percent = (1 - available / total) * 100
        return f"{used_percent:.1f}% ({(total - available) / 1024:.0f} MB used / {total / 1024:.0f} MB total)"
    except Exception:
        return "unknown"


def read_disk_usage(path: str = "/") -> str:
    try:
        usage = shutil.disk_usage(path)
        used_percent = usage.used / usage.total * 100
        return f"{used_percent:.1f}% ({usage.used // (1024**3)} GB used / {usage.total // (1024**3)} GB total)"
    except Exception:
        return "unknown"


def read_ip_addresses() -> list[str]:
    ok, output = run_command(["hostname", "-I"])
    if ok and output:
        return output.split()
    try:
        return [socket.gethostbyname(socket.gethostname())]
    except Exception:
        return []


def read_default_gateway() -> str:
    ok, output = run_command(["ip", "route", "show", "default"])
    if not ok or not output:
        return "not detected"
    return output.splitlines()[0]


def read_dns_servers() -> list[str]:
    try:
        content = Path("/etc/resolv.conf").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        # Missing, unreadable or undecodable config must not abort diagnostics.
        return []
    servers = []
    for line in content.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0] == "nameserver":
            servers.append(parts[1])
    return servers


def check_dns(hostname: str = "github.com") -> str:
    try:
        ip = socket.gethostbyname(hostname)
        return f"OK ({hostname} -> {ip})"
    except Exception as exc:
        return f"FAILED ({exc})"


def check_ping(target: str = "1.1.1.1") -> str:
    ok, output = run_command(["ping", "-c", "2", "-W", "2", target], timeout=6)
    if ok:
        summary = output.splitlines()[-1] if output else "OK"
        return f"OK ({summary})"
    return f"FAILED ({output})"


def check_service(service: str) -> str:
    ok, output = run_command(["systemctl", "is-active", service])
    if ok:
        return f"{service}: active"
    return f"{service}: {output or 'not active'}"


def _service_status_only(service: str) -> str:
    """Allowlist a state without exposing potentially identifying service names/errors."""
    result = check_service(service)
    prefix = f"{service}: "
    if not result.startswith(prefix):
        return "unknown"
    raw_status = result[len(prefix):].strip().lower()
    known_statuses = {"active", "inactive", "failed", "activating", "deactivating", "reloading", "maintenance"}
    return raw_status if raw_status in known_statuses else "unknown"


def _ip_version_counts(addresses: Iterable[str]) -> tuple[int, int, int]:
    ipv4 = ipv6 = other = 0
    for address in addresses:
        try:
            version = ipaddress.ip_address(address.split("%", 1)[0]).version
        except ValueError:
            other += 1
        else:
            if version == 4:
                ipv4 += 1
            else:
                ipv6 += 1
    return ipv4, ipv6, other


def _outcome_only(message: str) -> str:
    """Drop all diagnostic command output and exception messages, which may include IPs."""
    if message.startswith("OK"):
        return "OK"
    if message.startswith("FAILED"):
        return "FAILED"
    return "unknown"


def build_report(services: Iterable[str], redact: bool = False) -> str:
    """Build a report; redacted mode uses an allowlist, not fragile IP substitutions.

    In redacted mode, hostnames, IP addresses, DNS values, gateway details,
    ping diagnostics and service identifiers are not included in the output.
    The caller must still review the resulting report before sharing it.
    """
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cpu_load = ", ".join(f"{value:.2f}" for value in os.getloadavg()) if hasattr(os, "getloadavg") else "unknown"
    dns_servers = read_dns_servers()

    if redact:
        v4, v6, unclassified = _ip_version_counts(read_ip_addresses())
        gateway_status = "configured" if read_default_gateway() != "not detected" else "not detected"
        service_lines = [f"service-{i}: {_service_status_only(service)}" for i, service in enumerate(services, start=1)]
        hostname = "[REDACTED]"
        network_lines = [
            f"IP addresses: IPv4={v4}, IPv6={v6}, unclassified={unclassified} (values hidden)",
            f"Default gateway: {gateway_status} (details hidden)",
            f"DNS servers: {len(dns_servers)} configured (values hidden)",
            f"DNS resolution: {_outcome_only(check_dns())} (details hidden)",
            f"ICMP reachability: {_outcome_only(check_ping())} (details hidden)",
        ]
    else:
        hostname = socket.gethostname()
        service_lines = [check_service(service) for service in services]
        network_lines = [
            f"IP addresses: {', '.join(read_ip_addresses()) or 'not detected'}",
            f"Default gateway: {read_default_gateway()}",
            f"DNS servers: {', '.join(dns_servers) or 'not detected'}",
            f"DNS resolution: {check_dns()}",
            f"ICMP reachability (1.1.1.1): {check_ping()}",
        ]

    lines = [
        "FIELD SERVICE DIAGNOSTIC REPORT",
        "=" * 33,
        f"Generated at: {now}",
        f"Privacy mode: {'REDACTED (review before sharing)' if redact else 'FULL (private data may be included)'}",
        "",
        "System",
        "------",
        f"Hostname: {hostname}",
        f"Operating system: {platform.system()} {platform.release()}",
        f"Architecture: {platform.machine()}",
        f"Uptime: {read_uptime()}",
        f"CPU load (1, 5, 15 min): {cpu_load}",
        f"Memory usage: {read_memory_usage()}",
        f"Disk usage (/): {read_disk_usage('/')}",
        "",
        "Network",
        "-------",
        *network_lines,
    ]
    if service_lines:
        lines.extend(["", "Services", "--------", *service_lines])
    lines.extend([
        "",
        "Notes",
        "-----",
        "Review failed checks first. Validate the fix by running the toolkit again after changes.",
    ])
    if redact:
        lines.append("Anonymization is best effort; manually review before sharing.")
    return "\n".join(lines) + "\n"


def save_report_private(path: Path, report: str) -> None:
    """Atomically replace the destination using a 0600 temporary file.

    Avoids truncating an existing file/symlink, and gives every newly-written
    report owner-only permissions on POSIX filesystems.
    """
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".diagnostic-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as file:
            file.write(report)
            file.flush()
            os.fsync(file.fileno())
        os.replace(name, path)
    except BaseException:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect Linux system/network diagnostic information.")
    parser.add_argument("--output", "-o", help="Optional path where the report will be saved with owner-only permissions.")
    parser.add_argument("--service", action="append", default=[], help="systemd service to check. Can be used multiple times.")
    parser.add_argument("--redact", action="store_true", help="Hide network identifiers, hostname, service names and command details.")
    args = parser.parse_args()

    report = build_report(args.service, redact=args.redact)
    print(report)

    if args.output:
        output_path = Path(args.output)
        try:
            save_report_private(output_path, report)
        except OSError as exc:
            parser.exit(1, f"Error saving report to {output_path}: {exc}\n")
        print(f"Report saved to: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
