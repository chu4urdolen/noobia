# Lynx expdb read-only capture — 2026-10-18

The known-good V19 BusyBox boot exposed `/dev/sdc7` as the unique `expdb`
partition. Sysfs reported 262,144 sectors, and `blockdev --getsize64`
confirmed 134,217,728 bytes. Pinned native SSH identity was checked before
every transfer. No partition write, flash, slot change, or reboot was made.

The first 0xF0000 bytes were captured at
`logs/expdb-readonly-1792332080695864222/`. The full 128 MiB transfer timed
out after 123,489,341 bytes. A guarded read of the final 11 MiB from offset
117 MiB overlapped the partial capture by 805,949 bytes. That entire overlap
matched byte-for-byte, allowing an exact full reconstruction at
`logs/expdb-full-readonly-1792332114335920464/expdb-complete.raw`.
SHA-256: `a43d4175da758be81508452d1071b869dd4736d865b02e547a3dbd9ecdc371cb`.
The raw capture is private and remains local.

The stock LK log had identified `SYS_RAMCONSOLE_RAW` at expdb offset 0x2000,
size 0x1000, and `SYS_PSTORE_RAW` at offset 0x3000, size 0xE0000. Those
regions contain the older diagnostic token
`69adf9d14707d848063b861b8f248748`, also seen in live pstore. A
bytewise marker inventory of the complete partition is at
`logs/expdb-full-readonly-1792332114335920464/marker-inventory.json`:
there are no `LOCAL_` self-boot markers, no current V19 token, and no literal
`Kernel panic` string. The `Call trace:` records belong to an older kernel
startup warning about duplicate `/devices/armv8_pmuv3`, adjacent to the old
token; they do not identify the V25d/f failure. Compressed or proprietary
records could remain undecoded, so the marker search is not proof that no
newer failure record exists.

The live capture establishes a usable read-only expdb path for future trials.
If another candidate boot fails, return to V19 and compare a fresh expdb hash
and decoded record provenance before attributing any retained log to it.
