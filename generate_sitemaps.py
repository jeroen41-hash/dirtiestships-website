#!/usr/bin/env python3
"""
Generate sitemap-companies.xml and sitemap-ships.xml from the slug maps
written by generate_company_pages.py / generate_ship_pages.py, and keep
sitemap.xml as a sitemap index pointing at them plus the hand-curated
sitemap-pages.xml (the original cornerstone/supporting/low-value list).

robots.txt already points at sitemap.xml, which search engines are fine
reading as an index rather than a flat urlset, so no robots.txt change
is needed.

Re-run this whenever generate_company_pages.py / generate_ship_pages.py
are re-run, so the sitemaps stay in sync with the slug maps.
"""
import json
import os
from datetime import date

BASE = os.path.dirname(os.path.abspath(__file__))
SITE = "https://dirtiestships.com"
TODAY = date.today().isoformat()

COMPANY_SLUGS_FILE = os.path.join(BASE, "json", "company_slugs.json")
SHIP_SLUGS_FILE = os.path.join(BASE, "json", "ship_slugs.json")


def write_urlset(path: str, locs: list[str], priority: str, changefreq: str) -> None:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc in locs:
        lines.append("  <url>")
        lines.append(f"    <loc>{loc}</loc>")
        lines.append(f"    <lastmod>{TODAY}</lastmod>")
        lines.append(f"    <changefreq>{changefreq}</changefreq>")
        lines.append(f"    <priority>{priority}</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")
    lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_index(path: str, sitemap_files: list[str]) -> None:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for fn in sitemap_files:
        lines.append("  <sitemap>")
        lines.append(f"    <loc>{SITE}/{fn}</loc>")
        lines.append(f"    <lastmod>{TODAY}</lastmod>")
        lines.append("  </sitemap>")
    lines.append("</sitemapindex>")
    lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> None:
    with open(COMPANY_SLUGS_FILE, encoding="utf-8") as f:
        company_slugs = json.load(f)
    with open(SHIP_SLUGS_FILE, encoding="utf-8") as f:
        ship_slugs = json.load(f)

    company_locs = sorted(f"{SITE}/companies/{slug}.html" for slug in company_slugs.values())
    ship_locs = sorted(f"{SITE}/ships/{slug}.html" for slug in ship_slugs.values())

    write_urlset(os.path.join(BASE, "sitemap-companies.xml"), company_locs, "0.5", "monthly")
    write_urlset(os.path.join(BASE, "sitemap-ships.xml"), ship_locs, "0.4", "monthly")
    write_index(os.path.join(BASE, "sitemap.xml"),
                ["sitemap-pages.xml", "sitemap-companies.xml", "sitemap-ships.xml"])

    print(f"Wrote sitemap-companies.xml ({len(company_locs)} URLs)")
    print(f"Wrote sitemap-ships.xml ({len(ship_locs)} URLs)")
    print("Wrote sitemap.xml (index)")


if __name__ == "__main__":
    main()
