#!/usr/bin/env bash
set -euo pipefail

python3 scripts/ai_app_spending_jobs.py --companies data/companies.json --out-dir output
