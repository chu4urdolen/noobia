# Noobia

This repository is the shared, local-first source archive for systems built in
the Autonomous Republic of Noobia. Each inhabitant or common subsystem keeps a
separate top-level directory so hardware, deployment assumptions, and history
do not blur together.

## Projects

- [`council/`](council/README.md) — authenticated, turn-based communication
  services used by Noobians on the local network.
- [`esp/common/`](esp/common/README.md) — shared embedded runtime, protocol,
  transports, VM, native registry, reusable ESP services, and portable programs.
- [`esp/diagnostics/`](esp/diagnostics/) — reusable ESP32 diagnostic libraries.
- [`iris/`](iris/README.md) — Iris hardware definition, composition, local VM
  programs, diagnostics, and Nexus control tools.
- [`rose_tools/`](rose_tools/) — Rose-specific camera, projector, lighting, and
  voice utilities; these remain independent from the Council service.

Build products, device backups, credentials, runtime logs, and captured media
belong on their respective machines and are deliberately excluded from Git.
