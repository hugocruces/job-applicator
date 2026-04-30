"""Stage 3 — Document Adaptation: adapt CV and cover letter for the vacancy."""

import json
from pathlib import Path
from string import Template

from stages._client import call_with_cache, strip_code_fence

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def adapt_cv(vacancy_text: str, analysis: dict, cv_tex: str) -> str:
    """Return adapted CV LaTeX source."""
    prompt = Template((PROMPTS_DIR / "adapt_cv.txt").read_text()).substitute(
        vacancy_text=vacancy_text,
        analysis_json=json.dumps(analysis, indent=2),
        cv_tex=cv_tex,
    )
    return _call_and_extract(prompt, "Adapt CV")


def adapt_cl(vacancy_text: str, analysis: dict, cl_tex: str) -> str:
    """Return adapted cover letter LaTeX source."""
    prompt = Template((PROMPTS_DIR / "adapt_cl.txt").read_text()).substitute(
        vacancy_text=vacancy_text,
        analysis_json=json.dumps(analysis, indent=2),
        cl_tex=cl_tex,
    )
    return _call_and_extract(prompt, "Adapt CL")


def _call_and_extract(prompt: str, stage_label: str) -> str:
    message = call_with_cache(
        model="claude-sonnet-4-6",
        max_tokens=16384,
        prompt=prompt,
        stage_label=stage_label,
    )
    return strip_code_fence(message.content[0].text)
