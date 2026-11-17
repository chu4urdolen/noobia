# Stock metadata probe: connected phase interrupted by deadline

Session `1791593553575115672` successfully handshook with MT6983, uploaded the
original signed DA1 and unchanged DA2, and logged
`Requesting stock partition-table metadata; no authentication attempt`.
The external ten-minute timeout then ended the process with exit code 124.
No `stock-partition-table.xml` was produced. No explicit read-denial response
was captured. This is not proof that the stock loader allows or denies metadata
reads; the shared preparation/connection deadline interrupted the test.

The wrapper now uses separate phases: up to ten minutes awaiting a fresh
handshake, then a new three-minute active deadline after device identification.
The external timeout must be fifteen minutes, with a five-second hard-kill
fallback. This covers both internal bounded phases without expiring immediately
after a late physical connection. No method or payload changed in this fix.

The phone remains in a RAM diagnostic state until power-cycled. There were no
partition writes, erases, slot changes or Linux-image downloads in this attempt.
