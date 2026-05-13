"""Stage 4-5 — Document Adaptation: adapt CV and cover letter for the vacancy."""

import json

from stages._client import call_with_cache, render_prompt, strip_code_fence


def adapt_cv(vacancy_text: str, analysis: dict, cv_tex: str) -> str:
    """Return adapted CV LaTeX source."""
    prompt = render_prompt(
        "adapt_cv.txt",
        vacancy_text=vacancy_text,
        analysis_json=json.dumps(analysis, indent=2),
        cv_tex=cv_tex,
    )
    return _call_and_extract(prompt, "Adapt CV")


def adapt_cl(vacancy_text: str, analysis: dict, cl_tex: str) -> str:
    """Return adapted cover letter LaTeX source."""
    prompt = render_prompt(
        "adapt_cl.txt",
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
    text_blocks = [b for b in message.content if getattr(b, "type", None) == "text"]
    if not text_blocks:
        raise RuntimeError(f"{stage_label}: model returned no text content.")
    return strip_code_fence(text_blocks[0].text)
