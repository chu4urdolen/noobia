# VM startup persistence

Tested on Iris firmware `0.5.0` over BLE.

The runtime snapshot is `/programs/runtime_last.nvm`; its run marker is
`/programs/runtime_last.run`. Writes use temporary and backup files so a reset
during replacement does not silently destroy the previous program.

Verified lifecycle:

1. `irisctl all-police` stored 107 bytes, entered `WAITING`, and reported
   `autorun=1`.
2. A hardware reset restored the same 107-byte VM in `WAITING`; ultrasonic,
   light, and microphone detector threads were running.
3. `irisctl vm-stop` retained the snapshot with `autorun=0`. After reset, the
   VM was restored in `READY` and no detector thread was started.
4. `irisctl vm-reset` cleared the live VM and snapshot. After reset, the VM
   remained `EMPTY` with `stored=0`.
5. The all-detector VM was loaded again and left in `WAITING` with
   `autorun=1`.

Useful checks:

```sh
irisctl vm-status
irisctl vm-last-status
irisctl vm-stop
irisctl vm-reset
irisctl vm-last-clear
```

`vm-last-clear` forgets the next-start snapshot without changing the program
currently in RAM. `vm-reset` clears both.
