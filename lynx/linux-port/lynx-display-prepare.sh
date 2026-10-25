#!/bin/sh
# Recreate the V49 DRM module sequence from matching stock modules on Alpine.
# This prepares /dev/dri/card0 but does not light the panel or change boot_a.
set -eu

base=/usr/local/lib/lynx-display/modules
kernel=5.10.149-android12-9-o-g311738fbb5a8
[ "$(uname -r)" = "$kernel" ] || { echo 'unexpected kernel' >&2; exit 1; }
grep -q 'CHECKPOINT_MODULE_OK mtk_iommu.ko' /run/lynx/boot.log || {
    echo 'V49 early IOMMU proof missing' >&2; exit 1;
}
test -L /sys/bus/platform/devices/1e980000.gce/iommu_group || {
    echo 'GCE IOMMU domain missing' >&2; exit 1;
}

while read -r name digest; do
    [ -n "$name" ] || continue
    path="$base/$name.ko"
    [ -f "$path" ] || { echo "missing $path" >&2; exit 1; }
    got=$(sha256sum "$path")
    got=${got%% *}
    [ "$got" = "$digest" ] || { echo "hash mismatch: $name" >&2; exit 1; }
    modname=$(printf '%s' "$name" | tr - _)
    if grep -q "^$modname " /proc/modules; then
        echo "already loaded $name"
    else
        /bin/busybox timeout 15 /sbin/insmod "$path"
        grep -q "^$modname " /proc/modules || {
            echo "module did not register: $name" >&2; exit 1;
        }
        echo "loaded $name"
    fi
done <<'MODULES'
cmdq-platform-mt6983 3eabc1e9731637286264e7eb5a6d18485e668beb87b305797fcc43f10ef454ec
mtk-mbox-mailbox 77003c737e417b6f51e365faca06f9d3823222746af2561cd014b26cd5b91b46
tinysys-scmi 6fa7f4469c3eaee17cb4d039dc30fe31e38bdd8c914925036ebe36861a8c04cf
mtk-mminfra-debug 7c40aa8abb29927e0bfef68484946f225b2dd5a8d983f411be166827a524eaff
mtk-dvfsrc f64bc73bbaa9acc5a9c6b8b5e83ee53ab21798acfdaa77819043e0c430a47913
mtk-dvfsrc-regulator a49acf1bc974d7deae015befc2bb38df751e0050ae968d5e54ec0d52e44b1d6b
pinctrl-mt6373 c48f4fe779e3dd084d329a441f51d381df9b004c3d566520233215a1b92c6694
mtk-spmi-pmic-adc 66a3e5426b200acf783413a09561e584cb89fd20244d9d8568d399431468e01c
mtk_iommu f2f2d31ec2dcb769311dfab3621622a7deff7ba83d14c2f5137d94f38c44b332
mtk-mml-mt6983 473c429e8b71aded1fe2f6f9128210e7fdd62df32f1d9cae234a92ac818578a5
oplus22823_tm_nt37705_fhd_dsi_cmd 498be900a01f21eba3116820d4fae965ee3796a953d30f66fb4aa72436334e98
MODULES

if ! test -L /sys/bus/platform/devices/14017000.dsi/driver; then
    printf '%s' 14017000.dsi > /sys/bus/platform/drivers/mtk-dsi/bind
fi
test -c /dev/dri/card0
[ "$(cat /sys/class/drm/card0-DSI-1/status)" = connected ]
echo 'Lynx DRM ready; panel remains off'
