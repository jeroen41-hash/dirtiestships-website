#!/usr/bin/env python3
"""
Boox Note Air → AI Handwriting Recognition → Email

Monitors a sync folder for handwritten note exports (PDF/PNG) from a Boox Note Air,
converts them to text using Claude's vision API, and emails the results at end of day.

Setup:
1. On your Boox Note Air, export notes as PDF (Menu → Share → Export as PDF)
2. Sync exported PDFs to a local folder using one of:
   - Dropbox / Google Drive / OneDrive (install on Boox via Play Store)
   - Syncthing (recommended for self-hosted)
   - Boox built-in Push / cloud
   - SMB share on local network
3. Install dependencies: pip install anthropic pymupdf Pillow
4. Configure msmtp for email (same as daily_news_summary.py):
   - sudo apt install msmtp msmtp-mta
   - Configure ~/.msmtprc with your SMTP credentials
5. Set environment variables (or edit config below):
   - ANTHROPIC_API_KEY: Your Anthropic API key
   - BOOX_NOTES_DIR: Folder where Boox syncs note exports
   - BOOX_EMAIL_TO: Your email address
6. Add to crontab for end-of-day delivery:
   0 18 * * * cd /path/to/dirtiestships && python3 boox_notes_to_email.py >> /var/log/boox_notes.log 2>&1
"""

import os
import sys
import json
import base64
import subprocess
import hashlib
from datetime import datetime, date
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("ERROR: 'anthropic' package not installed. Run: pip install anthropic")
    sys.exit(1)

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None
    print("WARNING: 'pymupdf' not installed. PDF support disabled. Run: pip install pymupdf")

try:
    from PIL import Image
except ImportError:
    Image = None
    print("WARNING: 'Pillow' not installed. Image optimization disabled. Run: pip install Pillow")


# --- CONFIGURATION ---
BASE_DIR = Path(__file__).parent
NOTES_DIR = Path(os.environ.get("BOOX_NOTES_DIR", str(BASE_DIR / "boox_notes")))
EMAIL_TO = os.environ.get("BOOX_EMAIL_TO", os.environ.get("NEWS_EMAIL_TO", "your-email@example.com"))
EMAIL_FROM = os.environ.get("BOOX_EMAIL_FROM", "boox-notes@dirtiestships.com")
PROCESSED_LOG = BASE_DIR / "boox_processed.json"

# AI settings
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-20250514"
MAX_PAGES_PER_PDF = 20
IMAGE_MAX_WIDTH = 1568  # Claude vision recommended max

# Supported file extensions
SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif"}


def load_processed_log():
    """Load the log of already-processed files (hash → date)."""
    if PROCESSED_LOG.exists():
        try:
            with open(PROCESSED_LOG, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_processed_log(log):
    """Save the processed files log."""
    with open(PROCESSED_LOG, "w") as f:
        json.dump(log, f, indent=2)


def file_hash(filepath):
    """Get SHA-256 hash of a file to detect changes."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def find_new_notes(notes_dir, processed_log):
    """Find note files that haven't been processed yet."""
    new_files = []
    if not notes_dir.exists():
        print(f"Notes directory does not exist: {notes_dir}")
        return new_files

    for filepath in sorted(notes_dir.rglob("*")):
        if filepath.is_file() and filepath.suffix.lower() in SUPPORTED_EXTENSIONS:
            fhash = file_hash(filepath)
            if fhash not in processed_log:
                new_files.append((filepath, fhash))

    return new_files


def pdf_to_images(pdf_path, max_pages=MAX_PAGES_PER_PDF):
    """Convert PDF pages to PNG images (in memory) using PyMuPDF."""
    if fitz is None:
        print(f"  Skipping PDF {pdf_path.name}: pymupdf not installed")
        return []

    images = []
    doc = fitz.open(str(pdf_path))
    page_count = min(len(doc), max_pages)

    for page_num in range(page_count):
        page = doc[page_num]
        # Render at 200 DPI for good OCR quality
        mat = fitz.Matrix(200 / 72, 200 / 72)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        images.append({
            "data": base64.standard_b64encode(img_bytes).decode("utf-8"),
            "media_type": "image/png",
            "page": page_num + 1,
        })

    doc.close()
    return images


def load_image(image_path):
    """Load an image file and return base64 data."""
    suffix = image_path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".bmp": "image/png",  # will convert
        ".tiff": "image/png",  # will convert
        ".tif": "image/png",  # will convert
    }
    media_type = media_types.get(suffix, "image/png")

    # Convert non-standard formats to PNG, and optionally resize
    if Image and suffix in {".bmp", ".tiff", ".tif"}:
        img = Image.open(image_path)
        if img.width > IMAGE_MAX_WIDTH:
            ratio = IMAGE_MAX_WIDTH / img.width
            img = img.resize((IMAGE_MAX_WIDTH, int(img.height * ratio)), Image.LANCZOS)
        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        img_bytes = buf.getvalue()
    else:
        img_bytes = image_path.read_bytes()

    return [{
        "data": base64.standard_b64encode(img_bytes).decode("utf-8"),
        "media_type": media_type,
        "page": 1,
    }]


def recognize_handwriting(images, filename):
    """Send images to Claude Vision API for handwriting recognition."""
    if not ANTHROPIC_API_KEY:
        return f"[ERROR: ANTHROPIC_API_KEY not set - cannot process {filename}]"

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Build content blocks: images + prompt
    content = []
    for img in images:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": img["media_type"],
                "data": img["data"],
            }
        })

    page_info = f" ({len(images)} pages)" if len(images) > 1 else ""
    content.append({
        "type": "text",
        "text": (
            f"This is a scan of handwritten notes from a Boox Note Air e-reader{page_info}. "
            "Please transcribe ALL the handwritten text you can see, preserving the original "
            "structure as much as possible (headings, bullet points, numbered lists, paragraphs). "
            "If there are diagrams or drawings, briefly describe them in [brackets]. "
            "If any text is unclear, make your best guess and mark it with [?]. "
            "Output only the transcribed text, no commentary."
        )
    })

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": content}]
        )
        return response.content[0].text
    except anthropic.APIError as e:
        return f"[API ERROR processing {filename}: {e}]"
    except Exception as e:
        return f"[ERROR processing {filename}: {e}]"


def process_note(filepath):
    """Process a single note file: convert to images, run OCR."""
    print(f"  Processing: {filepath.name}")
    suffix = filepath.suffix.lower()

    if suffix == ".pdf":
        images = pdf_to_images(filepath)
    else:
        images = load_image(filepath)

    if not images:
        return f"[Could not extract images from {filepath.name}]"

    print(f"    → {len(images)} image(s), sending to Claude for recognition...")
    text = recognize_handwriting(images, filepath.name)
    print(f"    → Got {len(text)} characters of text")
    return text


def build_email_body(results):
    """Build the email body from all processed notes."""
    today_str = date.today().strftime("%A, %B %d, %Y")

    body = f"""Boox Notes Summary - {today_str}
{'=' * 60}

{len(results)} note(s) processed today.
"""

    for i, (filename, text) in enumerate(results, 1):
        body += f"""
{'─' * 60}
📄 Note {i}: {filename}
{'─' * 60}

{text}
"""

    body += f"""

{'=' * 60}
Processed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Powered by Claude Vision API
"""
    return body


def send_email(subject, body):
    """Send email via msmtp (same method as daily_news_summary.py)."""
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
    print(f"Boox Notes Processor - {datetime.now()}")
    print(f"Notes directory: {NOTES_DIR}")
    print(f"{'=' * 60}\n")

    # Ensure notes directory exists
    if not NOTES_DIR.exists():
        NOTES_DIR.mkdir(parents=True, exist_ok=True)
        print(f"Created notes directory: {NOTES_DIR}")
        print("Place your Boox note exports (PDF/PNG) here, or configure sync.")
        return

    # Find new/unprocessed notes
    processed_log = load_processed_log()
    new_notes = find_new_notes(NOTES_DIR, processed_log)

    if not new_notes:
        print("No new notes to process.")
        return

    print(f"Found {len(new_notes)} new note(s) to process.\n")

    # Process each note
    results = []
    for filepath, fhash in new_notes:
        text = process_note(filepath)
        results.append((filepath.name, text))
        # Mark as processed
        processed_log[fhash] = {
            "file": str(filepath),
            "processed_at": datetime.now().isoformat(),
        }

    # Save processed log
    save_processed_log(processed_log)

    # Build and send email
    subject = f"[Boox Notes] {len(results)} note(s) - {date.today().isoformat()}"
    body = build_email_body(results)

    # Print to stdout as well
    print(f"\n{'=' * 60}")
    print("EMAIL PREVIEW:")
    print(f"{'=' * 60}")
    print(body)

    if EMAIL_TO == "your-email@example.com":
        print("\nWARNING: Email not sent - configure BOOX_EMAIL_TO or NEWS_EMAIL_TO")
        print("Set via: export BOOX_EMAIL_TO=you@example.com")
    else:
        send_email(subject, body)

    print(f"\nDone. Processed {len(results)} note(s).")


if __name__ == "__main__":
    main()
