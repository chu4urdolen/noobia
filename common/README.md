# Common Noobia resources

The shared [coding agent instructions](AGENTS.md), readable
[contact book](CONTACT-BOOK.md), [Nexus inference notes](NEXUS-INFERENCE.md),
and [Linux service sources](services/README.md) live here.
Inhabitant-specific work belongs in the
inhabitant's own top-level directory, such as `../rose/` or `../dushich/`.

Shared services currently keep established paths because running units and
device builds refer to them. Use these entry points until each deployment is
migrated and verified:

| Shared system | Current source |
| --- | --- |
| Council communication | [`../council/`](../council/) |
| Embedded runtime and protocol | [`../esp/common/`](../esp/common/) |
| Nexus administration scripts | [`../tools/`](../tools/) and [`../boot-manager/`](../boot-manager/) |
| Speech and transcription | [`../speech_to_text/`](../speech_to_text/) |
| Site and device documentation | [`../docs/`](../docs/) |

The old `docs/CONTACT-BOOK.md` and `docs/NEXUS-INFERENCE.md` paths are
compatibility links. The archive and private runtime directories are excluded
from Git; they are not shared reference material.

Large device backups, operating-system images, and live service trees remain
at their current paths. Move them only with a device-specific migration plan
and a check of installed units, mounts, scripts, and recovery procedures.
