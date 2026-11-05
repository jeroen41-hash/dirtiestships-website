#!/usr/bin/env python3
"""
Generate one static HTML page per shipping company under companies/<slug>.html.

Each page is a byte-for-byte copy of company.html's working template (same CSS,
nav, footer, and rendering JS), except:
  - <title>, meta description, canonical, and Open Graph/Twitter tags are
    baked in with the real company name and real aggregate numbers, so search
    engines and social-preview crawlers (which don't execute JS) see correct,
    unique metadata instead of company.html's generic placeholder.
  - getCompanyFromURL() falls back to the company's real name when no ?name=
    query param is present, so the existing fetch/render logic works unchanged.

Also writes json/company_slugs.json, a {company name: slug} map consumed by
companies.html and charts.html to link directly to the static pages.

Re-run this whenever the ships dataset is refreshed (same cadence as
convert_excel_to_json.py / calculate_cii_ratings.py).
"""
import json
import os
import re
import html
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
SHIPS_FILE = os.path.join(BASE, "json", "2025_ships_data.json")
TEMPLATE_FILE = os.path.join(BASE, "company.html")
OUT_DIR = os.path.join(BASE, "companies")
SLUG_MAP_FILE = os.path.join(BASE, "json", "company_slugs.json")
SITE = "https://dirtiestships.com"

# companies.html/charts.html display these conglomerates under a parent label
# (see COMPANY_GROUPS in convert_excel_to_json.py, grouped by company IMO).
# That parent label never appears as a raw ship.company value, so company.html's
# own filter (s.company === companyName) already returns "No ships found" for
# these on the live site - a pre-existing bug, not introduced here. Member name
# strings below were extracted directly from the source MRV Excel file by
# cross-referencing each group's company IMO numbers; fix this list by re-running
# that extraction (see git history for the one-off script) if COMPANY_GROUPS in
# convert_excel_to_json.py changes.
COMPANY_GROUPS = {
    "MSC Group": [
        "MEDITERRANEAN SHIPPING CO SRL",
        "MSC Cruise Management UK Ltd",
        "MSC SHIPMANAGEMENT LIMITED",
        "MSC Shipmanagement Ltd",
    ],
    "Maersk": ["Maersk A/S", "Maersk Line, Limited-USA"],
    "CMA CGM Group": [
        "CMA CGM ASIA SHIPPING PTE LTD",
        "CMA CGM INTERNATIONAL SHIPPING COMPANY PTE LTD",
        "CMA CGM SA",
        "CMA SHIPS GERMANY GMBH",
        "CMA SHIPS SAS",
    ],
    "Carnival Corporation": [
        "Carnival Corp",
        "Carnival Plc",
        "Costa Crociere S.p.A.",
        "Holland America Line Limited",
        "Princess Cruise Lines Ltd",
    ],
    "Evergreen Marine": [
        "EVERGREEN MARINE CORP. (TAIWAN) LTD",
        "EVERGREEN SHIPPING HOLDINGS LTD",
    ],
}


def slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    s = s[:80].rstrip("-")
    return s or "company"


def build_slugs(names: list[str]) -> dict[str, str]:
    counts: dict[str, int] = {}
    slugs: dict[str, str] = {}
    for name in sorted(names):
        base = slugify(name)
        n = counts.get(base, 0)
        slug = base if n == 0 else f"{base}-{n + 1}"
        counts[base] = n + 1
        slugs[name] = slug
    return slugs


def js_string(value: str) -> str:
    """Safe double-quoted JS/JSON string literal for embedding in a <script>."""
    return json.dumps(value)


def main() -> None:
    with open(SHIPS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    ships = data.get("ships", data)

    agg: dict[str, dict] = defaultdict(lambda: {"count": 0, "co2eq": 0.0})
    for s in ships:
        name = (s.get("company") or "").strip()
        if not name:
            continue
        a = agg[name]
        a["count"] += 1
        a["co2eq"] += s.get("co2eq") or 0.0

    # Aggregate each known group from its member raw names, same arithmetic as
    # convert_excel_to_json.py's company-IMO grouping, just keyed by name here.
    group_agg: dict[str, dict] = {}
    for group, members in COMPANY_GROUPS.items():
        g = {"count": 0, "co2eq": 0.0}
        for member in members:
            if member in agg:
                g["count"] += agg[member]["count"]
                g["co2eq"] += agg[member]["co2eq"]
        group_agg[group] = g

    names = list(agg.keys()) + list(COMPANY_GROUPS.keys())
    slugs = build_slugs(names)

    with open(SLUG_MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(slugs, f, ensure_ascii=False, separators=(",", ":"))

    with open(TEMPLATE_FILE, encoding="utf-8") as f:
        template = f.read()

    # Pages live one directory down (companies/<slug>.html), so every relative
    # URL in the template (css/, images/, json/ fetches, nav hrefs) would
    # otherwise resolve against companies/ instead of the site root. A <base>
    # tag fixes all of them at once without rewriting each reference.
    old_doctype_head = "<head>\n    <!-- Google tag (gtag.js) -->\n"
    assert old_doctype_head in template, "company.html <head> opening changed - update old_doctype_head"
    new_doctype_head = f'<head>\n    <base href="{SITE}/">\n    <!-- Google tag (gtag.js) -->\n'
    template = template.replace(old_doctype_head, new_doctype_head, 1)

    old_head = (
        '    <meta name="description" content="View CO2 emissions data for this shipping company. '
        'See all ships and total emissions from EU MRV data.">\n'
        '    <meta name="robots" content="index, follow">\n'
        '    <link rel="canonical" href="https://dirtiestships.com/company.html">\n'
        "\n"
        "    <!-- Open Graph / Facebook -->\n"
        '    <meta property="og:type" content="website">\n'
        '    <meta property="og:site_name" content="Dirtiest Ships">\n'
        "\n"
        "    <!-- Twitter -->\n"
        '    <meta name="twitter:card" content="summary_large_image">\n'
        "\n"
        '    <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-9641573711172527"\n'
        '     crossorigin="anonymous"></script>\n'
        "    <title>Company Details - Dirtiest Ships</title>\n"
    )
    assert old_head in template, "company.html head block changed - update the generator's old_head string"

    old_js = (
        "        function getCompanyFromURL() {\n"
        "            const params = new URLSearchParams(window.location.search);\n"
        "            return params.get('name');\n"
        "        }\n"
    )
    assert old_js in template, "company.html getCompanyFromURL() changed - update the generator's old_js string"

    old_filter = "                        .filter(s => s.company === companyName)\n"
    assert old_filter in template, "company.html ship filter line changed - update the generator's old_filter string"

    old_load_fn = "        function loadCompanyData() {\n"
    assert old_load_fn in template, "company.html loadCompanyData() changed - update the generator's old_load_fn string"

    os.makedirs(OUT_DIR, exist_ok=True)

    for name, slug in slugs.items():
        is_group = name in COMPANY_GROUPS
        a = group_agg[name] if is_group else agg[name]
        co2_m = a["co2eq"] / 1_000_000
        count = a["count"]
        description = html.escape(
            f"CO2 emissions for {name}: {count} ship{'s' if count != 1 else ''} totaling "
            f"{co2_m:.2f} million tonnes CO2-eq, based on EU MRV data.",
            quote=True,
        )
        canonical = f"{SITE}/companies/{slug}.html"
        title = html.escape(f"{name} - CO2 Emissions | Dirtiest Ships", quote=True)
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
            "\n"
            "    <!-- Twitter -->\n"
            '    <meta name="twitter:card" content="summary_large_image">\n'
            f'    <meta name="twitter:url" content="{canonical}">\n'
            f'    <meta name="twitter:title" content="{og_title}">\n'
            f'    <meta name="twitter:description" content="{description}">\n'
            "\n"
            '    <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-9641573711172527"\n'
            '     crossorigin="anonymous"></script>\n'
            f"    <title>{title}</title>\n"
        )

        new_js = (
            "        function getCompanyFromURL() {\n"
            "            const params = new URLSearchParams(window.location.search);\n"
            f"            return params.get('name') || {js_string(name)};\n"
            "        }\n"
        )

        page = template.replace(old_head, new_head, 1).replace(old_js, new_js, 1)

        if is_group:
            members_js = json.dumps(COMPANY_GROUPS[name])
            page = page.replace(old_filter, "                        .filter(s => companyMembers.includes(s.company))\n", 1)
            page = page.replace(
                old_load_fn,
                f"        const companyMembers = {members_js};\n\n{old_load_fn}",
                1,
            )

        out_path = os.path.join(OUT_DIR, f"{slug}.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(page)

    print(f"Generated {len(slugs)} company pages in {OUT_DIR}/")
    print(f"Wrote slug map: {SLUG_MAP_FILE}")


if __name__ == "__main__":
    main()
