"""End-to-end integration test for stages.orchestrate.process_vacancy.

Mocks the Anthropic client and patches the output ROOT to a temp dir so we can
assert the full report → adapt CV → adapt CL → verify flow writes the
expected files.
"""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def _mk_message(content_blocks, stop_reason="end_turn"):
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


class _FakeClient:
    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._replies.pop(0)


class TestProcessVacancyIntegration(unittest.TestCase):
    def test_full_pipeline_writes_all_artefacts(self):
        from stages import orchestrate

        replies = [
            _mk_message([_text_block("# Interview Prep\nKey points here.")]),
            _mk_message([_text_block("```latex\n\\documentclass{article}\n```")]),
            _mk_message([_text_block("\\documentclass{letter}")]),
            _mk_message([_text_block("[]")]),
            _mk_message([_text_block("[]")]),
        ]
        fake = _FakeClient(replies)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            with patch("stages.orchestrate.ROOT", tmp_root), \
                 patch("stages._client._client", return_value=fake):
                orchestrate.process_vacancy(
                    slug="test-slug",
                    vacancy_text="A vacancy.",
                    analysis={"fit_score": "Strong", "strengths": [], "gaps": []},
                    cv_tex="\\documentclass{article}\\begin{document}CV\\end{document}",
                    cl_tex="\\documentclass{letter}\\begin{document}CL\\end{document}",
                    cv_stem="CV-test",
                    cl_stem="CL-test",
                    do_report=True,
                    do_adapt=True,
                    verify=True,
                )

            out = tmp_root / "output" / "test-slug"
            self.assertTrue((out / "report-test-slug.md").exists())
            self.assertTrue((out / "CV-test-test-slug.tex").exists())
            self.assertTrue((out / "CL-test-test-slug.tex").exists())
            self.assertIn("Interview Prep", (out / "report-test-slug.md").read_text())
            self.assertEqual(
                (out / "CV-test-test-slug.tex").read_text(),
                "\\documentclass{article}",
            )

        self.assertEqual(len(fake.calls), 5)

    def test_report_only_skips_adapt_and_verify(self):
        from stages import orchestrate

        replies = [_mk_message([_text_block("# Report")])]
        fake = _FakeClient(replies)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            with patch("stages.orchestrate.ROOT", tmp_root), \
                 patch("stages._client._client", return_value=fake):
                orchestrate.process_vacancy(
                    slug="r-only",
                    vacancy_text="V",
                    analysis={"fit_score": "Moderate"},
                    cv_tex="CV", cl_tex="CL",
                    cv_stem="CV", cl_stem="CL",
                    do_report=True,
                    do_adapt=False,
                    verify=False,
                )

            out = tmp_root / "output" / "r-only"
            self.assertTrue((out / "report-r-only.md").exists())
            self.assertFalse((out / "CV-r-only.tex").exists())
            self.assertFalse((out / "CL-r-only.tex").exists())

        self.assertEqual(len(fake.calls), 1)


if __name__ == "__main__":
    unittest.main()
