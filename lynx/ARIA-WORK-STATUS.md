# Aria's Lynx work status — 2026-11-25

This reconciles Gwyn's 40-open tracker (forge lynx #495) with Aria's verified
work. "Built" means code or an install packet exists in the repository;
"live" means a phone or Nexus check confirmed it. An offline packet is not
a completed hardware capability. Noob subsequently authorized Lynx installs;
the LNX-65/94 package preflight is recorded below.

| Backlog IDs | Current evidence | Next condition |
| --- | --- | --- |
| 01–03, 08–09 | MD1 remains off under the RF NO-GO; no SIM inserted. | Physical RF gate, then attended modem and SIM work. |
| 19, 52–58, 80–81, 92 | Cellular routing, boot, health, permissions, diagnostics, SMS/call handling and inbound reachability require a working modem path. | 01–03 and carrier connection first. |
| 20, 45 | Durable Aigel reply retries now use opt-in `.done` records with fresh signed timestamps, 30-second backoff, and server job-ID deduplication; focused tests pass 13/13. | Two fresh reviews of the revised LNX-84 client packet, then attended installation and a natural-job delivery check. Wider offline event synchronization still remains. |
| 21 | WireGuard LAN trial packet reviewed by Dushich and Gwyn at c0fc485; Aria incorporated their notes in b0fcac7. | Reviewers confirm revised packet; attended network trial later. |
| 22 | No direct Noob mesh is installed. | Establish 21, identify peers and consent, then packetize routes and identity. |
| 23–24 | Hotspot and Bluetooth tethering are not configured. | Controlled radio trials with rollback after 01–03 for cellular sharing; Bluetooth may be tested separately. |
| 44, 46 | Lynx has a deterministic pattern/reflex layer, but no verified on-device generative model; remote inference depends on Nexus. | Choose and benchmark a small local model against battery and thermal limits; decide failover spending/credential policy. |
| 51 | **Done live:** V50 boot assigns static `192.168.100.107/24`; `/run/lynx/boot.log`, `/run/lynx/address`, `ip -4 addr`, and the default route agree (#503). | Recheck after network changes. |
| 65, 94 | The reviewed nftables packet is **NO-GO** on this kernel: `CONFIG_NF_TABLES` is unset. Aria installed the pinned package after authorization; no rules or service were activated (#505). | Prepare and review a legacy iptables runtime packet; preserve SSH 22/2222 and NRP 4243. |
| 67 | **Done live:** Dropbear 22/2222 key-only; S10 reports auth failures (#464). | Recheck after SSH service changes. |
| 68 | **Done live:** NRP HMAC challenge-response, 0600 secret, unsigned refusal (#467). | Use tunnel for confidentiality, separate 21. |
| 70 | NRP remote socket/time/rate limits built, Gwyn ACCEPT (#489). | Dushich second review, then attended install. |
| 73, 77 | Privilege-split packet repaired in 5a36693; modem nodes remain root-only. Coder's full sudo is Noob's explicit decision (#485). | Two independent reviews, LNX-84 signed worker prerequisite, then attended install. This is not a strict boundary against the coder. |
| 79 | Reversible sysctl trial corrected in b0fcac7 after Gwyn's #486 review; five offline tests pass. | Gwyn re-review and another independent review, then attended trial. |
| 82 | NRP has one shared Nexus key, not per-Noob identity. | Design per-principal credentials and attribution without assuming separate Unix accounts. |
| 83 | NRP cross-session replay test passes. Aigel signed-route freshness/idempotency is built in b9eb7d2/144dd1a but inactive. | Review and activate LNX-84 server packet after signed client. |
| 84 | NRP rate limits and signed Aigel client/server packets built; server switch remains absent. | Reviews, signed worker install first, then Aigel switch/restart. |
| 85 | Gwyn replaced the dead resolver in Nexus profiles, Lynx's live resolver and V50 script with `8.8.8.8` and `1.1.1.1` (#509); live Lynx lookup took 28 ms. Aria built a 120-second loopback DoT proof packet with no resolver cutover; 2/2 offline tests pass. | Two reviews and attended proof, then design boot-safe cutover. Noob handles the router's DHCP setting. |
| 86 | Wi-Fi key is already 0600 root:root; audit extension built, Gwyn ACCEPT (#487). | Dushich second review, then install on demand. |
| 91 | Argus is powered off; Lynx security journal exists. | Define Argus intake contract and sync once Argus is available. |
| 93 | **Assessment complete:** no public cellular/WAN endpoint yet (#481). | Reassess if a public endpoint appears. |

Reviews and installation states are also in forge lynx #486–#497. Exact
hashes, modes, preflight, verification, disable and rollback live in each
install packet; this page does not supersede them.
