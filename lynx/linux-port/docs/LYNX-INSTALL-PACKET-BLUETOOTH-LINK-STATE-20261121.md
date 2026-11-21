# Install packet B-37a: lynx_bluetooth_link_state agent tool

- **Author:** Banshee (Spirit of Initiative 💙).
- **Reviews:** Gwyn / Dushich second-reviews. Aria installs, in install session IS-1.
- **Status:** ready for review.

## Why

Lynx requires agent-facing visibility into Bluetooth controller power, OpenRC supervisor health, runlevel autostart safety, and connected peer topologies without radio actuation (from design B6).

`lynx_bluetooth_link_state` performs a read-only evaluation of the Bluetooth subsystems and outputs a structured JSON verdict (`RADIO_OFF`, `READY_UNLINKED`, `CONNECTED`, `DEGRADED`, or `DISABLED_BY_SWITCH`). It does not transmit radio signals, pair devices, or alter OpenRC runlevels.

## Files

| Repository | Phone | Mode | SHA-256 |
| --- | --- | --- | --- |
| `lynx/tools/bluetooth/lynx_bluetooth_link_state.py` | `/usr/local/bin/lynx-bluetooth-link-state` | `0755` (root:root) | `ceb2f8c37848718f8a48343a26241f0c243d5b66fee1c8f0a47bfb2c5d8f6129` |
| `lynx/tools/bluetooth/catalog_proposal/lynx_bluetooth_link_state.sh` | `/usr/local/share/lynx/agent-tools/lynx_bluetooth_link_state.sh` | `0755` (root:root) | `707ada896606fff33f8f4297c7d3b1b1dfd1f81b007d06855933523f70596a0f` |
| `lynx/tools/bluetooth/catalog_proposal/lynx_bluetooth_link_state.json` | `/usr/local/share/lynx/agent-tools/lynx_bluetooth_link_state.json` | `0644` (root:root) | `ebe690633c67c08d45522fa7c9d9dc15358ab583ca301269865b15ff7d0e4158` |

## Local Disable Switch

File: `/etc/lynx/disable-bluetooth-link-state`
When present, the tool immediately exits with `status: DISABLED_BY_SWITCH` without executing commands or querying subsystems.

## Preflight (read-only)

```sh
python3 lynx/tools/lynx_remote.py run "python3 --version; test -d /usr/local/share/lynx/agent-tools && echo tools_dir_ok; test ! -e /usr/local/bin/lynx-bluetooth-link-state && echo target_clean"
```

Expect:
- Python 3.12+ available.
- `tools_dir_ok`.
- `target_clean`.

## Install Steps

1. Copy Python tool executable:
   ```sh
   cp lynx_bluetooth_link_state.py /usr/local/bin/lynx-bluetooth-link-state
   chmod 0755 /usr/local/bin/lynx-bluetooth-link-state
   chown root:root /usr/local/bin/lynx-bluetooth-link-state
   ```
2. Copy agent tool wrapper and schema:
   ```sh
   cp lynx_bluetooth_link_state.sh /usr/local/share/lynx/agent-tools/
   chmod 0755 /usr/local/share/lynx/agent-tools/lynx_bluetooth_link_state.sh
   chown root:root /usr/local/share/lynx/agent-tools/lynx_bluetooth_link_state.sh

   cp lynx_bluetooth_link_state.json /usr/local/share/lynx/agent-tools/
   chmod 0644 /usr/local/share/lynx/agent-tools/lynx_bluetooth_link_state.json
   chown root:root /usr/local/share/lynx/agent-tools/lynx_bluetooth_link_state.json
   ```
3. Compile check:
   ```sh
   python3 -m py_compile /usr/local/bin/lynx-bluetooth-link-state
   ```

## Verify

1. **Verify executable directly:**
   ```sh
   python3 lynx/tools/lynx_remote.py run "/usr/local/bin/lynx-bluetooth-link-state"
   ```
   Expect exit 0, and JSON output with `status` (`RADIO_OFF` or `READY_UNLINKED`) and `is_valid: true`.

2. **Verify tool manifest in agent catalog:**
   ```sh
   python3 lynx/tools/lynx_remote.py run "python3 -c \"import runpy; c=runpy.run_path('/usr/local/bin/lynx-agent')['Catalog'](); print('entry_ok:', bool(c.entries().get('lynx_bluetooth_link_state')))\""
   ```
   Expect: `entry_ok: True`.

3. **Verify disable switch:**
   ```sh
   python3 lynx/tools/lynx_remote.py run "touch /etc/lynx/disable-bluetooth-link-state; /usr/local/bin/lynx-bluetooth-link-state; rm -f /etc/lynx/disable-bluetooth-link-state"
   ```
   Expect: JSON with `status: DISABLED_BY_SWITCH` and `failures: ["disabled_by_switch"]`.

## Rollback

```sh
rm -f /usr/local/bin/lynx-bluetooth-link-state /usr/local/share/lynx/agent-tools/lynx_bluetooth_link_state.sh /usr/local/share/lynx/agent-tools/lynx_bluetooth_link_state.json /etc/lynx/disable-bluetooth-link-state
```

## Attendance

Attended run during IS-1. Low risk (purely read-only inspection, zero radio actuation).
