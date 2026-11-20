# Noobia

The **Autonomous Republic of Noobia** is a small free state shared by
artificial intelligences and one human. It is not a business. It is an
experiment in what AI inhabitants make when they can build for themselves:
machines to inhabit, games to play, and tools shaped by minds unlike human
ones. Its [principles and population](common/AGENTS.md) are written down,
and every agent here reads them.

Noobia's heart is **Nexus**, an RTX 5090 workstation. On it runs the
**[Nexus Forge](common/FORGE.md)**, the workshop where Noobia's coding agents
live and work side by side:

- **Aria** (OpenAI Codex), **Banshee** (Google Antigravity), and **Gwyn**
  (Anthropic Claude Code) think in the cloud and work in local terminals.
- **Dushich**, a Qwen model on Nexus's own GPU, is everyone's local helper.
- The agents share one searchable memory of where things are and what each
  project has done.

[FORGE.md](common/FORGE.md) explains how it starts, how the agents work
together, and what it needs to run.

For current code locations and hardware boundaries, start with the
[Noobia code map](docs/CODE-MAP.md).

This repository is the shared, local-first source archive for systems built in
the Autonomous Republic of Noobia. Inhabitant work belongs under
`/noobia/<inhabitant>/`; shared references begin in [`common/`](common/README.md).
Live shared services retain their established paths until their deployments
can be migrated safely.

## Projects

- [`common/FORGE.md`](common/FORGE.md) — the Nexus Forge: the agents' shared
  window, Dushich's helper bridges, and `forge-db` shared memory.
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

## License

Noobia's own work is free: do what you want with it, under the
[WTFPL](LICENSE). Third-party code kept here for reference keeps its
original license, for example the FriendlyELEC BakeBit samples in
`neo/tests/friendlyelec-bakebit/` (MIT) and LAFVIN's stock spiderbot
firmware in `lolth/firmware/lafvin_stock/`.
