#!/usr/bin/env python3
"""Field Service Diagnostic Toolkit.

Collects basic Linux system and network diagnostic information and prints/generates
a text report. The script intentionally uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import platform
import shutil
import socket
import subprocess
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
        available = meminfo.get("MemAvailable", 0)
        used_percent = (1 - available / total) * 100 if total else 0
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
    resolv = Path("/etc/resolv.conf")
    if not resolv.exists():
        return []
    servers = []
    for line in resolv.read_text().splitlines():
        line = line.strip()
        if line.startswith("nameserver"):
            parts = line.split()
            if len(parts) >= 2:
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


def build_report(services: Iterable[str]) -> str:
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cpu_load = ", ".join(f"{value:.2f}" for value in os.getloadavg()) if hasattr(os, "getloadavg") else "unknown"
    dns_servers = read_dns_servers()
    service_lines = [check_service(service) for service in services]

    lines = [
        "FIELD SERVICE DIAGNOSTIC REPORT",
        "=" * 33,
        f"Generated at: {now}",
        "",
        "System",
        "------",
        f"Hostname: {socket.gethostname()}",
        f"Operating system: {platform.system()} {platform.release()}",
        f"Architecture: {platform.machine()}",
        f"Uptime: {read_uptime()}",
        f"CPU load (1, 5, 15 min): {cpu_load}",
        f"Memory usage: {read_memory_usage()}",
        f"Disk usage (/): {read_disk_usage('/')}",
        "",
        "Network",
        "-------",
        f"IP addresses: {', '.join(read_ip_addresses()) or 'not detected'}",
        f"Default gateway: {read_default_gateway()}",
        f"DNS servers: {', '.join(dns_servers) or 'not detected'}",
        f"DNS resolution: {check_dns()}",
        f"Internet connectivity: {check_ping()}",
    ]

    if service_lines:
        lines.extend(["", "Services", "--------", *service_lines])

    lines.extend([
        "",
        "Notes",
        "-----",
        "Review failed checks first. Validate the fix by running the toolkit again after changes.",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect Linux system/network diagnostic information.")
    parser.add_argument("--output", "-o", help="Optional path where the report will be saved.")
    parser.add_argument("--service", action="append", default=[], help="systemd service to check. Can be used multiple times.")
    args = parser.parse_args()

    report = build_report(args.service)
    print(report)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(f"Report saved to: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
