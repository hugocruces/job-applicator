"""Stage 3 — Report Generation: produce Markdown interview preparation report."""

import json

from stages._client import call_with_cache, render_prompt, strip_code_fence


def generate_report(
    vacancy_text: str,
    analysis: dict,
    cv_text: str,
) -> str:
    """Return a Markdown interview preparation report."""
    prompt = render_prompt(
        "report.txt",
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
    return strip_code_fence(message.content[0].text, languages=("markdown", "md"))
