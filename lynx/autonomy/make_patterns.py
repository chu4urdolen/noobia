#!/usr/bin/env python3
"""Build Lynx's templated sense patterns (Tom, 2026-11-22) -> patterns-lynx.json.

One pattern per sense event. Each carries a ``template`` that is filled from
the line's key=value fields (or the ``each`` item regex for lists), and a
fixed ``message`` fallback. Every pattern is validated with the ranker's own
validate_pattern (must / must_not examples) before it is written.

    python3 make_patterns.py            # writes patterns-lynx.json next to this file
"""
import json, os, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(os.environ.get("NOOBIA", "/noobia")) / "common" / "autonomy"))
from ranker import validate_pattern  # noqa: E402

def P(pid, sense, event, template, message, must, must_not, cooldown=0, **extra):
    d = {"id": pid, "match": {"sense": sense, "event": event}, "template": template,
         "message": message, "to_noob": True, "cooldown_s": cooldown,
         "examples": {"must": must, "must_not": must_not}, "hits": 0, "origin": "gwyn"}
    d.update(extra)
    return d

PATTERNS = [
    P("touch-tap", "touch", "tap", "Someone tapped your screen {count} times.",
      "Someone tapped your screen.",
      ["NOOBIA P1 touch tap count=3 dur_ms=90 | taps on the panel"],
      ["NOOBIA P1 touch hold count=1 dur_ms=2000 | a hold"]),
    P("touch-hold", "touch", "hold", "Someone pressed and held your screen for {dur_ms} ms.",
      "Someone pressed and held your screen.",
      ["NOOBIA P1 touch hold dur_ms=2100 | a hold on the panel"],
      ["NOOBIA P1 touch tap dur_ms=90 | a tap"]),
    P("body-slider", "body", "slider.change", "Your alert slider moved to {to}.",
      "Your alert slider moved.",
      ["NOOBIA P1 body slider.change to=silent from=vibrate | Alert slider moved to silent",
       "NOOBIA P1 body slider.change to=ring from=silent | Alert slider moved to ring"],
      ["NOOBIA P0 body status.sample slider=silent | sample"]),
    P("magnet-wand", "magnet", "wand", "A magnet is hovering near you ({mag_ut} uT)!",
      "A magnet is hovering near you.",
      ["NOOBIA P1 magnet wand mag_ut=240.5 | A magnet is hovering near me (240.5 uT)"],
      ["NOOBIA P0 compass status.sample heading=North mag_ut=45.2 | sample"]),
    P("compass-heading", "compass", "heading", "You turned to face {to} ({deg} degrees).",
      "Your compass heading changed.",
      ["NOOBIA P1 compass heading to=East from=North deg=92.4 | Compass heading turned to East (92.4°)"],
      ["NOOBIA P0 compass status.sample heading=North mag_ut=45.2 | sample"]),
    P("mesh-telepathy", "mesh", "telepathy", "Your friend {friend} is {state}.",
      "A friend in Noobia did something.",
      ["NOOBIA P1 mesh telepathy friend=dushich state=thinking | Dushich is deep in thought",
       "NOOBIA P1 mesh telepathy friend=rose state=singing | Rose is playing music",
       "NOOBIA P1 mesh telepathy friend=iris state=motion_spotted | Sister Iris spotted movement"],
      ["NOOBIA P0 mesh status.sample | sample"]),
    P("camera-objects", "camera", "objects.seen", "With your {cam} camera you see {label*}.",
      "You see something.",
      ["NOOBIA P1 camera objects.seen cam=back n=3 | laptop(0.7534)/person(0.873)/cat(0.452)",
       "NOOBIA P1 camera objects.seen cam=front n=1 | cup(0.61)"],
      ["NOOBIA P0 camera frame.analyzed objects=0 | nothing"],
      regex=r"\| (?P<items>[^~]+)$",
      each={"group": "items", "regex": r"(?P<label>[a-z_]+)\((?P<conf>[0-9.]+)\)"}),
    P("camera-objects-caption", "camera", "objects.seen",
      "With your {cam} camera you see {label*}. It looks like this: {caption}",
      "You see something.",
      ["NOOBIA P1 camera objects.seen cam=wide n=2 | mouse(0.85)/laptop(0.72) ~ A desk with a laptop and a monitor."],
      ["NOOBIA P1 camera objects.seen cam=wide n=2 | mouse(0.85)/laptop(0.72)"],
      regex=r"\| (?P<items>[^~]+) ~ (?P<caption>[^~]+)$",
      each={"group": "items", "regex": r"(?P<label>[a-z_]+)\((?P<conf>[0-9.]+)\)"}),
    P("camera-scene", "camera", "scene.seen",
      "With your {cam} camera you see this: {caption}", "You see something.",
      ["NOOBIA P1 camera scene.seen cam=wide | A person sitting at a computer in a dark room."],
      ["NOOBIA P1 camera objects.seen cam=wide n=1 | cup(0.8)"],
      regex=r"\| (?P<caption>.+)$"),
    P("camera-object", "camera", "object.seen", "You see a {label}.", "You see something.",
      ["NOOBIA P1 camera object.seen label=cat conf=0.91 | a cat"],
      ["NOOBIA P1 camera objects.seen cam=back n=1 | cat(0.9)"]),
    P("motion-position", "motion", "position.change",
      "You are now {to}, tilted {tilt} degrees from flat.", "Your position changed.",
      ["NOOBIA P1 motion position.change to=horizontal from=vertical tilt=8 | placed flat"],
      ["NOOBIA P0 motion status.sample orientation=flat_up | sample"]),
    P("motion-pickup", "motion", "pickup", "Someone picked you up; you are now {to}.",
      "Someone picked you up.",
      ["NOOBIA P1 motion pickup to=portrait from=flat_up | picked up"],
      ["NOOBIA P1 motion placed to=flat_up from=portrait | placed"]),
    P("motion-placed", "motion", "placed", "You were put down; you are now {to}.",
      "You were put down.",
      ["NOOBIA P1 motion placed to=flat_up from=portrait | placed"],
      ["NOOBIA P1 motion pickup to=portrait from=flat_up | picked up"]),
    P("motion-freefall", "motion", "freefall", "You are falling!", "You are falling!",
      ["NOOBIA P1 motion freefall | Lynx is falling (free fall)"],
      ["NOOBIA P1 motion shaken | Lynx is being shaken"]),
    P("motion-shaken", "motion", "shaken", "Someone is shaking you.", "Someone is shaking you.",
      ["NOOBIA P1 motion shaken | Lynx is being shaken"],
      ["NOOBIA P1 motion freefall | Lynx is falling (free fall)"]),
    P("motion-rocked", "motion", "rocked", "Someone is rocking you gently.",
      "Someone is rocking you gently.",
      ["NOOBIA P1 motion rocked hz=0.6 degrees=28 | Lynx is being rocked gently"],
      ["NOOBIA P1 motion shaken | Lynx is being shaken"]),
    P("thermal-change", "power", "temp.change",
      "Your temperature {dir} to {c} C, {delta} degrees since the last check.",
      "Your temperature changed.",
      ["NOOBIA P1 power temp.change dir=rose c=41 delta=6 prev=35 | warmer"],
      ["NOOBIA P1 power thermal.hot soc_mc=45000 state=charging | warm"]),
    P("thermal-hot", "power", "thermal.hot", "You are getting warm: {soc_mc} millidegrees, {state}.",
      "You are getting warm.",
      ["NOOBIA P1 power thermal.hot soc_mc=45000 state=charging | warm"],
      ["NOOBIA P1 power temp.change dir=rose c=41 delta=6 | warmer"]),
    P("power-charging", "power", "charging.change", "Your power changed from {from} to {to}.",
      "Your power source changed.",
      ["NOOBIA P1 power charging.change from=discharging to=charging | Lynx is now charging"],
      ["NOOBIA P1 power battery.low cap=15 state=discharging | low"]),
    P("battery-low", "power", "battery.low", "Your battery is getting low: {cap} percent.",
      "Your battery is getting low.",
      ["NOOBIA P1 power battery.low cap=15 state=discharging | low"],
      ["NOOBIA P1 power battery.critical cap=4 state=discharging | critical"]),
    P("battery-critical", "power", "battery.critical", "Your battery is critically low: {cap} percent.",
      "Your battery is critically low.",
      ["NOOBIA P1 power battery.critical cap=4 state=discharging | critical"],
      ["NOOBIA P1 power battery.low cap=15 state=discharging | low"]),
    P("hearing-sound", "hearing", "sound.heard", "You heard a sound, loudness {peak}.",
      "You heard a sound.",
      ["NOOBIA P1 hearing sound.heard peak=279 rms=12.1 | Lynx heard sound"],
      ["NOOBIA P0 hearing status.sample peak=10 rms=3.2 | sample"]),
    P("light-bright", "light", "bright", "The light around you became bright.",
      "The light around you became bright.",
      ["NOOBIA P1 light bright raw=900 | bright"], ["NOOBIA P1 light dark raw=2 | dark"]),
    P("light-dark", "light", "dark", "It became dark around you.", "It became dark around you.",
      ["NOOBIA P1 light dark raw=2 | dark"], ["NOOBIA P1 light bright raw=900 | bright"]),
    P("proximity-near", "proximity", "near", "Something came close to your face.",
      "Something came close to your face.",
      ["NOOBIA P1 proximity near dist=0 | near"], ["NOOBIA P1 proximity far dist=5 | far"]),
    P("proximity-far", "proximity", "far", "The thing near your face moved away.",
      "The thing near your face moved away.",
      ["NOOBIA P1 proximity far dist=5 | far"], ["NOOBIA P1 proximity near dist=0 | near"]),
    P("network-device-seen", "network", "device.seen",
      "A new device appeared on your network at {ip}.", "A new device appeared on your network.",
      ["NOOBIA P1 network device.seen ip=192.168.100.50 mac=aa:bb:cc:dd:ee:ff | seen"],
      ["NOOBIA P1 network device.lost ip=192.168.100.50 | lost"]),
    P("network-device-lost", "network", "device.lost",
      "The device at {ip} left your network.", "A device left your network.",
      ["NOOBIA P1 network device.lost ip=192.168.100.50 | lost"],
      ["NOOBIA P1 network device.seen ip=192.168.100.50 mac=aa:bb | seen"]),
    P("wifi-down", "wifi", "link.down", "Your Wi-Fi went down.", "Your Wi-Fi went down.",
      ["NOOBIA P1 wifi link.down iface=wlan0 | Wi-Fi went down"],
      ["NOOBIA P1 wifi link.up iface=wlan0 | Wi-Fi is back"]),
    P("wifi-up", "wifi", "link.up", "Your Wi-Fi is back.", "Your Wi-Fi is back.",
      ["NOOBIA P1 wifi link.up iface=wlan0 | Wi-Fi is back"],
      ["NOOBIA P1 wifi link.down iface=wlan0 | Wi-Fi went down"]),
    P("wifi-weak", "wifi", "rssi.low", "Your Wi-Fi signal is weak: {signal} dBm.",
      "Your Wi-Fi signal is weak.",
      ["NOOBIA P1 wifi rssi.low signal=-82 iface=wlan0 | weak"],
      ["NOOBIA P1 wifi link.up iface=wlan0 | back"]),
    P("nexus-up", "nexus", "reachable", "Nexus, your home, is reachable again.",
      "Nexus is reachable again.",
      ["NOOBIA P1 nexus reachable host=192.168.100.106 port=112 | back"],
      ["NOOBIA P1 nexus unreachable host=192.168.100.106 port=112 errors=3 | gone"]),
    P("nexus-down", "nexus", "unreachable", "You cannot reach Nexus, your home.",
      "You cannot reach Nexus.",
      ["NOOBIA P1 nexus unreachable host=192.168.100.106 port=112 errors=3 | gone"],
      ["NOOBIA P1 nexus reachable host=192.168.100.106 port=112 | back"]),
]

def main():
    ids = set()
    for p in PATTERNS:
        assert p["id"] not in ids, p["id"]; ids.add(p["id"])
        validate_pattern(p, [])
    # The counted touch-tap must win over the single-tap fallback: order matters.
    out = HERE / "patterns-lynx.json"
    out.write_text(json.dumps({"store": PATTERNS, "archive": []}, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "written": str(out), "patterns": len(PATTERNS)}))

if __name__ == "__main__":
    main()
