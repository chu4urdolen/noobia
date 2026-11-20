# Argus Pi 5 fan control

On 2026-10-13 the Argon ONE V3 fan cable was extended and connected to the
Raspberry Pi 5 FAN header. The case still supplies power and keeps its
always-on jumper on pins 2–3, but the RP2040 no longer drives the fan.

The previous `argononed.service` diagnostic override and vendor unit were
stopped and moved on Argus to
`/var/backups/argon-fan-service-removal-20261012/`. The Argon service is absent
from systemd. Do not run it alongside the native fan controller.

`argus-pi5-fan.service` runs `/usr/local/bin/argus-pi5-fan-control` as root.
It reads `/sys/class/thermal/thermal_zone0/temp` at startup and every 60
seconds. At 40°C or above it commands the Pi fan's maximum cooling state every
four seconds. At 35°C or below it commands state zero. Between the thresholds,
it keeps its previous state. The Pi's native cooling driver remains enabled.

Install the files from this repository:

```sh
sudo install -m 755 tools/pi5_fan_thermal_control.sh /usr/local/bin/argus-pi5-fan-control
sudo install -m 644 services/argus-pi5-fan.service /etc/systemd/system/argus-pi5-fan.service
sudo systemctl daemon-reload
sudo systemctl enable --now argus-pi5-fan.service
```

Check the service and tachometer:

```sh
systemctl status argus-pi5-fan.service
cat /sys/class/hwmon/hwmon*/fan1_input
```

For a temporary constant-on test, stop the temperature service and run
`sudo tools/pi5_fan_repeat_on.sh 75 4`. The first argument is the duration in
seconds (`0` means continuous); the second is the repeat period in seconds.
The script returns the cooling state to zero when it exits. Restart the
temperature service afterward.
