# Lynx diagnostic tools — preserved on Nexus

All phone-work artifacts are kept under `/noobia/lynx`. Argus is powered
off after archive restoration; these tools and the Linux build do not require
him. Cached ARM64 BusyBox validation evidence remains available locally.

## Current V52 entry points (2026-10-30)

Use the [Lynx code map](../../docs/noobs/LYNX.md) and
[hardware tool contract](../linux-port/docs/LYNX-HARDWARE-TOOLS.md) for current
paths. `lynx_noob_runtime.py` runs the Iris-compatible NRP/1 server;
`lynx_noobctl.py` calls it from Nexus. `lynx_hardware.py` is the shared local
inventory behind five JSON-stdin wrappers in `local_calls/` and native IDs
390–394. `lynx_microphone_level.py` provides a one-second level-only local
tool and native ID 395, with no saved audio and mixer restoration. The other
four devices have status tools only while their driver trials remain pending.
`analyze_v50_module_dependencies.py` builds a read-only stock module graph.
The older V49 sections below remain for the historical display work; check
the V52 connectivity report before running any old trial script.
The V50 hardware installers are one-shot deployment records and refuse to
overwrite their existing rollback copies. Review the current source and live
hashes before writing a new update installer.

The current shared-radio investigation and V52 offline candidate are in
[`LYNX-CONNECTIVITY-PRECAL.md`](../linux-port/docs/LYNX-CONNECTIVITY-PRECAL.md).
`lynx_boot_a_v52_trial.py --prepare` checks the exact V52 and V50 images without
contacting Lynx. `trial_v52_bluetooth_hci.py` is the guarded post-boot HCI
probe. `read_lynx_bt_factory_addr.py` reads only the factory Bluetooth address;
the guarded HCI probe can apply it to controller RAM and test a Nexus link.
`trial_v52_bluetooth_hci.py --bluez-power` now proves a bounded standard
`hci0` and BlueZ power-on through `lynx_stpbt_hciuart_bridge.py`; it starts
neither service at boot. The bridge's exact one-bit feature correction and
rollback evidence are in the connectivity report. `lynx_bt_mgmt_query.py`
checks kernel management index visibility without revealing payloads.
The `--gatt-probe` variant stages `lynx_ble_gatt_probe.py` and a temporary
Python D-Bus library in RAM. `lynx_ble_nexus_ping.py` proved an unpaired
NRP/1 `PING` round trip over BLE on V52; see
[`LYNX-BLUETOOTH-NRP.md`](../linux-port/docs/LYNX-BLUETOOTH-NRP.md).
Bluetooth remains off at boot and the GATT probe accepts only `PING`/`INFO`.
The trial scripts use Python `dbus-next==0.2.3` on Nexus. Recreate the ignored
local dependency with `python3 -m pip install --no-deps --target /noobia/lynx/tools/vendor_dbus_next dbus-next==0.2.3`;
the installer stages that pure-Python package on Lynx from this directory.
`lynx_bluetoothd.py` and `lynx-bluetooth-openrc.sh` are an installed but
boot-disabled service candidate. `trial_v52_bluetooth_service.py` proved three
same-boot start, BLE PING (later INFO), and stop cycles with healthy cleanup. See the
Bluetooth NRP report before enabling it at boot; authorization and power-use
tests are still open.
`trial_v52_gps_pwr.py` and `trial_v52_gps_scp_stack.py` loaded the exact stock
GNSS power/SCP modules into V52 RAM. `trial_v52_gnss_mnld.py --start-mnl
--capture-logd --port2` is the bounded native NMEA trial, and
`parse_lynx_mnl_nmea.py` checks fix validity. See the connectivity report for
the exact receipts and prerequisites before repeating a hardware trial.
`trial_v52_gnss_mnld.py --sky-trial` is prepared for a 60-second outdoor fix
check once Lynx has sky view and still has Wi-Fi. If Lynx has rebooted,
`stage_august_gnss_bundle.py` restores the verified stock GNSS userspace to
`/run/lynx-gnss-static` without writing phone storage; the matching GNSS
modules must also be loaded before another receiver trial. On the current
V52 boot, that stable path points to the already verified RAM bundle.

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
