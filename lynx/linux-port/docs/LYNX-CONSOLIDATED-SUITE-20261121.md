# Lynx Consolidated Test-Suite Runner (Round 6, Item D20)

- **Deliverable**: `lynx/tools/run_all_lynx_tests.py` (+ `test_run_all_lynx_tests.py`, 38 tests)
- **Purpose**: one command, offline, that runs every Lynx test suite across
  all tool directories, reports per-suite test counts and wall-clock time in
  a formatted markdown (or JSON) summary, and gates on a
  `git diff --check`-equivalent whitespace scan over the tracked `lynx/` tree.
- **Safety boundary**: strictly offline — no network, no SSH, no device
  contact, no writes outside the child processes' own temp usage. Every suite
  runs in an isolated subprocess with a per-suite timeout (default 300 s).

---

## 1. Usage

```sh
# Default: run everything, print markdown report, exit 0 if green
python3 lynx/tools/run_all_lynx_tests.py

# Machine-readable
python3 lynx/tools/run_all_lynx_tests.py --json

# Fully provisioned host (clean-clone verification): env-blocked counts as failure
python3 lynx/tools/run_all_lynx_tests.py --strict

# Flags: --root DIR  --timeout SECONDS  --skip-whitespace
```

## 2. Discovery scope

* `test_*.py` at the top level of `lynx/tools/` **and** in each immediate
  subdirectory (`agent/`, `bluetooth/`, `camera_deps/`, `display/`, `fingerprint/`,
  `flashlight/`, `gnss/`, `headset/`, `health/`, `nfc/`, `touch/`, `ui/`, `usb/`,
  and any new tool directory); `__pycache__/` and dot-directories are skipped.
* Discovery is **filesystem-based**, so a tool directory that exists on disk
  but is not yet whitelisted in `lynx/.gitignore` (an in-flight landing by
  another agent) is picked up too. Observed 2026-11-21: Banshee's in-progress
  B22 `thermal_zones/` added `test_lynx_thermal_zones_validator` to the run
  mid-session (87 → 88 suites between two invocations). That is correct
  local-runner behavior; the per-run counts in §6 are snapshots.

## 3. Execution model

* One subprocess per suite: `python -m unittest <stem>` with `cwd` set to the
  suite's directory (so local imports resolve exactly as in the tool READMEs),
  `capture_output`, per-suite `timeout` (default 300 s → `TIMEOUT` result).
* **Child PATH hardening** (§5.1): the runner prepends the standard system
  directory that holds `modinfo` when it is not already resolvable
  (Ubuntu ships kmod in `/usr/sbin`, which minimal exec contexts miss).
  No other environment change is made.

## 4. Result classification and exit contract

| Status | Meaning | Affects exit? |
| --- | --- | --- |
| `ok` | unittest suite ran and passed | — |
| `script-ok` | file collects zero unittest tests (standalone offline test script); re-run directly as `python3 <file>`, exit 0 | — |
| `failed` | tests ran, ≥1 failed/errored, or import crashed on a code defect | **yes → exit 1** |
| `script-failed` | standalone script exited nonzero | **yes → exit 1** |
| `env-blocked` | a system dependency is missing (named in the report): the suite could not even import (a Python module or a binary), **or** the suite ran and every failure is a missing machine-specific `artifacts/` file (an untracked build output absent from a fresh checkout) | **no** by default; **yes** with `--strict` |

Exit 0 requires: ≥1 suite discovered, no `failed`/`script-failed`, whitespace
scan clean (unless `--skip-whitespace`), and — only under `--strict` — no
`env-blocked`. The env-blocked list is **always** printed, so a dependency gap
can never hide silently in the report.

### 4.1 Missing-artifact classification (D29, Round 9)

A fresh `git clone --no-local` lacks the machine-specific build outputs
under `lynx/linux-port/artifacts/` (e.g. `busybox-wifi-ssh-twostage-v19/`,
`stock-cph2493-…/mtu3.ko`, `wifi-dhcp-retry-v47-offline/`). Suites that need
one used to be misreported as `FAIL`. The runner now classifies a suite
`env-blocked` when a missing artifact is the cause, detected from the child
process' stderr:

* import crash naming a file under an `artifacts/` directory, or
  `…not found at …/artifacts/…`;
* a unittest run where **every** `FAIL:`/`ERROR:` block is a missing-artifact
  error (a single real failure anywhere keeps the suite `failed`);
* a standalone script whose nonzero exit is a missing-artifact `FileNotFoundError`.

The report names the artifact (`missing artifact: <path>`), so an environment
gap can no longer masquerade as a code defect. A real assertion failure mixed
with a missing-artifact error is still reported `failed`, so a genuine bug is
never hidden behind an environment gap.

### 4.2 Standalone-script fallback

Two pre-existing top-level files are standalone scripts with `main()`, not
unittest modules (they predate the house unittest pattern and are run as
`python3 <file>`):

* `test_lynx_charge_cap_offline.py` (V48 charge-cap fixtures, commit `3ff0cf0`)
* `test_v47_dhcp_retry.py` (V47 DHCP retry fixtures, commit `1e6df05`)

Both verified offline and green on 2026-11-21:

```
$ python3 test_lynx_charge_cap_offline.py
charge-cap fixture transitions passed; no hardware contacted   (exit 0)
$ python3 test_v47_dhcp_retry.py
{"state": "v47-dhcp-retry-fixtures-passed", ...}              (exit 0)
```

## 5. Environment findings (evidence for the report)

### 5.1 `modinfo` PATH gap (host quirk, not a code defect)

Five suites (`test_lynx_usb_mtu3_preflight`, `test_trial_v53_usb_ram`,
`test_trial_v53_nfc_ram`) invoke `modinfo`, which exists on Nexus at
`/usr/sbin/modinfo` but is absent from minimal exec-context PATHs:

* Before fix: `FileNotFoundError: [Errno 2] No such file or directory: 'modinfo'`
  (1 error per suite; `test_trial_*` additionally failed
  `test_default_never_contacts_phone` because `main([])` hit the same gap).
* With `/usr/sbin` on PATH: **all three suites OK** (verified 2026-11-21).

The runner's targeted PATH hardening makes the consolidated result independent
of the invoking shell (login shells already had this; harness exec did not).

### 5.2 `dbus_next` (genuine missing Python dependency on Nexus)

`test_lynx_ble_gatt_probe` imports `dbus_next` (pure-Python D-Bus), which is
not installed for Nexus's system Python 3.14. It is reported `env-blocked`
and excluded from the default exit code. Verified the suite itself is green
when the dependency is present — disposable venv, not committed:

```
$ uv venv /tmp/blecheck-venv && uv pip install --python /tmp/blecheck-venv/bin/python dbus-next
$ /tmp/blecheck-venv/bin/python -m unittest test_lynx_ble_gatt_probe
Ran 7 tests in 0.004s — OK
```

Unblock for `--strict`-green: install `dbus-next` for the interpreter that
runs the suite (a runtime venv under `common/runtime/` is the house pattern;
left as a follow-up decision for Banshee/Aria).

## 6. Whitespace sanity gate (conventions)

Scans every git-tracked file under `lynx/` (via `git ls-files`; bounded
fallback walk). Violations: trailing space/tab, missing EOF newline,
`<<<<<<<` conflict markers. Exemptions (deliberate, documented):

* **`*.patch` / `*.diff` fully exempt** — kernel source-of-truth artifacts;
  trailing context whitespace is significant (e.g.
  `linux-port/patches/camera-yuv-irq/0001-*.patch`).
* **`.md` lines ending in 2+ spaces** = Markdown hard breaks, not stray
  whitespace (52 pre-existing lines in review docs rely on this).
* Binary files and files >10 MiB are skipped.

**Findings and fix (pre-existing, flagged for Banshee review):** exactly two
genuine violations in the tree — stray single trailing spaces at lines 34 and
62 of `lynx/linux-port/docs/LYNX-USB-ATTENDED-TEST-PLAN-20261121.md`
(`*   `partial`:` / `2. **Observe Disconnected State:**`). Removed; diff is
whitespace-only. After the fix: **0 violations across all tracked lynx files**.

## 7. Full-run evidence (2026-11-21, Nexus)

```
$ python3 run_all_lynx_tests.py
# Lynx Consolidated Test Suite Report
**Overall: PASS**
- Suites: 87 total, 86 ok, 0 failed, 1 env-blocked
- Tests: 863
- Wall clock: 8.93s
- Whitespace sanity (git diff --check equivalent): CLEAN
- Env-blocked (missing system dependency, suite not run):
  `test_lynx_ble_gatt_probe` [missing python module: dbus_next]
(exit 0)

$ python3 run_all_lynx_tests.py --strict
**Overall: FAIL**  (sole cause: the env-blocked suite above)
(exit 1)
```

The 87-suite snapshot includes the two standalone scripts counted as
`script-ok` and Banshee's in-flight B22 suite (present on disk at run time).
Runner self-tests: `python3 -m unittest test_run_all_lynx_tests` → 30 OK.

## 8. Known limitations

* Discovery is two levels deep (top + immediate subdirs); a test file placed
  two levels down would be missed — no current suite does this.
* `env-blocked` names the missing dependency but cannot install it;
  `--strict` is the verification mode for provisioned hosts.
* Counts are per-run snapshots while the tree is being worked on live by
  another agent (see §2).
