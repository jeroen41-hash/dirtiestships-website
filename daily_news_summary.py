#!/usr/bin/env python3
"""
Daily news scraper wrapper that runs both scrapers and sends email summary via msmtp.

Setup:
1. Configure msmtp: ~/.msmtprc
2. Set EMAIL_TO below or use environment variable
3. Add to crontab: 0 8 * * * cd /path/to/dirtiestships && /usr/bin/python3 daily_news_summary.py >> /var/log/news_scraper.log 2>&1
"""

import subprocess
import json
import os
from datetime import datetime, date
from pathlib import Path

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).parent
EMAIL_TO = os.environ.get("NEWS_EMAIL_TO", "your-email@example.com")  # Change this!
EMAIL_FROM = os.environ.get("NEWS_EMAIL_FROM", "scraper@dirtiestships.com")

# Repo directories
HYDROGEN_DIR = Path("/media/jeroen/work/16 Claude/hydrogenshipbuilding")

# JSON files produced by scrapers
EMISSIONS_NEWS_FILE = BASE_DIR / "json" / "news.json"
HYDROGEN_NEWS_FILE = HYDROGEN_DIR / "json" / "news_hydrogen.json"

# Scraper scripts
EMISSIONS_SCRAPER = BASE_DIR / "emissions_news_scraper.py"
HYDROGEN_SCRAPER = HYDROGEN_DIR / "hydrogen_news_scraper.py"


def run_scraper(script_path, name):
    """Run a scraper and capture output."""
    print(f"[{datetime.now()}] Running {name}...")
    try:
        result = subprocess.run(
            ["python3", str(script_path)],
            capture_output=True,
            text=True,
            timeout=600,  # 10 min timeout
            cwd=str(BASE_DIR),
            env={**os.environ, "PYTHONUNBUFFERED": "1"}
        )
        output = result.stdout + result.stderr
        success = result.returncode == 0
        print(output)
        return success, output
    except subprocess.TimeoutExpired:
        return False, f"{name} timed out after 10 minutes"
    except Exception as e:
        return False, f"{name} error: {e}"


def get_todays_articles(json_file):
    """Get articles from today."""
    if not json_file.exists():
        return []

    try:
        with open(json_file, "r") as f:
            articles = json.load(f)

        today = date.today().isoformat()
        return [a for a in articles if a.get("date") == today]
    except Exception as e:
        print(f"Error reading {json_file}: {e}")
        return []


def format_article(article):
    """Format a single article for email."""
    title = article.get("title", "No title")
    summary = article.get("summary", "")
    source = article.get("source", "")
    url = article.get("source_url", "")
    score = article.get("score", 0)

    return f"""
  * {title}
    Score: {score} | Source: {source}
    {summary[:200]}{'...' if len(summary) > 200 else ''}
    Link: {url}
"""


def build_email_body(emissions_articles, hydrogen_articles, emissions_output, hydrogen_output):
    """Build the email body."""
    today = date.today().strftime("%A, %B %d, %Y")

    body = f"""Daily News Scraper Summary - {today}
{'=' * 60}

EMISSIONS NEWS (dirtiestships.com)
{'-' * 40}
New articles today: {len(emissions_articles)}
"""

    if emissions_articles:
        for article in emissions_articles[:10]:  # Max 10
            body += format_article(article)
    else:
        body += "\n  No new articles found.\n"

    body += f"""

HYDROGEN NEWS (hydrogenshipbuilding.com)
{'-' * 40}
New articles today: {len(hydrogen_articles)}
"""

    if hydrogen_articles:
        for article in hydrogen_articles[:10]:  # Max 10
            body += format_article(article)
    else:
        body += "\n  No new articles found.\n"

    body += f"""

{'=' * 60}
SCRAPER LOG SUMMARY
{'=' * 60}

Emissions scraper:
{'-' * 20}
{emissions_output[-500:] if len(emissions_output) > 500 else emissions_output}

Hydrogen scraper:
{'-' * 20}
{hydrogen_output[-500:] if len(hydrogen_output) > 500 else hydrogen_output}

---
Sent from headless Debian scraper at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

    return body


def send_email(subject, body):
    """Send email via msmtp."""
    email_content = f"""To: {EMAIL_TO}
From: {EMAIL_FROM}
Subject: {subject}
Content-Type: text/plain; charset=utf-8

{body}
"""

    try:
        process = subprocess.Popen(
            ["msmtp", "-t"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = process.communicate(input=email_content.encode("utf-8"))

        if process.returncode == 0:
            print(f"Email sent successfully to {EMAIL_TO}")
            return True
        else:
            print(f"msmtp error: {stderr.decode()}")
            return False
    except FileNotFoundError:
        print("ERROR: msmtp not installed. Run: sudo apt install msmtp msmtp-mta")
        return False
    except Exception as e:
        print(f"Email error: {e}")
        return False


def main():
    print(f"\n{'=' * 60}")
    print(f"Daily News Summary - {datetime.now()}")
    print(f"{'=' * 60}\n")

    # Run both scrapers
    emissions_success, emissions_output = run_scraper(EMISSIONS_SCRAPER, "Emissions scraper")
    hydrogen_success, hydrogen_output = run_scraper(HYDROGEN_SCRAPER, "Hydrogen scraper")

    # Get today's articles
    emissions_articles = get_todays_articles(EMISSIONS_NEWS_FILE)
    hydrogen_articles = get_todays_articles(HYDROGEN_NEWS_FILE)

    total_new = len(emissions_articles) + len(hydrogen_articles)

    # Build and send email
    subject = f"[News Scraper] {total_new} new articles - {date.today().isoformat()}"
    body = build_email_body(emissions_articles, hydrogen_articles, emissions_output, hydrogen_output)

    send_email(subject, body)

    print(f"\nSummary: {len(emissions_articles)} emissions, {len(hydrogen_articles)} hydrogen articles")


if __name__ == "__main__":
    main()
