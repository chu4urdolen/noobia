# Lynx kernel and agent handoff gate

Prepared 2026-11-06 after the guarded IMX355 wide-frame success. This is a
current decision record, not a claim that all phone hardware is finished.

## Flash decision

No additional `boot_a` flash is required for the verified Lynx camera paths.
V53 already boots Alpine, Wi-Fi, SSH, display, touchscreen, audio, battery
monitoring, and the Noobia runtime. The YUV IRQ and CAMSV sensor-power repairs
are in a loadable `mtk-cam-isp.ko` with V53's exact kernel ABI, stock vermagic,
322 matching imported symbol CRCs, and an attended RAM-only trial. GC02M1
macro and IMX355 wide have each returned recognizable frames. Their modules,
firmware, and routes can be brought up after Alpine starts, so persistence is
an Alpine filesystem and service change, not a boot-partition change.

Keep the exact V53 image and V50 BusyBox rollback. Do not fold the camera
stack into the initramfs merely to call the kernel complete. The stock ISP
module produced a severe YUV-B interrupt storm; only the reviewed patched
module may be considered for persistence. Automatic camera loading still
needs a cold-boot trial and a reliable local disable switch before enabling
it by default. Main IMX890 and front S5K3P9SP optical capture remain untested.

## Verified inference path

Nexus's authenticated proxy at `192.168.100.106:8080` accepted a local
`POST /v1/responses` with model `gpt-oss-20b` and returned HTTP 200. A second
forced-function test returned a `function_call`. Lynx reached the public
`/health` endpoint over its current Wi-Fi. This verifies the local transport
and Responses tool-call shape, not the complete on-device agent loop. The
proxy key stays outside the repository. When Nexus is unavailable, Lynx may
use OpenAI's Responses API through a separately stored phone credential; the
cloud path must be tested without exposing that key in logs.

Official [Codex CLI releases](https://github.com/openai/codex#installing-and-running-codex)
include `aarch64-unknown-linux-musl`, suitable
for Alpine's CPU and libc. Lynx currently has no `codex`, Node, or npm in
`PATH`; the standalone binary avoids adding Node solely for Codex. Installing
it and configuring its model/provider choices are separate from granting an
agent unrestricted shell access. Run it under a dedicated Lynx user with its
own workspace and explicit command timeout.

## Remaining kernel-facing work

| Area | Current evidence | Next gate | Boot flash? |
| --- | --- | --- | --- |
| Camera ISP | Patched module survives RAM trials; two rear sensors produce frames | Package exact module and dependencies on Alpine; guarded cold boot and disable switch | No |
| Main/front cameras | Sensors bind; four-cell modes differ from simple Bayer | Bounded one-frame route and format trials | No known need |
| SIM/cellular | MT6983 modem/CCCI devices exist, including `/dev/ccci_*` | Inventory SIM slot, modem state, and userspace before radio activation | No known need |
| GNSS/Bluetooth | NMEA and Bluetooth exchange trials recorded; service boundaries remain | Validate outdoor fix and stable local transport | No known need |
| Boot reliability | V53 supports Alpine, but long-uptime warm reboot has not been proved | Controlled reboot/rollback trial after services are staged | Only if a boot defect is demonstrated |

The agent can be built and tested now against verified interfaces. A single
tool catalog should supply both the local agent's function definitions and
the Noobia NRP/1 adapter for new tools; existing NRP natives remain available
through the local socket. A plugin's presence must not imply its hardware is
validated. Keep local and remote issuer permissions explicit and auditable.
