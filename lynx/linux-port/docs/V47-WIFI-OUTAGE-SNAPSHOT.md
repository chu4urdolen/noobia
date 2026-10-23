# Lynx V47 Wi-Fi outage snapshot

The maintenance watcher already records `WIFI_DEGRADED` and
`WIFI_RECOVERED` at a persistent syslog severity. Its first event did not
include enough state to distinguish lost carrier, lost IPv4 address, or
link association failure. A bounded read-only snapshot now records only
carrier (`0`, `1`, or `unknown`), a Noobia IPv4 address or `none`, and a
connected/disconnected/unknown nl80211 link state. It does not log SSID,
BSSID, keys, or scan results, and it does not change network state.

The first staged implementation queried WPA's control socket. Its
read-only installation test showed a healthy carrier and IPv4 address,
but Alpine's `wpa_cli` did not return a status within three seconds, while
rescue-root `wpa_cli` did return `COMPLETED`. The tool rejected that result
and restored the previous maintenance script automatically:
`logs/v47-wifi-snapshot-install-1792786561149977254/result.json`.
No Wi-Fi fault was induced.

The revised snapshot uses bounded `/usr/sbin/iw dev wlan0 link`, which
answered from Alpine. The guarded installer verified V47 rescue image
hashes, Alpine/OpenRC PID 1, ext4 root, the signed `iw` binary, safety and
network services, and a healthy battery reading. It copied the previous
script to `/root/lynx-rescue/lynx-maintenance-before-link-snapshot-v47.sh`,
installed the new script atomically, and restarted only
`lynx-maintenance`. The live read-only proof returned
`carrier=1 ipv4=192.168.100.8 nl80211_link=connected`; maintenance,
health, and battery-reserve services remained active:
`logs/v47-wifi-snapshot-install-1792786607322911702/result.json`.

The `WIFI_DEGRADED` event now includes that snapshot once per transition.
An actual outage has not been induced, and automatic radio repair remains
disabled. If an outage occurs, the persistent event can guide a separate,
controlled recovery design while Lynx's safety guards continue running.
