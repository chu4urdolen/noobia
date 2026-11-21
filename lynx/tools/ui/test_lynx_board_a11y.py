"""Offline structural accessibility tests for the static board (stdlib only).

Browser checks (contrast, focus, overflow) live in check_board_a11y.py and need
Playwright; these tests pin the HTML structure that screen readers rely on.
"""

from datetime import timedelta
from html.parser import HTMLParser
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lynx_tool_board as board  # noqa: E402
import lynx_tool_manifest as mm  # noqa: E402
from test_lynx_snapshot_age import CAPTURED, fixture  # noqa: E402
N_TOOLS = len(list((Path(__file__).resolve().parents[1] / "local_calls").glob("*.json")))


class Outline(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.headings, self.ids, self.links = [], [], set(), []
        self.footer_in_main = False
        self.cards_in_list = self.cards = 0
        self.sections_labelled = self.sections = 0
        self.landmarks = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag in ("h1", "h2", "h3", "h4"):
            self.headings.append(int(tag[1]))
        if tag == "a":
            self.links.append(attrs.get("href", ""))
        if tag in ("main", "nav", "footer", "header"):
            self.landmarks.append(tag)
        if tag == "footer" and "main" in self.stack:
            self.footer_in_main = True
        if tag == "section":
            self.sections += 1
            if attrs.get("aria-labelledby"):
                self.sections_labelled += 1
        if "card" in (attrs.get("class") or "").split():
            self.cards += 1
            if self.stack and self.stack[-1] == "ul" and tag == "li":
                self.cards_in_list += 1
        if tag not in ("meta", "br", "img", "input", "link"):
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.stack:
            while self.stack and self.stack.pop() != tag:
                pass


def outline(html):
    parser = Outline()
    parser.feed(html)
    return parser


def render(snapshot, now):
    return board.render(mm.apply_snapshot(mm.build(), snapshot), now)


class BoardStructureTest(unittest.TestCase):
    def setUp(self):
        self.html = render(fixture(), CAPTURED + timedelta(minutes=1))
        self.doc = outline(self.html)

    def test_one_h1_and_no_skipped_levels(self):
        levels = self.doc.headings
        self.assertEqual(levels.count(1), 1)
        self.assertEqual(levels[0], 1)
        for a, b in zip(levels, levels[1:]):
            self.assertLessEqual(b, a + 1)

    def test_landmarks_and_footer_outside_main(self):
        self.assertIn("main", self.doc.landmarks)
        self.assertIn("nav", self.doc.landmarks)
        self.assertIn("footer", self.doc.landmarks)
        self.assertFalse(self.doc.footer_in_main)
        self.assertIn('lang="en"', self.html)

    def test_cards_are_list_items_in_labelled_sections(self):
        self.assertEqual(self.doc.cards, N_TOOLS)
        self.assertEqual(self.doc.cards_in_list, N_TOOLS)
        self.assertEqual(self.doc.sections, self.doc.sections_labelled)
        self.assertIn('<span class="sr">(3 tools)</span>', self.html)  # Haptics

    def test_nav_links_resolve_and_stay_in_page(self):
        self.assertTrue(self.doc.links)
        for href in self.doc.links:
            self.assertTrue(href.startswith("#"), href)
            self.assertIn(href[1:], self.doc.ids)

    def test_badges_have_spoken_labels(self):
        self.assertEqual(self.html.count('<span class="sr">Effect: </span>'), N_TOOLS)
        self.assertEqual(self.html.count('<span class="sr">Phone state: </span>'), N_TOOLS)
        self.assertEqual(self.html.count('<span class="sr">Install: </span>'), N_TOOLS)
        self.assertIn('<span class="sr">Human check: </span>attended', self.html)

    def test_stale_state_is_spoken_on_every_badge(self):
        stale = render(fixture(), CAPTURED + timedelta(hours=2))
        self.assertNotIn("(as captured)", self.html)
        known = stale.count('<span class="sr">Phone state: </span>') - \
            stale.count('</span>unknown</span>') - stale.count('</span>summary</span>')
        self.assertEqual(stale.count('<span class="asof">(as captured)</span>'), known)
        self.assertIn('role="status"', stale)

    def test_still_no_scripts_forms_or_remote_assets(self):
        lower = self.html.lower()
        for tag in ("<script", "<form", "<button", "<input", "<iframe", "http://", "https://"):
            self.assertNotIn(tag, lower)


if __name__ == "__main__":
    unittest.main()
