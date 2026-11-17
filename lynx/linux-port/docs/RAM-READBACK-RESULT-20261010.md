# RAM hash-redirection attempt rejected

Session: `/noobia/lynx/tools/mtk-sessions/1791592491849853661`.
Complete output is in `probe-output.log` there.

MT6983 identity and preloader mode were confirmed. The original signed DA1
uploaded and started successfully. The subsequent 32-byte RAM hash-redirection
request was rejected with `DA Hash mismatch`. The guard raised
`DA1 RAM hash redirection failed; no fallback` and the process exited.

The patched DA2 was not uploaded or executed. No GPT, partition contents or
backup was obtained. No stored partition was flashed, erased or switched.
The vendor error text mentions possible DRAM problems but is generic and does
not establish a hardware memory fault. This tested method is not a verified
readback/restoration route and live repetition is disabled in the wrapper.

The next stock metadata check will request READ-PARTITION-TABLE from the
unmodified accepted loader without attempting authentication or patching RAM.
The earlier enabled-authentication result was a host guard decision before
that read request, not proof that partition-table reads are denied by the phone.
