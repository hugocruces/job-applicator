# Job Application Tool

A Python CLI tool that analyzes job vacancies against your CV and cover letter, then produces tailored versions of both documents plus an interview preparation report.

## Setup

```bash
bash setup.sh
source .venv/bin/activate
```

This creates an isolated virtual environment (in `.venv/`) and installs all dependencies, including `python-dotenv` which auto-loads your `.env` file at runtime.

## Usage

```bash
python apply.py --vacancy <path_or_url> --slug <position-slug> [--mode all|report|adapt]
```

### Arguments

- `--vacancy`: Path to a PDF file or URL of the vacancy notice (required for `all` and `report` modes)
- `--slug`: Short label for output filenames (e.g., `efb-analyst`)
- `--mode`: Which stages to run (default: `all`)

### Modes

| Mode            | Stages                                                            | Use case                                                      |
| --------------- | ----------------------------------------------------------------- | ------------------------------------------------------------- |
| `all` (default) | Ingest → Analysis → Report → Adapt CV → Adapt CL                  | Full run for a new vacancy                                    |
| `report`        | Ingest → Analysis → Report                                        | Check fit before committing to document adaptation            |
| `adapt`         | Adapt CV → Adapt CL                                               | Adapt documents after reviewing the report; reuses saved data |
| `batch`         | Quick-scan → interactive selection → full pipeline on chosen ones | Scan many vacancies at once and pick the best matches         |

### Examples

```bash
# Full run
python apply.py --vacancy notices/efb-analyst.pdf --slug efb-analyst

# Report only (assess fit first)
python apply.py --vacancy https://ec.europa.eu/jobs/vacancy/123 --slug efb-analyst --mode report

# Adapt documents later, without re-running the analysis
python apply.py --slug efb-analyst --mode adapt

# Batch: scan multiple PDFs
python apply.py --mode batch --vacancies notices/job1.pdf notices/job2.pdf notices/job3.pdf

# Batch: scan all listings on a careers page
python apply.py --mode batch --vacancies https://careers.company.com/jobs

# Batch: mix of PDFs and URLs
python apply.py --mode batch --vacancies notices/job1.pdf https://careers.company.com/jobs
```

## Output

All outputs are written to `output/<slug>/`:

- `vacancy-<slug>.txt` — Raw extracted vacancy text (saved for reuse)
- `analysis-<slug>.json` — Gap analysis (structured JSON)
- `report-<slug>.md` — Interview preparation report (Markdown)
- `CV-hugocruces-<slug>.tex` — Adapted CV (LaTeX)
- `coverletter-hugocruces-<slug>.tex` — Adapted cover letter (LaTeX)

## How It Works

### Batch Mode
Quick-scans multiple vacancies in parallel using Claude Haiku and displays a ranked list:

```
  1  [●●● Strong  ]  Senior Economist · World Bank
       "EUROMOD expertise directly relevant to fiscal policy mandate"

  2  [●●○ Moderate]  Data Analyst · OECD
       "Strong quantitative skills, limited experience with OECD datasets"

  3  [●○○ Weak    ]  ML Engineer · Google
       "Research profile doesn't match the engineering-focused requirements"

Select vacancies to process (e.g. 1,3 or 2-4 or all), or Enter to exit:
Run which mode for selected? [all/report] (default: report):
```

Results are sorted Strong → Moderate → Weak. Selected vacancies are then processed through the normal pipeline. Slugs are auto-generated from the position title and organisation.

For URL inputs in batch mode, the tool fetches the page and extracts individual job listing links automatically.

### Stage 1: Vacancy Ingestion
Extracts text from the vacancy notice (PDF or URL) and saves it to disk.

### Stage 2: Gap Analysis
Analyzes the vacancy against your CV, cover letter, and personal preferences using Claude Haiku, producing:
- Key requirements (must-haves and nice-to-haves)
- Your strengths relative to the role
- Identified gaps or weaknesses
- Overall fit score
- Personal objectives fit (aligned, misaligned, and unknown preferences)

### Stage 3: Report Generation
Produces a Markdown interview preparation report with:
- Fit summary
- Application advice (what to emphasise, whether to apply)
- Likely interview questions with suggested answers
- Topics to study
- Questions to ask the interviewer

### Stage 4: CV Adaptation
Reorders/reframes bullet points, highlights relevant experience, and updates the professional summary. Output is valid LaTeX.

### Stage 5: Cover Letter Adaptation
Updates position reference and employer name, rewrites body paragraphs to emphasise fit. Output is valid LaTeX.

## Personalisation

Edit `preferences.md` in the project root to describe your career goals, location preferences, desired work environment, and contract requirements. This file is read during Stage 2 and adds a **personal objectives fit** section to the gap analysis, flagging which of your preferences the role aligns with, conflicts with, or cannot be assessed from the vacancy alone.

If the file is left empty or not present, the rest of the pipeline works as normal.

## Requirements

- Python 3.9+
- `.env` file with `ANTHROPIC_API_KEY` (auto-loaded at runtime)
- Your CV as a `.tex` file in `CV/` (one file only — replace `CV/CV-example.tex`)
- Your cover letter as a `.tex` file in `CL/` (one file only — replace `CL/coverletter-example.tex`)
- Personal preferences: `preferences.md` (optional but recommended)

The tool auto-detects whichever `.tex` file is present in each directory and derives output filenames from it. Your personal files are gitignored; only the example templates are tracked.

### Setting up the API Key

Create a `.env` file in the project root:
```bash
echo 'ANTHROPIC_API_KEY="sk-ant-..."' > .env
```

The file is ignored by git (see `.gitignore`) so it won't be committed.

## Tech Stack

- **Claude API** (claude-haiku-4-5-20251001 for gap analysis, claude-sonnet-4-6 for report and document adaptation)
- **pdfplumber** for PDF text extraction
- **requests** + **BeautifulSoup4** for URL fetching
- **python-dotenv** for `.env` loading
- **argparse** for CLI

## Notes

- Adapted documents are LaTeX only (no PDF compilation)
- Vacancy text and gap analysis are saved to disk, so `--mode adapt` never re-calls the API unnecessarily
- Documents are adapted by reframing existing content only — no fabricated experience
- Each slug gets its own folder, preserving history across applications
