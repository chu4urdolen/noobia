# RAM log readback review after the USB-role trial

Lynx is left in Fastboot after successful stock boot_a undo. Native Linux has
not been demonstrated on the hardware. Further USB-init image variants lack
sufficient new evidence; obtaining actual kernel crash records is the next priority.

User authorization was expanded to permit judged-safe authentication bypasses.
The earlier no-bypass review records describe their original scope, not a current
authorization prohibition. No bypass was executed in this investigation.

`audit_loader_auth_keys.py` evaluates only public modulus fields from the pinned
MTKClient key definitions against the exact saved stock DA2. None of eight keys
matches its big-endian modulus-selection rule. No key material is sent to the phone,
and no private key fields are evaluated or included in the audit output.
This removes the tool's existing known-key path as a demonstrated solution.

The earlier Carbonara-style RAM hash redirect was rejected by Lynx; it was not
repeated. A distinct HeapBait method exists in the same pinned checkout, revision
cd25cf9c1ff6d36e82697ac2c798e69e9cfb78c3. An isolated AST-selected analysis class
excludes all transport, exploit execution, payload building and patch methods.
`audit_heapbait_offline.py` extracts all parameter sets from the exact saved loader.
Its missing patch-marker string is only a heuristic, not exploitability proof.

Independent disassembly confirms heap setup at 0x40009dc8: base 0x4008fd80,
end 0x7208fd80, size 0x32000000. The large reported size is present in the
loader instructions rather than a confirmed analysis error. The upstream method
would create an approximately 80 MiB NOP sled and deliberately corrupt/repair
RAM heap state. It also patches several security-policy functions, not solely
storage read access. Its unchecked return handling and general mutation surface
must not be treated as a ready read-only diagnostic.

The exact upstream payload was missing from the sparse checkout. It was fetched
for offline inspection into `artifacts/heapbait-review/heapbait_arm64.bin`,
8336 bytes, SHA256 89413d885b92bb9dce2d0682fa0a88d398da1214d412ff93250dbea84b6d7b48.
Its Git blob was checked against the pinned revision. The payload exposes arbitrary
RAM patch and function-call commands; a linear disassembly alone does not prove
all effects. `heapbait-payload-audit.json` and the saved disassembly document this.

Original payload source was saved in `sources/mtk-payloads-review`, revision
4c53c01111a90fa8e81498454fcc27bf8fabb183. Its current command registration differs
from the downloaded binary, so exact source/binary correspondence has not been
established. It cannot yet substantiate a claim that this exact binary is safe.

A possible narrower future approach is a separately built payload that exports
only the confirmed pstore RAM region, with no flash, security-policy patch,
general RAM-write or arbitrary-call command. It still requires independently
checked heap/loader pointers, reviewed heap repair, a bounded host transport,
and proof that pstore survived the loader transition. It is not prepared or
approved for execution by this review. Reading RAM may fail to recover the
original crash log even if the session succeeds.

References: [MTKClient method](https://github.com/bkerler/mtkclient/blob/cd25cf9c1ff6d36e82697ac2c798e69e9cfb78c3/mtkclient/Library/Exploit/heapbait.py),
[original payload source](https://github.com/shomykohai/mtk-payloads/tree/4c53c01111a90fa8e81498454fcc27bf8fabb183/hakujoudai).
