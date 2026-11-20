#!/usr/bin/env python3
"""Unit tests for the Dushich iterative context-shifting summarizer."""

import contextlib
import io
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dushich_summarizer import (
    summarize_piece,
    AGENT_INSTRUCTIONS,
    MODEL_CONTEXT_SPECS,
    build_piece_prompt,
    build_refine_prompt,
    calculate_model_context_size,
    cut_at_sentence_boundary,
    instruction_size,
    refine_summary,
    summarize_this,
)


class TestCalculateModelContextSize(unittest.TestCase):
    def test_qwen_default(self) -> None:
        self.assertEqual(calculate_model_context_size(), (32000, 8000))
        self.assertEqual(calculate_model_context_size("qwen3.8:27b"), (32000, 8000))

    def test_gpt_oss(self) -> None:
        self.assertEqual(calculate_model_context_size("gpt-oss:20b"), (24000, 6000))

    def test_desired_is_25_percent_of_context(self) -> None:
        for model, (context_size, desired_size) in {
            "qwen3.8:27b": (32000, 8000),
            "gpt-oss:20b": (24000, 6000),
        }.items():
            spec = MODEL_CONTEXT_SPECS[model]
            self.assertEqual(context_size, spec["summarizer_tokens"] * spec["chars_per_token"])
            self.assertEqual(desired_size, int(context_size * 0.25))

    def test_unknown_model_raises(self) -> None:
        with self.assertRaises(KeyError):
            calculate_model_context_size("no-such-model")


class TestInstructionSizeSubtraction(unittest.TestCase):
    def test_instruction_size_is_worst_case_template(self) -> None:
        desired = 500
        self.assertEqual(
            instruction_size(desired),
            max(len(build_piece_prompt("", desired)), len(build_refine_prompt("", desired, 99))),
        )

    def test_piece_budget_subtracts_instructions(self) -> None:
        context_size, desired_size = 2000, 500
        budget = context_size - desired_size - instruction_size(desired_size)
        self.assertGreater(budget, 20)

        prompts: list[str] = []

        def fake(prompt: str, context: int) -> str:
            prompts.append(prompt)
            return "Summary here."

        text = "Noob shipped the lighthouse. " * 60  # 1740 chars, needs 2 pieces
        summarize_this(text, context_size=context_size, desired_size=desired_size, infer_fn=fake)

        self.assertGreaterEqual(len(prompts), 2)
        template = build_piece_prompt("", desired_size)
        first_piece = prompts[0][len(template):]
        # The first piece must fit the budget AFTER instructions were subtracted.
        self.assertLessEqual(len(first_piece), budget)
        # And the whole first prompt must fit inside the context window.
        self.assertLessEqual(len(prompts[0]), context_size)


class TestCutAtSentenceBoundary(unittest.TestCase):
    def test_cut_at_period(self) -> None:
        head, rest = cut_at_sentence_boundary("Hello there. How are you? I am fine! Yes.", 12)
        self.assertEqual(head, "Hello there.")
        self.assertEqual(rest, "How are you? I am fine! Yes.")

    def test_cut_at_exclamation(self) -> None:
        head, rest = cut_at_sentence_boundary("Wow! Amazing. Next thing here.", 5)
        self.assertEqual(head, "Wow!")
        self.assertEqual(rest, "Amazing. Next thing here.")

    def test_cut_at_question_mark(self) -> None:
        head, rest = cut_at_sentence_boundary("Really? Of course. And then more follows.", 7)
        self.assertEqual(head, "Really?")
        self.assertEqual(rest, "Of course. And then more follows.")

    def test_cut_at_newline(self) -> None:
        text = "First line here.\nSecond line follows. End."
        head, rest = cut_at_sentence_boundary(text, 20)
        self.assertEqual(head, "First line here.")
        self.assertEqual(rest, "Second line follows. End.")

    def test_no_sentence_end_falls_back_to_whitespace(self) -> None:
        head, rest = cut_at_sentence_boundary("A very long word here. Short tail.", 10)
        # Window is text[:10] == "A very lon"; last whitespace inside it is after "very".
        self.assertEqual(head, "A very")
        self.assertTrue(rest.startswith("long word here."))

    def test_short_text_returns_whole(self) -> None:
        text = "Tiny bit."
        self.assertEqual(cut_at_sentence_boundary(text, 50), (text, ""))

    def test_preserves_all_content(self) -> None:
        text = "One. Two. Three. Four. Five."
        head, rest = cut_at_sentence_boundary(text, 8)
        self.assertEqual(head + " " + rest, text)


class TestRefineSummary(unittest.TestCase):
    def test_loops_until_fitting_and_computes_pct(self) -> None:
        calls: list[str] = []
        responses = [
            "This is a long summary that still exceeds the target size. " * 2,  # 120 chars
            "Now it fits.",
        ]

        def fake(prompt: str, context: int) -> str:
            calls.append(prompt)
            return responses[len(calls) - 1]

        initial = "Word " * 40  # 200 chars, desired 100 -> 50% shorter
        result = refine_summary(initial, 100, 32000, infer_fn=fake)
        self.assertLessEqual(len(result), 100)
        self.assertEqual(result, "Now it fits.")
        # First refine asks for 50%; the second uses the actual length of the
        # too-long first response (118 chars) -> ceil(18*100/118) = 16%.
        expected_first = math.ceil((200 - 100) * 100 / 200)
        second_len = len(responses[0])
        expected_second = math.ceil((second_len - 100) * 100 / second_len)
        self.assertIn(f"at least {expected_first}%", calls[0])
        self.assertIn(f"at least {expected_second}%", calls[1])
        self.assertTrue(all(c.startswith(AGENT_INSTRUCTIONS) for c in calls))

    def test_fits_immediately_no_refine(self) -> None:
        calls: list[str] = []
        result = refine_summary(
            "Already short.", 100, 32000, infer_fn=lambda p, c: calls.append(p) or "never"
        )
        self.assertEqual(result, "Already short.")
        self.assertEqual(calls, [])

    def test_trims_after_max_refinements(self) -> None:
        calls: list[str] = []
        too_long = "Very long summary sentence. " * 6  # 168 chars, never shrinks

        def fake(prompt: str, context: int) -> str:
            calls.append(prompt)
            return too_long

        desired = 100
        result = refine_summary(too_long, desired, 32000, infer_fn=fake, max_refinements=2)
        self.assertEqual(len(calls), 2)
        self.assertLessEqual(len(result), desired)
        self.assertEqual(result, cut_at_sentence_boundary(too_long, desired)[0])


class TestSummarizeThisIteration(unittest.TestCase):
    def test_short_text_returned_as_is(self) -> None:
        text = "Already small."
        self.assertEqual(summarize_this(text, context_size=300, desired_size=80, infer_fn=lambda p, c: "X"), text)

    def test_context_shifts_across_pieces(self) -> None:
        prompts: list[str] = []

        def fake(prompt: str, context: int) -> str:
            prompts.append(prompt)
            return "Summary here."

        text = "Noob shipped the lighthouse. " * 60
        out = summarize_this(text, context_size=2000, desired_size=500, infer_fn=fake)
        self.assertLessEqual(len(out), 500)
        self.assertEqual(len(prompts), 2)
        # The second prompt must carry the running summary AND the next piece.
        self.assertIn("Summary here.", prompts[1])
        self.assertIn(text.rstrip()[-30:], prompts[1])
        self.assertTrue(prompts[1].startswith(AGENT_INSTRUCTIONS))

    def test_tiny_window_still_fits(self) -> None:
        out = summarize_this(
            "First sentence is here. " * 30,
            context_size=300,
            desired_size=80,
            infer_fn=lambda p, c: "Short summary.",
        )
        self.assertLessEqual(len(out), 80)
        self.assertGreater(len(out), 0)

    def test_invalid_windows_raise(self) -> None:
        with self.assertRaises(ValueError):
            summarize_this("text", context_size=100, desired_size=100)
        with self.assertRaises(ValueError):
            summarize_this("text", context_size=0, desired_size=10)


class TestLiveOllamaIntegration(unittest.TestCase):
    """One real round trip through local Ollama on Nexus (Ada, RTX 5090)."""

    NOOBIA_CONVERSATION = (
        "Noob: OK we had a restart please continue, sorry\n"
        "Banshee: Everything survived the restart and is back up and verified, "
        "including a completed handoff with Dushich (20261117T155554Z-dce2e4af).\n"
        "Dushich: All services re-verified: ufw, fail2ban, ssh, noobia-inference-proxy, "
        "and noobia-wifi-guard.service are active (running).\n"
        "Noob: OK so in a sentence per added feature, please explain what we have now\n"
        "Banshee: We now have the host firewall, fail2ban intrusion prevention, "
        "subnet-aware SSH hardening, kernel network hardening, Wi-Fi power-save "
        "disablement, static IP profile locking, the self-healing watchdog, and the "
        "Noob Lighthouse presence beacon for the whole Noobia LAN.\n"
        "Noob: Alright we got stuff! Do you have any suggestions for additional features?\n"
        "Banshee: Yes: BBR with fq_codel anti-bufferbloat, an ARP neighbor guard, a "
        "config integrity checksum guard, and the Noob Lighthouse status board.\n"
        "Dushich: I verified RSSI at -57 dBm, gateway ARP present at 192.168.100.1, "
        "and all four hardening config files present with SHA-256 digests recorded.\n"
        "Noob: And yes please do push stuff to git, keep in mind the structure like /noobia/common\n"
        "Banshee: Pushed commit e77623f399fecdff12ab7fe033513c40233bf2ed to main on "
        "git@github.com:chu4urdolen/noobia.git, confirmed via git ls-remote.\n"
        "Noob: Great. Next: build the Dushich summarizer role to compact big "
        "conversation chunks before they reach the Dushich helper context window.\n"
    )

    def test_live_summarize_this_against_local_ollama(self) -> None:
        self.assertGreaterEqual(len(self.NOOBIA_CONVERSATION), 1200)
        result = summarize_this(
            self.NOOBIA_CONVERSATION,
            context_size=1200,
            desired_size=300,
        )
        self.assertGreater(len(result), 0)
        self.assertLessEqual(len(result), 300)




class TestIncrementalSummarize(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.state_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_below_desired_size_skips_llm_and_persists_state(self) -> None:
        from dushich_summarizer import incremental_summarize

        calls: list[str] = []
        turns = ["Hi there.", "How are you?"]
        result = incremental_summarize(
            "conv-1",
            turns,
            context_size=300,
            desired_size=80,
            state_dir=self.state_dir,
            infer_fn=lambda prompt, context: calls.append(prompt) or "never",
        )
        self.assertEqual(calls, [])
        self.assertEqual(result, "Hi there.\n\nHow are you?")
        state_file = self.state_dir / "summary-conv-1.json"
        log_file = self.state_dir / "summary-conv-1.log"
        self.assertTrue(state_file.exists())
        self.assertTrue(log_file.exists())
        state = json.loads(state_file.read_text())
        self.assertEqual(state["last_cursor"], 2)
        self.assertEqual(state["summary"], "Hi there.\n\nHow are you?")
        self.assertEqual(state["conversation_id"], "conv-1")
        self.assertEqual(log_file.read_text(), "Hi there.\n\nHow are you?")
        self.assertEqual(log_file.stat().st_mode & 0o777, 0o600)

    def test_second_call_appends_only_new_turns(self) -> None:
        from dushich_summarizer import incremental_summarize

        first_turns = ["Hi there.", "How are you?"]
        incremental_summarize(
            "conv-2",
            first_turns,
            context_size=300,
            desired_size=80,
            state_dir=self.state_dir,
            infer_fn=lambda prompt, context: "never",
        )

        prompts: list[str] = []
        more_turns = first_turns + ["Long follow-up number one here. " * 10]
        # Normal-sized window so the piece cuts at a real sentence boundary.
        result = incremental_summarize(
            "conv-2",
            more_turns,
            context_size=1000,
            desired_size=200,
            state_dir=self.state_dir,
            infer_fn=lambda prompt, context: prompts.append(prompt) or "Compact summary.",
        )
        self.assertGreaterEqual(len(prompts), 1)
        first_prompt = prompts[0]
        # The saved prior summary AND the new turns (but not a re-read of old
        # context) must feed the single summarize pass.
        self.assertIn("Hi there.", first_prompt)
        self.assertIn("Long follow-up number one here.", first_prompt)
        self.assertLessEqual(len(result), 80)
        state = json.loads((self.state_dir / "summary-conv-2.json").read_text())
        self.assertEqual(state["last_cursor"], len(more_turns))
        self.assertEqual(state["summary"], "Compact summary.")

    def test_huge_cold_start_backlog_is_bounded_to_two_context_windows(self) -> None:
        from dushich_summarizer import incremental_summarize

        prompts: list[str] = []
        # 500 turns (~15,000 chars) with context_size=500 -> max_new_chars=1000
        huge_turns = [f"Turn {i} with details here." for i in range(500)]
        result = incremental_summarize(
            "conv-huge",
            huge_turns,
            context_size=500,
            desired_size=120,
            state_dir=self.state_dir,
            infer_fn=lambda prompt, context: prompts.append(prompt) or "Bounded cold summary.",
        )
        self.assertEqual(result, "Bounded cold summary.")
        # Only the newest ~2 context windows are read: old turns never reach a prompt.
        # (A 500-char window leaves almost no piece budget after the instructions,
        # so the prompt count is loose; real windows are 32,000 characters.)
        self.assertFalse(any("Turn 0 " in p or "Turn 100 " in p for p in prompts))
        self.assertLessEqual(len(prompts), 20)
        self.assertIn("Turn 499", prompts[-1])


class TestCustomInstructions(unittest.TestCase):
    INSTRUCTIONS = "Focus only on mentions of Banshee."

    def test_piece_prompt_inserts_right_after_agent_instructions(self) -> None:
        prompt = build_piece_prompt("piece", 500, self.INSTRUCTIONS)
        self.assertTrue(prompt.startswith(AGENT_INSTRUCTIONS))
        self.assertEqual(
            prompt[len(AGENT_INSTRUCTIONS):len(AGENT_INSTRUCTIONS) + 1 + len(self.INSTRUCTIONS)],
            "\n" + self.INSTRUCTIONS,
        )

    def test_refine_prompt_inserts_right_after_agent_instructions(self) -> None:
        prompt = build_refine_prompt("sum", 500, 30, self.INSTRUCTIONS)
        self.assertTrue(prompt.startswith(AGENT_INSTRUCTIONS))
        self.assertEqual(
            prompt[len(AGENT_INSTRUCTIONS):len(AGENT_INSTRUCTIONS) + 1 + len(self.INSTRUCTIONS)],
            "\n" + self.INSTRUCTIONS,
        )

    def test_empty_or_blank_instructions_are_ignored(self) -> None:
        self.assertEqual(build_piece_prompt("piece", 500), build_piece_prompt("piece", 500, ""))
        self.assertEqual(build_piece_prompt("piece", 500), build_piece_prompt("piece", 500, "   \n  "))
        self.assertEqual(build_refine_prompt("s", 500, 30), build_refine_prompt("s", 500, 30, ""))

    def test_instruction_size_includes_custom_instructions(self) -> None:
        desired = 500
        base = instruction_size(desired)
        with_custom = instruction_size(desired, self.INSTRUCTIONS)
        self.assertGreater(with_custom, base)
        self.assertEqual(with_custom - base, len("\n" + self.INSTRUCTIONS))

    def test_summarize_piece_passes_custom_instructions(self) -> None:
        prompts: list[str] = []
        summarize_piece(
            "piece", 500, 32000,
            infer_fn=lambda p, c: prompts.append(p) or "sum",
            custom_instructions=self.INSTRUCTIONS,
        )
        self.assertEqual(len(prompts), 1)
        self.assertIn(self.INSTRUCTIONS, prompts[0])

    def test_summarize_this_short_text_still_applies_custom(self) -> None:
        prompts: list[str] = []
        out = summarize_this(
            "Tiny text.",
            context_size=500,
            desired_size=200,
            infer_fn=lambda p, c: prompts.append(p) or "Focus summary.",
            custom_instructions=self.INSTRUCTIONS,
        )
        self.assertEqual(len(prompts), 1)
        self.assertIn(self.INSTRUCTIONS, prompts[0])
        self.assertEqual(out, "Focus summary.")

    def test_summarize_this_short_text_no_custom_returns_text(self) -> None:
        out = summarize_this(
            "Tiny text.",
            context_size=500,
            desired_size=200,
            infer_fn=lambda p, c: "never",
        )
        self.assertEqual(out, "Tiny text.")

    def test_piece_budget_shrinks_with_custom_instructions(self) -> None:
        desired, context = 300, 2000
        base_budget = context - desired - instruction_size(desired)
        custom_budget = context - desired - instruction_size(desired, self.INSTRUCTIONS)
        self.assertLess(custom_budget, base_budget)

        prompts: list[str] = []
        def fake(prompt: str, context: int) -> str:
            prompts.append(prompt)
            return "Summary here."
        text = "Noob shipped the lighthouse. " * 120  # large -> forces a cut
        summarize_this(
            text, context_size=context, desired_size=desired,
            infer_fn=fake, custom_instructions=self.INSTRUCTIONS,
        )
        self.assertGreaterEqual(len(prompts), 1)
        template = build_piece_prompt("", desired, self.INSTRUCTIONS)
        first_piece = prompts[0][len(template):]
        self.assertLessEqual(len(first_piece), custom_budget)
        self.assertLessEqual(len(prompts[0]), context)


class TestCLISources(unittest.TestCase):
    def _run_main(self, argv: list[str], stdin: str = ""):
        import dushich_summarizer as ds

        recorded: dict = {}

        def fake_summarize_this(text, context_size=None, desired_size=None,
                                infer_fn=None, custom_instructions=""):
            recorded["text"] = text
            recorded["custom_instructions"] = custom_instructions
            return "SUMMARY"

        old_argv, old_stdin = sys.argv, sys.stdin
        out = io.StringIO()
        try:
            sys.argv = ["dushich_summarizer"] + argv
            sys.stdin = io.StringIO(stdin)
            with mock.patch.object(ds, "summarize_this", side_effect=fake_summarize_this):
                with contextlib.redirect_stdout(out):
                    rc = ds.main()
        finally:
            sys.argv, sys.stdin = old_argv, old_stdin
        return rc, out.getvalue(), recorded

    def test_cli_text_and_instructions(self) -> None:
        body = "Some big conversation text here. " * 5
        rc, out, rec = self._run_main(["--text", body, "-i", "Focus on Banshee"])
        self.assertEqual(rc, 0)
        self.assertIn("Some big conversation text here.", rec["text"])
        self.assertEqual(rec["custom_instructions"], "Focus on Banshee")
        self.assertIn("SUMMARY", out)

    def test_cli_file_and_instructions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "conv.txt"
            body = "Aria discussed the lighthouse with Banshee. " * 5
            f.write_text(body)
            rc, out, rec = self._run_main(
                ["--file", str(f), "--instructions", "Keep speaker names"]
            )
        self.assertEqual(rc, 0)
        self.assertEqual(rec["text"], body)
        self.assertEqual(rec["custom_instructions"], "Keep speaker names")
        self.assertIn("SUMMARY", out)

    def test_cli_stdin_and_default_empty_instructions(self) -> None:
        body = "Dushich shipped the fix. " * 5
        rc, out, rec = self._run_main([], stdin=body)
        self.assertEqual(rc, 0)
        self.assertEqual(rec["text"], body)
        self.assertEqual(rec["custom_instructions"], "")

    def test_cli_empty_input_returns_error(self) -> None:
        rc, out, rec = self._run_main(["--text", "   "])
        self.assertEqual(rc, 1)
        self.assertNotIn("SUMMARY", out)

    def test_cli_text_with_custom_instructions_mocked(self) -> None:
        """CLI --text + --instructions must reach summarize_this as custom_instructions."""
        import dushich_summarizer as ds

        body = "Banshee shipped the lighthouse and Dushich verified the tests passed. " * 4
        custom = "Focus on mentions of Banshee"
        recorded: dict = {}

        def fake(text, context_size=None, desired_size=None, infer_fn=None, custom_instructions=""):
            recorded["text"] = text
            recorded["custom_instructions"] = custom_instructions
            return "Compacted."

        old_argv, old_stdin = sys.argv, sys.stdin
        out = io.StringIO()
        try:
            sys.argv = ["dushich_summarizer", "--text", body, "--instructions", custom]
            sys.stdin = io.StringIO("")
            with mock.patch.object(ds, "summarize_this", side_effect=fake):
                with contextlib.redirect_stdout(out):
                    rc = ds.main()
        finally:
            sys.argv, sys.stdin = old_argv, old_stdin

        self.assertEqual(rc, 0)
        self.assertEqual(recorded["text"], body)
        self.assertEqual(recorded["custom_instructions"], custom)
        self.assertIn("Compacted.", out.getvalue())


if __name__ == "__main__":
    unittest.main()
