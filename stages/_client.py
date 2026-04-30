"""Shared helpers: prompt-cache plumbing, Claude calls with retries, usage logging."""

from __future__ import annotations

import anthropic

CACHE_MARKER = "===CACHE_BREAKPOINT==="

# anthropic SDK's built-in retry handles 429/408/500/502/503/504/529 and network errors
# with exponential backoff. We just bump the count from the default of 2.
_MAX_RETRIES = 5


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(max_retries=_MAX_RETRIES)


def split_at_breakpoint(prompt: str) -> tuple[str, str]:
    """Split a rendered prompt into (cached_prefix, variable_suffix)."""
    if CACHE_MARKER not in prompt:
        raise ValueError(f"Prompt is missing the {CACHE_MARKER} marker.")
    prefix, suffix = prompt.split(CACHE_MARKER, 1)
    return prefix.strip(), suffix.strip()


def _log_usage(message, stage_label: str) -> None:
    """Print token usage and cache hit info for a single call."""
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
    print(f"  [{stage_label}] tokens: " + " ".join(parts))


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
        print(f"\nWARNING: Claude reached the max_tokens limit ({stage_label}). Output may be truncated.")
    _log_usage(message, stage_label)
    return message


def call_simple(*, model: str, max_tokens: int, prompt: str, stage_label: str):
    """Single-shot call with no caching (for one-off prompts like URL classification)."""
    message = _client().messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    if message.stop_reason == "max_tokens":
        print(f"\nWARNING: Claude reached the max_tokens limit ({stage_label}). Output may be truncated.")
    _log_usage(message, stage_label)
    return message


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


def estimate_tokens(text: str) -> int:
    """Rough token-count estimate: ~4 chars/token. Used by --dry-run."""
    return max(1, len(text) // 4)
