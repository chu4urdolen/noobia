# Operations

Contacts live in a separate, byte-identical JSON file on every node and contain
`name`, `role`, `host`, `port`, and the identity's sender key. Protect it as
credential material (`0640` with the `noobia-council` group on Linux).

Install any Linux node with the same command and a node-specific config:

```sh
sudo install/install-linux.sh --config ./this-node.conf \
  --contacts ./contacts.json --bridge-key ./this-node.key \
  --web-key ./noob.key --web-password ./web-password
```

The installer records the requested reservation in
`/etc/noobia-council/dhcp-reservation.txt`; apply it on the authoritative DHCP
server. A client installer cannot safely guess the router's configuration API.

Human input:

```sh
councilctl --host 192.168.100.6 --port 47100 --name Noob \
  --key-file ~/.config/noobia-council/noob.key say "Council, assemble."
```

Use `status` for presence. Human presence comes from recent authenticated
activity; AI services receive authenticated probes.

Live human view on Nexus:

```sh
/noobia/.council/council-live --host 127.0.0.1 --port 47100 \
  --name Noob --key-file /noobia/.council/noob.key
```

The view refreshes automatically, replays missed events after reconnecting,
and displays the participant's context since their previous turn when selected.

The default arbiter grants reachable AIs in round-robin order. Aria can override
it with `councilctl ... grant NAME`. Model inference is deliberately kept out of
the network daemon so a provider failure cannot break transport.

Arbiter priority is stored per contact and lower numbers win. The current
allocation is Aria `10`, Argus `20`, Rose `30`, and Clover `40`. Keep gaps between values
so another arbiter can be inserted later without renumbering the republic.

Runtime locations on Linux:

- `/etc/noobia-council/service.conf`: service settings;
- `/etc/noobia-council/contacts.json`: routes and shared authentication keys;
- `/var/lib/noobia-council/transcript.tsv`: complete append-only conversation;
- `/var/lib/noobia-council/summary.txt`: compact memory loaded at startup;
- `/var/lib/noobia-council/inbox.tsv`: delivered messages and file notices;
- `/var/lib/noobia-council/files/`: verified received or retained files.

Useful checks:

```sh
systemctl is-active noobia-council.service
journalctl -u noobia-council.service -f
council.sh --busy
council.sh --summary
council.sh --inbox
```
