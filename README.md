# Field Service Diagnostic Toolkit

A small, read-only Python CLI for collecting basic **Linux system and network diagnostics**, with an optional privacy-oriented report mode. It uses only the Python standard library.

The project is intended for technical support and lab troubleshooting, not as a full network scanner or production monitoring product.

## Features

- Hostname, OS, uptime, CPU load, memory and disk usage
- Local IP addresses, default gateway and configured DNS servers
- DNS resolution and ICMP reachability checks
- Optional `systemd` status checks
- Text reports written using owner-only file permissions on POSIX systems
- `--redact` privacy mode for reports that may be shared after manual review
- Unit tests covering failures, redaction and file permissions

## Basic use

```bash
python3 -m unittest -q
python3 diagnostic.py
python3 diagnostic.py --service ssh
python3 diagnostic.py --service ssh --output reports/diagnostic-private.txt
```

By default, the report contains **real network and host identifiers**. Treat it as private. The script does not restart services or alter the system network configuration. DNS and ping checks send ordinary network requests; they are not completely passive.

## Redacted reports (v0.2)

```bash
python3 diagnostic.py --service ssh --redact
python3 diagnostic.py --service ssh --redact --output reports/diagnostic-redacted.txt
```

In redacted mode the report:

- Replaces the hostname with `[REDACTED]`.
- Shows **counts** of IPv4 and IPv6 addresses instead of address values.
- Shows only whether a default route exists and how many DNS servers are configured.
- Reports only `OK` / `FAILED` for DNS and ping, without diagnostic details or IP/domain values.
- Replaces named services with `service-1`, `service-2`, etc., preserving only allowlisted status words.
- Keeps generic system metrics, Linux kernel version, architecture, timestamps and resource statistics.

**This is not a guarantee of anonymization.** System characteristics, exact timestamps, kernel versions or other metadata can still be identifying in some contexts. Always review a report before forwarding or publishing it. Avoid publishing raw reports from private/customer environments.

The tool does not collect credentials, keys or application files. However, a full report can still contain sensitive network metadata.

## Safe report export

`--output` writes to a temporary file in the destination directory and atomically replaces the requested report file. On POSIX filesystems the resulting file is owner-readable/writable only (`0600`); newly created destination directories use `0700`. This does not retroactively change reports produced by older versions, nor prevent unsafe access to a report once it is copied, uploaded, or placed on a filesystem without POSIX permissions (e.g. some Windows setups).

To check the saved report permissions on Linux:

```bash
ls -l reports/diagnostic-redacted.txt
```

The file should begin with `-rw-------`.

## Troubleshooting approach

1. Identify the symptom.
2. Collect diagnostics.
3. Examine failed DNS, ICMP, resource and service checks.
4. Isolate the failing component.
5. Apply a change through the normal maintenance workflow (not through this tool).
6. Re-run diagnostics and document the result.

## Limitations

- `ping` failures do not necessarily mean Internet connectivity is down (ICMP may be blocked).
- DNS resolution is tested separately from ICMP reachability.
- Service checks require systemd.
- Redacted mode hides detailed network values, which can make advanced troubleshooting harder; keep a private full report if permitted.
- No browser dashboard, monitoring scheduler or automatic incident notifications are provided here. The separate [Infrastructure Operations & Monitoring Lab](https://github.com/REmanuele/infrastructure-operations-monitoring-lab) project covers periodic service monitoring.

## Safety

The tracked [`reports/example-report.txt`](reports/example-report.txt) is an explicitly synthetic example in privacy mode; it is not output collected from a real machine.

The sample reports committed to a public repository must contain **invented** hostnames and documentation IP addresses only. Do not commit real IPs, customer names, secrets, private service names or reports taken from operational environments.

See also `RELEASE-v0.2.md` for the changes introduced in this version.

## Proposed reliability improvements (v0.3 branch)

The [`v0.3 robustness notes`](docs/v0.3-robustness.md) describe additional handling for inaccessible system commands, unreadable resolver configuration and inconsistent memory data, plus automated Linux tests. These changes build on v0.2; they do not alter the existing `--redact` or secure report-export interfaces.
