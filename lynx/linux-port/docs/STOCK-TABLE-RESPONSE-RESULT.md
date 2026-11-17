# Stock metadata read: invalid response, no table obtained

Session `1791594246473496534` is preserved under `tools/mtk-sessions` with complete
output in `probe-output.log`.

The physical connection succeeded. MT6983 identity and preloader mode were
confirmed, and the original signed DA1 plus unchanged DA2 loaded in RAM.
The corrected wrapper started a fresh three-minute active deadline after the
handshake and requested READ-PARTITION-TABLE without authentication attempts.

The XML reader reported `xread: Wrong length`. The stock table function returned
no usable data, and our guard raised
`Stock loader did not provide partition-table metadata; no fallback`.
The process exited with status 1. No table XML or partition backups were made.

This is an invalid USB/protocol response, not evidence that the user's button
sequence was wrong. It does not establish a specific device-side authentication
denial, a damaged partition table, or a physical memory fault. A repeated
unchanged power-cycle test has no identified reason to produce a different
result. No partition write, erase, slot change or Linux-image flash occurred.

Current established capabilities: physical Fastboot return, read-only Fastboot
variables, preloader enumeration/handshake and stock RAM-loader startup.
Unresolved capabilities: usable partition readback, stock restoration and
native Linux hardware boot. Successful RAM-loader startup alone must not be
treated as a verified restoration path.
