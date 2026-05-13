"""Stage 6 — Verification: detect fabricated experience in adapted CV/CL."""

import json
import re

from stages._client import call_simple, strip_code_fence

_VERIFY_PROMPT = """You are a fact-checker. Compare an ORIGINAL document to an ADAPTED version of it.
List any phrases in the ADAPTED document that describe specific experience, roles, employers,
qualifications, or quantitative achievements that are NOT supported by the ORIGINAL.

Ignore:
- Reorderings of existing content
- Paraphrasings that preserve meaning
- Additions of section headings, formatting, or LaTeX commands
- Generic framing like "experienced in X" if X appears in the original

Return ONLY a JSON array of strings, each string being a verbatim fabricated phrase from the
ADAPTED document. If nothing is fabricated, return [].

ORIGINAL:
{original}

ADAPTED:
{adapted}
"""

# LaTeX command + environment patterns. Stripped before comparison so the model
# isn't distracted by markup differences that don't change meaning.
_LATEX_CMD_RE = re.compile(r"\\[a-zA-Z@]+\*?(?:\[[^\]]*\])?")
_LATEX_BRACE_RE = re.compile(r"[{}]")
_LATEX_COMMENT_RE = re.compile(r"(?<!\\)%.*$", re.MULTILINE)
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_latex(text: str) -> str:
    """Reduce LaTeX source to plain prose for fact-checking."""
    text = _LATEX_COMMENT_RE.sub("", text)
    # Iterate: \textbf{\emph{x}} needs two passes
    for _ in range(3):
        text = _LATEX_CMD_RE.sub(" ", text)
    text = _LATEX_BRACE_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def find_fabrications(original: str, adapted: str, label: str = "Verify") -> list[str]:
    """Return a list of phrases in `adapted` not supported by `original`. Empty list = clean."""
    prompt = _VERIFY_PROMPT.format(
        original=_strip_latex(original),
        adapted=_strip_latex(adapted),
    )
    message = call_simple(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        prompt=prompt,
        stage_label=label,
    )
    text = strip_code_fence(message.content[0].text)
    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"{label}: model returned non-JSON output (could not parse). "
            f"Raw output (first 200 chars): {text[:200]!r}"
        ) from e
    if not isinstance(result, list):
        raise RuntimeError(
            f"{label}: model returned JSON but not a list (got {type(result).__name__})."
        )
    return [s for s in result if isinstance(s, str)]
