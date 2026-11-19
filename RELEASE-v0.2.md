# Field Service Diagnostic Toolkit — v0.2

## Changes

- Added `--redact`, an allowlist-based privacy-oriented report mode. Hostname, raw IPv4/IPv6 addresses, gateway details, DNS values, and service identifiers are not printed in this mode.
- Kept system diagnostics and safe success/failure statuses visible for troubleshooting.
- Report export uses an owner-only temporary file and atomic replacement, with `0600` permissions on POSIX systems; newly created directories use `0700`.
- Extended automated tests from 13 to 23, covering redaction of network values and command errors, file permissions, and replacement behavior.
- Updated the README and replaced the tracked report example with a clearly synthetic, redacted sample.

## Verification (2026-11-19)

- All 23 tests passed on the Raspberry Pi 4 (Debian Linux, aarch64).
- A real redacted diagnostic run completed with DNS, ICMP and `ssh` systemd checks.
- The saved report was verified locally with `-rw-------` permissions.
- The full report from the actual host was **not** included in this release.

## Compatibility and limitations

- Existing `--service` and `--output` usage is retained; without `--redact`, the command prints and optionally writes the full report, which may contain private infrastructure identifiers.
- Redaction is best effort. Linux kernel version, architecture, timestamps and metrics remain visible; review outputs before sharing.
- `--output` atomically **replaces** the named destination; select the output path carefully.
- No service configuration or Raspberry Pi monitoring timer is modified by this release.
