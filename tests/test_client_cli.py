"""Tests for the `claude -p` backend in stages._client, with subprocess.run mocked."""

import json
import os
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from stages import _client, batch
from stages.analyse import ANALYSIS_TOOL, analyse

_USAGE = {
    "input_tokens": 3, "output_tokens": 7,
    "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
}
_PROMPT = "static prefix\n===CACHE_BREAKPOINT===\nvariable suffix"


def _proc(payload: dict | str, returncode: int = 0, stderr: str = ""):
    stdout = payload if isinstance(payload, str) else json.dumps(payload)
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def _ok(result="hello", **extra):
    return {"is_error": False, "result": result, "stop_reason": "end_turn",
            "usage": _USAGE, **extra}


_ANALYSIS = {"position_title": "Analyst", "fit_score": "Strong"}


class CliBackendTests(unittest.TestCase):
    def setUp(self):
        _client.set_backend("cli")

    def tearDown(self):
        _client.set_backend("api")

    def _call(self, run, **kw):
        with patch("stages._client.subprocess.run", run):
            return _client.call_with_cache(
                model="claude-sonnet-5-5", max_tokens=1234, effort="medium", prompt=_PROMPT,
                stage_label="Test Stage", **kw,
            )

    def test_text_result(self):
        run = MagicMock(return_value=_proc(_ok("some text")))
        msg = self._call(run)
        self.assertEqual(_client.extract_text(msg, "t"), "some text")
        self.assertEqual(msg.stop_reason, "end_turn")
        self.assertEqual(run.call_args.kwargs["input"], "static prefix\n\nvariable suffix")

    def test_call_simple_text(self):
        run = MagicMock(return_value=_proc(_ok("simple")))
        with patch("stages._client.subprocess.run", run):
            msg = _client.call_simple(
                model="m", max_tokens=10, effort="high", prompt="no marker needed",
                stage_label="S")
        self.assertEqual(_client.extract_text(msg, "S"), "simple")
        argv = run.call_args.args[0]
        self.assertNotIn("--json-schema", argv)
        self.assertEqual(argv[argv.index("--effort") + 1], "high")

    def test_schema_result_through_analyse(self):
        payload = _ok(structured_output=_ANALYSIS, stop_reason="tool_use")
        run = MagicMock(return_value=_proc(payload))
        with patch("stages._client.subprocess.run", run):
            result = analyse("vacancy", "cv", "cl", "prefs")
        self.assertEqual(result, _ANALYSIS)
        argv = run.call_args.args[0]
        self.assertEqual(
            json.loads(argv[argv.index("--json-schema") + 1]), ANALYSIS_TOOL["input_schema"])

    def test_api_key_stripped_and_max_tokens_env(self):
        run = MagicMock(return_value=_proc(_ok()))
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "dummy-not-a-key"}):
            self._call(run)
        env = run.call_args.kwargs["env"]
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        self.assertEqual(env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"], "1234")

    def test_argv_model_and_isolation_flags(self):
        run = MagicMock(return_value=_proc(_ok()))
        self._call(run)
        argv = run.call_args.args[0]
        self.assertEqual(argv[argv.index("--model") + 1], "claude-sonnet-5-5")
        self.assertEqual(argv[argv.index("--effort") + 1], "medium")
        self.assertIn("--safe-mode", argv)
        self.assertIn("--strict-mcp-config", argv)
        self.assertEqual(argv[argv.index("--tools") + 1], "")
        self.assertIn("--system-prompt", argv)
        self.assertNotIn("--json-schema", argv)

    def test_max_output_tokens_raises(self):
        payload = {"is_error": True, "api_error": "max_output_tokens",
                   "terminal_reason": "api_error", "result": "API Error: exceeded"}
        run = MagicMock(return_value=_proc(payload, returncode=1))
        with self.assertRaises(RuntimeError) as cm:
            self._call(run)
        self.assertIn("max_tokens", str(cm.exception))
        self.assertIn("Test Stage", str(cm.exception))

    def test_error_result_raises(self):
        payload = {"is_error": True, "terminal_reason": "api_error", "result": "boom"}
        run = MagicMock(return_value=_proc(payload, returncode=0))
        with self.assertRaisesRegex(RuntimeError, "Test Stage.*boom"):
            self._call(run)

    def test_nonzero_exit_raises(self):
        run = MagicMock(return_value=_proc(_ok(), returncode=2))
        with self.assertRaisesRegex(RuntimeError, "Test Stage"):
            self._call(run)

    def test_non_json_output_raises(self):
        run = MagicMock(return_value=_proc("not json", returncode=1, stderr="bad flag"))
        with self.assertRaisesRegex(RuntimeError, "bad flag"):
            self._call(run)

    def test_missing_structured_output_raises(self):
        run = MagicMock(return_value=_proc(_ok()))
        with self.assertRaisesRegex(RuntimeError, "structured output"):
            self._call(run, tools=[ANALYSIS_TOOL])

    def test_missing_binary_raises(self):
        run = MagicMock(side_effect=FileNotFoundError())
        with self.assertRaisesRegex(RuntimeError, "--backend api"):
            self._call(run)

    def test_timeout_raises(self):
        run = MagicMock(side_effect=subprocess.TimeoutExpired("claude", 600))
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            self._call(run)

    def test_estimate_tokens_makes_no_api_call(self):
        with patch("stages._client._client") as mock_client:
            n = _client.estimate_tokens("x" * 40)
        mock_client.assert_not_called()
        self.assertEqual(n, 10)

    def test_scan_all_uses_cli_worker_cap(self):
        with patch("stages.batch.ThreadPoolExecutor") as pool, \
                patch("stages.batch.quick_scan", return_value={}), \
                patch("stages.batch._throttle"):
            pool.return_value.__enter__.return_value.submit.side_effect = (
                lambda fn, *a: MagicMock(result=lambda: fn(*a)))
            with patch("stages.batch.as_completed", side_effect=lambda fs: list(fs)):
                batch.scan_all([("a", "text")], "cv")
        pool.assert_called_once_with(max_workers=batch.CLI_MAX_SCAN_WORKERS)

    def test_scan_all_uses_api_worker_cap(self):
        _client.set_backend("api")
        with patch("stages.batch.ThreadPoolExecutor") as pool:
            pool.return_value.__enter__.return_value.submit.side_effect = None
            with patch("stages.batch.as_completed", return_value=[]):
                batch.scan_all([], "cv")
        pool.assert_called_once_with(max_workers=batch.MAX_SCAN_WORKERS)


class SetBackendTests(unittest.TestCase):
    def tearDown(self):
        _client.set_backend("api")

    def test_bogus_raises(self):
        with self.assertRaises(ValueError):
            _client.set_backend("bogus")

    def test_get_backend(self):
        _client.set_backend("cli")
        self.assertEqual(_client.get_backend(), "cli")


if __name__ == "__main__":
    unittest.main()
