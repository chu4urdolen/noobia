# V50 display status-screen candidate

V49 proved the stock Tianma panel can show an atomic DRM primary-plane
color-bar image. The V50 boot at `192.168.100.107` retains the same early
IOMMU checkpoint and the V49 image remains available for boot_a rollback.

The updated `tools/lynx_drm_dmabuf_pattern.c` adds `--show-ui 1..15`: a
short-lived Lynx / Alpine / battery status image. Existing `--show-atomic`
behavior is unchanged. The image is rendered in memory and uses the same
atomic commit path as the V49 visual proof. It does not install a compositor
or persistent display service.

Preparation on 2026-10-26:

- Host C syntax passed with `-Wall -Wextra -Werror` against the local libdrm
  headers; a 1240×2772 offline preview is in `logs/ui-preview/lynx-ui.png`.
- `tools/stage_v50_ui_candidate.py` staged the source and compiled it with
  Alpine GCC on Lynx. Receipt:
  `logs/v50-ui-stage-1793036773438198487/result.json`.
- Staged source SHA-256:
  `ecf8e55f6fcbba97543aa391da55ee555ccac760148df7b92942f89853aa9a25`.
  Native binary SHA-256:
  `69b6e00947b3741e3adbdfc966df33f9cb5abc137a2b64e8631b0ed868a4ed70`.
- The binary has **not** been executed. The panel remains dark on this boot.

The V50 display and touch bootstrap tools now recognize the static V50 IP
and pinned rescue image. The display trial retains a battery floor of 50%
and the established temperature limits. The original offline-charger rule
predated reliable charging. V50 now also accepts a charger only when the
stock driver reports `online=2`, `Charging`, and selected `[DCP]`; earlier
targets retain their original offline requirement. Tell Noob before the
visual check. Do not repeat panel binding on an already probed boot.

The Hama charging stack is proven across one reboot; see
`V50-CHARGING-STARTUP.md`. On 2026-10-27 the phone was already unplugged
when the display guard was revisited, at 60% battery and 25.2°C.

Noob reconnected the Hama cable. One display-bootstrap attempt stopped before
loading a module because the new attach was still in its 27-second charger
type check (`usb_type=[Unknown]`). The guard worked as intended. After the
stock driver selected `[DCP]`, the V50 bootstrap completed on boot ID
`98813e2e-f528-419f-90fa-c9016dc0c005`: DRM card registered and Alpine
health passed. Receipt: `logs/v50-display-bootstrap-1793052265066021387/`.
The panel remained dark. A separate test-only atomic commit of the pinned
status-screen binary was accepted at 1240×2772@60 Hz, and Alpine health
remained clear. This was the preflight before the visual trial below.

Noob watched the first V50 status-screen trial on the Hama charger. The first
attempt stopped before modeset because the optional `/dev/kmsg` stream exited
with a broken pipe. Receipt:
`logs/v50-dmabuf-trial-1793052317677198618/result.json`. Alpine remained
healthy and panel brightness stayed zero. The second attempt used the
documented post-trial `dmesg` fallback and completed one 12-second
`--show-ui` run with brightness 400 for five seconds. The program printed
`displaying Lynx status`, exited zero, and restored brightness to zero.
Receipt: `logs/v50-dmabuf-trial-1793052336575098497/result.json`.

**Noob saw only a black screen.** The kernel logged two genuine CMDQ thread
timeouts while waiting for event 644 (the same event that affected an older
legacy DRM test), CRTC timeout callbacks, and subsequent ESD/doze warnings during
the second trial. These errors were absent from the successful V49 color-bar
trial. A charger interaction is unproven; the V50 status image, panel state,
and current boot's module ordering also differ. Lynx stayed on boot ID
`98813e2e-f528-419f-90fa-c9016dc0c005` with Alpine health clear, charger
DCP, 60% battery, and brightness zero. Stop display trials until the CMDQ
trace is reviewed. Noob explicitly asked to be consulted before any next
trial and will say when ready. At uptime 1655, read-only SSH confirmed the
same boot, brightness zero, Alpine health clear, and no further CMDQ timeout
after the two trial events.

Offline comparison with the successful V49 atomic trial found a concrete
sequence difference: V49 logged `lcm_panel_reset`, `lcm_panel_init`, and
`lcm_prepare: Successful` immediately before the modeset. The captured V50
log contains no `lcm_prepare` before its first event-644 timeout; its first
`lcm_prepare: Successful` came during ESD recovery after the timeout. This
suggests a panel prepare/state issue on the V50 boot, but does not establish
why that sequence differed. The pixel pattern itself uses the same atomic
commit path as V49. Review panel initialization and command timing offline
before selecting a next trial. Noob will signal when ready for that trial.

## Same-boot recovery and first Lynx UI visual proof

Noob later signalled readiness. On the **same** V50 boot, with 63% battery,
25°C pack, verified Hama DCP charging, DRM card present, and brightness zero,
the original V49 atomic color-bar binary ran for eight seconds at temporary
brightness 400. **Noob saw the test stripes.** The phone stayed on the same
boot, brightness returned to zero, and Alpine health remained clear. The
post-trial kernel scan found idle/doze warnings but **no new CMDQ timeout**.
The panel driver logged `lcm_panel_reset`, `lcm_panel_init`, and
`lcm_prepare: Successful` immediately before the backlight command. Receipt:
`logs/v50-dmabuf-trial-1793053145280893284/result.json`.

At Noob's next cue, the pinned V50 `--show-ui` binary used the same guarded
atomic path for eight seconds with brightness 400. **Noob saw Lynx's status
screen.** The program exited zero, brightness returned to zero, the phone
stayed on boot ID `98813e2e-f528-419f-90fa-c9016dc0c005`, and Alpine health
was clear at 64% battery, 25.1°C, with DCP charging. The kernel scan found
idle-manager, ESD-read, and doze warnings, but **no new CMDQ timeout**.
Receipt: `logs/v50-dmabuf-trial-1793053183316568088/result.json`.

This proves the V50 UI can render on Lynx, including while charging from the
Hama adapter. It does not yet prove that the **first** modeset after every
cold boot works, nor that the display can remain on as a long-lived service.
The first V50 UI attempt on this boot stayed black and timed out until ESD
recovery had prepared the panel; the later successful color-bar and UI trials
both used the same boot after that recovery. A clean-boot display sequence
needs separate investigation. Do not run a new visual trial without Noob's
readiness cue.

## Persistent status program, staged but not enabled

The status renderer now has `--show-ui-until-signal`. It keeps the DRM buffer
and CRTC active, refreshes the battery reading once per minute when it changes,
and disables the CRTC on SIGTERM or SIGINT. The original 1–15-second trial
interface remains intact. `tools/stage_v50_ui_candidate.py --persistent`
compiled it natively on Lynx into the separate
`/var/lib/lynx-devroot/tmp/lynx_drm_status_persistent` path. The verified
binary SHA-256 is
`1bab6b4e95949b46b160178945439b7ed2e1e370ce39da935918b1cd7a5027f8`;
receipt: `logs/v50-ui-stage-1793053967353526641/result.json`. It has **not**
been run, put in OpenRC, or substituted for the working short-lived UI binary.
The clean-boot display initialization issue must be resolved before enabling
automatic startup.
