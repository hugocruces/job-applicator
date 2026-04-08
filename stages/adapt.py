"""Stage 3 — Document Adaptation: adapt CV and cover letter for the vacancy."""

import json
from pathlib import Path

import anthropic

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def adapt_cv(vacancy_text: str, analysis: dict, cv_tex: str) -> str:
    """Return adapted CV LaTeX source."""
    prompt_template = (PROMPTS_DIR / "adapt_cv.txt").read_text()
    prompt = prompt_template.format(
        vacancy_text=vacancy_text,
        analysis_json=json.dumps(analysis, indent=2),
        cv_tex=cv_tex,
    )
    return _call_claude(prompt)


def adapt_cl(vacancy_text: str, analysis: dict, cl_tex: str) -> str:
    """Return adapted cover letter LaTeX source."""
    prompt_template = (PROMPTS_DIR / "adapt_cl.txt").read_text()
    prompt = prompt_template.format(
        vacancy_text=vacancy_text,
        analysis_json=json.dumps(analysis, indent=2),
        cl_tex=cl_tex,
    )
    return _call_claude(prompt)


def _call_claude(prompt: str) -> str:
    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )
    text = message.content[0].text

    # Extract LaTeX from markdown code blocks if present
    if "```latex" in text:
        text = text.split("```latex")[1].split("```")[0]
    elif "```tex" in text:
        text = text.split("```tex")[1].split("```")[0]
    elif "```" in text:
        # Only strip if it looks like the whole response is wrapped
        parts = text.split("```")
        if len(parts) == 3 and parts[0].strip() == "":
            text = parts[1]
            # Remove optional language tag on first line
            if text.startswith(("\n", "latex", "tex")):
                text = text.split("\n", 1)[-1] if "\n" in text else text

    return text.strip()
