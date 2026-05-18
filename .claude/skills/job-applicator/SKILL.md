---
name: job-applicator
description: >
  Processes job vacancy notices through Hugo's job-applicator pipeline — gap
  analysis, interview-prep report, and adapted CV/cover letter. Use this skill
  whenever the user mentions a vacancy, job notice, job posting, job ad, or
  shares a URL or PDF path that looks like a job listing. Trigger on phrases
  like "there's a vacancy", "process this notice", "apply to", "job posting",
  "I found a job", "run the pipeline", "this position", or whenever the user
  drops a URL or file path in the context of job applications. Don't wait for
  the user to ask explicitly — if the message contains a URL or PDF path
  alongside any job-related language, invoke this skill.
---

# Job Applicator Skill

## Project location

```
/home/hugo/code-projects/job-applicator
```

Always `cd` to this directory and activate the venv before running anything:

```bash
cd /home/hugo/code-projects/job-applicator
source .venv/bin/activate
```

## Step 1 — Extract the source

Pull the vacancy source (URL or file path) from the user's message.

- URL: any `http://` or `https://` link
- File path: any `.pdf` path (absolute or relative to the project root)
- If the user mentions a filename without a full path, look for it in the default notices directory first: `/home/hugo/code-projects/job-applicator/notices/`

If no source is present, check `/home/hugo/code-projects/job-applicator/notices/` for PDF files. If exactly one PDF is there, proceed with it. If multiple, list them and ask which one. If none, ask: "What's the vacancy URL or PDF path?"

## Step 2 — Derive the slug

The slug is a short kebab-case label used for output filenames (e.g. `imf-economist`, `oecd-analyst`).

Derivation priority:
1. If the user stated a slug explicitly, use it.
2. From a URL: combine the org name + a keyword from the path.
   - `https://jobs.imf.org/job/economist-research` → `imf-economist`
   - `https://careers.worldbank.org/en/jobs/123-senior-analyst` → `wb-senior-analyst`
3. From a filename: strip `.pdf` and clean it.
   - `OECD_Vacancy_Analyst_2024.pdf` → `oecd-analyst`
4. If ambiguous or very generic (e.g. `jobs.pdf`, `vacancy.pdf`), ask the user: "What slug should I use for this vacancy? (e.g. `org-role`)"

Keep slugs short (2–3 words max), lowercase, hyphenated, no year unless needed to disambiguate.

## Step 3 — Choose mode

| Situation | Mode |
|---|---|
| Single vacancy (default) | `all` — full pipeline |
| User says "report only" / "just analyse" | `report` |
| User says "adapt only" / "just adapt" | `adapt` (needs prior run) |
| Multiple vacancies / "batch" / "quick scan" | `batch` |

## Step 4 — Run the pipeline

**Single vacancy:**
```bash
cd /home/hugo/code-projects/job-applicator
source .venv/bin/activate
python apply.py --vacancy <source> --slug <slug> [--mode <mode>] [--verify]
```

**Batch mode** (multiple sources):
```bash
cd /home/hugo/code-projects/job-applicator
source .venv/bin/activate
python apply.py --mode batch --vacancies <source1> <source2> ...
```

Add `--verify` if the user asks for a fabrication check on the adapted documents.

## Step 5 — Report back

After the run completes, tell the user:
- Slug used
- Output directory: `output/<slug>/`
- Key files produced (report, adapted CV, adapted CL)
- Fit score from the analysis (visible in the console output)
- Any warnings or errors

## Edge cases

- **Missing source + no job context**: don't trigger. Ask what they need.
- **`--mode adapt` with no prior run**: warn the user — they need to run `all` or `report` first for that slug.
- **Dry run** (`--dry-run`): if the user wants a token/cost estimate without running, add `--dry-run`.
- **URL that needs login / paywall**: ingest will try Playwright headless; if it still fails, ask for a PDF download.
