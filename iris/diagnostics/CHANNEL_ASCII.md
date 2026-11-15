# Numeric/ASCII channel integration test

`vm_sequence_sd_read.hex` is a 106-byte diagnostic VM. It configures sequence
slot 0 for one SD_READ (251), forwarding fixed arguments 0/32 and ASCII
`/noob/runtime_iris.txt`, with bit forwarding disabled. It starts the sequence,
waits 500 ms, pops its result into r2 and halts. Expected r2 is the metadata file
read count (up to 32). No target files are modified; LOAD/RUN updates the usual VM
persistence snapshot. Restore `police_on_all` afterwards.

Stop the VM and all three detector threads before running this diagnostic so
their police sequence cannot replace its channel configuration. It requires
the numeric/ASCII channel firmware; it is not for historical builds.

Live result (2026-10-04): HALTED at pc=106, r2=30 (the metadata file's size).
Sequence completed with all busy bits cleared. Police-on-all was restored and
confirmed WAITING at pc=135, bytes=138, stored autorun=1 afterwards.
