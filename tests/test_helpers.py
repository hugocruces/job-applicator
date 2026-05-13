"""Tests for pure helpers (no API calls)."""

import tempfile
import unittest
from pathlib import Path

from stages._client import (
    CACHE_MARKER,
    _heuristic_tokens,
    split_at_breakpoint,
    strip_code_fence,
)
from stages.batch import _ATS_RE, make_slug, parse_selection


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


class TestHeuristicTokens(unittest.TestCase):
    def test_rough_estimate(self):
        self.assertEqual(_heuristic_tokens(""), 1)
        self.assertEqual(_heuristic_tokens("abcd"), 1)
        self.assertEqual(_heuristic_tokens("a" * 400), 100)


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

    def test_empty_string(self):
        self.assertEqual(parse_selection("", 3), [])

    def test_whitespace_only(self):
        self.assertEqual(parse_selection("   ", 3), [])

    def test_dedup(self):
        self.assertEqual(parse_selection("1,1,2", 3), [0, 1])

    def test_reversed_range(self):
        # "3-1" yields no valid range (range stops immediately).
        self.assertEqual(parse_selection("3-1", 5), [])


class TestAtsRegex(unittest.TestCase):
    MATCHES = [
        "https://boards.greenhouse.io/acme/jobs/12345",
        "https://jobs.lever.co/acme/12345678-1234-1234-1234-123456789012",
        "https://acme.myworkdayjobs.com/External/job/SF/Engineer_R12",
        "https://chipotle.taleo.net/careersection/requisition/job.ftl?job=R1",
        "https://jobs.smartrecruiters.com/Acme/job/SF-Engineer",
        "https://jobs.ashbyhq.com/acme/abc123",
        "https://acme.breezy.hr/p/abc/position/engineer",
        "https://apply.workable.com/acme/j/AB12CD",
    ]
    NON_MATCHES = [
        "https://example.com/about",
        "https://jobs.lever.co/acme/notahex-but-dashes-here",
        "https://acme.com/careers",
        "https://www.linkedin.com/jobs/view/12345",
    ]

    def test_matches(self):
        for url in self.MATCHES:
            with self.subTest(url=url):
                self.assertTrue(_ATS_RE.search(url), f"should match: {url}")

    def test_non_matches(self):
        for url in self.NON_MATCHES:
            with self.subTest(url=url):
                self.assertFalse(_ATS_RE.search(url), f"should NOT match: {url}")


class TestFindTex(unittest.TestCase):
    def setUp(self):
        from apply import find_tex
        self.find_tex = find_tex
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_skips_helpers(self):
        (self.dir / "main.tex").write_text("x")
        (self.dir / "main-old.tex").write_text("x")
        (self.dir / "scratch-draft.tex").write_text("x")
        self.assertEqual(self.find_tex(self.dir, "CV").name, "main.tex")

    def test_no_files_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.find_tex(self.dir, "CV")

    def test_multiple_canonical_raises(self):
        (self.dir / "a.tex").write_text("x")
        (self.dir / "b.tex").write_text("x")
        with self.assertRaises(ValueError):
            self.find_tex(self.dir, "CV")

    def test_override_absolute(self):
        f = self.dir / "x.tex"
        f.write_text("y")
        self.assertEqual(self.find_tex(self.dir, "CV", override=str(f)), f)

    def test_override_missing_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.find_tex(self.dir, "CV", override="missing.tex")


if __name__ == "__main__":
    unittest.main()
