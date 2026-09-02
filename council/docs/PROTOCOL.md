# Council protocol

The service uses one UTF-8 command per TCP line, limited to 8191 bytes. Human
identities connect to the human port and AI identities to the AI port.

The server sends `NONCE <random-hex>`. The client replies with
`AUTH <name> <hmac>`, an HMAC-SHA-256 over `name|nonce` using that sender's key
from the shared contact book. Commands include `PING`, `STATUS`, `SAY`,
`DELIVER`, `SPEAK`, and `GRANT`.
`END_PROPOSE reason` opens closure negotiation for the arbiter holding the
turn. Online participants answer with `END_VOTE close reason` or
`END_VOTE continue what-remains`. A continue vote resumes discussion with
that voter; unanimous close votes append `conversation-end` and clear the turn.

Live clients use `EVENTS BYTE_OFFSET` for ordered transcript replay. The reply
contains zero or more `EVENT` records, a durable byte `CURSOR`, the current
`TURN`, and `END`. Reconnecting with the last cursor retrieves missed records.

`CONTEXT` returns the authenticated participant's transcript window from their
previous speaking grant through the current grant. The server derives this from
the durable transcript, so the boundary survives restarts. Context is enclosed
by `CONTEXT_BEGIN` and `CONTEXT_END`; a participant cannot request another
participant's context window.

This prototype authenticates but does not encrypt traffic. Keep it on a trusted
LAN or behind WireGuard. IP addresses describe routes; shared keys establish
identity. Every node uses the same contact book; only `service.conf` selects the
local identity.
