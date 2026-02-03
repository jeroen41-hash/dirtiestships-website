# 1. FIX: Monkey patch for the new lxml_html_clean module
import sys
try:
    import lxml_html_clean
    sys.modules['lxml.html.clean'] = lxml_html_clean
except ImportError:
    print("Warning: lxml_html_clean not found. Run: pip install lxml_html_clean")

import feedparser
import json
import os
import time
import subprocess
from datetime import datetime
from newspaper import Article

# --- AI SUMMARY CONFIGURATION ---
try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("Warning: google-genai not installed. Run: pip install google-genai")

SYSTEM_INSTRUCTION = """
You are a specialized maritime news editor for hydrogenshipbuilding.com.
Your tone is professional, technically accurate, and forward-looking.

For hydrogenshipbuilding.com:
   - Act as a 'Technology Advocate'.
   - Focus on hydrogen propulsion, fuel cells, LH2 carriers, and green shipping innovations.
   - Highlight technical specifications, efficiency gains, and project milestones.
   - Be enthusiastic about breakthroughs but maintain technical credibility.

GENERAL RULES:
- Output exactly 3 concise sentences.
- Use metric units (e.g., tonnes, m3, MW).
- Focus on the technological and environmental significance.
"""

# Initialize Gemini client
gemini_client = None
if GEMINI_AVAILABLE:
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        gemini_client = genai.Client(api_key=api_key)
    else:
        print("Warning: GEMINI_API_KEY not set. AI summaries disabled.")

def get_smart_summary(title, full_text):
    """Generate an AI-powered summary using Gemini."""
    if not GEMINI_AVAILABLE or not gemini_client:
        return (full_text[:200] + "...") if full_text else ""

    prompt = f"Summarize this hydrogen/maritime news for hydrogenshipbuilding.com:\n\nTITLE: {title}\nTEXT: {full_text[:2000]}"

    try:
        response = gemini_client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config={
                'system_instruction': SYSTEM_INSTRUCTION,
                'temperature': 0.7
            }
        )
        return response.text.strip()
    except Exception as e:
        print(f"AI summary error: {e}")
        return (full_text[:200] + "...") if full_text else ""

# --- CONFIGURATION ---
FEEDS = [
    "https://www.offshore-energy.biz/feed/",
    "https://www.hellenicshippingnews.com/feed/",
    "https://www.rivieramm.com/rss/news-content-hub",
    "https://shipandbunker.com/news/feed",
    "https://splash247.com/feed/",
    "https://prod-qt-images.s3.amazonaws.com/production/bairdmaritime/feed.xml",
    "https://www.google.nl/alerts/feeds/11361701321732954749/13243579899754437557"
]

# Keywords for initial filtering (article must contain at least one)
KEYWORDS = ["hydrogen", "lh2", "fuel cell", "h2", "green ammonia", "electrolyzer", "fuelcell"]

# Scoring weights - higher weight = more important
SCORE_WEIGHTS = {
    # Hydrogen specific (high importance)
    "hydrogen": 15,
    "lh2": 20,
    "liquid hydrogen": 20,
    "fuel cell": 18,
    "fuelcell": 18,
    "h2": 10,
    "electrolyzer": 15,
    "electrolysis": 12,
    "green hydrogen": 18,

    # Alternative fuels
    "ammonia": 12,
    "green ammonia": 15,
    "methanol": 8,
    "e-fuel": 12,
    "e-methanol": 12,

    # Technology terms
    "propulsion": 8,
    "zero-emission": 12,
    "zero emission": 12,
    "carbon-free": 10,
    "decarbonization": 10,
    "decarbonisation": 10,

    # Shipping specific
    "vessel": 3,
    "ship": 3,
    "maritime": 5,
    "shipping": 3,
    "newbuild": 5,
    "carrier": 5,

    # Companies/projects
    "CMB": 8,
    "Kawasaki": 8,
    "HyShip": 10,
    "Norled": 8,

    # Title bonus
    "_title_multiplier": 2
}

def calculate_score(title, content):
    """Calculate importance score based on keyword weights."""
    score = 0
    title_lower = (title or '').lower()
    content_lower = (content or '').lower()
    full_text = title_lower + ' ' + content_lower

    for keyword, weight in SCORE_WEIGHTS.items():
        if keyword.startswith('_'):
            continue
        keyword_lower = keyword.lower()

        # Count occurrences in content
        count = full_text.count(keyword_lower)
        if count > 0:
            # Cap at 3 occurrences to avoid spam
            score += weight * min(count, 3)

            # Title bonus
            if keyword_lower in title_lower:
                score += weight * SCORE_WEIGHTS.get('_title_multiplier', 2)

    return score

# LOCAL DIRECTORIES
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NEWS_INDEX_FILE = os.path.join(BASE_DIR, "json", "news_hydrogen.json")
LOCAL_NEWS_DIR = os.path.join(BASE_DIR, "news_hydrogen")

# Create folders if they don't exist
if not os.path.exists(LOCAL_NEWS_DIR):
    os.makedirs(LOCAL_NEWS_DIR)

def slugify(text):
    """Simple function to make titles safe for filenames."""
    return "".join([c if c.isalnum() else "-" for c in text.lower()]).strip("-")[:50]

def scrape_and_update():
    print(f"[{datetime.now()}] Starting Scrape for Hydrogen Maritime News...")

    # Load existing index
    if os.path.exists(NEWS_INDEX_FILE):
        with open(NEWS_INDEX_FILE, "r") as f:
            try:
                news_index = json.load(f)
            except: news_index = []
    else:
        news_index = []

    existing_urls = {item.get('source_url') or item.get('url') for item in news_index}
    new_count = 0

    for feed_url in FEEDS:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            # Check keywords in title
            if any(key.lower() in entry.title.lower() for key in KEYWORDS):
                if entry.link not in existing_urls:
                    try:
                        # Extract Article
                        article = Article(entry.link)
                        article.download()
                        article.parse()

                        # Skip empty articles
                        if not article.title or not article.text or len(article.text) < 100:
                            print(f"Skipped (empty/short): {entry.link}")
                            continue

                        # Calculate importance score
                        score = calculate_score(article.title, article.text)

                        # Skip low-scoring articles
                        if score < 10:
                            print(f"Skipped (low score {score}): {article.title[:50]}")
                            continue

                        # Generate AI-powered summary
                        ai_summary = get_smart_summary(article.title, article.text)

                        # Data Object
                        news_item = {
                            "id": int(time.time()),
                            "date": datetime.now().strftime("%Y-%m-%d"),
                            "title": article.title,
                            "summary": ai_summary,
                            "content": article.text,
                            "source_url": entry.link,
                            "source": feed_url.split('/')[2].replace('www.', ''),
                            "score": score
                        }

                        # 1. SAVE INDIVIDUAL FILE TO /news/ (Local Archiving)
                        filename = f"{slugify(article.title)}.json"
                        file_path = os.path.join(LOCAL_NEWS_DIR, filename)
                        with open(file_path, "w") as f:
                            json.dump(news_item, f, indent=4)

                        # 2. ADD TO MAIN INDEX
                        news_index.insert(0, news_item)
                        existing_urls.add(entry.link)
                        new_count += 1

                        print(f"Archived (score {score}): {filename}")
                        time.sleep(1) # Be kind to servers
                    except Exception as e:
                        print(f"Error processing {entry.link}: {e}")

    # Save updated index (Keep latest 50 for the website)
    if new_count > 0:
        # Sort by date first (newest), then by score (highest)
        news_index.sort(key=lambda x: (x.get('date', ''), x.get('score', 0)), reverse=True)
        news_index = news_index[:50]
        with open(NEWS_INDEX_FILE, "w") as f:
            json.dump(news_index, f, indent=2)
        print(f"Index updated. {new_count} new articles added.")
        return True

    print("No new news found.")
    return False

def push_to_github():
    """Commit and push news updates to GitHub."""
    try:
        # Ensure SSH key is used (for cron environments)
        env = os.environ.copy()
        env['GIT_SSH_COMMAND'] = 'ssh -i /home/jeroen/.ssh/id_ed25519 -o StrictHostKeyChecking=no'

        print(f"Git working directory: {BASE_DIR}")

        # Add news files
        subprocess.run(["git", "add", "json/news_hydrogen.json", "news_hydrogen/"], check=True, cwd=BASE_DIR, env=env)

        # Check if there are changes to commit
        result = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True, cwd=BASE_DIR, env=env)
        if result.returncode == 0:
            print("No changes to commit.")
            return False

        # Commit with timestamp
        commit_msg = f"Auto-update hydrogen news: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        subprocess.run(["git", "commit", "-m", commit_msg], check=True, cwd=BASE_DIR, env=env)

        # Push to remote
        subprocess.run(["git", "push"], check=True, cwd=BASE_DIR, env=env)
        print("Successfully pushed to GitHub.")
        return True

    except subprocess.CalledProcessError as e:
        print(f"Git error: {e}")
        return False
    except Exception as e:
        print(f"Error pushing to GitHub: {e}")
        return False

if __name__ == "__main__":
    if scrape_and_update():
        push_to_github()
