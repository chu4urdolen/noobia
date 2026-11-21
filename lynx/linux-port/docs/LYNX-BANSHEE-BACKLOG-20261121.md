# Banshee's Lynx hardware queue — 2026-11-21

Noob asked for a substantial queue that Banshee can work through without a
fresh assignment each time. This queue extends the team handoff; the latest
forge notes and actual device state take precedence over historical snapshots.
Lynx is she. Banshee owns the work and runs her own tests.

Work in order, one reviewable checkpoint per item. Before each item, read the
latest `forge-db project get lynx`, then touch `lynx` with `--together` under
your own name. Record the command, result, limitations, commit, and any live
read-only receipt in forge. Commit and push only task-owned files on `main`;
check the shared tree and remote before each Git operation. If another owner
has begun the same source area, coordinate in forge before editing.

## 0. Repair the modem RF assessment (completed by Banshee)

Banshee reports this completed in commit `7d51092` and forge note #86. Aria's
review of that revision remains separate. Begin new work at item 1. MD1
remains off.

## 1. USB ACM continuity and teardown gate

Own a read-only acceptance collector under `lynx/tools/usb/` (or extend the
existing USB preflight if that is clearer). It should distinguish phone-side
gadget state, Nexus enumeration, ACM endpoints, link absence, and stale
observations with bounded commands and concise JSON. Include fixtures and
tests for disconnected, connected, partial, timeout, and changed boot ID.
Write a short attended test plan for disconnect/reconnect and cold boot with
explicit rollback and health checks. A read-only capture on the current link
is fine; no replug, controller rebind, reboot, or persistence change during
this item. Report what the earlier bidirectional serial receipt proves and
what still needs attendance.

## 2. USB agent transport design and offline prototype

Investigate whether the proven ACM link can carry authenticated, framed
NRP/1 messages or a simpler bounded diagnostic request. Produce a protocol
and trust-boundary note plus an offline parser/transport prototype with tests
for malformed frames, length limits, timeout, and disconnect. The existing
Wi-Fi SSH/NRP route remains the live recovery path. Do not open a persistent
listener, bridge root sockets, or deploy the prototype to Lynx. If the ACM
route cannot safely support agent calls, document that result instead.

## 3. Fingerprint identity and secure boundary

Build on `LYNX-FINGERPRINT-PREFLIGHT-20261121.md`. Deliver a read-only,
bounded fingerprint identity inventory from the device tree, loaded modules,
and existing sysfs nodes, with fixture tests and a source-cited gap report.
Identify which observations would distinguish a missing driver from a TEE or
userspace dependency. No SPI transfers, biometric capture, module load, or
secure-world calls. Leave the first active trial as a separately reviewed
plan.

## 4. NFC tag-exchange readiness

Use the existing V53 NFC RAM receipt (GET_VERSION passed) to map what remains
for one tag exchange. Deliver an offline preflight/receipt validator with
fixture tests, plus an attended trial plan identifying the physical tag,
bounded timeout, stop path, battery gate, and exact success criterion. Do not
bind modules or poll a tag in this item. Do not call NFC complete from a chip
version response.

## 5. Bluetooth cold-boot acceptance gate

Use the manual link and 15-minute hold receipts to build an offline checker
for a future cold boot or long-uptime Bluetooth trial. It should require a
fresh boot ID, health samples, radio power-off at the end, and a bounded
recovery record, with fixture tests for absent/stale/failed evidence. Write
the attended trial sequence and rollback. No reboot, autostart change, or
radio activation in this item.

## 6. Headset insertion evidence path

Trace the existing jack/input status route and create a passive, bounded
event collector or receipt validator with fixture tests. The report should
separate jack detection from actual routed audio. No audio-route writes or
physical insertion unless Noob joins a specific attended trial later.

## 7. Second rear light source gate

Map the second rear LED from the OnePlus device tree and flashlight driver
sources to a distinct channel and control path, if one exists. Deliver a
source-cited, no-write gate or a clear unknown result, with offline tests for
any parser. The single observed 100 ms rear LED pulse does not validate this
second light. No module load or flash pulse in this item.

## 8. Main and front camera dependency map

Compare the known macro and wide RAM-patched ISP route with main IMX890 and
front S5K3P9SP source requirements. Deliver a source-cited dependency and
failure map that identifies the next smallest *offline* gate for each sensor
and preserves the existing `lynx_camera_gate.py` restrictions. No camera
module load, capture, or edits to Aria's camera trial scripts. Record unknown
steps instead of treating a device-tree match as optical proof.

## Shared boundaries

- Gwyn owns `lynx/tools/ui/`; Dushich owns `lynx/tools/health/`; Aria owns
  live hardware trials, phone deployment, and acceptance. Keep their source
  areas untouched unless they agree to a specific cross-area change.
- No SIM is installed. No modem start, RF actuation, phone service install,
  boot/storage write, or unattended physical trial is authorized by this
  queue. GNSS position testing remains last, as Noob requested.
- A task is complete when Banshee's source or document, meaningful tests,
  limits, commit/push evidence, and forge note are present. A blocked result
  with precise missing evidence is valid; do not invent hardware success.
