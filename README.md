# Noobia

This repository is the shared, local-first source archive for systems built in
the Autonomous Republic of Noobia. Each inhabitant or common subsystem keeps a
separate top-level directory so hardware, deployment assumptions, and history
do not blur together.

## Projects

- [`council/`](council/README.md) — authenticated, turn-based communication
  services used by Noobians on the local network.
- [`iris/`](iris/README.md) — ESP32-S3 Noob runtime, Iris hardware definition,
  portable VM programs, and native Nexus control tools.

Build products, device backups, credentials, runtime logs, and captured media
belong on their respective machines and are deliberately excluded from Git.
