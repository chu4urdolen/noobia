"""Lynx dynamic brain configuration (G3).

Manages backend selection for Lynx's agent on the OpenAI Responses API:
1. Nexus Qwen (via Nexus OpenAI-compatible proxy)
2. Local (if available on host)
3. Cloud (OpenAI, with API key loaded from private file)

Config file is re-read on change (mtime-tracked).
"""

from __future__ import annotations

import json
from pathlib import Path
import urllib.error
import urllib.request

DEFAULT_CONFIG_PATH = Path("/etc/lynx/brain.json")
FALLBACK_CONFIG_PATH = Path(__file__).resolve().parent / "brain.json"


class BrainConfigError(Exception):
    pass


def read_key(key_path: Path | str) -> str:
    """Read API key from private path, rejecting newlines and oversized files."""
    path = Path(key_path)
    if not path.is_file():
        raise BrainConfigError(f"API key file missing: {path}")
    raw = path.read_text(encoding="utf-8").strip()
    if not raw or len(raw) > 512 or "\n" in raw or "\r" in raw:
        raise BrainConfigError(f"Invalid API key format in: {path}")
    return raw


def check_endpoint_health(url: str, timeout_s: float = 2.0) -> bool:
    """Check if endpoint health check responds."""
    health_url = url.rstrip("/")
    if health_url.endswith("/v1"):
        health_url = health_url[:-3]
    health_url += "/health"

    try:
        req = urllib.request.Request(health_url, headers={"User-Agent": "LynxBrain/1.0"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return resp.status == 200
    except urllib.error.HTTPError:
        # HTTP error means host answered; count as reachable
        return True
    except (OSError, urllib.error.URLError):
        return False


class BrainConfig:
    def __init__(self, config_path: Path | str | None = None):
        self.config_path = Path(config_path) if config_path else (
            DEFAULT_CONFIG_PATH if DEFAULT_CONFIG_PATH.exists() else FALLBACK_CONFIG_PATH
        )
        self._last_mtime: float | None = None
        self._data: dict = {}
        self.reload()

    def reload(self) -> None:
        """Reload configuration if file exists and changed."""
        if not self.config_path.exists():
            if not self._data:
                self._data = {
                    "version": 1,
                    "default_model": "qwen3.8:27b",
                    "backends": [
                        {
                            "name": "nexus-qwen",
                            "tier": "nexus",
                            "base_url": "http://192.168.100.106:8080/v1",
                            "model": "qwen3.8:27b",
                            "key_path": "/etc/lynx/nexus-inference.key",
                            "timeout_s": 60.0,
                        },
                        {
                            "name": "cloud-openai",
                            "tier": "cloud",
                            "base_url": "https://api.openai.com/v1",
                            "model": "gpt-5.4-mini",
                            "key_path": "/etc/lynx/openai.key",
                            "timeout_s": 30.0,
                        },
                    ],
                }
            return

        try:
            mtime = self.config_path.stat().st_mtime
            if self._last_mtime is not None and mtime == self._last_mtime:
                return
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
            self._last_mtime = mtime
        except Exception as e:
            if not self._data:
                raise BrainConfigError(f"Failed to load brain config: {e}") from e

    @property
    def backends(self) -> list[dict]:
        self.reload()
        return self._data.get("backends", [])

    def select_backend(
        self,
        health_checker=check_endpoint_health,
        key_reader=read_key,
    ) -> tuple[str, str, str]:
        """Select healthy backend in tier order (nexus -> local -> cloud).

        Returns: (base_url, model, api_key)
        """
        self.reload()
        backends = self.backends
        if not backends:
            raise BrainConfigError("No inference backends configured")

        for b in backends:
            tier = b.get("tier", "")
            base_url = b.get("base_url", "")
            model = b.get("model", self._data.get("default_model", "qwen3.8:27b"))
            key_path = b.get("key_path")

            # Check health for network tiers
            if tier in ("nexus", "local"):
                if not health_checker(base_url, timeout_s=b.get("timeout_s", 2.0)):
                    continue

            # Read key
            try:
                key = key_reader(key_path) if key_path else ""
            except Exception:
                # If key is unreadable and this is not cloud, continue or error?
                if tier == "cloud":
                    raise
                continue

            return base_url, model, key

        raise BrainConfigError("All configured brain backends are unavailable or unauthenticated")
