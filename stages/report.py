"""Stage 3 — Report Generation: produce interview preparation report."""

import json
from pathlib import Path

import anthropic

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "report.txt"


def generate_report(
    vacancy_text: str,
    analysis: dict,
    cv_text: str,
) -> str:
    """Return a Markdown interview preparation report."""
    prompt_template = PROMPT_PATH.read_text()
    prompt = prompt_template.format(
        vacancy_text=vacancy_text,
        analysis_json=json.dumps(analysis, indent=2),
        cv_text=cv_text,
    )

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    return message.content[0].text
