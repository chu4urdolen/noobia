# V50 speaker playback trial

On 27 October 2026, V50 boot `1a524657-04f4-4306-9458-c5ced1c2bfb0` registered ALSA card `mt6983-mt6338` and completed a bounded speaker playback test. Both a muted pass and a half-second unmuted pass through `hw:0,0` returned success. Kernel logs show the TFA9873 amplifier starting, `DL1` triggering, and normal PCM shutdown. The phone remained on the same boot, all eight core Alpine services passed `lynx-status --assert-ready`, and speaker mute and I2S routes were restored. A person near Lynx still needs to confirm whether the sound was actually audible.

This was an in-memory audio trial. No boot partition was modified and no audio service was enabled at startup. The V50 image and rollback path remain intact.

## Codec fix

The first stock audio probe had crashed in `nvmem_device_read` after the MT6338 codec ignored `-EPROBE_DEFER` from its IIO and efuse providers. The fault is saved at `logs/v50-audio-reboot-pstore-1793093632878559895/`. The source fix is `linux-port/patches/mt6338-probe-defer.patch`. The locally built `snd-soc-mt6338.ko` is in `linux-port/artifacts/audio-codec-fix/`, SHA-256 `d9f93f42c19fd75ae803be3726aa961c9be52a7c1960924cc6f2db82248e688f`. Its imported symbol versions and kernel ABI were checked against the stock module. The stock module must not be substituted until its deferral handling is fixed.

`tools/lynx_audio_provider_probe.py` loaded `mt6338_core`, `mt6338_auxadc`, and `nvmem_mt6338_efuse` first. `tools/lynx_audio_card_probe.py` then loaded stock audio dependencies and the corrected codec. The card appeared only after `mtk_soc_offload_common` loaded. Receipts are `logs/v50-audio-provider-1793117468261518413/` and `logs/v50-audio-card-1793117665987272840/`.

## Firmware and route

`tools/lynx_audio_firmware_stage.py` installed the matching August 2023 CPH2493 `tfa98xx.cnt` as `/lib/firmware/tfa98xx.cnt`, SHA-256 `d5d0f96d14b6fb0f324b162de3c3898f2caaac6ee6a5fad64cf9bc29f4e74e87`, then loaded it while both speakers were muted. The kernel recognized two TFA9873 devices and seven container profiles. Receipt: `logs/v50-audio-firmware-1793137102715148962/`.

The test route follows the stock ODM `Speaker_ForceEn` path: `I2S3_CH1 DL1_CH1=on`, `I2S3_CH2 DL1_CH2=on`, `I2S3_HD_Mux=Low_Jitter`, `primary_play_scenario=on`, `Audio IRQ1 CNT=1024`, `TFA_CHIP_SELECTOR=2`, and `TFA98XX Profile=MMI_Test_SpeakerR`. The test waveform is 700 Hz, 48 kHz stereo S16_LE, 500 ms, about 4.3% digital amplitude with 20 ms fades; SHA-256 `c38ca04592122af3aeac827f27aae848315641782dc5b712bcd86e521986b7de`. The exact trial script is `tools/lynx_audio_beep_trial.sh`. It begins with both speakers muted, runs one muted playback, unmutes only the right speaker for one playback, then restores mute and route controls on exit. It checks the exact boot ID and card before acting.

Receipt: `logs/v50-audio-beep-trial-1793137219179008873/`. `run.stdout` contains `LYNX_MUTED_PLAYBACK_OK` and `LYNX_AUDIBLE_PLAYBACK_OK`; `after.stdout` confirms both speaker mute controls are `On`, both I2S3 DL1 routes are `off`, and the health check passed. These results establish a working ALSA playback path, pending human confirmation of actual sound. The log also contains `tfa98xx_adsp_send_chan_sel ... failed` during playback; investigate that before treating speaker output as production-ready.

Noob thought they heard the first beep and requested a repeat. The identical bounded test succeeded again on the same boot; the post-test check confirmed both speakers muted, both DL1 routes off, and Alpine health ready. Receipt: `logs/v50-audio-beep-repeat-1793137682185121136/`. Human confirmation of the second audible result is pending.

## Next step

If the beep was audible, package the corrected codec, dependencies, matching firmware, and conservative mixer setup into an optional Alpine service. Keep playback disabled at boot until an audible, volume-controlled trial and shutdown behavior are verified. If no beep was heard, inspect amplifier calibration and the `tfa98xx_adsp_send_chan_sel` failure before changing mixer routes again.
