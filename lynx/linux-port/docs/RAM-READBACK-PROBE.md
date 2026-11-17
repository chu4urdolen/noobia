# Bounded RAM readback probe for Lynx

Stock DA stage 2 requires session authentication. Eight upstream DA public-key
identifiers were checked offline; none matches this loader. The older signed
DA1 has none of the upstream Carbonara patch markers, and contains the exact
SHA-256 digest of its unsigned DA2 at offset 579248. These are compatibility
indicators, not proof of a working hardware bypass.

The prepared probe uses the same accepted signed DA1. It attempts to replace
only the embedded DA2 hash in RAM at 0x0108d6b0, then load the reviewed patched
DA2 into RAM at 0x40000000. The patched reference changes 35 bytes in the loader
and relaxes erase/write policy checks; consequently it must never be described
as intrinsically incapable of writing flash. Our host wrapper permits only
printgpt and blocks storage write, erase, RPMB write/authentication, automatic
security bypass, alternate boot mode and fallback loader APIs. It does not load
the upstream custom extension payload or derive hardware keys.

The exact reviewed payload, inputs and source files are pinned by hashes under
`tools/mtk-readonly-source-manifest.json`. Offline tests exercise the two RAM
addresses and payload bytes, reject other modes and storage commands, and stop
on malformed, missing or enabled session-authentication state. This is a
software guard and reviewed command path, not a hardware enforcement boundary.

The live probe must use `--ram-probe --connect`. Its external timeout terminates
the process after ten minutes, with a hard kill five seconds later if needed.
It stops without fallback on any RAM upload, identity, integrity or remaining
authentication failure. Complete stdout/stderr is saved in its fresh workspace
session directory. A power cycle removes RAM loader changes.

No stored partition is to be written by this probe. A successful GPT read would
be a first diagnostic result, not a verified backup or a restoration guarantee.
The native Linux flash still awaits the agreed restoration requirements.
