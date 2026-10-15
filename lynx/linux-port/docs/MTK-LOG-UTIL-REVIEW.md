# mtk-log-util: offline review for Lynx

Reviewed wrapper commit `b8b92c24c9de31af2ca011ae4e491da7fa86936d` and its exact
MTKClient submodule commit `9377bfa0553e42089a9376bc4773765e129dbc37`.
Sources and SHA-256 manifest are preserved under
`sources/mtk-log-util-review/`. No device was contacted during this review.
No full wrapper, MTKClient initialization, loader, exploit or authentication
routine was executed. A reviewed pure command-formatting function was tested
with a mocked executor; all three expected command strings were checked.
The preserved audit script is `audit_mtk_log_util.py`, with results in
`docs/mtk-log-util-audit.json`.

## Compatibility and acquisition

The dependency recognizes MT6983 (hardware code 0x907) and selects XML DA mode.
This establishes configuration recognition, not working read access on Lynx.
The wrapper is an MTKClient subprocess frontend, not a Fastboot log reader.

| Mode | Delegated command | Prerequisite |
| --- | --- | --- |
| expdb | `mtk.py r expdb ...` | Usable storage-read session and partition lookup |
| pstore, default | `mtk.py da peek ...` | Usable DA session and custom memory-read extension |
| pstore, without DA | `mtk.py peek ...` | Preloader memory-read access; DAA can trigger a bypass path |

The wrapper default pstore address was copied from MT6833P. Independently,
Lynx's saved log `logs/pllk-1791606541890396711.clean.txt` confirms address
0x48090000 and size 0xe0000, so the defaults do match this observed session.
Multiple boot/recovery transitions mean the age and retention of RAM contents
are unknown. Saved expdb data would remain the preferable evidence if it can
be read through an authenticated or verified non-bypass interface.

## Constraint check

The pinned DA setup includes automatic security-handling paths. XML loader
upload checks session SLA and can try known-key or dummy authentication;
that handling is not disabled merely by stock mode. Non-DA peek explicitly
calls bypass_security when DAA is enabled. Therefore --dont-peek-via-da is
not an option that guarantees compliance with the no-bypass constraint.

Lynx's prior guarded stock loader reached stage 2 but required session
authentication. Our guard stopped before partition readback or fallback-key
attempts. See `STOCK-LOADER-AUTH-RESULT-20261010.md`. The wrapper adds no
independent authentication or read-only transport to resolve that barrier.
An unlocked Android bootloader does not establish an authorized DA session.

No compliant live acquisition route has been established by this review.
Do not launch the wrapper on Lynx. The user prohibited flash, erase and
authentication bypass; none was attempted. No USB query was needed here.

## Output limitations

The wrapper scans for printable ASCII, ignores compressed records, and deletes
its temporary binary dumps after conversion. Lynx's stock configuration selects
deflate pstore compression, so ASCII output alone can miss compressed crash
data. Auto-detection falls back to defaults on failure. It has no offline-input
CLI and uses shell-interpolated arguments without serial-scoped, bounded device
access. A future decoder should preserve the complete raw dump and hashes,
then parse/decompress records locally; extracting strings is only a supplement.

## Recommendation

Keep the source and audit for reference. Continue using the already verified
Fastboot preloader/LK log export for its limited scope. For kernel crash data,
we need an authorized expdb read path, a functioning read-only recovery shell,
or an early hardware console. This wrapper alone supplies none of those.
Do not move Lynx into preloader/BROM merely to repeat the known barrier.

Primary references:

- [Pinned wrapper source](https://github.com/chkndrp/mtk-log-util/blob/b8b92c24c9de31af2ca011ae4e491da7fa86936d/logutil.py)
- [Pinned MTKClient chip configuration](https://github.com/bkerler/mtkclient/blob/9377bfa0553e42089a9376bc4773765e129dbc37/mtkclient/config/brom_config.py)
- [Pinned DA initialization and SLA handling](https://github.com/bkerler/mtkclient/blob/9377bfa0553e42089a9376bc4773765e129dbc37/mtkclient/Library/DA/xml/xml_lib.py)
- [Pinned non-DA peek implementation](https://github.com/bkerler/mtkclient/blob/9377bfa0553e42089a9376bc4773765e129dbc37/mtkclient/Library/mtk_main.py)
