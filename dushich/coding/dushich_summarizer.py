#!/usr/bin/env python3
"""Dushich Summarizer - iterative context-shifting conversation compactor.

Co-developed by Dushich, Banshee, and Noob on Nexus.

Stands between Aria/Banshee and the Dushich Helper: it takes a large chunk of
conversation text and compactly summarizes it into a desired output size,
iteratively. It cuts the first piece at a sentence boundary, summarizes it to
just under the desired size (refining until it fits), then concatenates the
next sentence-boundary piece to the running summary and summarizes again,
until the whole chunk is digested. Inference uses the local Ollama endpoint
on Nexus (RTX 5090) and never leaves the machine.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
import urllib.request
import os

HOME = os.path.expanduser("~")

AGENT_INSTRUCTIONS = (
    "You are Dushich Summarizer for Noobia. Preserve speaker names, decisions, "
    "file paths, commands, commits, test results, and open tasks. Omit filler "
    "and repetition. Output only the summary."
)

MODEL_CONTEXT_SPECS = {
    "qwen3.8:27b": {"max_tokens": 131072, "summarizer_tokens": 8000, "chars_per_token": 4},
    "gpt-oss:20b": {"max_tokens": 131072, "summarizer_tokens": 6000, "chars_per_token": 4},
}

DEFAULT_MODEL = "qwen3.8:27b"
OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"


def calculate_model_context_size(model: str = DEFAULT_MODEL) -> tuple[int, int]:
    """Return ``(context_size, desired_size)`` character budgets for ``model``.

    ``context_size = summarizer_tokens * chars_per_token`` and
    ``desired_size`` defaults to 25% of ``context_size``.
    """
    spec = MODEL_CONTEXT_SPECS[model]
    context_size = int(spec["summarizer_tokens"] * spec["chars_per_token"])
    desired_size = int(context_size * 0.25)
    return context_size, desired_size


def build_piece_prompt(piece: str, desired_size: int, custom_instructions: str = "") -> str:
    custom = f"\n{custom_instructions.strip()}" if custom_instructions.strip() else ""
    return (
        f"{AGENT_INSTRUCTIONS}{custom}\n"
        f"Summarize the following conversation segment in under {desired_size} characters:\n\n"
        f"{piece}"
    )


def build_refine_prompt(summary: str, desired_size: int, pct_shorter: int, custom_instructions: str = "") -> str:
    custom = f"\n{custom_instructions.strip()}" if custom_instructions.strip() else ""
    return (
        f"{AGENT_INSTRUCTIONS}{custom}\n"
        f"Shorten this summary by at least {pct_shorter}% so it is under {desired_size} characters while keeping key facts:\n\n"
        f"{summary}"
    )


def instruction_size(desired_size: int, custom_instructions: str = "") -> int:
    """Worst-case prompt overhead (instructions + template) for ``desired_size``."""
    return max(
        len(build_piece_prompt("", desired_size, custom_instructions)),
        len(build_refine_prompt("", desired_size, 99, custom_instructions)),
    )


_SENTENCE_END_RE = re.compile(r"[.!?]+(?:[\"')\]]+)?(?:\s+|\n|$)|\n+")


def cut_at_sentence_boundary(text: str, max_len: int) -> tuple[str, str]:
    """Split ``text`` into ``(head, rest)`` so ``head`` fits within ``max_len``.

    Prefers cutting at the last sentence end (``.!?`` + optional closing
    quotes/brackets, or a newline) inside the window; falls back to the last
    whitespace, then to a hard cut at ``max_len``.
    """
    if len(text) <= max_len:
        return text, ""
    window = text[:max_len]
    floor = max(1, max_len // 4)
    cut: int | None = None
    for match in _SENTENCE_END_RE.finditer(window):
        if match.end() >= floor:
            cut = match.end()
    if cut is None:
        whitespace = window.rfind(" ")
        if whitespace >= max_len // 4:
            cut = whitespace
        else:
            cut = max_len
    return text[:cut].rstrip(), text[cut:].lstrip()


def _ollama_infer(prompt: str, context_size: int, model: str = DEFAULT_MODEL) -> str:
    """POST one prompt to the local Ollama chat endpoint and return the reply.

    Does not override ``num_ctx`` so Ollama reuses the warm 131K runner shared
    with Dushich's Codex CLI instead of unloading and reloading the model.
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
    }
    request = urllib.request.Request(
        OLLAMA_CHAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data["message"]["content"].strip()


def summarize_piece(piece: str, desired_size: int, context_size: int = 32000, infer_fn=None, custom_instructions: str = "") -> str:
    """Summarize one conversation segment to under ``desired_size`` characters."""
    infer = infer_fn or _ollama_infer
    return infer(build_piece_prompt(piece, desired_size, custom_instructions), context_size)


def refine_summary(
    summary: str,
    desired_size: int,
    context_size: int = 32000,
    infer_fn=None,
    max_refinements: int = 4,
    custom_instructions: str = "",
) -> str:
    """Shorten ``summary`` (iteratively, with an explicit % target) until it
    fits under ``desired_size`` characters, then trim as a last resort."""
    infer = infer_fn or _ollama_infer
    refinements = 0
    while len(summary) > desired_size and refinements < max_refinements:
        pct_shorter = max(1, math.ceil((len(summary) - desired_size) * 100 / len(summary)))
        summary = infer(build_refine_prompt(summary, desired_size, pct_shorter, custom_instructions), context_size)
        refinements += 1
    if len(summary) > desired_size:
        summary = cut_at_sentence_boundary(summary, desired_size)[0]
    return summary


def summarize_this(
    text: str,
    context_size: int | None = None,
    desired_size: int | None = None,
    infer_fn=None,
    custom_instructions: str = "",
) -> str:
    """Iteratively summarize ``text`` into a summary of at most ``desired_size``.

    The first sentence-boundary piece is summarized into a running summary,
    then each next sentence-boundary piece is concatenated to the running
    summary and re-summarized, until the whole text is digested.
    """
    if context_size is None:
        context_size, default_desired = calculate_model_context_size()
    if desired_size is None:
        desired_size = int(context_size * 0.25)
    if context_size <= 0 or desired_size <= 0:
        raise ValueError("context_size and desired_size must be positive")
    if context_size <= desired_size:
        raise ValueError("context_size must be larger than desired_size")

    instr_len = instruction_size(desired_size, custom_instructions)
    piece_budget = context_size - desired_size - instr_len
    if piece_budget <= 20:
        # Tiny windows (e.g. unit tests) still need a working slice budget;
        # a real model window never lands here because its context size is
        # orders of magnitude larger than the instruction templates.
        piece_budget = 10

    if len(text) <= desired_size:
        if not custom_instructions.strip():
            return text
        # Custom instructions must still be applied for already-small text:
        # run one instruction-aware summarize + refine pass.
        infer_early = infer_fn or _ollama_infer
        return refine_summary(
            summarize_piece(text, desired_size, context_size, infer_early, custom_instructions),
            desired_size,
            context_size,
            infer_early,
            custom_instructions=custom_instructions,
        )

    infer = infer_fn or _ollama_infer
    remaining = text
    first_piece, remaining = cut_at_sentence_boundary(remaining, piece_budget)
    running_summary = refine_summary(
        summarize_piece(first_piece, desired_size, context_size, infer, custom_instructions),
        desired_size,
        context_size,
        infer,
        custom_instructions=custom_instructions,
    )
    while remaining:
        next_piece, remaining = cut_at_sentence_boundary(remaining, max(10, piece_budget - 2))
        if not next_piece:
            break
        combined = running_summary + "\n\n" + next_piece
        running_summary = refine_summary(
            summarize_piece(combined, desired_size, context_size, infer, custom_instructions),
            desired_size,
            context_size,
            infer,
            custom_instructions=custom_instructions,
        )
    return running_summary


DEFAULT_STATE_DIR = Path(HOME + "/.codex/dushich-bridge/summaries")


def incremental_summarize(
    conversation_id: str,
    turns: list[str],
    context_size: int | None = None,
    desired_size: int | None = None,
    state_dir: Path = DEFAULT_STATE_DIR,
    infer_fn=None,
    custom_instructions: str = "",
) -> str:
    """Incrementally summarize a conversation across helper calls.

    Persists the running summary and turn cursor in
    ``summary-<conversation_id>.json`` (plus a ``.log`` copy, mode 0600) so
    only the turns added since the last call are re-processed. ``summarize_this``
    is invoked only when the combined prior summary + new turns crosses
    ``desired_size``.
    """
    if context_size is None:
        context_size, default_desired = calculate_model_context_size()
    if desired_size is None:
        desired_size = int(context_size * 0.25)

    state_dir = Path(state_dir)
    state_file = state_dir / f"summary-{conversation_id}.json"
    state: dict = {"last_cursor": 0, "summary": ""}
    if state_file.exists():
        try:
            loaded = json.loads(state_file.read_text(encoding="utf-8"))
            state["last_cursor"] = int(loaded.get("last_cursor", 0))
            state["summary"] = str(loaded.get("summary", ""))
        except (OSError, ValueError):
            pass

    prior_summary = state["summary"]
    if 0 <= state["last_cursor"] <= len(turns):
        new_slice = turns[state["last_cursor"]:]
    else:
        # Transcript reset (fewer turns than before): start fresh.
        new_slice = turns
        prior_summary = ""

    if not new_slice and prior_summary and len(prior_summary) <= desired_size and not custom_instructions.strip():
        return prior_summary

    new_text = "\n\n".join(new_slice)
    max_new_chars = context_size * 2
    if len(new_text) > max_new_chars:
        tail = new_text[-max_new_chars:]
        newline = tail.find("\n")
        new_text = tail[newline + 1:].strip() if 0 <= newline < len(tail) // 2 else tail.strip()

    combined = "\n\n".join(
        [part for part in [prior_summary, new_text] if part]
    ).strip()
    if len(combined) > desired_size:
        updated_summary = summarize_this(
            combined,
            context_size=context_size,
            desired_size=desired_size,
            infer_fn=infer_fn,
            custom_instructions=custom_instructions,
        )
    else:
        updated_summary = combined

    state_dir.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(
            {
                "conversation_id": conversation_id,
                "last_cursor": len(turns),
                "summary": updated_summary,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    log_file = state_dir / f"summary-{conversation_id}.log"
    log_file.write_text(updated_summary, encoding="utf-8")
    log_file.chmod(0o600)
    return updated_summary


def _self_test() -> int:
    assert calculate_model_context_size() == (32000, 8000)
    assert calculate_model_context_size("gpt-oss:20b") == (24000, 6000)
    head, rest = cut_at_sentence_boundary("One two three. Four five six. Seven eight nine.", 16)
    assert head == "One two three." and rest == "Four five six. Seven eight nine."
    head, rest = cut_at_sentence_boundary("One two three. Four five six. Seven eight nine.", 12)
    assert head == "One two" and rest.startswith("three. Four")
    out = summarize_this(
        "First sentence is here. " * 30,
        context_size=300,
        desired_size=80,
        infer_fn=lambda prompt, context: "Short summary.",
    )
    assert len(out) <= 80
    print("dushich-summarizer self-test: OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize a conversation (stdin, --text, or --file) into a bounded size using local Ollama."
    )
    parser.add_argument("--context-size", type=int, default=None, help="Context window in characters")
    parser.add_argument("--desired-size", type=int, default=None, help="Desired summary size in characters")
    parser.add_argument("--file", "-f", default=None, help="Read input from this file instead of stdin/--text")
    parser.add_argument("--text", "-t", default=None, help="Read input from this string instead of stdin")
    parser.add_argument("--instructions", "-i", default="", help="Custom focus instructions appended after the base prompt")
    parser.add_argument("--self-test", action="store_true", help="Run built-in checks and exit")
    args = parser.parse_args()

    if args.self_test:
        return _self_test()

    if args.file is not None:
        text = Path(args.file).read_text(encoding="utf-8")
    elif args.text is not None:
        text = args.text
    else:
        text = sys.stdin.read()
    if not text.strip():
        print("dushich-summarizer: no input", file=sys.stderr)
        return 1
    effective_desired = args.desired_size
    if effective_desired is None:
        _, default_desired = calculate_model_context_size()
        if args.context_size is not None:
            default_desired = int(args.context_size * 0.25)
        effective_desired = min(default_desired, max(1, int(len(text) * 0.6)))
    summary = summarize_this(
        text,
        context_size=args.context_size,
        desired_size=effective_desired,
        custom_instructions=args.instructions,
    )
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
