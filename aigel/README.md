# Aigel — draft Nexus nurse project

Noob describes Aigel as a planned local nurse for Nexus. Her full plan has not
been found in the current `/noobia` tree or visible Aria conversation records.
This is a planning record, not an active service or a grant of host authority.

## Verified starting point

The existing [Council health monitor](../council/services/health/README.md) is
a C program. It reports root filesystem use, available memory, load, thermal
zones, and local AI contact endpoints. Normal operation writes to syslog;
`--once` writes text to stdout and stderr. A normal `--once` run reads live
Nexus state and may make TCP connection attempts, so it is not an offline unit
test. The monitor parses its configuration before invoking those checks.

## First candidate test

Build the C program in a temporary directory without installing it. Run the
temporary binary with `--once` and an invalid `HEALTH_INTERVAL_SECONDS` or
warning threshold. Assert a nonzero exit and the expected diagnostic. The
invalid setting makes the program return before probing live metrics or contact
endpoints. Keep the test isolated from installed units and configuration.

This is a small safety check for existing code. It does not define Aigel's
architecture, tools, permission boundaries, recovery behavior, or escalation
rules. Noob's existing Aigel plan should be added here before implementation
or executor assignment is treated as settled.
