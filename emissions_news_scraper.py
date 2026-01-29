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

# --- CONFIGURATION ---
FEEDS = [
    "https://www.offshore-energy.biz/feed/",
    "https://www.hellenicshippingnews.com/feed/",
    "https://www.rivieramm.com/rss/news-content-hub",
    "https://shipandbunker.com/news/feed",
    "https://www.google.nl/alerts/feeds/11361701321732954749/806710994395188837"
]
KEYWORDS = ["EU-ETS", "CO2", "greenhouse gas", "CO2", "emissions", "fueleu", "MRV", "thesis"]

# LOCAL DIRECTORIES
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NEWS_INDEX_FILE = os.path.join(BASE_DIR, "json", "news.json")
LOCAL_NEWS_DIR = os.path.join(BASE_DIR, "news_emissions")

# Create /news/ folder if it doesn't exist
if not os.path.exists(LOCAL_NEWS_DIR):
    os.makedirs(LOCAL_NEWS_DIR)

def slugify(text):
    """Simple function to make titles safe for filenames."""
    return "".join([c if c.isalnum() else "-" for c in text.lower()]).strip("-")[:50]

def scrape_and_update():
    print(f"[{datetime.now()}] Starting Scrape for 2026 Maritime News...")
    
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

                        # Data Object
                        news_item = {
                            "id": int(time.time()),
                            "date": datetime.now().strftime("%Y-%m-%d"),
                            "title": article.title,
                            "summary": (article.text[:200] + "...") if article.text else "",
                            "content": article.text,
                            "source_url": entry.link,
                            "source": feed_url.split('/')[2].replace('www.', '')
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
                        
                        print(f"Archived: {filename}")
                        time.sleep(1) # Be kind to servers
                    except Exception as e:
                        print(f"Error processing {entry.link}: {e}")

    # Save updated index (Keep latest 50 for the website)
    if new_count > 0:
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
        os.chdir(BASE_DIR)

        # Ensure SSH key is used (for cron environments)
        os.environ['GIT_SSH_COMMAND'] = 'ssh -i /home/jeroen/.ssh/id_ed25519 -o StrictHostKeyChecking=no'

        # Add news files
        subprocess.run(["git", "add", "json/news.json", "news_emissions/"], check=True)

        # Check if there are changes to commit
        result = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True)
        if result.returncode == 0:
            print("No changes to commit.")
            return False

        # Commit with timestamp
        commit_msg = f"Auto-update news: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        subprocess.run(["git", "commit", "-m", commit_msg], check=True)

        # Push to remote
        subprocess.run(["git", "push"], check=True)
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
