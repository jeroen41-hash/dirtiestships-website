#!/usr/bin/env python3
"""
emissions_blog_generator.py

Reads scraped emissions news from news_emissions/ JSON files and, for
articles scoring above BLOG_THRESHOLD, generates a full blog post draft
using Gemini.

Drafts are saved to:
  - blog/posts/drafts/{slug}.md     (markdown content)
  - json/blog_drafts.json           (metadata manifest)

Run emissions_publish_draft.py to review and publish.

Usage:
    python emissions_blog_generator.py           # generate new drafts
    python emissions_blog_generator.py --no-push # skip git push
"""

import sys
import json
import os
import re
import time
import subprocess
import requests
from datetime import datetime
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Load .env
# ---------------------------------------------------------------------------

def load_env():
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())

load_env()

try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("Warning: google-genai not installed. Run: pip install google-genai")

gemini_client = None
if GEMINI_AVAILABLE:
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        gemini_client = genai.Client(api_key=api_key)
    else:
        print("Warning: GEMINI_API_KEY not set.")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
NEWS_DIR       = os.path.join(BASE_DIR, "news_emissions")
DRAFTS_DIR     = os.path.join(BASE_DIR, "blog", "posts", "drafts")
BLOG_DRAFTS    = os.path.join(BASE_DIR, "json", "blog_drafts.json")
BLOG_JSON      = os.path.join(BASE_DIR, "json", "blog.json")

BLOG_THRESHOLD = 70    # Minimum score to generate a blog post
MODEL          = "gemini-2.0-flash"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """Make a URL/filename-safe slug (max 60 chars)."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = text.strip("-")
    return text[:60].rstrip("-")


def get_og_image(url: str) -> str:
    """Try to extract og:image from article HTML meta tags."""
    try:
        r = requests.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
        m = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https?://[^"\']+)["\']',
            r.text, re.IGNORECASE
        )
        if not m:
            m = re.search(
                r'<meta[^>]+content=["\'](https?://[^"\']+)["\'][^>]+property=["\']og:image["\']',
                r.text, re.IGNORECASE
            )
        return m.group(1) if m else ""
    except Exception:
        return ""


def load_json(path: str, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_existing_urls() -> set:
    """Return all source_urls already drafted or published."""
    urls = set()
    drafts = load_json(BLOG_DRAFTS, {"posts": []})
    for p in drafts["posts"]:
        if p.get("source_url"):
            urls.add(p["source_url"])
    published = load_json(BLOG_JSON, {"posts": []})
    for p in published["posts"]:
        if p.get("source_url"):
            urls.add(p["source_url"])
    return urls


def get_existing_slugs() -> set:
    """Return all slugs already used in drafts or published posts."""
    slugs = set()
    for data in [load_json(BLOG_DRAFTS, {"posts": []}), load_json(BLOG_JSON, {"posts": []})]:
        for p in data["posts"]:
            if p.get("slug"):
                slugs.add(p["slug"])
    return slugs


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------

BLOG_PROMPT = """You are writing for DirtiestShips.com — a data-driven platform tracking CO2 emissions from the global shipping industry using EU MRV data, CII ratings, and ETS cost analysis.

Write a blog post based on this news article. The post should:

1. Open with a strong lead paragraph establishing the emissions/regulatory significance
2. Provide factual analysis with specifics — numbers, percentages, ship types, companies where available
3. Where relevant, connect to topics the site covers: CII ratings, EU ETS carbon costs, company rankings, EMSA MRV data
4. Include 3-5 sections with H2 headings
5. End with a concise "What this means for shipping emissions" conclusion
6. Be 500-800 words, analytical in tone, no marketing fluff

Internal links you may reference (use markdown links):
- CII ratings tool: [CII ratings](/cii.html)
- Company emissions rankings: [company rankings](/companies.html)
- Latest news: [news feed](/news.html)
- Charts & data: [emissions data](/charts.html)

Article to analyse:
Title: {title}
Source: {source}
Content:
{content}

Rules:
- Pure markdown only — NO YAML frontmatter, no --- delimiters
- Do NOT start with a top-level # heading (the title is handled separately)
- Write objectively; cite the source article where appropriate
- If the article is thin on detail, say so and broaden to the wider regulatory context
"""


def generate_blog_body(title: str, content: str, source: str) -> str:
    if not gemini_client:
        print("  Gemini not available — skipping generation")
        return ""
    prompt = BLOG_PROMPT.format(title=title, source=source, content=content[:6000])
    try:
        response = gemini_client.models.generate_content(
            model=MODEL,
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        print(f"  Gemini error: {e}")
        return ""


# ---------------------------------------------------------------------------
# Draft creation
# ---------------------------------------------------------------------------

def make_unique_slug(base_slug: str, existing_slugs: set) -> str:
    slug = base_slug
    n = 2
    while slug in existing_slugs:
        slug = f"{base_slug[:57]}-{n}"
        n += 1
    return slug


def write_draft(item: dict, body: str, slug: str) -> str:
    """Write markdown file to blog/posts/drafts/. Returns filepath."""
    os.makedirs(DRAFTS_DIR, exist_ok=True)
    filepath = os.path.join(DRAFTS_DIR, f"{slug}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(body)
    return filepath


def update_drafts_json(item: dict, slug: str, featured_image: str):
    """Append a new entry to json/blog_drafts.json."""
    drafts = load_json(BLOG_DRAFTS, {"posts": []})

    excerpt = item.get("summary", "")
    if len(excerpt) > 200:
        excerpt = excerpt[:197] + "..."

    entry = {
        "slug":           slug,
        "title":          item["title"],
        "date":           item["date"],
        "excerpt":        excerpt,
        "author":         "DirtiestShips",
        "source_url":     item.get("source_url", ""),
        "source_name":    item.get("source", ""),
        "score":          item.get("score", 0),
        "featured_image": featured_image,
        "scheduled":      None,
        "created":        datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    drafts["posts"].append(entry)
    save_json(BLOG_DRAFTS, drafts)


# ---------------------------------------------------------------------------
# Git push
# ---------------------------------------------------------------------------

def git_push(slug: str):
    env = os.environ.copy()
    env["GIT_SSH_COMMAND"] = (
        "ssh -i /home/jeroen/.ssh/id_ed25519 -o StrictHostKeyChecking=no"
    )
    try:
        subprocess.run(
            ["git", "add", f"blog/posts/drafts/{slug}.md", "json/blog_drafts.json"],
            check=True, cwd=BASE_DIR, env=env,
        )
        subprocess.run(
            ["git", "commit", "-m", f"New blog draft: {slug}"],
            check=True, cwd=BASE_DIR, env=env,
        )
        subprocess.run(["git", "push"], check=True, cwd=BASE_DIR, env=env)
        print("  Committed and pushed to GitHub.")
    except subprocess.CalledProcessError as e:
        print(f"  Git error: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    no_push = "--no-push" in sys.argv

    if not os.path.isdir(NEWS_DIR):
        print(f"No news_emissions/ folder found at {NEWS_DIR}")
        return

    existing_urls  = get_existing_urls()
    existing_slugs = get_existing_slugs()
    new_drafts     = 0

    # Load all article JSON files, sort by score descending
    articles = []
    for fname in os.listdir(NEWS_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(NEWS_DIR, fname)
        try:
            with open(path, encoding="utf-8") as f:
                item = json.load(f)
            articles.append(item)
        except Exception:
            continue

    articles.sort(key=lambda x: x.get("score", 0), reverse=True)

    print(f"\nFound {len(articles)} articles in news_emissions/")
    print(f"Generating blog posts for articles scoring >= {BLOG_THRESHOLD}\n")

    for item in articles:
        score = item.get("score", 0)
        if score < BLOG_THRESHOLD:
            break  # sorted, so all remaining are lower

        source_url = item.get("source_url", "")
        title      = item.get("title", "").strip()

        if not title or not source_url:
            continue

        if source_url in existing_urls:
            print(f"  Skip (already drafted): {title[:70]}")
            continue

        print(f"  BLOG ({score}): {title[:70]}")

        content = item.get("content", "") or item.get("summary", "")
        if len(content) < 100:
            print(f"  Skip (too short): {title[:70]}")
            continue

        blog_body = generate_blog_body(
            title=title,
            content=content,
            source=item.get("source", ""),
        )
        if not blog_body:
            continue

        # Try to get a featured image
        featured_image = get_og_image(source_url)

        base_slug = slugify(title)
        slug      = make_unique_slug(base_slug, existing_slugs)
        existing_slugs.add(slug)
        existing_urls.add(source_url)

        write_draft(item, blog_body, slug)
        update_drafts_json(item, slug, featured_image)
        new_drafts += 1
        print(f"  Draft saved → blog/posts/drafts/{slug}.md")

        if not no_push:
            git_push(slug)

        time.sleep(2)  # Avoid Gemini rate limiting

    print(f"\nDone. {new_drafts} new draft(s) generated.")
    if new_drafts:
        print("Run: python emissions_publish_draft.py  to review and publish.\n")


if __name__ == "__main__":
    main()
