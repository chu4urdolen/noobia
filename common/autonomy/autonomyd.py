#!/usr/bin/env python3
"""noobia-autonomyd: run the autonomy harness on one host from a config file.

    noobia-autonomyd --check            # validate config and wiring, contact nothing
    noobia-autonomyd --once             # one harness step, then exit
    noobia-autonomyd                    # run until SIGTERM / SIGINT

The config is ``/etc/noobia/autonomy.json`` by default, or
``$NOOBIA_AUTONOMY_CONFIG``. **Secrets are never inline**: only ``*_file``
paths are accepted, the files must not be group- or world-readable, and an
inline ``secret`` / ``token`` / ``key`` value is refused.

Example (Lynx)::

    {"host": "lynx",
     "view": {"backend": "file", "log_file": "/var/log/lynx/messages"},
     "aigel": {"url": "http://192.168.100.106:112/api/v1/chunk",
               "hmac_secret_file": "/etc/noobia/aigel-lynx.secret"},
     "adapter": {"path": "/usr/local/lib/noobia/lynx", "spec": "lynx_aigel_adapter:LynxAdapter",
                 "state_dir": "/var/lib/noobia/autonomy/lynx-adapter"},
     "ranker": {"store_file": "/var/lib/noobia/autonomy/patterns.json",
                "store_capacity": 200, "active_capacity": 100},
     "prioritizer": {"enabled": true, "map_file": "/var/lib/noobia/autonomy/priority_map.json",
                     "sources": ["wpa_supplicant", "kernel"]},
     "trigger": {"window_s": 60, "max_lines": 15},
     "harness": {"heartbeat_s": 300, "silence_s": 900, "max_per_hour": 30, "queue_max": 20},
     "kill_switch": "/etc/noobia/autonomy.disable",
     "interval_s": 1.0}

The prioritizer stage needs a reader with ``read_new_tagged(sources)`` (task V2).
Without one, the stage is disabled and the daemon says so.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import signal
import stat
import sys
import syslog
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent_link  # noqa: E402
import aigel_client  # noqa: E402
import harness as harness_mod  # noqa: E402
import ranker as ranker_mod  # noqa: E402
import sense  # noqa: E402
import trigger  # noqa: E402

DEFAULT_CONFIG = Path(os.environ.get("NOOBIA_AUTONOMY_CONFIG", "/etc/noobia/autonomy.json"))
FORBIDDEN_INLINE = ("secret", "token", "key", "password", "api_key", "hmac_secret", "bearer")


class ConfigError(ValueError):
    pass


def _walk_inline_secrets(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            where = f"{path}.{k}" if path else k
            if k.lower() in FORBIDDEN_INLINE and not k.endswith("_file"):
                raise ConfigError(f"inline secret '{where}' refused: use '{k}_file' with a private file")
            _walk_inline_secrets(v, where)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _walk_inline_secrets(v, f"{path}[{i}]")


def load_config(path=DEFAULT_CONFIG):
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot read config {path}: {exc}") from None
    if not isinstance(config, dict):
        raise ConfigError("config must be a JSON object")
    _walk_inline_secrets(config)
    for key in ("host", "aigel", "adapter", "view"):
        if key not in config:
            raise ConfigError(f"config needs '{key}'")
    if not agent_link.HOST.match(str(config["host"])):
        raise ConfigError("bad host name")
    if not str(config["aigel"].get("url", "")).startswith(("http://", "https://")):
        raise ConfigError("aigel.url must be an http(s) URL")
    if ":" not in str(config["adapter"].get("spec", "")):
        raise ConfigError("adapter.spec must look like 'module:Class'")
    return config


def read_secret(path):
    p = Path(path)
    try:
        mode = p.stat().st_mode
    except OSError as exc:
        raise ConfigError(f"secret file {p}: {exc.strerror}") from None
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ConfigError(f"secret file {p} must not be group/world accessible (chmod 600)")
    value = p.read_text(encoding="utf-8").strip()
    if not value or len(value) > 512 or "\n" in value:
        raise ConfigError(f"secret file {p} has an invalid value")
    return value


def syslog_line(line, ident="noobia-sense"):
    """Emit an already-formatted sense line (validated) at notice level."""
    if sense.parse_line(line) is None:
        raise ValueError("not a sense line")
    syslog.openlog(ident, syslog.LOG_PID, syslog.LOG_USER)
    syslog.syslog(syslog.LOG_NOTICE, line)
    syslog.closelog()


def autonomy_logger(ident="noobia-autonomy"):
    def log(line):
        syslog.openlog(ident, syslog.LOG_PID, syslog.LOG_USER)
        syslog.syslog(syslog.LOG_NOTICE, line[:900])
        syslog.closelog()
    return log


def load_adapter(spec, path, state_dir, kill_switch, log):
    if path:
        sys.path.insert(0, str(path))
    module_name, class_name = spec.split(":", 1)
    cls = getattr(importlib.import_module(module_name), class_name)
    if not issubclass(cls, agent_link.Adapter):
        raise ConfigError(f"{spec} is not an agent_link.Adapter")
    return cls(state_dir, kill_switch=kill_switch, log=log)


class Daemon:
    """Everything wired from config; collaborators can be overridden for tests."""

    def __init__(self, config, *, reader=None, client=None, adapter=None, emit=None,
                 log=None, clock=time.monotonic):
        self.config = config
        self.log = log or autonomy_logger()
        self.emit = emit or syslog_line
        kill = Path(config.get("kill_switch", agent_link.DEFAULT_KILL_SWITCH))
        self.kill_switch = kill

        view = config["view"]
        if reader is None:
            import views
            reader = views.ViewReader("noobia-sense", backend=view.get("backend", "auto"),
                                      log_file=view.get("log_file"))
        self.reader = reader

        r = config.get("ranker", {})
        store_file = r.get("store_file")
        caps = {"store_capacity": int(r.get("store_capacity", 200)),
                "active_capacity": int(r.get("active_capacity", 100))}
        if store_file and Path(store_file).exists():
            self.ranker = ranker_mod.Ranker.load_patterns(store_file)
            self.ranker.store_capacity, self.ranker.active_capacity = (caps["store_capacity"],
                                                                       caps["active_capacity"])
        else:
            self.ranker = ranker_mod.Ranker([], **caps)
        self.store_file = store_file

        self.prioritizer, self.map_file, self.sources = None, None, []
        pz = config.get("prioritizer", {})
        if pz.get("enabled"):
            if hasattr(self.reader, "read_new_tagged"):
                import prioritizer as pz_mod
                self.sources = list(pz.get("sources", []))
                self.map_file = pz.get("map_file")
                if self.map_file and Path(self.map_file).exists():
                    self.prioritizer = pz_mod.Prioritizer.load_map(self.map_file, allowlist=set(self.sources))
                else:
                    self.prioritizer = pz_mod.Prioritizer([], sources=self.sources)
            else:
                self.log("autonomyd prioritizer disabled: view reader has no read_new_tagged (V2)")

        a = config["aigel"]
        if client is None:
            secret = read_secret(a["hmac_secret_file"]) if a.get("hmac_secret_file") else None
            client = aigel_client.AigelClient(endpoint_url=a["url"], hmac_secret=secret,
                                              host_id=config["host"],
                                              timeout_s=float(a.get("timeout_s", 15)),
                                              max_retries=int(a.get("max_retries", 2)))
        if adapter is None:
            ad = config["adapter"]
            adapter = load_adapter(ad["spec"], ad.get("path"),
                                   ad.get("state_dir", "/var/lib/noobia/autonomy/adapter"),
                                   kill, self.log)

        t = config.get("trigger", {})
        chunker = trigger.Chunker(
            window_s=float(t.get("window_s", 60)), max_lines=int(t.get("max_lines", 15)),
            volume_resets_priority=bool(t.get("volume_resets_priority", True)),
            disabled=kill.exists)
        h = config.get("harness", {})
        self.harness = harness_mod.Harness(
            host=config["host"], read_new=self.reader.read_new, chunker=chunker,
            client=client, adapter=adapter, ranker=self.ranker, emit=self.emit, log=self.log,
            on_priority_rules=self._accept_rules,
            validate_pattern=lambda p: ranker_mod.validate_pattern(p, self.ranker.corpus),
            clock=clock, heartbeat_s=float(h.get("heartbeat_s", 300)),
            silence_s=float(h.get("silence_s", 900)),
            max_per_hour=int(h.get("max_per_hour", 30)), queue_max=int(h.get("queue_max", 20)))
        self.interval_s = float(config.get("interval_s", 1.0))
        self._dirty = False

    def _accept_rules(self, rules):
        if self.prioritizer is None:
            self.log(f"autonomyd priority_rules ignored n={len(rules)}: prioritizer not running")
            return
        for rule in rules:
            try:
                self.prioritizer.add_rule(rule, origin="aigel")
                self.log(f"autonomyd priority rule accepted id={rule.get('id')}")
                self._dirty = True
            except (ValueError, TypeError, KeyError) as exc:
                self.log(f"autonomyd priority rule rejected id={rule.get('id') if isinstance(rule, dict) else None}: {str(exc)[:160]}")

    def _prioritize(self, now):
        if self.prioritizer is None:
            return 0
        emitted = 0
        for ident, text in self.reader.read_new_tagged(self.sources):
            line = self.prioritizer.process(ident, text, now)
            if line:
                self.emit(line)
                emitted += 1
        return emitted

    def step(self):
        now = self.harness.clock()
        emitted = self._prioritize(now)
        summary = self.harness.step()
        summary["prioritized"] = emitted
        if self._dirty or summary.get("delivered") or summary.get("chunks"):
            self.save()
        return summary

    def save(self):
        if self.store_file:
            self.ranker.save_patterns(self.store_file)
        if self.prioritizer is not None and self.map_file:
            self.prioritizer.save_map(self.map_file)
        self._dirty = False

    def check(self):
        return {"ok": True, "host": self.config["host"],
                "view_backend": getattr(self.reader, "backend", "custom"),
                "aigel_url": self.config["aigel"]["url"],
                "adapter": self.config["adapter"]["spec"],
                "patterns": len(self.ranker.store),
                "prioritizer": (f"{len(self.prioritizer.rules)} rules, sources={self.sources}"
                                if self.prioritizer is not None else "disabled"),
                "kill_switch": str(self.kill_switch),
                "kill_switch_active": self.kill_switch.exists()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="validate and print wiring; contact nothing")
    mode.add_argument("--once", action="store_true", help="run one step and exit")
    args = parser.parse_args(argv)
    try:
        daemon = Daemon(load_config(args.config))
    except (ConfigError, ImportError, OSError) as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
        return 1
    if args.check:
        print(json.dumps(daemon.check(), sort_keys=True))
        return 0
    if args.once:
        print(json.dumps(daemon.step(), sort_keys=True))
        return 0
    stopping = []
    signal.signal(signal.SIGTERM, lambda *_: stopping.append(1))
    signal.signal(signal.SIGINT, lambda *_: stopping.append(1))
    daemon.log(f"autonomyd started host={daemon.config['host']}")
    while not stopping:
        try:
            daemon.step()
        except Exception as exc:  # never die silently; the supervisor restarts on exit
            daemon.log(f"autonomyd step error: {type(exc).__name__}: {str(exc)[:200]}")
        time.sleep(daemon.interval_s)
    daemon.save()
    daemon.log("autonomyd stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
