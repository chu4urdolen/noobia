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
- `STATUS`

Example:

    NRP/1 1 PING
    NRP/1 1 OK PONG

`LOAD` is intentionally hex for the first milestone. A later binary framing
transport can carry larger programs without changing VM semantics.
