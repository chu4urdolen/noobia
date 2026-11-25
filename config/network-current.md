# Nexus network configuration

Verified on 2026-10-06 after a duplicate-address conflict with Syra.

| Role | Wi-Fi | Adapter | Address |
| --- | --- | --- | --- |
| Noobia LAN, primary | Noobia | wlx40a5ef5f66f1 | 192.168.100.106/24, static |
| Cellular fallback | MTEL-4064 | wlx20e017103ffb | 192.168.8.101/24, DHCP at verification |

LAN profile: `Noobia MT7612U`, UUID `dfa26e16-06b4-4746-95fd-4ad3bbc57f63`.
Gateway: `192.168.100.1`; route metric 100; automatic connection enabled.
DNS: `8.8.8.8` and `1.1.1.1` (Tom, 2026-11-25; was `185.82.217.89`, a dead ITLDC hosting address the big router hands out by DHCP, and `8.8.8.8`).
Cellular profile: UUID `26bbfc45-0a19-46ab-b28d-04bd8ceb53b9`, automatic
connection enabled, DHCP route metric 602 at verification. Both adapters
remained connected, and HTTPS was tested independently through each.

Argus's saved SSH address is `192.168.100.105`; Nexus was assigned the adjacent
`.106`. Nexus's Council contact book now lists Argus at `.105` and Noob/Aria at
`.106`. Its service configuration also records `.106` and the correct LAN MAC.
Original Council configurations were backed up under
`/var/backups/noobia-council-addresses-20261006-204022/`. Argus is offline.

Syra is reported by Noob at `192.168.100.7`. This address no longer belongs to
Nexus. Noob verified Syra's ED25519 fingerprint locally:
`SHA256:TMv9fSll2eSGp+ZpuLziYgqG3g5ruz5fft+2QZLbhSM`.
The `.7` trusted host record was updated with a backup in
`/noobia/state/known_hosts-before-syra-20261006`. The saved `rose` SSH login
works and identifies the host as `syra`, running Debian 13 on a Raspberry Pi.

The `M-Tel_1F6C` access point gave ARP responses but neither LAN pings, SSH, nor
HTTPS worked. Switching the LAN adapter to the saved `Noobia` access point
restored router pings, SSH reachability to `.7`, and HTTPS at `.106`.

Automatic connection was disabled for the obsolete `M-Tel_1F6C`,
`M-Tel_1F6C 1`, and old `Noobia` profile (the latter used `.6` on the cellular
adapter). Their profiles remain available for manual recovery.
Both temporary rollback timers are inactive. Original settings and recovery
scripts are under `/noobia/state/nexus-network-20261006/` and
`/noobia/state/nexus-network-lan-20261006/`; running them would restore earlier
settings and can reintroduce the conflict, so inspect them before use.
