# Lynx work continuity

Lynx is the OnePlus Nord 3 CPH2493 / MT6983. All project files, tools, build
artifacts, test fixtures, and raw captures belong under `/noobia/lynx`.
The current code and hardware entry points are indexed in
`/noobia/docs/noobs/LYNX.md`; the wider repository map is
`/noobia/docs/CODE-MAP.md`. Keep those pointers current as interfaces change.

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
