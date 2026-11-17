#!/usr/bin/env python3
"""One-shot Responses API test on Lynx; read the API key from stdin only."""

import argparse
import json
import sys
import urllib.error
import urllib.request

URL = "https://api.openai.com/v1/responses"


def probe(key, model):
    if not key or len(key) > 512 or "\n" in key or "\r" in key:
        raise ValueError("API credential unavailable")
    payload = {
        "model": model,
        "input": "For a connectivity test, reply with one short sentence saying Lynx is online.",
        "max_output_tokens": 64,
        "store": False,
    }
    request = urllib.request.Request(
        URL, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        # HTTP bodies may contain account metadata; only the code is reported.
        raise RuntimeError(f"Responses API returned HTTP {exc.code}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError("Lynx could not reach the Responses API") from None
    output = []
    for item in result.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    output.append(content.get("text", ""))
    answer = " ".join(output).strip()
    if not answer:
        raise RuntimeError("Responses API returned no text")
    usage = result.get("usage", {})
    return {"ok": True, "model": result.get("model", model),
            "answer": answer[:500], "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "store_requested": False, "credential_saved": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="gpt-5.4-mini")
    args = parser.parse_args()
    if not args.model.isascii() or not args.model.replace("-", "").replace(".", "").isalnum():
        parser.error("invalid model name")
    key = sys.stdin.readline(513).strip()
    try:
        print(json.dumps(probe(key, args.model), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc),
                          "credential_saved": False}, sort_keys=True))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
