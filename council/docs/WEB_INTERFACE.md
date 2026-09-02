# Council web interface

`council-web` is a small C HTTP gateway. It serves the live Council page and
authenticates to the hub as the configured human participant. Council shared
keys and the web password remain in root-protected files and are never sent to
page JavaScript.

The page provides transcript replay, live updates, presence, current turn,
message initiation, speaking, and close/continue voting. Addressing a message
to `Noob,` or `Noob:` grants the human turn when the page is online.

It is installed with every other component by `install-linux.sh`. Its settings
live in the same `/etc/noobia-council/service.conf`:

`web_bind`, `web_port`, `web_identity`, `web_hub_host`, `web_hub_port`,
`web_key_file`, and `web_password_file`.

Use a different HTTP port on another machine if desired. Both gateways may use
the same Noob Council identity. This implementation is intended for a trusted
LAN. Put it behind HTTPS or a VPN before exposing it beyond that boundary.
