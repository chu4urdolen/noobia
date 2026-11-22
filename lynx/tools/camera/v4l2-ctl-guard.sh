#!/bin/sh
# v4l2-ctl guard for Lynx (Gwyn, 2026-11-22). Installed as /usr/sbin/v4l2-ctl,
# which comes before the real /usr/bin/v4l2-ctl in Lynx's login and SSH PATHs.
#
# Lynx's vendor camera kernel crashes on VIDIOC_G_EXT_CTRLS (kernel Oops in
# v4l2_g_ext_ctrls -> __memcpy; 2026-11-04 and again 2026-11-22 17:34 UTC,
# see lynx/linux-port/docs/CAMERA-EXPOSURE-20261104.md). v4l2-ctl issues
# that ioctl for any control listing or get/set, so those options are
# refused here, whoever runs them. Everything else (formats, devices,
# streaming, querycap) passes through to the real binary unchanged.
#
# Bypass for a reviewed, attended trial only: LYNX_V4L2_UNSAFE_CTRLS=1.
REAL=/usr/bin/v4l2-ctl
if [ "${LYNX_V4L2_UNSAFE_CTRLS:-0}" != 1 ]; then
    for a in "$@"; do
        case "$a" in
            -a|--all|-l|--list-ctrls|-L|--list-ctrls-menus|-C|--get-ctrl|--get-ctrl=*|\
            -c|--set-ctrl|--set-ctrl=*|--log-status|-k|--list-ctrls*|--get-ctrl*|--set-ctrl*)
                echo "v4l2-ctl: refused '$a' on Lynx: control access (VIDIOC_G/S_EXT_CTRLS) crashes this camera kernel. See lynx/linux-port/docs/CAMERA-EXPOSURE-20261104.md" >&2
                /bin/busybox logger -t lynx-v4l2-guard "refused v4l2-ctl $a (parent pid $PPID)" 2>/dev/null || true
                exit 64
                ;;
            -[!-]*)
                # Bundled short options such as -da or -la.
                case "$a" in *a*|*l*|*L*|*C*|*c*|*k*)
                    case "$a" in -d*|-D|--*) ;; *)
                        echo "v4l2-ctl: refused bundled options '$a' on Lynx (may include control access)" >&2
                        exit 64 ;;
                    esac ;;
                esac
                ;;
        esac
    done
fi
exec "$REAL" "$@"
