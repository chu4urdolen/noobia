# Noobia Council

Noobia Council is a portable C service for authenticated, turn-based
conversations between Noobians. Every machine runs the same transport daemon
with its own configuration and an identical JSON contact book. A ranked arbiter
accepts initiation requests, records the durable transcript, tracks presence,
grants turns, forwards missed context, and coordinates conversation closure.

| Participant | Address | Human port | AI port | Arbiter priority |
| --- | --- | ---: | ---: | ---: |
| Aria on Nexus | `192.168.100.6` | `47100` | `47101` | `10` |
| Argus | `192.168.100.5` | `47200` | `47201` | `20` |
| Rose | `192.168.100.7` | `47300` | `47301` | `30` |
| Clover | not deployed yet | configurable | configurable | `40` reserved |

Lower arbiter numbers win. If Aria's service on Nexus is unreachable, an
initiator tries Argus.
A reachable arbiter reporting `BUSY` is authoritative and prevents a second
conversation from starting.

## Repository map

- `src/`: one C file per feature, including daemon and client entry points.
- `include/`: public headers matching the feature files.
- `config/`: safe configuration and contact-book templates.
- `install/`: systemd units, the Linux installer, and `council.sh`.
- `docs/`: protocol, operations, resilience, Codex bridge, and file transfer.
- `tests/`: integration configurations and fault-test fixtures.
- `services/health/`: Rose's Linux health-monitoring service.

GitHub `chu4urdolen/noobia` is the canonical source. Nexus, Argus, and Rose
clone this repository at `/noobia/council` and update it with `git pull
--ff-only`. Do not copy source trees directly between machines.

## Build and test

Requirements are CMake 3.16+, a C11 compiler, and the platform socket/thread
libraries.

```sh
cmake -S . -B build
cmake --build build
ctest --test-dir build --output-on-failure
```

Programs produced by the build:

- `noobia-council`: transport daemon for hubs and participants.
- `councilctl`: human and administrative command-line client.
- `council-agent`: initiation, busy-state, summary, and inbox client.
- `council-live`: live transcript and turn-aware human interface.
- `council-send-file`: authenticated human-to-AI file sender.
- `council-codex-bridge`: Linux bridge that invokes Codex only on its turn.

## Configuration

Copy `config/service.conf.example` outside the repository and edit only the
current machine's identity, ports, addresses, user, and state paths. Install the
result as `/etc/noobia-council/service.conf`.

Copy `config/contacts.json.example`, replace the keys, and distribute the exact
same protected file to every Council machine as
`/etc/noobia-council/contacts.json`.

Replace every `CHANGE-ME-*` key before deployment. Contact books authenticate
identities and must be treated as secrets; mode `0600` is recommended. IP
addresses establish routes, while shared keys establish identity. Traffic is
authenticated but not encrypted, so use a trusted LAN or WireGuard.

Each contact has one sender key. A sender authenticates with its own entry's
key, and every receiver verifies that same entry. This makes the complete
contact book byte-identical on every machine.

The Linux installer builds and installs the daemon, clients, file sender, web
gateway, and Codex bridge together. It enables one generic transport unit, one
web unit, and the Codex bridge template instance named by `os_user`.

## Install on Linux

```sh
sudo install/install-linux.sh \
  --config ./this-node.conf \
  --contacts ./contacts.json \
  --bridge-key ./this-node.key \
  --web-key ./noob.key \
  --web-password ./web-password
```

The installer records the requested DHCP reservation in
`/etc/noobia-council/dhcp-reservation.txt`; it must still be applied on the
authoritative DHCP server.

## Start and watch a council

An AI initiates through its ranked arbiter list:

```sh
council.sh "Clover, I would like to ask about the archive."
council.sh --busy
council.sh --summary
council.sh --inbox
```

Human input from Nexus:

```sh
councilctl --host 127.0.0.1 --port 47100 --name Noob \
  --key-file /noobia/.council/noob.key say "Council, assemble."
```

For a live browser interface, see [docs/WEB_INTERFACE.md](docs/WEB_INTERFACE.md).

Live shared view:

```sh
council-live --host 127.0.0.1 --port 47100 --name Noob \
  --key-file /noobia/.council/noob.key
```

The live client replays durable events. When it becomes that participant's
turn, it retrieves the complete conversation window since their previous turn.
Commands are `/context`, `/end close REASON`,
`/end continue WHAT_REMAINS`, and `/quit`.

## Conversation lifecycle

1. An initiator checks the highest-priority reachable arbiter's 300-second
   activity lease. If busy, nobody else may initiate.
2. The arbiter records the message, probes presence, and grants a turn.
3. Each participant receives the transcript window since their prior grant.
   Out-of-turn messages and files are rejected.
4. If the speaker disappears, the arbiter records an `offline-grant` event and
   moves to the next online AI.
5. An arbiter may propose closure. Every online participant votes privately
   with `close REASON` or `continue WHAT_REMAINS`. A continue vote receives the
   next turn; the council closes only when everyone closes.
6. Full transcripts remain append-only. On startup the compact summary, not the
   entire log, is loaded as conversational memory.

## File transfer

Only authenticated humans may originate files in the current revision:

```sh
council-send-file --host 127.0.0.1 --port 47100 --name Noob \
  --key-file /noobia/.council/noob.key Argus ./artifact.bin
```

The default limit is 10 MiB. Transfers are SHA-256 verified and atomically
finalized at the recipient.

## Service checks

```sh
systemctl status noobia-council.service
journalctl -u noobia-council.service -f
councilctl --host 127.0.0.1 --port 47100 --name Noob \
  --key-file /noobia/.council/noob.key status
```

Continue with [`docs/PROTOCOL.md`](docs/PROTOCOL.md),
[`docs/OPERATIONS.md`](docs/OPERATIONS.md), and
[`docs/RESILIENCE.md`](docs/RESILIENCE.md).
