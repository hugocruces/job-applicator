"""Stage 2 — Gap Analysis: send vacancy + CV + CL to Claude for structured analysis."""

from stages._client import call_with_cache, render_prompt

ANALYSIS_TOOL = {
    "name": "submit_analysis",
    "description": "Submit a structured gap analysis of the candidate against the vacancy.",
    "input_schema": {
        "type": "object",
        "properties": {
            "position_title": {"type": "string"},
            "organisation": {"type": "string"},
            "key_requirements": {
                "type": "object",
                "properties": {
                    "must_haves": {"type": "array", "items": {"type": "string"}},
                    "nice_to_haves": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["must_haves", "nice_to_haves"],
            },
            "strengths": {"type": "array", "items": {"type": "string"}},
            "gaps": {"type": "array", "items": {"type": "string"}},
            "fit_score": {"type": "string", "enum": ["Strong", "Moderate", "Weak"]},
            "fit_summary": {"type": "string"},
            "personal_objectives_fit": {
                "type": "object",
                "properties": {
                    "aligned": {"type": "array", "items": {"type": "string"}},
                    "misaligned": {"type": "array", "items": {"type": "string"}},
                    "unknown": {"type": "array", "items": {"type": "string"}},
                    "summary": {"type": "string"},
                },
                "required": ["aligned", "misaligned", "unknown", "summary"],
            },
        },
        "required": [
            "position_title", "organisation", "key_requirements",
            "strengths", "gaps", "fit_score", "fit_summary",
            "personal_objectives_fit",
        ],
    },
}


def analyse(vacancy_text: str, cv_text: str, cl_text: str, preferences_text: str = "") -> dict:
    """Return a gap analysis dict from Claude."""
    prompt = render_prompt(
        "analyse.txt",
        vacancy_text=vacancy_text,
        cv_text=cv_text,
        cl_text=cl_text,
        preferences_text=preferences_text,
    )

    message = call_with_cache(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,
        prompt=prompt,
        tools=[ANALYSIS_TOOL],
        tool_choice={"type": "tool", "name": "submit_analysis"},
        stage_label="Gap Analysis",
    )

    for block in message.content:
        if block.type == "tool_use" and block.name == "submit_analysis":
            return block.input

    raise RuntimeError("Gap analysis: model did not return a submit_analysis tool call.")
