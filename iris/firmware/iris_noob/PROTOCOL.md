# NRP/1 protocol

NRP/1 is UTF-8, line-delimited, and transport-independent.

Request:

    NRP/1 <request-id> <COMMAND> [arguments]

Success:

    NRP/1 <request-id> OK [payload]

Failure:

    NRP/1 <request-id> ERR <code> <message>

Milestone commands:

- `PING`
- `INFO`
- `CAPS`
- `LOAD <hex bytecode>`
- `RUN`
- `STOP`
- `RESET_VM`
- `CALL <function-id-or-name> [integer arguments]`
- `CALL_MIXED <function-id-or-name> [integer arguments] "ASCII"`
- `STATUS`

Example:

    NRP/1 1 PING
    NRP/1 1 OK PONG

`LOAD` is intentionally hex for the first milestone. A later binary framing
transport can carry larger programs without changing VM semantics.

`CALL_MIXED` accepts up to eight signed 32-bit integers followed by one quoted
printable ASCII string (0–255 bytes). Use `""` when text is unused. Inside the
string, escape a quote with `\"` and a backslash with `\\`. A filename containing
spaces remains one argument. `CAPS` advertises `NATIVE_ASCII`. Existing `CALL`
and `CALL_TEXT` encodings remain supported.

    NRP/1 7 CALL_MIXED LED_EXTERNAL 0 1 ""
    NRP/1 8 CALL_MIXED SD_READ 0 32 "/captured/a photo.jpg"

Both clients encode quoting with `call-mixed NAME [NUMBERS...] ASCII`:

    irisctl call-mixed SD_READ 0 32 "/captured/a photo.jpg"
    irisctl-usb call-mixed LED_EXTERNAL 0 1 ""

## Neo command proxy

Iris exposes Neo-owned Linux functions through its ordinary native registry.
They are callable from a VM `SYS` instruction or remotely with `CALL`; Iris
forwards only named NRP/1 operations to Neo's private USB address on port 4243.
This is not a general shell. Initial functions are `NEO_CAPS`,
`NEO_IR_STATUS`, `NEO_IR_SCAN_START`, `NEO_IR_SCAN_STOP`, and
`NEO_IR_SCAN_READ`. `NEO_CAPS` asks the Linux endpoint for its current function
list. The IR calls return an unavailable error until Neo's Linux IR driver has
registered the NanoHat receiver.
