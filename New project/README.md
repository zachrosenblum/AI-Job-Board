# AI App Spending Careers Scraper

This repo contains a small script that scrapes entry-level or 0–2 years roles from the Top 50 AI apps list in the a16z AI Application Spending Report.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python scripts/ai_app_spending_jobs.py --companies data/companies.json --out-dir output
```

Outputs:
- `output/jobs.json`
- `output/jobs.csv`
- `output/metadata.json`

## Notes
- The script looks for job postings that are entry-level or that list a minimum experience of 0–2 years (including "2+ years").
- Some companies have ambiguous names or multiple possible career pages; see `data/companies.json` notes for places to verify.
- If a careers page is not on a supported ATS provider, the script falls back to parsing JSON-LD `JobPosting` data embedded in the page.

## Website

The site lives in `site/` and reads data from `output/jobs.json` and `output/metadata.json`.

Run a simple local server from the repo root:

```bash
python -m http.server 8000
```

Then open `http://localhost:8000/site/`.

Alternatively, run the included server helper:

```bash
python3 scripts/run_server.py
```
