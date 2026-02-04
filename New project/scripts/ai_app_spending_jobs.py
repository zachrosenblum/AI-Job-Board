#!/usr/bin/env python3
import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
TIMEOUT = 20

COMMON_CAREERS_PATHS = [
    "careers",
    "jobs",
    "company/careers",
    "company/jobs",
    "about/careers",
    "about/jobs",
    "careers/jobs",
    "join-us",
    "work-with-us",
    "team",
]

TITLE_KEYWORDS = [
    "entry",
    "entry-level",
    "junior",
    "associate",
    "new grad",
    "graduate",
    "early career",
    "intern",
    "apprentice",
]

YEARS_PATTERNS = [
    re.compile(r"(\d+)\s*[-–]\s*(\d+)\s*years", re.I),
    re.compile(r"(\d+)\+\s*years", re.I),
    re.compile(r"at least\s*(\d+)\s*years", re.I),
    re.compile(r"minimum\s*of\s*(\d+)\s*years", re.I),
    re.compile(r"(\d+)\s*years", re.I),
]

@dataclass
class Job:
    company: str
    title: str
    location: str
    url: str
    posted_at: Optional[str]
    source: str
    careers_url: str
    min_years: Optional[int]
    entry_level: bool
    match_reason: str


def load_companies(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def fetch_url(session: requests.Session, url: str) -> Optional[requests.Response]:
    try:
        resp = session.get(url, timeout=TIMEOUT, allow_redirects=True)
    except requests.RequestException:
        return None
    if resp.status_code >= 400:
        return None
    if not resp.text or len(resp.text) < 200:
        return None
    return resp


def normalize_url(url: str) -> str:
    if not url:
        return url
    return url.rstrip("/")


def candidate_careers_urls(company: Dict[str, Any]) -> List[str]:
    urls = []
    for u in company.get("careers_urls", []) or []:
        if u:
            urls.append(u)
    homepage = company.get("homepage", "").rstrip("/")
    if homepage:
        for path in COMMON_CAREERS_PATHS:
            urls.append(f"{homepage}/{path}")
    # Deduplicate while preserving order
    seen = set()
    ordered = []
    for u in urls:
        nu = normalize_url(u)
        if nu and nu not in seen:
            seen.add(nu)
            ordered.append(nu)
    return ordered


def find_working_careers_url(session: requests.Session, company: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    for url in candidate_careers_urls(company):
        resp = fetch_url(session, url)
        if resp is not None:
            return url, resp.text
    return None, None


def detect_provider(url: str, html: str) -> str:
    lower = (html or "").lower() + " " + (url or "").lower()
    if "greenhouse.io" in lower or "boards.greenhouse.io" in lower:
        return "greenhouse"
    if "lever.co" in lower:
        return "lever"
    if "ashbyhq.com" in lower:
        return "ashby"
    if "workable.com" in lower:
        return "workable"
    if "smartrecruiters.com" in lower:
        return "smartrecruiters"
    if "recruitee.com" in lower:
        return "recruitee"
    if "breezy.hr" in lower:
        return "breezy"
    if "teamtailor.com" in lower:
        return "teamtailor"
    if "jobvite.com" in lower:
        return "jobvite"
    return "generic"


def extract_first_match(patterns: Iterable[re.Pattern], text: str) -> Optional[str]:
    for p in patterns:
        m = p.search(text)
        if m:
            return m.group(1)
    return None


def extract_greenhouse_board(url: str, html: str) -> Optional[str]:
    patterns = [
        re.compile(r"boards\.greenhouse\.io/([a-zA-Z0-9_-]+)", re.I),
        re.compile(r"boards-api\.greenhouse\.io/v1/boards/([a-zA-Z0-9_-]+)", re.I),
        re.compile(r"greenhouse\.io/([a-zA-Z0-9_-]+)", re.I),
    ]
    return extract_first_match(patterns, " ".join([url or "", html or ""]))


def extract_lever_account(url: str, html: str) -> Optional[str]:
    patterns = [
        re.compile(r"jobs\.lever\.co/([a-zA-Z0-9_-]+)", re.I),
        re.compile(r"api\.lever\.co/v0/postings/([a-zA-Z0-9_-]+)", re.I),
    ]
    return extract_first_match(patterns, " ".join([url or "", html or ""]))


def extract_ashby_account(url: str, html: str) -> Optional[str]:
    patterns = [
        re.compile(r"jobs\.ashbyhq\.com/([a-zA-Z0-9_-]+)", re.I),
        re.compile(r"ashbyhq\.com/([a-zA-Z0-9_-]+)", re.I),
    ]
    return extract_first_match(patterns, " ".join([url or "", html or ""]))


def extract_workable_account(url: str, html: str) -> Optional[str]:
    patterns = [
        re.compile(r"jobs\.workable\.com/([a-zA-Z0-9_-]+)", re.I),
        re.compile(r"apply\.workable\.com/([a-zA-Z0-9_-]+)", re.I),
        re.compile(r"workable\.com/([a-zA-Z0-9_-]+)/jobs", re.I),
    ]
    return extract_first_match(patterns, " ".join([url or "", html or ""]))


def extract_smartrecruiters_company(url: str, html: str) -> Optional[str]:
    patterns = [
        re.compile(r"smartrecruiters\.com/([a-zA-Z0-9_-]+)", re.I),
        re.compile(r"api\.smartrecruiters\.com/v1/companies/([a-zA-Z0-9_-]+)", re.I),
    ]
    return extract_first_match(patterns, " ".join([url or "", html or ""]))


def extract_recruitee_company(url: str, html: str) -> Optional[str]:
    patterns = [
        re.compile(r"https?://([a-zA-Z0-9_-]+)\.recruitee\.com", re.I),
        re.compile(r"recruitee\.com/o/([a-zA-Z0-9_-]+)", re.I),
    ]
    return extract_first_match(patterns, " ".join([url or "", html or ""]))


def extract_breezy_company(url: str, html: str) -> Optional[str]:
    patterns = [
        re.compile(r"https?://([a-zA-Z0-9_-]+)\.breezy\.hr", re.I),
        re.compile(r"breezy\.hr/([a-zA-Z0-9_-]+)", re.I),
    ]
    return extract_first_match(patterns, " ".join([url or "", html or ""]))


def parse_json_ld_jobs(html: str, base_url: str) -> List[Dict[str, Any]]:
    jobs = []
    soup = BeautifulSoup(html, "lxml")
    scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            continue
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict) and "@graph" in data:
            items = data.get("@graph", [])
        else:
            items = [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("@type") != "JobPosting":
                continue
            title = item.get("title") or ""
            url = item.get("url") or base_url
            if url and url.startswith("/"):
                url = urljoin(base_url, url)
            location = ""
            loc = item.get("jobLocation")
            if isinstance(loc, dict):
                location = loc.get("address", {}).get("addressLocality", "")
            elif isinstance(loc, list) and loc:
                first = loc[0]
                if isinstance(first, dict):
                    location = first.get("address", {}).get("addressLocality", "")
            description = item.get("description", "")
            jobs.append(
                {
                    "title": title,
                    "url": url,
                    "location": location,
                    "description": description,
                    "posted_at": item.get("datePosted"),
                }
            )
    return jobs


def greenhouse_jobs(session: requests.Session, board: str) -> List[Dict[str, Any]]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    resp = fetch_url(session, url)
    if not resp:
        return []
    data = resp.json()
    jobs = []
    for job in data.get("jobs", []):
        jobs.append(
            {
                "title": job.get("title", ""),
                "location": (job.get("location") or {}).get("name", ""),
                "url": job.get("absolute_url", ""),
                "posted_at": job.get("updated_at") or job.get("created_at"),
                "description": job.get("content") or "",
            }
        )
    return jobs


def lever_jobs(session: requests.Session, account: str) -> List[Dict[str, Any]]:
    url = f"https://api.lever.co/v0/postings/{account}?mode=json"
    resp = fetch_url(session, url)
    if not resp:
        return []
    data = resp.json()
    jobs = []
    for job in data:
        jobs.append(
            {
                "title": job.get("text", ""),
                "location": job.get("categories", {}).get("location", ""),
                "url": job.get("hostedUrl") or job.get("applyUrl") or "",
                "posted_at": job.get("createdAt"),
                "description": job.get("descriptionPlain") or job.get("description") or "",
            }
        )
    return jobs


def ashby_jobs(session: requests.Session, account: str) -> List[Dict[str, Any]]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{account}?includeCompensation=true"
    resp = fetch_url(session, url)
    if not resp:
        return []
    data = resp.json()
    jobs = []
    for job in data.get("jobs", []):
        location = ""
        if isinstance(job.get("location"), str):
            location = job.get("location", "")
        elif isinstance(job.get("location"), dict):
            location = job.get("location", {}).get("name", "")
        jobs.append(
            {
                "title": job.get("title", ""),
                "location": location,
                "url": job.get("jobUrl") or job.get("applicationFormUrl") or "",
                "posted_at": job.get("publishedAt"),
                "description": job.get("descriptionHtml") or job.get("descriptionPlain") or "",
            }
        )
    return jobs


def workable_jobs(session: requests.Session, account: str) -> List[Dict[str, Any]]:
    url = f"https://www.workable.com/api/accounts/{account}?details=true"
    resp = fetch_url(session, url)
    if not resp:
        return []
    data = resp.json()
    jobs = []
    for job in data.get("jobs", []):
        jobs.append(
            {
                "title": job.get("title", ""),
                "location": job.get("location", {}).get("city", "") or job.get("location", {}).get("country", ""),
                "url": job.get("shortlink") or job.get("application_url") or "",
                "posted_at": job.get("created_at"),
                "description": job.get("description", ""),
            }
        )
    return jobs


def smartrecruiters_jobs(session: requests.Session, company: str) -> List[Dict[str, Any]]:
    url = f"https://api.smartrecruiters.com/v1/companies/{company}/postings"
    resp = fetch_url(session, url)
    if not resp:
        return []
    data = resp.json()
    jobs = []
    for job in data.get("content", []):
        jobs.append(
            {
                "title": job.get("name", ""),
                "location": (job.get("location") or {}).get("city", "") or (job.get("location") or {}).get("country", ""),
                "url": job.get("ref", ""),
                "posted_at": job.get("releasedDate"),
                "description": job.get("jobAd", {}).get("sections", {}).get("jobDescription", {}).get("text", ""),
            }
        )
    return jobs


def recruitee_jobs(session: requests.Session, company: str) -> List[Dict[str, Any]]:
    url = f"https://{company}.recruitee.com/api/offers/"
    resp = fetch_url(session, url)
    if not resp:
        return []
    data = resp.json()
    jobs = []
    for job in data.get("offers", []):
        jobs.append(
            {
                "title": job.get("title", ""),
                "location": job.get("location", ""),
                "url": job.get("careers_url", ""),
                "posted_at": job.get("created_at"),
                "description": job.get("description", ""),
            }
        )
    return jobs


def breezy_jobs(session: requests.Session, company: str) -> List[Dict[str, Any]]:
    url = f"https://api.breezy.hr/v3/company/{company}/positions"
    resp = fetch_url(session, url)
    if not resp:
        return []
    data = resp.json()
    jobs = []
    for job in data:
        jobs.append(
            {
                "title": job.get("name", ""),
                "location": job.get("location", {}).get("name", "") if isinstance(job.get("location"), dict) else job.get("location", ""),
                "url": job.get("url", ""),
                "posted_at": job.get("created_at"),
                "description": job.get("description", ""),
            }
        )
    return jobs


def extract_min_years(text: str) -> Optional[int]:
    if not text:
        return None
    min_years = None
    for pattern in YEARS_PATTERNS:
        for match in pattern.finditer(text):
            if len(match.groups()) >= 2:
                try:
                    low = int(match.group(1))
                    if min_years is None or low < min_years:
                        min_years = low
                except ValueError:
                    continue
            else:
                try:
                    years = int(match.group(1))
                    if min_years is None or years < min_years:
                        min_years = years
                except ValueError:
                    continue
    return min_years


def is_entry_level_title(title: str) -> bool:
    lower = title.lower()
    return any(k in lower for k in TITLE_KEYWORDS)


def filter_jobs(company: str, jobs: List[Dict[str, Any]], careers_url: str, source: str) -> List[Job]:
    filtered: List[Job] = []
    for job in jobs:
        title = (job.get("title") or "").strip()
        if not title:
            continue
        description = (job.get("description") or "").strip()
        min_years = extract_min_years(description)
        entry = is_entry_level_title(title)
        include = False
        reason = ""
        if entry:
            include = True
            reason = "entry_title"
        elif min_years is not None and min_years <= 2:
            include = True
            reason = f"min_years_{min_years}"
        elif description:
            if re.search(r"\b0\s*[-–]\s*2\s*years\b", description, re.I):
                include = True
                reason = "0-2_years"
            elif re.search(r"\b2\+\s*years\b", description, re.I):
                include = True
                reason = "2plus_years"
        if include:
            filtered.append(
                Job(
                    company=company,
                    title=title,
                    location=(job.get("location") or "").strip(),
                    url=(job.get("url") or "").strip(),
                    posted_at=job.get("posted_at"),
                    source=source,
                    careers_url=careers_url,
                    min_years=min_years,
                    entry_level=entry,
                    match_reason=reason,
                )
            )
    return filtered


def collect_jobs(session: requests.Session, company: Dict[str, Any], sleep_s: float) -> List[Job]:
    careers_url, html = find_working_careers_url(session, company)
    if not careers_url or not html:
        return []
    provider = detect_provider(careers_url, html)
    jobs: List[Dict[str, Any]] = []
    if provider == "greenhouse":
        board = extract_greenhouse_board(careers_url, html)
        if board:
            jobs = greenhouse_jobs(session, board)
    elif provider == "lever":
        account = extract_lever_account(careers_url, html)
        if account:
            jobs = lever_jobs(session, account)
    elif provider == "ashby":
        account = extract_ashby_account(careers_url, html)
        if account:
            jobs = ashby_jobs(session, account)
    elif provider == "workable":
        account = extract_workable_account(careers_url, html)
        if account:
            jobs = workable_jobs(session, account)
    elif provider == "smartrecruiters":
        company_key = extract_smartrecruiters_company(careers_url, html)
        if company_key:
            jobs = smartrecruiters_jobs(session, company_key)
    elif provider == "recruitee":
        company_key = extract_recruitee_company(careers_url, html)
        if company_key:
            jobs = recruitee_jobs(session, company_key)
    elif provider == "breezy":
        company_key = extract_breezy_company(careers_url, html)
        if company_key:
            jobs = breezy_jobs(session, company_key)

    if not jobs:
        jobs = parse_json_ld_jobs(html, careers_url)

    time.sleep(sleep_s)
    return filter_jobs(company["name"], jobs, careers_url, provider)


def write_outputs(out_dir: str, jobs: List[Job], companies_count: int) -> None:
    json_path = f"{out_dir.rstrip('/')}/jobs.json"
    csv_path = f"{out_dir.rstrip('/')}/jobs.csv"
    meta_path = f"{out_dir.rstrip('/')}/metadata.json"

    payload = [job.__dict__ for job in jobs]
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "company",
                "title",
                "location",
                "url",
                "posted_at",
                "source",
                "careers_url",
                "min_years",
                "entry_level",
                "match_reason",
            ],
        )
        writer.writeheader()
        for job in payload:
            writer.writerow(job)

    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_jobs": len(jobs),
        "company_count": companies_count,
        "filters": {
            "entry_level_titles": TITLE_KEYWORDS,
            "max_years_experience": 2,
        },
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape entry-level AI app jobs from top 50 careers sites.")
    parser.add_argument("--companies", default="data/companies.json", help="Path to companies.json")
    parser.add_argument("--out-dir", default="output", help="Output directory")
    parser.add_argument("--sleep", type=float, default=0.3, help="Sleep between requests")
    parser.add_argument("--max-per-company", type=int, default=0, help="Limit results per company (0 = no limit)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    companies = load_companies(args.companies)
    session = make_session()

    all_jobs: List[Job] = []
    for company in companies:
        jobs = collect_jobs(session, company, args.sleep)
        if args.max_per_company and len(jobs) > args.max_per_company:
            jobs = jobs[: args.max_per_company]
        all_jobs.extend(jobs)

    write_outputs(args.out_dir, all_jobs, len(companies))
    print(f"Wrote {len(all_jobs)} jobs to {args.out_dir}/jobs.json and jobs.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
