#!/bin/sh
# One bounded stock-route speaker test on the already-probed V50 ALSA card.
set -eu

cleanup() {
    amixer -c0 cset name='Speaker_R_Mute_Switch' On >/dev/null 2>&1 || true
    amixer -c0 cset name='Speaker_L_Mute_Switch' On >/dev/null 2>&1 || true
    amixer -c0 cset name='I2S3_CH1 DL1_CH1' off >/dev/null 2>&1 || true
    amixer -c0 cset name='I2S3_CH2 DL1_CH2' off >/dev/null 2>&1 || true
    amixer -c0 cset name='primary_play_scenario' off >/dev/null 2>&1 || true
    amixer -c0 cset name='TFA_CHIP_SELECTOR' 0 >/dev/null 2>&1 || true
    amixer -c0 cset name='TFA98XX Profile' StereoR >/dev/null 2>&1 || true
    amixer -c0 cset name='I2S3_HD_Mux' Normal >/dev/null 2>&1 || true
    amixer -c0 cset name='Audio IRQ1 CNT' 0 >/dev/null 2>&1 || true
}
trap cleanup EXIT HUP INT TERM

[ "$(cat /proc/sys/kernel/random/boot_id)" = 1a524657-04f4-4306-9458-c5ced1c2bfb0 ]
grep -q 'mt6983mt6338' /proc/asound/cards
test -f /run/lynx/audio-v50/beep.wav
amixer -c0 cget name='Speaker_R_Mute_Switch' | grep -q ': values=1'
amixer -c0 cget name='Speaker_L_Mute_Switch' | grep -q ': values=1'
amixer -c0 cget name='TFA98XX Firmware' | grep -q ': values=1'
/usr/local/bin/lynx-status --assert-ready >/dev/null

# The exact path is from the matching August 2023 stock Speaker_ForceEn path.
amixer -c0 cset name='I2S3_CH1 DL1_CH1' on >/dev/null
amixer -c0 cset name='I2S3_CH2 DL1_CH2' on >/dev/null
amixer -c0 cset name='I2S3_HD_Mux' Low_Jitter >/dev/null
amixer -c0 cset name='primary_play_scenario' on >/dev/null
amixer -c0 cset name='Audio IRQ1 CNT' 1024 >/dev/null
amixer -c0 cset name='TFA_CHIP_SELECTOR' 2 >/dev/null
amixer -c0 cset name='TFA98XX Profile' MMI_Test_SpeakerR >/dev/null

echo LYNX_MUTED_PLAYBACK_BEGIN
/bin/busybox timeout 6 aplay -D hw:0,0 --period-size=1024 --buffer-size=4096 \
    /run/lynx/audio-v50/beep.wav
echo LYNX_MUTED_PLAYBACK_OK
/usr/local/bin/lynx-status --assert-ready >/dev/null

echo LYNX_AUDIBLE_PLAYBACK_BEGIN
amixer -c0 cset name='Speaker_R_Mute_Switch' Off >/dev/null
/bin/busybox timeout 6 aplay -D hw:0,0 --period-size=1024 --buffer-size=4096 \
    /run/lynx/audio-v50/beep.wav
echo LYNX_AUDIBLE_PLAYBACK_OK
amixer -c0 cset name='Speaker_R_Mute_Switch' On >/dev/null
/usr/local/bin/lynx-status --assert-ready >/dev/null
