import os
import re
import time
from pathlib import Path
from dotenv import load_dotenv
import requests

load_dotenv()

api_key = os.getenv("FIRECRAWL_API_KEY")

# --- Step 01: Search + scrape with Firecrawl ---

api_url = "https://api.firecrawl.dev/v2/search"

headers = {
    "Authorization": f"Bearer {api_key}"
}

payload = {
    "query": "Chipotle investor relations press releases",
    "limit": 5,
    "scrapeOptions": {"formats": ["markdown"]}
}

response = requests.post(api_url, headers=headers, json=payload)

data = response.json() # convert response to json
results = data["data"]["web"] # get the results from the response
print(f"Firecrawl returned {len(results)} results")

date_str = time.strftime("%Y-%m-%d")
output_dir = Path("knowledge/raw")
output_dir.mkdir(parents=True, exist_ok=True)

def save_result(r, output_dir, date_str, index, prefix=""):
    slug = re.sub(r'[^a-z0-9]+', '-', r['url'].replace('https://', '').lower()).strip('-')
    filename = f"{prefix}{index:02d}-{date_str}-{slug}.md"
    frontmatter = f"---\ntitle: {r['title']}\nurl: {r['url']}\nscraped: {date_str}\n---\n\n"
    body = r.get('markdown') or ''
    (output_dir / filename).write_text(frontmatter + body, encoding='utf-8')
    print(f"  saved → {filename}")

for i, r in enumerate(results, start=1):
    print(f"  - {r['title']}")
    print(f"    {r['url']}")
    print(f"    markdown length: {len(r.get('markdown') or '')} chars")
    save_result(r, output_dir, date_str, i)