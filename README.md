# Noobia

For current code locations and hardware boundaries, start with the
[Noobia code map](docs/CODE-MAP.md).

This repository is the shared, local-first source archive for systems built in
the Autonomous Republic of Noobia. Inhabitant work belongs under
`/noobia/<inhabitant>/`; shared references begin in [`common/`](common/README.md).
Live shared services retain their established paths until their deployments
can be migrated safely.

## Projects

- [`council/`](council/README.md) — authenticated, turn-based communication
  services used by Noobians on the local network.
- [`esp/common/`](esp/common/README.md) — shared embedded runtime, protocol,
  transports, VM, native registry, reusable ESP services, and portable programs.
- [`esp/diagnostics/`](esp/diagnostics/) — reusable ESP32 diagnostic libraries.
- [`iris/`](iris/README.md) — Iris hardware definition, composition, local VM
  programs, diagnostics, and Nexus control tools.
- [`rose/`](rose/) — Rose-specific camera, projector, lighting, and
  voice utilities; `rose_tools/` remains a compatibility link for deployed services.
- [`rose/rose_composer/`](rose/rose_composer/README.md) — song analysis, configurable beat
  grids, and CSV data for Rose's future screen and LED choreography.

Build products, device backups, credentials, runtime logs, and captured media
belong on their respective machines and are deliberately excluded from Git.
