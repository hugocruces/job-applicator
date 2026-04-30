"""Stage 2 — Gap Analysis: send vacancy + CV + CL to Claude for structured analysis."""

import json
from pathlib import Path

import anthropic

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "analyse.txt"
PREFERENCES_PATH = Path(__file__).resolve().parent.parent / "preferences.md"


def analyse(vacancy_text: str, cv_text: str, cl_text: str) -> dict:
    """Return a gap analysis dict from Claude."""
    preferences_text = PREFERENCES_PATH.read_text() if PREFERENCES_PATH.exists() else ""

    prompt_template = PROMPT_PATH.read_text()
    prompt = prompt_template.format(
        vacancy_text=vacancy_text,
        cv_text=cv_text,
        cl_text=cl_text,
        preferences_text=preferences_text,
    )

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    if message.stop_reason == "max_tokens":
        print("\nWARNING: Claude reached the max_tokens limit (Gap Analysis). The analysis might be incomplete.")

    response_text = message.content[0].text

    # Extract JSON from response (handle markdown code blocks)
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    return json.loads(response_text.strip())
