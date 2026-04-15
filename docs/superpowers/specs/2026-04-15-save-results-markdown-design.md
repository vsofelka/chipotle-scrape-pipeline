# Design: Save Firecrawl Results as Markdown Files

**Date:** 2026-04-15
**Status:** Approved

## Goal

Extend `scrape_pipeline.py` so that each Firecrawl search result is saved as a markdown file in `knowledge/raw/`.

## File Naming

Filenames are derived from the result URL and today's date:

- Strip `https://` from the URL
- Lowercase the remainder
- Replace all non-alphanumeric characters with `-`
- Trim trailing dashes
- Prepend `YYYY-MM-DD`

**Example:** `https://ir.chipotle.com/news-releases` → `2026-04-15-ir-chipotle-com-news-releases.md`

## File Content

Each file contains a YAML frontmatter block followed by the scraped markdown body:

```markdown
---
title: News Releases - Chipotle Mexican Grill
url: https://ir.chipotle.com/news-releases
scraped: 2026-04-15
---

# News Releases
...
```

If a result's `markdown` field is `None` (page failed to scrape), the file is still written with frontmatter and an empty body.

## Implementation

### New function: `save_result(r, output_dir, date_str)`

Added above the results loop in `scrape_pipeline.py`:

```python
def save_result(r, output_dir, date_str):
    slug = re.sub(r'[^a-z0-9]+', '-', r['url'].replace('https://', '').lower()).strip('-')
    filename = f"{date_str}-{slug}.md"
    frontmatter = f"---\ntitle: {r['title']}\nurl: {r['url']}\nscraped: {date_str}\n---\n\n"
    body = r.get('markdown') or ''
    (output_dir / filename).write_text(frontmatter + body, encoding='utf-8')
    print(f"  saved → {filename}")
```

### Setup before the loop

```python
date_str = time.strftime("%Y-%m-%d")
output_dir = Path("knowledge/raw")
output_dir.mkdir(parents=True, exist_ok=True)
```

### Integration

`save_result(r, output_dir, date_str)` is called inside the existing `for r in results` loop after the existing print statements.

## Dependencies

No new imports or packages required. `re`, `time`, and `Path` are already imported.

## Output

- Directory `knowledge/raw/` is created if it does not exist.
- One `.md` file per result, named by date + URL slug.
- Console prints `saved → <filename>` for each file written.
