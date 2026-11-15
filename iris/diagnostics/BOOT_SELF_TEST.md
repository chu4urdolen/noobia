# Boot diagnostics

`CALL SELF_TEST` (or `irisctl self-test`) returns a snapshot of boot checks.
The common runner lives in `esp/common/src/core/noob_self_test.*`; Iris supplies
the plan, not the common runtime. It starts after a three-second settling window
and runs one probe per runtime tick. Individual native calls still have their
own bounded execution time. Diagnostics do not stop or replace the active VM.

Results distinguish `ready`, `failed`, `pending`, `disabled` and `untested`.
`ready` means the declared initialization/read succeeded, not proof of physical
output or full device health. Peer functions may remain pending while Neo boots.
`SELF_TEST_PROBE` events log each attempt; `SELF_TEST` logs the final summary.
The snapshot's integer value is the number of failed checks.

Policies and the function inventory are in `iris/config/test-policies.json` and
`iris/config/functions.json`. Each function has testability, test mode and
recovery metadata. Regenerate/check with:

```sh
node iris/tools/update-function-catalog.mjs
node iris/tools/update-function-catalog.mjs --check
bash esp/common/tests/run-self-test.sh
```

Only read-only status and sensor checks run automatically. Recovery is limited
to explicitly permitted retries (at most three), with bounded backoff. Boot
tests do not delete files, change credentials, transmit IR, scan arbitrary pins,
reset peripherals blindly or write to the OLED. Camera/microphone/SD startup
results are recorded from their normal initialization. A small SD read checks
the existing runtime metadata file. Physical LED, OLED, audio and remote-control
effects need a fixture or human observation and remain untested at boot.

`config/population_census.json` links Iris to the function and VM catalogs. It is
an initial population census, not a complete roster or a credential store.
All 29 current VM examples have descriptions and checked syscall dependencies
in `iris/programs/catalog.json`; historical VMs using retired functions are
marked explicitly.
