# Lynx diagnostic tools — preserved on Nexus

All phone-work artifacts are kept under `/noobia/lynx`. Argus is powered
off after archive restoration; these tools and the Linux build do not require
him. Cached ARM64 BusyBox validation evidence remains available locally.

## Active tools and archived trials (2026-10-25)

The active tree keeps the current V49 builder/validator, boot_a trial and V48
rollback, SSH and Alpine wrappers, health/power diagnostics, and display/touch
bring-up tools. One-off scripts from earlier failed trials were removed from
the active directory after dependency analysis. Their names are in
`ARCHIVED-PYTHON-TOOLS.txt`; their exact contents remain in Git commit
`0477e55` and can be retrieved with
`git show 0477e55:lynx/tools/NAME.py`. This cleanup did not touch images,
kernel sources, receipts, phone storage, or the running V49 system.

Current display proof: `trial_v47_dmabuf.py --target v49 --atomic
--show-seconds 12 --brightness 400 --no-live-trace`. This is a bounded test,
not a background service. The user must be told before any visual trial.
See `../linux-port/docs/V49-IOMMU-BEFORE-CMDQ.md` for the observed result.
`install_v49_display_bundle.py --install` stores the verified module sequence
and manual replay commands on Alpine; its default mode only checks sources,
identity, and health. It does not show pixels or enable startup.

## Files

- `platform-tools/adb`, `platform-tools/fastboot`: downloaded Google tools.
- `android-user-home`, `adb-tmp`: task-local ADB state and temporary files.
- `mtk-venv`: isolated CLI dependencies, without system package changes.
- `mtk_readonly.py`: guarded MT6983/OPLUS diagnostic entry point.
- `mtk-readonly-source-manifest.json`: hashes binding the reviewed source,
  loader, authentication reference, layout reports and offline RAM payload.
- `pin_mtk_readonly.py`: explicitly refreshes that manifest after a reviewed
  source change. It is not a substitute for reviewing new code.
- `mtk-sessions/<id>/probe-output.log`: complete later probe output.
- `../linux-port/sources/mtkclient-readback`: reduced, pinned upstream checkout.
- `../linux-port/artifacts/service-reference`: original small service resources
  and offline inspection artifacts. The offline patched DA2 is not an approved
  restoration image and must never be flashed.
- `../linux-port/docs`: hardware observations, firmware verification, loader
  authentication and failed-probe reports.
- `../search_nexus_images.py`, `../logs/nexus-image-search.json`: reproducible
  filename/archive-index search and its inventory.

## Default behavior and tested paths

Running `mtk_readonly.py` without `--connect` only verifies inputs and prints
the proposed configuration. `--self-test` exercises guards without USB access.
`--stock-table` selects a direct metadata read with the unmodified stock loader;
the latest corrected attempt connected and loaded both stages, then returned
False for the metadata acknowledgement and stopped without a transfer read.
No table was obtained. Ordinary stock mode reached DA stage 2 but
stopped on enabled session authentication before requesting the partition table.

The RAM hash probe was rejected by the loader. Live `--ram-probe --connect`
repetition is disabled; its offline payload is preserved for analysis. No
patched DA2 ran on Lynx in that attempt. Do not infer a hardware DRAM defect
from the generic loader hash-error message.

The wrapper rejects write/erase/RPMB mutation and automatic security-bypass
APIs, other boot modes, changed inputs, and unapproved commands. These are
software guards and a reviewed command path, not hardware write protection.
Live probes need a fresh physical preloader connection and a bounded timeout.
The wrapper allows ten minutes to connect, then three minutes of active work.
Use an external fifteen-minute timeout with a five-second hard-kill fallback;
a shorter total timeout can interrupt a valid late connection.
No diagnostic option authorizes a Linux flash or proves restoration capability.

The image builder and independent validators are under `../linux-port`.
Native Linux remains the goal; Android restoration is not a prerequisite.
