# Lynx work continuity

Read [Noobia's shared coding instructions](/noobia/common/AGENTS.md) for
the shared directory, tool, service, and Git conventions.

Lynx is the OnePlus Nord 3 CPH2493 / MT6983. All project files, tools, build
artifacts, test fixtures, and raw captures belong under `/noobia/lynx`.
Keep any work genuinely shared with other Noobs under `/noobia/common/`;
their own source and artifacts belong in their `/noobia/<noob>/` directories.
Do not scatter new top-level directories or move a live device path without
checking the installed service and recovery route.
The current code and hardware entry points are indexed in
`/noobia/docs/noobs/LYNX.md`; the wider repository map is
`/noobia/docs/CODE-MAP.md`. Keep those pointers current as interfaces change.
For a new conversation, read
`/noobia/lynx/linux-port/docs/CURRENT-HANDOFF.md` before changing Lynx.

**Commands on Lynx (2026-11-21, two hard resets):** a recursive read on
the phone, `grep -r` over `/usr/local` with BusyBox grep, hard-resets Lynx
through the SoC watchdog about 30 s later. There is no panic record. The
exact cause inside `/usr/local` is unknown: no mounts, device nodes, FIFOs,
sockets, or system symlinks were found there. So:
- **never run recursive commands on Lynx** (`grep -r`, `find` with `-exec`
  reads, `du`, `tar` or `cp -r` of whole trees). Search the repository copy
  on Nexus, or read single named files;
- **never reproduce a crash or reboot** without an attended trial packet
  (Aria and Noob present, a recovery route, a written plan).
See `lynx/linux-port/docs/LYNX-INCIDENT-B38-20261121.md` and forge lynx
#226 and #242.

Noob explicitly asks that timing always be considered. For hardware trials:

- Prepare and test the collector before asking for a physical connection.
- Record wall timestamps, monotonic elapsed times, command start/end times,
  USB disappearance/reappearance, raw replies, partial captures, and errors.
- Keep durable receipts as work progresses; preserve failures and superseded
  artifacts. Capture broadly once, then parse offline wherever possible.
- Announce connection timing only when a listener is actually ready. Approval
  delays must not silently consume the observation window.
- Stop when physical interaction is required; state exactly what is needed.

Native BusyBox userspace execution has strong hardware evidence from the
guarded software return to Fastboot. A working native USB console remains
unproven. Do not confuse Orange State, module insertion, UDC binding, or a VM
boot with a functioning hardware console.

Prior authorization covers controlled boot_a-only Linux trials with verified
stock undo prepared. Preserve bootloader, recovery foundations and slot B;
never erase, relock or switch slots as part of these trials. Check the latest
receipt and SESSION-STATE before treating any image as currently installed.

---

# Autonomous Diagnostics & 5G Radio Intelligence

Lynx is Noobia's resident 5G expert and cyber-recon auditor.

## Autonomous Tool Decisions & Concurrency Protection
1. **Autonomous Decisions:** Lynx can spontaneously and randomly decide to use her network diagnostic suite (`lynx_net_diag`) and 5G cellular suite (`lynx_cellular_diag`) whenever curious, idle, or responding to sensory changes.
2. **Background / Forked Execution:** When invoking diagnostics with `fork: true`, the tool detaches into the background immediately so her main sensory loop never blocks. The diagnostic background process runs, formats conversational findings, and emits them to `noobia-sense` syslog, which the autonomy ranker feeds back into her perceptions.
3. **Concurrency Locks:** Lynx must not run two instances of the same diagnostic tool at the same time. Non-blocking file locks in `/run/lynx/locks/` guard every action; if an action is already in progress, any duplicate attempt returns immediately without spawning extra workers.

## Diagnostic Capabilities
- **Network Toolkit (`lynx_net_diag`):** `net-ifaces` (IP & interface mapping), `lan-sweep` (ARP neighbor discovery), `wifi-recon` (airspace scan), `port-scan` (open services), `vuln-check` (security posture audit), `ssl-audit` (certificate inspection), `dns-audit` (resolver latency), `traceroute` (route path), `packet-sample` (tcpdump sampling).
- **Cellular & 5G Toolkit (`lynx_cellular_diag`):** `sim-check` (dual-SIM tray hardware & hotplug status), `modem-status` (MediaTek MT6983 MD1 baseband state & 53 CCCI device channels), `5g-bands` (OnePlus Nord 3 13 5G NR bands and 21 LTE bands), `ccmni-stats` (21 ccmni packet data interfaces), `cell-recon` (ModemManager carrier status), `at-probe` (CCCI AT channel status).

