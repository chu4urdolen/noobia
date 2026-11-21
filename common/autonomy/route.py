"""Compute routing for Noobia autonomy (ARCHITECTURE.md §7).

Deliverable A, task E5. Review fixes Rt1-Rt3 applied.

Routing order: Nexus -> local -> cloud.
Tasks: inference, detect, stt, tts.
Config re-read on change (tracks file mtime).
Decisions logged to noobia-autonomy.
Endpoints use authenticated proxies and bounded health probes.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
try:
    from . import viewlog
except ImportError:
    import viewlog

TASKS = ("inference", "detect", "stt", "tts")
TIERS = ("nexus", "local", "cloud")
NOOBIA_ROOT = Path(os.environ.get("NOOBIA", "/noobia"))
SYSTEM_CONFIG_PATH = Path("/etc/noobia/route.json")
FALLBACK_CONFIG_PATH = NOOBIA_ROOT / "common" / "autonomy" / "route.json"
LOG_IDENT = "noobia-autonomy"


class RoutingError(RuntimeError):
    pass


@dataclass
class Backend:
    name: str
    tier: str
    endpoint: str
    timeout_s: float = 5.0
    key_file: str | None = None
    health_check: Callable[[], bool] | None = None
    _health_cached_until: float = 0.0
    _health_cache_value: bool = True

    def read_key(self) -> str | None:
        """Read key from external key_file outside Git (Rt1)."""
        if not self.key_file:
            return None
        p = Path(self.key_file)
        if not p.is_file():
            return None
        val = p.read_text(encoding="utf-8").strip()
        return val if val else None

    def is_healthy(self, now: float | None = None) -> bool:
        """Check backend health with bounded probe and brief caching (Rt2)."""
        curr = time.time() if now is None else now
        if curr < self._health_cached_until:
            return self._health_cache_value

        healthy = self._probe()
        self._health_cache_value = healthy
        self._health_cached_until = curr + 5.0  # 5s cache TTL
        return healthy

    def _probe(self) -> bool:
        if self.health_check is not None:
            try:
                return bool(self.health_check())
            except Exception:
                return False

        # Built-in HTTP probe if endpoint is HTTP/HTTPS
        if self.endpoint.startswith(("http://", "https://")):
            health_url = self.endpoint.rstrip("/")
            if health_url.endswith("/v1"):
                health_url = health_url[:-3]
            health_url += "/health"
            try:
                req = Request(health_url, headers={"User-Agent": "NoobiaRouter/1.0"})
                with urlopen(req, timeout=min(2.0, self.timeout_s)) as resp:
                    return resp.status == 200
            except HTTPError:
                return True  # Server answered with HTTP status
            except (URLError, OSError, TimeoutError):
                return False

        return True


def _log_decision(task: str, tier: str, endpoint: str, status: str = "ok") -> None:
    line = f"NOOBIA P0 autonomy route task={task} tier={tier} endpoint={endpoint} status={status}"
    try:
        viewlog.write(LOG_IDENT, line)
    except Exception:
        pass


class Router:
    def __init__(
        self,
        config_path: Path | str | None = None,
        custom_backends: dict[str, list[Backend]] | None = None,
    ):
        self.config_path = Path(config_path) if config_path else (
            SYSTEM_CONFIG_PATH if SYSTEM_CONFIG_PATH.exists() else FALLBACK_CONFIG_PATH
        )
        self._last_mtime: float | None = None
        self._backends: dict[str, list[Backend]] = {}
        self._custom_backends = custom_backends

        if custom_backends is None:
            self._reload_if_needed()

    def _reload_if_needed(self) -> None:
        if self._custom_backends is not None:
            return

        if not self.config_path.exists():
            self._backends = self._default_config()
            return

        try:
            mtime = self.config_path.stat().st_mtime
            if self._last_mtime is not None and mtime == self._last_mtime:
                return
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._backends = self._parse_config(data)
            self._last_mtime = mtime
        except Exception:
            if not self._backends:
                self._backends = self._default_config()

    def _parse_config(self, data: dict) -> dict[str, list[Backend]]:
        parsed = {}
        for task, b_list in data.items():
            parsed_list = []
            for b in b_list:
                parsed_list.append(
                    Backend(
                        name=b.get("name", "unnamed"),
                        tier=b.get("tier", "nexus"),
                        endpoint=b.get("endpoint", ""),
                        timeout_s=float(b.get("timeout_s", 5.0)),
                        key_file=b.get("key_file"),
                    )
                )
            parsed[task] = parsed_list
        return parsed

    def _default_config(self) -> dict[str, list[Backend]]:
        # Rt3: Default inference endpoint is authenticated Nexus proxy on :8080/v1
        return {
            "inference": [
                Backend(
                    name="nexus-qwen",
                    tier="nexus",
                    endpoint="http://192.168.100.106:8080/v1",
                    key_file="/etc/lynx/nexus-inference.key",
                    timeout_s=30.0,
                ),
                Backend(
                    name="local-qwen",
                    tier="local",
                    endpoint="http://127.0.0.1:11434/v1",
                    key_file="/etc/lynx/local-inference.key",
                    timeout_s=30.0,
                ),
                Backend(
                    name="cloud-openai",
                    tier="cloud",
                    endpoint="https://api.openai.com/v1",
                    key_file="/etc/lynx/openai.key",
                    timeout_s=30.0,
                ),
            ],
            "detect": [
                Backend(
                    name="nexus-coral",
                    tier="nexus",
                    endpoint="http://192.168.100.106:5050/detect",
                    timeout_s=5.0,
                ),
                Backend(
                    name="local-cpu",
                    tier="local",
                    endpoint="http://127.0.0.1:5050/detect",
                    timeout_s=10.0,
                ),
            ],
            "stt": [
                Backend(
                    name="nexus-whisper",
                    tier="nexus",
                    endpoint="http://192.168.100.106:5051/transcribe",
                    timeout_s=10.0,
                ),
                Backend(
                    name="local-whisper",
                    tier="local",
                    endpoint="http://127.0.0.1:5051/transcribe",
                    timeout_s=20.0,
                ),
            ],
            "tts": [
                Backend(
                    name="nexus-piper",
                    tier="nexus",
                    endpoint="http://192.168.100.106:5052/tts",
                    timeout_s=5.0,
                ),
                Backend(
                    name="local-alsa",
                    tier="local",
                    endpoint="alsa://default",
                    timeout_s=5.0,
                ),
            ],
        }

    def route(self, task: str) -> Backend:
        """Select healthy backend for task following Nexus -> local -> cloud priority."""
        if task not in TASKS:
            raise RoutingError(f"unknown task: {task!r}")

        self._reload_if_needed()
        backends = (
            self._custom_backends.get(task, [])
            if self._custom_backends is not None
            else self._backends.get(task, [])
        )

        if not backends:
            raise RoutingError(f"no backends configured for task: {task}")

        for backend in backends:
            if backend.is_healthy():
                _log_decision(task, backend.tier, backend.endpoint, status="selected")
                return backend

        _log_decision(task, "none", "none", status="exhausted")
        raise RoutingError(f"all backends exhausted or unhealthy for task: {task}")
