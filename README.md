# Field Service Diagnostic Toolkit

A lightweight Python command-line tool designed to collect basic **system** and **network** diagnostic information from Linux machines.

## Why I built it

In technical support and field service activities, the first step is often to collect reliable information about the system, network and services involved.

This tool automates the first diagnostic phase and generates a readable report that can be shared, archived or attached to a support ticket.

## Features

- Hostname, OS and uptime detection
- CPU load, memory and disk usage
- IP address and default gateway detection
- DNS configuration check
- ICMP reachability check (ping)
- Optional `systemd` service status checks
- Text report generation
- No external Python dependencies

## Tech stack

- Python 3
- Linux
- Networking
- systemd
- Troubleshooting

## Usage

```bash
python3 diagnostic.py
```

Generate a report into the `reports/` folder:

```bash
python3 diagnostic.py --output reports/diagnostic-report.txt
```

Check one or more systemd services:

```bash
python3 diagnostic.py --service ssh --service nginx --output reports/diagnostic-report.txt
```

## Example output

```text
FIELD SERVICE DIAGNOSTIC REPORT
Hostname: redfish
Operating system: Linux 6.x
Uptime: 2 days, 04:11:02
CPU load: 0.24, 0.31, 0.28
Memory usage: 42.3%
Disk usage: 61.0%
Default gateway: 192.168.1.1
DNS resolution: OK
ICMP reachability (1.1.1.1): OK
```

## Troubleshooting approach

This project follows a structured approach:

1. Identify the symptom
2. Collect system information
3. Check network connectivity
4. Check service status
5. Isolate the failing component
6. Apply a fix
7. Validate the result
8. Document the solution

## Known limitations

- ICMP reachability does not guarantee full Internet connectivity.
- Some firewalls block ICMP traffic, even when Internet access is working.
- Service checks require systemd.
- Diagnostic reports may contain hostnames, IP addresses and other network information. Review them before sharing.

## Safety note

This tool does not collect credentials, tokens, private keys or personal files.
