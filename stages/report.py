"""Stage 3 — Report Generation: produce interview preparation report."""

import json
from pathlib import Path
from string import Template

from stages._client import call_with_cache

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "report.txt"


def generate_report(
    vacancy_text: str,
    analysis: dict,
    cv_text: str,
) -> str:
    """Return a Markdown interview preparation report."""
    prompt = Template(PROMPT_PATH.read_text()).substitute(
        vacancy_text=vacancy_text,
        analysis_json=json.dumps(analysis, indent=2),
        cv_text=cv_text,
    )

    message = call_with_cache(
        model="claude-sonnet-4-6",
        max_tokens=16384,
        prompt=prompt,
        stage_label="Report Generation",
    )
    return message.content[0].text
