"""Shared helpers: prompt-cache plumbing, Claude calls with retries, usage logging."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from string import Template
from types import SimpleNamespace

import anthropic

from stages.log import get_logger

log = get_logger(__name__)

CACHE_MARKER = "===CACHE_BREAKPOINT==="

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def render_prompt(name: str, **vars: str) -> str:
    """Render a prompt template from prompts/<name> with the given substitutions."""
    return Template((PROMPTS_DIR / name).read_text()).substitute(**vars)

# anthropic SDK's built-in retry handles 429/408/500/502/503/504/529 and network errors
# with exponential backoff. We just bump the count from the default of 2.
_MAX_RETRIES = 5


_BACKEND = "api"

_CLI_TIMEOUT_S = 600
_CLI_SYSTEM_PROMPT = "You are a text-processing function. Follow the user's instructions exactly."
_EXCERPT_CHARS = 300


def set_backend(name: str) -> None:
    """Select the LLM backend: "api" (Anthropic SDK) or "cli" (`claude -p`)."""
    global _BACKEND
    if name not in ("api", "cli"):
        raise ValueError(f"Unknown backend {name!r}; expected 'api' or 'cli'.")
    _BACKEND = name


def get_backend() -> str:
    return _BACKEND


def _excerpt(text: str) -> str:
    text = (text or "").strip()
    return text[:_EXCERPT_CHARS] + ("..." if len(text) > _EXCERPT_CHARS else "")


def _call_cli(
    *,
    model: str,
    max_tokens: int,
    prompt: str,
    schema: dict | None,
    tool_name: str | None,
    stage_label: str,
) -> SimpleNamespace:
    """Run one `claude -p` call and return an Anthropic-Message-shaped namespace."""
    argv = [
        "claude", "-p",
        "--model", model,
        "--output-format", "json",
        "--no-session-persistence",
        "--system-prompt", _CLI_SYSTEM_PROMPT,
        "--tools", "",
        "--safe-mode",
        "--strict-mcp-config",
    ]
    if schema is not None:
        argv += ["--json-schema", json.dumps(schema)]

    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(max_tokens)

    try:
        proc = subprocess.run(
            argv, input=prompt, capture_output=True, text=True,
            env=env, timeout=_CLI_TIMEOUT_S, check=False,
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            f"{stage_label}: `claude` binary not found. Install Claude Code or use --backend api."
        ) from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"{stage_label}: `claude -p` timed out after {_CLI_TIMEOUT_S}s.") from e

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"{stage_label}: `claude -p` exited {proc.returncode} without JSON output: "
            f"{_excerpt(proc.stderr or proc.stdout)}"
        ) from None

    if data.get("api_error") == "max_output_tokens":
        raise RuntimeError(
            f"{stage_label}: the max_tokens cap ({max_tokens}) was hit; the CLI returns no partial text."
        )
    if data.get("is_error") or proc.returncode != 0:
        raise RuntimeError(
            f"{stage_label}: `claude -p` failed (exit {proc.returncode}, "
            f"{data.get('api_error') or data.get('terminal_reason')}): {_excerpt(data.get('result', ''))}"
        )

    if schema is not None:
        if "structured_output" not in data:
            raise RuntimeError(
                f"{stage_label}: `claude -p` returned no structured output: "
                f"{_excerpt(data.get('result', ''))}"
            )
        content = [SimpleNamespace(type="tool_use", name=tool_name, input=data["structured_output"])]
        stop_reason = "tool_use"
    else:
        content = [SimpleNamespace(type="text", text=data.get("result", ""))]
        stop_reason = "end_turn"

    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        usage=SimpleNamespace(**data.get("usage", {})),
    )


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(max_retries=_MAX_RETRIES)


def split_at_breakpoint(prompt: str) -> tuple[str, str]:
    """Split a rendered prompt into (cached_prefix, variable_suffix)."""
    if CACHE_MARKER not in prompt:
        raise ValueError(f"Prompt is missing the {CACHE_MARKER} marker.")
    prefix, suffix = prompt.split(CACHE_MARKER, 1)
    return prefix.strip(), suffix.strip()


def _log_usage(message, stage_label: str) -> None:
    """Log token usage and cache hit info for a single call (DEBUG)."""
    u = getattr(message, "usage", None)
    if u is None:
        return
    parts = [f"in={getattr(u, 'input_tokens', 0)}", f"out={getattr(u, 'output_tokens', 0)}"]
    cw = getattr(u, "cache_creation_input_tokens", 0) or 0
    cr = getattr(u, "cache_read_input_tokens", 0) or 0
    if cw:
        parts.append(f"cache_write={cw}")
    if cr:
        parts.append(f"cache_read={cr}")
    log.debug("  [%s] tokens: %s", stage_label, " ".join(parts))


def call_with_cache(
    *,
    model: str,
    max_tokens: int,
    prompt: str,
    tools: list[dict] | None = None,
    tool_choice: dict | None = None,
    stage_label: str,
):
    """
    Call Claude with prompt caching applied to the static prefix.
    The prompt must contain CACHE_MARKER separating cached prefix from variable suffix.
    """
    cached, variable = split_at_breakpoint(prompt)

    if _BACKEND == "cli":
        message = _call_cli(
            model=model,
            max_tokens=max_tokens,
            prompt=f"{cached}\n\n{variable}",
            schema=tools[0]["input_schema"] if tools else None,
            tool_name=tools[0]["name"] if tools else None,
            stage_label=stage_label,
        )
        _log_usage(message, stage_label)
        return message

    content_blocks = [
        {"type": "text", "text": cached, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": variable},
    ]

    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content_blocks}],
    }
    if tools is not None:
        kwargs["tools"] = tools
    if tool_choice is not None:
        kwargs["tool_choice"] = tool_choice

    message = _client().messages.create(**kwargs)

    if message.stop_reason == "max_tokens":
        log.warning("Claude reached the max_tokens limit (%s). Output may be truncated.", stage_label)
    _log_usage(message, stage_label)
    return message


def call_simple(*, model: str, max_tokens: int, prompt: str, stage_label: str):
    """Single-shot call with no caching (for one-off prompts like URL classification)."""
    if _BACKEND == "cli":
        message = _call_cli(
            model=model, max_tokens=max_tokens, prompt=prompt,
            schema=None, tool_name=None, stage_label=stage_label,
        )
        _log_usage(message, stage_label)
        return message
    message = _client().messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    if message.stop_reason == "max_tokens":
        log.warning("Claude reached the max_tokens limit (%s). Output may be truncated.", stage_label)
    _log_usage(message, stage_label)
    return message


def extract_text(message, stage_label: str) -> str:
    """Join the text blocks of a response, skipping thinking blocks."""
    text_blocks = [b for b in message.content if getattr(b, "type", None) == "text"]
    if not text_blocks:
        raise RuntimeError(f"{stage_label}: model returned no text content.")
    return "".join(b.text for b in text_blocks)


def strip_code_fence(text: str, languages: tuple[str, ...] = ("latex", "tex", "json")) -> str:
    """
    Strip a single surrounding ```lang ... ``` fence if present, returning inner text.
    No-op if the text isn't fully wrapped in a fence.
    """
    text = text.strip()
    for lang in languages:
        opener = f"```{lang}"
        if text.startswith(opener) and text.endswith("```"):
            return text[len(opener):-3].lstrip("\n").rstrip()
    if text.startswith("```") and text.endswith("```"):
        inner = text[3:-3]
        # drop a leading language tag on its own line, if any
        first_nl = inner.find("\n")
        if first_nl != -1 and inner[:first_nl].strip().isalpha():
            inner = inner[first_nl + 1:]
        return inner.strip()
    return text


_DEFAULT_COUNT_MODEL = "claude-sonnet-5-5"


def estimate_tokens(text: str, model: str = _DEFAULT_COUNT_MODEL) -> int:
    """
    Token count for `text`. Tries Anthropic's `count_tokens` endpoint (accurate, free,
    does not count toward usage). Falls back to a chars/4 heuristic on error.
    Under the cli backend, always the heuristic (count_tokens needs an API key).
    """
    if _BACKEND == "cli":
        return _heuristic_tokens(text)
    try:
        result = _client().messages.count_tokens(
            model=model,
            messages=[{"role": "user", "content": text}],
        )
        return int(getattr(result, "input_tokens", 0)) or _heuristic_tokens(text)
    except Exception:
        return _heuristic_tokens(text)


def _heuristic_tokens(text: str) -> int:
    return max(1, len(text) // 4)
