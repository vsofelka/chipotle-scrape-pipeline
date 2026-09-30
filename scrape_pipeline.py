"""
scrape_pipeline.py — weekly scrape of Chipotle investor relations news.

Searches the web with the Firecrawl API, then saves each result page as a
markdown file in knowledge/raw/ with a small header (title, url, date scraped).
A GitHub Action runs this every Monday and commits the new files.

Built to keep running unattended:
  - every API call has a timeout, so a hung request can't stall the run
  - network errors, rate limits (429) and server errors (5xx) are retried up
    to 3 times with a growing wait; other errors (e.g. a bad API key) stop
    straight away with a clear message
  - a week with no results fails the run on purpose, so GitHub sends an
    email instead of the pipeline going quiet

Run from the repo root (needs FIRECRAWL_API_KEY in .env):
  python scrape_pipeline.py
"""
import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

API_URL = "https://api.firecrawl.dev/v2/search"
QUERY = "Chipotle investor relations press releases"
RESULT_LIMIT = 5
OUTPUT_DIR = Path("knowledge/raw")

TIMEOUT_SECONDS = 60
MAX_ATTEMPTS = 3
RETRY_STATUSES = {429, 500, 502, 503, 504}


class ScrapeError(Exception):
    """Something went wrong that should fail the run with a readable message."""


def slugify_url(url):
    # https://ir.chipotle.com/news-releases -> ir-chipotle-com-news-releases
    return re.sub(r"[^a-z0-9]+", "-", url.replace("https://", "").lower()).strip("-")


def save_result(r, output_dir, date_str, index, prefix=""):
    filename = f"{prefix}{index:02d}-{date_str}-{slugify_url(r['url'])}.md"
    frontmatter = f"---\ntitle: {r['title']}\nurl: {r['url']}\nscraped: {date_str}\n---\n\n"
    body = r.get("markdown") or ""  # a page that failed to scrape still gets a file
    path = Path(output_dir) / filename
    path.write_text(frontmatter + body, encoding="utf-8")
    print(f"  saved → {filename}")
    return path


def search(api_key, post=requests.post, sleep=time.sleep):
    # Returns the list of web results, retrying temporary failures
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {"query": QUERY, "limit": RESULT_LIMIT, "scrapeOptions": {"formats": ["markdown"]}}

    last_problem = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = post(API_URL, headers=headers, json=payload, timeout=TIMEOUT_SECONDS)
        except requests.RequestException as e:
            last_problem = f"network error: {e}"
        else:
            if response.status_code == 200:
                try:
                    return response.json()["data"]["web"]
                except (ValueError, KeyError, TypeError):
                    raise ScrapeError("Firecrawl returned an unexpected response format")
            if response.status_code not in RETRY_STATUSES:
                # Not temporary (bad key, bad request, no credits): retrying won't help
                raise ScrapeError(f"Firecrawl returned HTTP {response.status_code}")
            last_problem = f"HTTP {response.status_code}"

        if attempt < MAX_ATTEMPTS:
            wait = 10 * attempt  # 10s, then 20s
            print(f"Attempt {attempt} failed ({last_problem}); retrying in {wait}s...")
            sleep(wait)

    raise ScrapeError(f"Firecrawl failed after {MAX_ATTEMPTS} attempts ({last_problem})")


def run(api_key, output_dir, date_str, post=requests.post, sleep=time.sleep):
    results = search(api_key, post=post, sleep=sleep)
    print(f"Firecrawl returned {len(results)} results")
    if not results:
        raise ScrapeError("Firecrawl returned no results")

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    saved = []
    for i, r in enumerate(results, start=1):
        print(f"  - {r.get('title')}  ({r.get('url')})")
        saved.append(save_result(r, output_dir, date_str, i))
    return saved


def main():
    load_dotenv()
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        sys.exit("FIRECRAWL_API_KEY is not set (add it to .env, or as a repository secret for the workflow)")
    try:
        run(api_key, OUTPUT_DIR, time.strftime("%Y-%m-%d"))
    except ScrapeError as e:
        sys.exit(f"Scrape failed: {e}")


if __name__ == "__main__":
    main()
