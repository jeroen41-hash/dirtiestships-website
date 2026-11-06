#!/usr/bin/env python3
"""
Generate one static HTML page per ship under ships/<slug>.html.

Same approach as generate_company_pages.py: each page is a byte-for-byte
copy of ship.html's working template (same CSS, nav, footer, and rendering
JS), except:
  - <title>, meta description, canonical, and Open Graph/Twitter tags are
    baked in with the real ship name/IMO/type/flag, so search engines and
    social-preview crawlers (which don't execute JS) see correct, unique
    metadata instead of ship.html's generic placeholder.
  - getIMOFromURL() falls back to the ship's real IMO when no ?id= query
    param is present, so the existing fetch/render logic works unchanged.

Covers every IMO that has ever appeared in any yearly ships file (2020-2025),
not just json/ship/*.json (vessel-spec scraping didn't cover every IMO, but
ship.html itself only needs yearly emissions data to render, so every IMO
in those files is a real, indexable page on the live site today).

Also writes json/ship_slugs.json, a {imo: slug} map consumed by index.html,
company.html, compare.html, cii.html, and ship.html itself to link directly
to the static pages.

Re-run this whenever the ships dataset is refreshed (same cadence as
convert_excel_to_json.py / calculate_cii_ratings.py).
"""
import json
import os
import re
import html

BASE = os.path.dirname(os.path.abspath(__file__))
YEARS = ["2025", "2024", "2023", "2022", "2021", "2020"]
TEMPLATE_FILE = os.path.join(BASE, "ship.html")
OUT_DIR = os.path.join(BASE, "ships")
SLUG_MAP_FILE = os.path.join(BASE, "json", "ship_slugs.json")
SITE = "https://dirtiestships.com"


def slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    s = s[:60].rstrip("-")
    return s or "ship"


def js_string(value: str) -> str:
    return json.dumps(value)


def main() -> None:
    # by_year[year][imo] = ship dict, so we can pick the latest year with
    # data for each IMO, exactly like ship.html's own latestYear logic.
    by_year = {}
    for year in YEARS:
        with open(os.path.join(BASE, "json", f"{year}_ships_data.json"), encoding="utf-8") as f:
            data = json.load(f)
        ships = data.get("ships", data)
        by_year[year] = {s["imo"]: s for s in ships if s.get("imo")}

    all_imos = set()
    for year in YEARS:
        all_imos.update(by_year[year].keys())

    # Pick each ship's latest-year record for meta purposes, same order
    # ship.html uses: shipData['2025'] ? '2025' : (shipData['2024'] ? ... )
    latest = {}
    for imo in all_imos:
        for year in YEARS:
            ship = by_year[year].get(imo)
            if ship:
                latest[imo] = ship
                break

    slugs: dict[str, str] = {}
    seen_slugs: dict[str, int] = {}
    for imo in sorted(all_imos):
        ship = latest[imo]
        name = (ship.get("name") or "ship").strip()
        base = f"{slugify(name)}-{imo}"
        n = seen_slugs.get(base, 0)
        slug = base if n == 0 else f"{base}-{n + 1}"
        seen_slugs[base] = n + 1
        slugs[imo] = slug

    with open(SLUG_MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(slugs, f, ensure_ascii=False, separators=(",", ":"))

    with open(TEMPLATE_FILE, encoding="utf-8") as f:
        template = f.read()

    # Pages live one directory down (ships/<slug>.html), so every relative
    # URL in the template (css/, images/, json/ fetches, nav hrefs) would
    # otherwise resolve against ships/ instead of the site root. A <base>
    # tag fixes all of them at once without rewriting each reference.
    old_doctype_head = "<head>\n    <!-- Google tag (gtag.js) -->\n"
    assert old_doctype_head in template, "ship.html <head> opening changed - update old_doctype_head"
    new_doctype_head = f'<head>\n    <base href="{SITE}/">\n    <!-- Google tag (gtag.js) -->\n'
    template = template.replace(old_doctype_head, new_doctype_head, 1)

    old_head = (
        '    <meta name="description" content="View CO2 emissions data and historical trends for this ship. '
        'Track annual emissions from EU MRV data.">\n'
        '    <meta name="robots" content="index, follow">\n'
        '    <link rel="canonical" href="https://dirtiestships.com/ship.html">\n'
        "\n"
        "    <!-- Open Graph / Facebook -->\n"
        '    <meta property="og:type" content="website">\n'
        '    <meta property="og:site_name" content="Dirtiest Ships">\n'
        '    <meta property="og:image" content="https://dirtiestships.com/images/og-image.png">\n'
        '    <meta property="og:image:width" content="1200">\n'
        '    <meta property="og:image:height" content="630">\n'
        "\n"
        "    <!-- Twitter -->\n"
        '    <meta name="twitter:card" content="summary_large_image">\n'
        '    <meta name="twitter:image" content="https://dirtiestships.com/images/og-image.png">\n'
        "\n"
        '    <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-9641573711172527"\n'
        '     crossorigin="anonymous"></script>\n'
        "    <title>Ship Details - Dirtiest Ships</title>\n"
    )
    assert old_head in template, "ship.html head block changed - update the generator's old_head string"

    old_js = (
        "        function getIMOFromURL() {\n"
        "            const params = new URLSearchParams(window.location.search);\n"
        "            const encoded = params.get('id');\n"
        "            return encoded ? decodeId(encoded) : null;\n"
        "        }\n"
    )
    assert old_js in template, "ship.html getIMOFromURL() changed - update the generator's old_js string"

    os.makedirs(OUT_DIR, exist_ok=True)

    for imo, slug in slugs.items():
        ship = latest[imo]
        name = ship.get("name") or "Unknown Ship"
        ship_type = ship.get("type") or "Ship"
        flag = ship.get("country") or ship.get("registry") or "unknown flag"

        description = html.escape(
            f"View CO2 emissions data for {name} (IMO: {imo}). {ship_type} registered in {flag}.",
            quote=True,
        )
        canonical = f"{SITE}/ships/{slug}.html"
        title = html.escape(f"{name} - CO2 Emissions - Dirtiest Ships", quote=True)
        og_title = html.escape(f"{name} - CO2 Emissions", quote=True)

        new_head = (
            f'    <meta name="description" content="{description}">\n'
            '    <meta name="robots" content="index, follow">\n'
            f'    <link rel="canonical" href="{canonical}">\n'
            "\n"
            "    <!-- Open Graph / Facebook -->\n"
            '    <meta property="og:type" content="website">\n'
            f'    <meta property="og:url" content="{canonical}">\n'
            f'    <meta property="og:title" content="{og_title}">\n'
            f'    <meta property="og:description" content="{description}">\n'
            '    <meta property="og:site_name" content="Dirtiest Ships">\n'
            '    <meta property="og:image" content="https://dirtiestships.com/images/og-image.png">\n'
            '    <meta property="og:image:width" content="1200">\n'
            '    <meta property="og:image:height" content="630">\n'
            "\n"
            "    <!-- Twitter -->\n"
            '    <meta name="twitter:card" content="summary_large_image">\n'
            f'    <meta name="twitter:url" content="{canonical}">\n'
            f'    <meta name="twitter:title" content="{og_title}">\n'
            f'    <meta name="twitter:description" content="{description}">\n'
            '    <meta name="twitter:image" content="https://dirtiestships.com/images/og-image.png">\n'
            "\n"
            '    <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-9641573711172527"\n'
            '     crossorigin="anonymous"></script>\n'
            f"    <title>{title}</title>\n"
        )

        new_js = (
            "        function getIMOFromURL() {\n"
            "            const params = new URLSearchParams(window.location.search);\n"
            "            const encoded = params.get('id');\n"
            f"            return encoded ? decodeId(encoded) : {js_string(imo)};\n"
            "        }\n"
        )

        page = template.replace(old_head, new_head, 1).replace(old_js, new_js, 1)

        out_path = os.path.join(OUT_DIR, f"{slug}.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(page)

    print(f"Generated {len(slugs)} ship pages in {OUT_DIR}/")
    print(f"Wrote slug map: {SLUG_MAP_FILE}")


if __name__ == "__main__":
    main()
