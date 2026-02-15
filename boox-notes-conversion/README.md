# boox-notes-conversion

Convert handwritten notes from a **Boox Note Air** to text using AI vision, then email a daily digest.

## How it works

1. **Export** notes on your Boox as PDF (Menu → Share → Export as PDF)
2. **Sync** the PDFs to a folder on your computer (Dropbox, Syncthing, SMB, etc.)
3. **Run** this tool — it sends page images to Claude's vision API for handwriting recognition
4. **Email** — get a compiled digest of all your notes at end of day

## Install

```bash
pip install -e .
```

## Usage

```bash
# Set your API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Convert a single note
boox-notes convert my_note.pdf

# Convert and save to file
boox-notes convert my_note.pdf -o my_note.txt

# Process all new notes in a folder + email
boox-notes run --notes-dir ./notes --email you@example.com

# Check what's pending
boox-notes status --notes-dir ./notes
```

## Daily cron

```bash
# Add to crontab (sends email at 6 PM daily)
0 18 * * * cd /path/to/boox-notes-conversion && boox-notes run --notes-dir /path/to/synced/notes --email you@example.com >> /var/log/boox.log 2>&1
```

Requires `msmtp` for email: `sudo apt install msmtp msmtp-mta`

## Boox sync options

| Method | Setup | Notes |
|--------|-------|-------|
| **Dropbox** | Install via Play Store on Boox | Easiest, auto-sync |
| **Syncthing** | Install on both devices | Self-hosted, no cloud |
| **Google Drive** | Install via Play Store | Works well |
| **SMB share** | Boox Settings → Storage | Local network only |

## OpenAI fallback

```bash
pip install -e ".[openai]"
export OPENAI_API_KEY="sk-..."
boox-notes --provider openai convert my_note.pdf
```

## Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```
