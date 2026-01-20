# Dirtiest Ships Website

## Repository
- GitHub: `jeroen41-hash/dirtiestships` (or similar)
- Location: `/media/jeroen/work/16 Claude/dirtiestships website`
- Live site: https://dirtiestships.com (GitHub Pages)

## Overview
A website displaying CO2 emissions rankings for ships calling at EU/EEA ports, based on EU MRV (Monitoring, Reporting and Verification) Regulation data.

## Pages
- `index.html` - Ship Rankings: Paginated table of all ships, searchable by name/IMO, filterable by ship type
- `ship.html` - Individual Ship Profile: Shows ship details and historical emissions chart (accessed via `?imo=XXXXXXX`)
- `chart.html` - By Ship Type: Bar chart showing emissions by vessel category
- `companies.html` - By Company: Top 15 companies by emissions (2024 only)
- `countries.html` - By Country: Top 20 flag states by emissions

## Data Source
- EU MRV Regulation: https://mrv.emsa.europa.eu/
- Raw Excel files in `/data/` folder
- Processed JSON files in `/json/` folder

### Data Files
```
/data/
  2022-v240-...-EU MRV Publication of information.xlsx
  2023-v83-...-EU MRV Publication of information.xlsx
  2024-v160-...-EU MRV Publication of information.xlsx

/json/
  {year}_ships_data.json      - All ships with rankings
  {year}_ships_by_type.json   - Aggregated by ship type
  {year}_countries_top20.json - Top 20 flag states
  2024_companies_top15.json   - Top 15 companies (2024 only)
```

### Data Notes
- 2024 uses `co2eq` (CO2 equivalent including methane etc.)
- 2022/2023 use `co2` (CO2 only)
- Company data only available in 2024 dataset
- Country = flag state (port of registry), not operating region

## Tech Stack
- Static HTML/CSS/JavaScript (no build process)
- Chart.js for bar charts
- Google AdSense: `ca-pub-9641573711172527`
- GitHub Pages hosting

## Design
- Dark theme background: `#1a1a2e` to `#16213e` gradient
- Accent colors: teal `#4ecdc4`, coral `#ff6b6b`
- Header images: grayscale ship smoke photos with gradient masks
- Responsive design with mobile breakpoints

## Features
- Year selector (2022, 2023, 2024)
- Search by ship name or IMO number
- Filter by ship type
- Sortable table columns
- Pagination (50 ships per page)
- Individual ship pages with historical emissions charts
- SEO meta tags (Open Graph, Twitter Cards)

## File Structure
```
/
├── index.html        # Ship rankings
├── ship.html         # Individual ship profile (?imo=XXXXXXX)
├── chart.html        # By ship type
├── companies.html    # By company
├── countries.html    # By country
├── CNAME            # dirtiestships.com
├── .gitignore
├── /data/           # Raw Excel files
├── /json/           # Processed JSON data
├── /images/         # Header images
└── /launch instructins/  # Deployment notes
```
