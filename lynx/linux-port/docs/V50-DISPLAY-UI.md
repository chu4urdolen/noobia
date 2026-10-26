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
and pinned rescue image. The display trial retains a battery floor of 50%,
an offline charger requirement, and the established temperature limits.
Run the guarded trial only after charging is verified, and tell Noob before
the visual check. Do not repeat panel binding on an already probed boot.

Current charging evidence and unresolved attach state are in
`V50-CHARGER-TCPC.md`. The Hama charger is being tested separately with a
read-only, bounded observer, `tools/observe_v50_charge_attach.py`.
