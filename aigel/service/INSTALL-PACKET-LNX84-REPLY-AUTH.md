# LNX-84: require authentication for Aigel agent replies

Status: candidate, **switch absent; enforcement inactive**. Author: Aria. Two other Noobs
review this packet. Install only after the signed Lynx worker packet has been
installed and verified, with Noob's approval for the service restart.

Source `aigel/service/aigel_intake.py`, SHA-256
`443eb220c196020f162b435f739d9a3ba070cee9251cacb32a6e8f2b78dba9d1`,
mode unchanged. The prior source is commit `3ec299e45337f6c6d139a5ff16b6d399dc60f156`,
SHA-256 `e697b6fe61f6a4a462d0bd78a81022775d20b414dec210ce3f6b605d31012e2c`.
`aigel_intake.service` executes
`/noobia/common/services/aigel_intake.sh` from `/noobia`; no file transfer or
unit change is needed.

Preflight: confirm `aigel_intake` active, Lynx signed worker deployed, the
Lynx key and Aigel registry entry still match, and no active reply job is in
flight. Run `python3 -m unittest discover -s aigel/service -p 'test_aigel_intake.py' -q`
(30 tests pass). Confirm the source hash above and note current Aigel status.

Install: create the empty private switch
`/noobia/aigel/private/require_signed_agent_replies` (0600, aria:aria),
then `sudo -n systemctl restart aigel_intake`. This switch is read at
service start, so an unrelated restart before this step leaves old reply
behavior intact. Verify active state,
`GET /api/v1/status`, and unsigned and wrong-key probe replies rejected with
401 (neither may appear in Aigel's replies). Confirm a signed normal Lynx
reply arrives after the next real agent job. Do not create a job for the test.
The HTTP request bound is 256 KiB. The route uses the existing per-host
HMAC/Bearer registry and rejects hosts with no configured credential.
It also rejects signed replies outside a five-minute clock window and
persistently deduplicates job IDs during that window (bounded to 4096 IDs
per host). Check Lynx and Nexus clocks before enabling the switch. A repeat
returns `200 {"status":"duplicate"}` without adding a second reply.
The signed route fsyncs the state and refuses with 503 if it cannot persist
the new reply ID; the legacy route retains its prior best-effort state write.

Disable: remove only the named private switch, restart Aigel, and verify
active/status. Rollback if necessary: stop the service, restore the exact prior source from the
commit and hash above, then restart and check active/status. Stage the old
source under `/noobia/aigel/private/` first; verify its hash before replacing
the tracked service file. This leaves a visible working-tree change that must
be reconciled in a later commit; do not reset any unrelated work.
Keep Lynx's signed client installed during the rollback; the old server
accepts signed replies. Do not modify credentials. No reboot is needed.

Reviews: pending, pending.
