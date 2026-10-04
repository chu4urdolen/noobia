# Common runtime host tests

Run from the repository root:

```sh
sh esp/common/tests/run-mixed-calls.sh
sh esp/common/tests/run-channel-calls.sh
sh esp/common/tests/run-self-test.sh
sh esp/common/tests/run-police-display.sh
```

Channel tests exercise numeric/ASCII sequence and sampling-thread dispatch,
result queues and busy cleanup. Self-test checks cover bounded retries and
failed/pending/disabled/untested states. Police/display tests run the actual
VM bytecode through all three detector triggers and STOP.

The tests compile the actual native registry, protocol dispatcher, and VM
against a minimal host Arduino shim. They cover mixed numeric/ASCII calls,
empty strings, legacy numeric/text calls, quote escaping, number overflow,
invalid ASCII, excessive arguments, and truncated bytecode. They do not touch
devices or networks. Build artifacts use a fresh directory under `/tmp`.
