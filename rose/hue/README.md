# Rose Hue pattern player

`rose-hue` reads a CSV pattern and sends it to a Philips Hue bridge using the
local v1 HTTP API. No HTTP or JSON library is required.

```sh
make install-user
mkdir -p ~/.config/rose-tools
cp hue.conf.example ~/.config/rose-tools/hue.conf
chmod 600 ~/.config/rose-tools/hue.conf
rose-hue example.csv
```

Rows have five fields:

```text
red,green,blue,brightness,time
```

RGB and brightness range from 0 through 255. `time` is the transition and hold
duration in seconds, from 0 through 3600. Brightness zero turns the target off.
Blank lines and lines beginning with `#` are ignored; the header is optional.

The configured light is the default. Target another light or all lights in a Hue
group with `--light ID` or `--group ID`.

Use `--dry-run` to validate the entire CSV without contacting the bridge or
waiting between rows.

All LED users share `/tmp/rose-hue.lock`. A sequence waits up to 30 seconds for
the previous owner, holds the lock for its full run, then darkens the target and
removes the lock. `rose-hue-off` forcibly darkens the target and clears the lock.

`rose-hue-shutdown.service` runs that helper when Rose's user service manager
stops during logout or system shutdown. Install and enable it with:

```sh
make install-user
systemctl --user daemon-reload
systemctl --user enable --now rose-hue-shutdown.service
```
