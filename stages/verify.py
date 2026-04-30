"""Post-adaptation sanity check: detect fabricated experience in adapted CV/CL."""

from stages._client import call_simple, strip_code_fence

import json

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


def find_fabrications(original: str, adapted: str, label: str = "Verify") -> list[str]:
    """Return a list of phrases in `adapted` not supported by `original`. Empty list = clean."""
    prompt = _VERIFY_PROMPT.format(original=original, adapted=adapted)
    message = call_simple(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        prompt=prompt,
        stage_label=label,
    )
    text = strip_code_fence(message.content[0].text)
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(result, list):
        return []
    return [s for s in result if isinstance(s, str)]
