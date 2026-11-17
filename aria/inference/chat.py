#!/usr/bin/env python3
"""Small interactive client for Nexus's gpt-oss-20b service."""

import argparse
import json
import os
from pathlib import Path
from urllib import error, request


DEFAULT_KEY_FILE = Path.home() / ".config/noobia/gpt-oss-20b.api-key"


def api_key(path: Path) -> str:
    key = os.environ.get("NOOBIA_INFERENCE_API_KEY", "").strip()
    if key:
        return key
    try:
        key = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(
            f"Cannot read API key from {path}. Set NOOBIA_INFERENCE_API_KEY "
            "or pass --key-file."
        ) from exc
    if not key:
        raise RuntimeError(f"API key file is empty: {path}")
    return key


def chat(url: str, key: str, model: str, messages: list[dict], max_tokens: int) -> str:
    body = json.dumps(
        {"model": model, "messages": messages, "max_tokens": max_tokens, "stream": False}
    ).encode("utf-8")
    endpoint = url.rstrip("/") + "/v1/chat/completions"
    req = request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    opener = request.build_opener(request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=300) as response:
            payload = json.load(response)
    except error.HTTPError as exc:
        detail = exc.read(500).decode("utf-8", errors="replace")
        raise RuntimeError(f"Server returned HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Could not reach {endpoint}: {exc.reason}") from exc

    content = payload["choices"][0]["message"].get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("The model returned no final reply; try a larger --max-tokens value.")
    return content.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080", help="Nexus server URL")
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument("--model", default="gpt-oss-20b")
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--prompt", help="Send one message and exit instead of chatting interactively")
    args = parser.parse_args()
    if args.max_tokens < 1:
        parser.error("--max-tokens must be positive")

    try:
        key = api_key(args.key_file)
    except RuntimeError as exc:
        parser.error(str(exc))

    messages: list[dict] = []
    if args.prompt is not None:
        prompts = [args.prompt]
    else:
        print("Chat with gpt-oss-20b. Type /reset to clear history or /quit to exit.")
        prompts = None

    while True:
        try:
            prompt = prompts.pop(0) if prompts is not None else input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if prompt == "/quit":
            break
        if prompt == "/reset":
            messages.clear()
            print("History cleared.")
            continue
        if not prompt:
            if prompts is not None:
                break
            continue

        pending = messages + [{"role": "user", "content": prompt}]
        try:
            reply = chat(args.url, key, args.model, pending, args.max_tokens)
        except RuntimeError as exc:
            print(f"Error: {exc}")
            if prompts is not None:
                return 1
            continue
        print(f"Model> {reply}\n")
        messages = pending + [{"role": "assistant", "content": reply}]
        if prompts is not None:
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
