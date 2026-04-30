"""Golden-path tests for each stage with mocked Anthropic client."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch


def _mk_message(content_blocks, stop_reason="end_turn"):
    """Build a fake anthropic Message with the given content blocks."""
    return SimpleNamespace(
        content=content_blocks,
        stop_reason=stop_reason,
        usage=SimpleNamespace(
            input_tokens=10, output_tokens=5,
            cache_creation_input_tokens=0, cache_read_input_tokens=0,
        ),
    )


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_block(name, input_):
    return SimpleNamespace(type="tool_use", name=name, input=input_)


class _FakeClient:
    """Minimal stand-in for anthropic.Anthropic(); .messages.create returns a queued reply."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []
        self.messages = self  # so client.messages.create works

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._replies.pop(0)


def _patch_client(replies):
    """Patch stages._client._client to return a FakeClient with the given replies."""
    fake = _FakeClient(replies)
    return patch("stages._client._client", return_value=fake), fake


class TestAnalyse(unittest.TestCase):
    def test_returns_tool_input(self):
        from stages.analyse import analyse

        expected = {
            "position_title": "Analyst",
            "organisation": "EFB",
            "key_requirements": {"must_haves": ["x"], "nice_to_haves": []},
            "strengths": ["a"], "gaps": [],
            "fit_score": "Strong", "fit_summary": "ok",
            "personal_objectives_fit": {"aligned": [], "misaligned": [], "unknown": [], "summary": ""},
        }
        msg = _mk_message([_tool_block("submit_analysis", expected)])
        ctx, fake = _patch_client([msg])
        with ctx:
            result = analyse("VAC", "CV", "CL")
        self.assertEqual(result, expected)
        # Verify cache_control was set on the static block
        sent = fake.calls[0]
        blocks = sent["messages"][0]["content"]
        self.assertEqual(blocks[0]["cache_control"], {"type": "ephemeral"})
        self.assertNotIn("cache_control", blocks[1])

    def test_missing_tool_call_raises(self):
        from stages.analyse import analyse

        msg = _mk_message([_text_block("oops")])
        ctx, _ = _patch_client([msg])
        with ctx:
            with self.assertRaises(RuntimeError):
                analyse("V", "C", "L")


class TestBatchScan(unittest.TestCase):
    def test_quick_scan_returns_tool_input(self):
        from stages.batch import quick_scan

        expected = {
            "position_title": "X", "organisation": "Y",
            "fit_score": "Moderate", "reason": "z",
        }
        msg = _mk_message([_tool_block("submit_scan", expected)])
        ctx, _ = _patch_client([msg])
        with ctx:
            self.assertEqual(quick_scan("V", "C"), expected)


class TestReport(unittest.TestCase):
    def test_returns_text(self):
        from stages.report import generate_report

        msg = _mk_message([_text_block("# Fit Summary\nOK")])
        ctx, _ = _patch_client([msg])
        with ctx:
            out = generate_report("V", {"fit_score": "Strong"}, "CV")
        self.assertIn("Fit Summary", out)


class TestAdapt(unittest.TestCase):
    def test_strips_latex_fence(self):
        from stages.adapt import adapt_cv

        msg = _mk_message([_text_block("```latex\n\\documentclass{article}\n```")])
        ctx, _ = _patch_client([msg])
        with ctx:
            out = adapt_cv("V", {"fit_score": "Strong"}, "CV")
        self.assertEqual(out, "\\documentclass{article}")

    def test_passthrough_when_no_fence(self):
        from stages.adapt import adapt_cl

        msg = _mk_message([_text_block("\\documentclass{letter}")])
        ctx, _ = _patch_client([msg])
        with ctx:
            out = adapt_cl("V", {"fit_score": "Strong"}, "CL")
        self.assertEqual(out, "\\documentclass{letter}")


class TestVerify(unittest.TestCase):
    def test_returns_list_of_phrases(self):
        from stages.verify import find_fabrications

        msg = _mk_message([_text_block('["led a team of 50", "PhD from MIT"]')])
        ctx, _ = _patch_client([msg])
        with ctx:
            self.assertEqual(
                find_fabrications("orig", "adapted"),
                ["led a team of 50", "PhD from MIT"],
            )

    def test_returns_empty_when_clean(self):
        from stages.verify import find_fabrications

        msg = _mk_message([_text_block("[]")])
        ctx, _ = _patch_client([msg])
        with ctx:
            self.assertEqual(find_fabrications("o", "a"), [])

    def test_invalid_json_returns_empty(self):
        from stages.verify import find_fabrications

        msg = _mk_message([_text_block("nonsense")])
        ctx, _ = _patch_client([msg])
        with ctx:
            self.assertEqual(find_fabrications("o", "a"), [])


if __name__ == "__main__":
    unittest.main()
