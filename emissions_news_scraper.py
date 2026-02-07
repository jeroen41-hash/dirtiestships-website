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
from urllib.parse import urlparse, parse_qs
from newspaper import Article



# --- AI SUMMARY CONFIGURATION ---
try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("Warning: google-genai not installed. Run: pip install google-genai")

SYSTEM_INSTRUCTION = """
You are a specialized maritime news editor for dirtiestships.com.
Your tone is "scherp" (sharp), professional, and technically accurate.

For dirtiestships.com:
   - Act as a 'Watchdog Critic'.
   - Be skeptical of "greenwashing" from big shipping lines.
   - Focus on carbon intensity, FuelEU Maritime fines, and excessive HFO usage.
   - Highlight when a ship's emissions exceed its CII rating.

GENERAL RULES:
- Output exactly 3 concise sentences.
- Use metric units (e.g., tonnes, m3).
- Do not use corporate fluff. If a news item is boring, make it sharp.
"""

# Load .env file from script directory
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

    prompt = f"Summarize this maritime emissions news for dirtiestships.com:\n\nTITLE: {title}\nTEXT: {full_text[:2000]}"

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
    "https://www.google.nl/alerts/feeds/11361701321732954749/806710994395188837"
]

# Keywords for initial filtering (article must contain at least one)
KEYWORDS = ["EU-ETS", "CO2", "greenhouse gas", "emissions", "fueleu", "MRV", "CII", "EEDI", "decarbonization", "decarbonisation"]

# Scoring weights - higher weight = more important
SCORE_WEIGHTS = {
    # Regulatory terms (high importance)
    "EU-ETS": 15,
    "ETS": 10,
    "fueleu": 15,
    "MRV": 12,
    "IMO": 10,
    "CII": 12,
    "EEDI": 12,
    "EEXI": 12,

    # Emissions terms
    "CO2": 5,
    "emissions": 5,
    "greenhouse gas": 8,
    "carbon": 5,
    "decarbonization": 10,
    "decarbonisation": 10,
    "net-zero": 10,
    "net zero": 10,

    # Alternative fuels (medium-high importance)
    "methanol": 12,
    "ammonia": 12,
    "hydrogen": 10,
    "LNG": 8,
    "biofuel": 8,

    # Shipping specific
    "shipping": 3,
    "maritime": 3,
    "vessel": 2,
    "ship": 2,
    "fleet": 3,

    # Companies/organizations
    "Maersk": 5,
    "MSC": 5,
    "CMA CGM": 5,
    "EMSA": 8,

    # Title bonus (if keyword appears in title, extra points)
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
NEWS_INDEX_FILE = os.path.join(BASE_DIR, "json", "news.json")
LOCAL_NEWS_DIR = os.path.join(BASE_DIR, "news_emissions")

# Create /news/ folder if it doesn't exist
if not os.path.exists(LOCAL_NEWS_DIR):
    os.makedirs(LOCAL_NEWS_DIR)

def resolve_url(url):
    """Extract real URL from Google redirect URLs."""
    parsed = urlparse(url)
    if parsed.hostname and 'google' in parsed.hostname:
        params = parse_qs(parsed.query)
        if 'url' in params:
            return params['url'][0]
    return url

def slugify(text):
    """Simple function to make titles safe for filenames."""
    return "".join([c if c.isalnum() else "-" for c in text.lower()]).strip("-")[:50]

def scrape_and_update():
    print(f"[{datetime.now()}] Starting Scrape for 2026 Emissions News...")
    
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
                real_url = resolve_url(entry.link)
                if real_url not in existing_urls and entry.link not in existing_urls:
                    try:
                        # Extract Article
                        article = Article(real_url)
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
                            "source_url": real_url,
                            "source": urlparse(real_url).hostname.replace('www.', ''),
                            "score": score
                        }

                        # 1. SAVE INDIVIDUAL FILE TO /news/ (Local Archiving)
                        filename = f"{slugify(article.title)}.json"
                        file_path = os.path.join(LOCAL_NEWS_DIR, filename)
                        with open(file_path, "w") as f:
                            json.dump(news_item, f, indent=4)

                        # 2. ADD TO MAIN INDEX
                        news_index.insert(0, news_item)
                        existing_urls.add(real_url)
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
        # Check if we're in a git repo
        result = subprocess.run(["git", "rev-parse", "--git-dir"], capture_output=True, cwd=BASE_DIR)
        if result.returncode != 0:
            print(f"Not a git repository at {BASE_DIR}, skipping push.")
            return False

        # Ensure SSH key is used (for cron environments)
        env = os.environ.copy()
        env['GIT_SSH_COMMAND'] = 'ssh -i /home/jeroen/.ssh/id_ed25519 -o StrictHostKeyChecking=no'

        print(f"Git working directory: {BASE_DIR}")

        # Add news files
        subprocess.run(["git", "add", "json/news.json", "news_emissions/"], check=True, cwd=BASE_DIR, env=env)

        # Check if there are changes to commit
        result = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True, cwd=BASE_DIR, env=env)
        if result.returncode == 0:
            print("No changes to commit.")
            return False

        # Commit with timestamp
        commit_msg = f"Auto-update news: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
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
