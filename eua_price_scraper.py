#!/usr/bin/env python3
"""
Fetch current EU ETS carbon price (EUA - EU Allowance) and save to JSON.

Sources tried in order:
1. Trading Economics (primary, matches frontend link)
2. Investing.com
3. Fallback to last known value

Run daily via cron:
0 9 * * * cd /path/to/dirtiestships && python3 eua_price_scraper.py
"""

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent
OUTPUT_FILE = BASE_DIR / "json" / "eua_price.json"
DEFAULT_PRICE = 75.0  # Fallback if all sources fail


def fetch_investing_com():
    """Fetch EUA price from Investing.com - Carbon Emissions page."""
    try:
        url = "https://www.investing.com/commodities/carbon-emissions"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            # Look for the price in data-test attribute
            match = re.search(r'data-test="instrument-price-last">([0-9.,]+)', response.text)
            if match:
                price_str = match.group(1).replace(',', '.')
                price = float(price_str)
                if 20 < price < 200:  # Sanity check
                    print(f"Investing.com: €{price:.2f}")
                    return price
    except Exception as e:
        print(f"Investing.com error: {e}")

    return None


def fetch_trading_economics():
    """Fetch EUA price from Trading Economics."""
    try:
        url = "https://tradingeconomics.com/commodity/carbon"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            # Look for price in the HTML
            match = re.search(r'id="p"[^>]*>([0-9.,]+)', response.text)
            if match:
                price_str = match.group(1).replace(',', '.')
                price = float(price_str)
                if 20 < price < 200:  # Sanity check
                    print(f"Trading Economics: €{price:.2f}")
                    return price
    except Exception as e:
        print(f"Trading Economics error: {e}")

    return None


def fetch_icap():
    """Fetch EUA price from ICAP Carbon Action (backup source)."""
    try:
        # ICAP provides carbon price data
        url = "https://icapcarbonaction.com/en/ets-prices"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            # Look for EU ETS price pattern
            match = re.search(r'EU\s*ETS[^0-9]*([0-9.,]+)\s*(?:EUR|€)', response.text, re.IGNORECASE)
            if match:
                price_str = match.group(1).replace(',', '.')
                price = float(price_str)
                if 20 < price < 200:
                    print(f"ICAP: €{price:.2f}")
                    return price
    except Exception as e:
        print(f"ICAP error: {e}")

    return None


def get_last_known_price():
    """Get the last saved price as fallback."""
    try:
        if OUTPUT_FILE.exists():
            with open(OUTPUT_FILE, "r") as f:
                data = json.load(f)
                return data.get("price", DEFAULT_PRICE)
    except:
        pass
    return DEFAULT_PRICE


def save_price(price, source):
    """Save price to JSON file."""
    data = {
        "price": round(price, 2),
        "currency": "EUR",
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": source
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(data, f, indent=4)

    print(f"Saved: €{price:.2f} from {source}")


def push_to_github():
    """Commit and push price update to GitHub."""
    try:
        # Check if we're in a git repo
        result = subprocess.run(["git", "rev-parse", "--git-dir"], capture_output=True, cwd=BASE_DIR)
        if result.returncode != 0:
            print(f"Not a git repository at {BASE_DIR}, skipping push.")
            return False

        env = os.environ.copy()
        env['GIT_SSH_COMMAND'] = 'ssh -i /home/jeroen/.ssh/id_ed25519 -o StrictHostKeyChecking=no'

        subprocess.run(["git", "add", "json/eua_price.json"], check=True, cwd=BASE_DIR, env=env)

        result = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True, cwd=BASE_DIR, env=env)
        if result.returncode == 0:
            print("No price change to commit.")
            return False

        commit_msg = f"Update EUA price: {datetime.now().strftime('%Y-%m-%d')}"
        subprocess.run(["git", "commit", "-m", commit_msg], check=True, cwd=BASE_DIR, env=env)
        subprocess.run(["git", "push"], check=True, cwd=BASE_DIR, env=env)
        print("Pushed to GitHub.")
        return True

    except subprocess.CalledProcessError as e:
        print(f"Git error: {e}")
        return False


def main():
    print(f"[{datetime.now()}] Fetching EUA price...")

    # Try sources in order of reliability
    price = fetch_trading_economics()
    source = "Trading Economics"

    if price is None:
        price = fetch_investing_com()
        source = "Investing.com"

    if price is None:
        price = fetch_icap()
        source = "ICAP"

    if price is None:
        price = get_last_known_price()
        source = "Last known value"
        print(f"All sources failed, using fallback: €{price:.2f}")

    # Sanity check
    if price < 20 or price > 200:
        print(f"Price €{price:.2f} outside expected range (20-200), using fallback")
        price = get_last_known_price()
        source = "Last known value (sanity check)"

    save_price(price, source)
    push_to_github()


if __name__ == "__main__":
    main()
