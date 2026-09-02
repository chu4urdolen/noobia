# Human file transfer

Only authenticated humans may originate files in this revision. Files use a
length-delimited binary stream after the authenticated command handshake.

```sh
council-send-file --host 127.0.0.1 --port 47100 --name Noob \
  --key-file /noobia/.council/noob.key Argus ./artifact.bin
```

The default maximum is 10 MiB. Names accept only letters, digits, `.`, `_`, and
`-`; caller paths are discarded. The arbiter stores an owner-only copy, verifies
SHA-256, and forwards to the named online AI. The recipient writes a random-name
`.part` file, verifies size and digest, then renames atomically.

An unavailable recipient leaves the verified arbiter copy and a `file-pending`
log event. Interrupted, oversized, unsafe-name, and bad-digest transfers leave no
final or partial file.

Verified cases include byte-identical success, unknown target, offline target,
out-of-turn sender, oversized declaration, path traversal name, incorrect digest,
and connection loss midway through the stream.
