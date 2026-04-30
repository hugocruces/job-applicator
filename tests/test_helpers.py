"""Tests for pure helpers (no API calls)."""

import unittest

from stages._client import (
    CACHE_MARKER,
    estimate_tokens,
    split_at_breakpoint,
    strip_code_fence,
)
from stages.batch import make_slug, parse_selection


class TestSplitAtBreakpoint(unittest.TestCase):
    def test_splits_correctly(self):
        prompt = f"static\n{CACHE_MARKER}\nvariable"
        pre, post = split_at_breakpoint(prompt)
        self.assertEqual(pre, "static")
        self.assertEqual(post, "variable")

    def test_missing_marker_raises(self):
        with self.assertRaises(ValueError):
            split_at_breakpoint("no marker here")


class TestStripCodeFence(unittest.TestCase):
    def test_strips_latex_fence(self):
        self.assertEqual(strip_code_fence("```latex\n\\section{X}\n```"), "\\section{X}")

    def test_strips_tex_fence(self):
        self.assertEqual(strip_code_fence("```tex\n\\section{X}\n```"), "\\section{X}")

    def test_strips_json_fence(self):
        self.assertEqual(strip_code_fence('```json\n{"a":1}\n```'), '{"a":1}')

    def test_strips_unlabeled_fence(self):
        self.assertEqual(strip_code_fence("```\nhello\n```"), "hello")

    def test_no_fence_passthrough(self):
        self.assertEqual(strip_code_fence("plain text"), "plain text")

    def test_partial_fence_passthrough(self):
        self.assertEqual(strip_code_fence("a ```b``` c"), "a ```b``` c")


class TestEstimateTokens(unittest.TestCase):
    def test_rough_estimate(self):
        self.assertEqual(estimate_tokens(""), 1)
        self.assertEqual(estimate_tokens("abcd"), 1)
        self.assertEqual(estimate_tokens("a" * 400), 100)


class TestSlug(unittest.TestCase):
    def test_make_slug(self):
        self.assertEqual(make_slug("Senior Economist", "World Bank"), "senior-economist-world-bank")
        self.assertEqual(make_slug("Data/AI Lead", "OECD!"), "data-ai-lead-oecd")

    def test_slug_truncates(self):
        self.assertLessEqual(len(make_slug("x" * 200, "y" * 200)), 60)


class TestParseSelection(unittest.TestCase):
    def test_all(self):
        self.assertEqual(parse_selection("all", 3), [0, 1, 2])

    def test_individuals(self):
        self.assertEqual(parse_selection("1,3", 5), [0, 2])

    def test_range(self):
        self.assertEqual(parse_selection("2-4", 5), [1, 2, 3])

    def test_mixed(self):
        self.assertEqual(parse_selection("1,3-5", 5), [0, 2, 3, 4])

    def test_out_of_range_dropped(self):
        self.assertEqual(parse_selection("1,99", 3), [0])

    def test_garbage_dropped(self):
        self.assertEqual(parse_selection("1,foo", 3), [0])


if __name__ == "__main__":
    unittest.main()
