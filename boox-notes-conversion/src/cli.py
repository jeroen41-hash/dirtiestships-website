"""
CLI entrypoint for boox-notes-conversion.

Usage:
    # Convert all new notes and email digest
    python -m src.cli run --notes-dir ./notes --email you@example.com

    # Convert a single file (print to stdout)
    python -m src.cli convert note.pdf

    # Convert a single file and save to text
    python -m src.cli convert note.pdf -o note.txt

    # List unprocessed files
    python -m src.cli status --notes-dir ./notes

    # Run as daily cron (end-of-day email)
    0 18 * * * cd /path/to/boox-notes-conversion && python -m src.cli run >> /var/log/boox.log 2>&1
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from .extract import extract
from .convert import Converter, ConversionResult
from .tracker import ProcessedTracker
from .email_sender import send_digest, build_digest


def cmd_convert(args):
    """Convert a single file and print/save the result."""
    filepath = Path(args.file)
    if not filepath.exists():
        print(f"Error: {filepath} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Extracting pages from {filepath.name}...", file=sys.stderr)
    pages = extract(filepath)
    print(f"  {len(pages)} page(s) extracted", file=sys.stderr)

    print(f"Converting with {args.provider} ({args.model or 'default'})...", file=sys.stderr)
    converter = Converter(provider=args.provider, model=args.model)
    result = converter.convert_pages(pages)

    if result.error:
        print(f"Error: {result.error}", file=sys.stderr)
        sys.exit(1)

    # Output text
    if args.output:
        Path(args.output).write_text(result.text, encoding="utf-8")
        print(f"Saved to {args.output}", file=sys.stderr)
    else:
        print(result.text)

    if result.token_usage:
        tokens_in = result.token_usage.get("input_tokens", 0)
        tokens_out = result.token_usage.get("output_tokens", 0)
        print(f"\nTokens: {tokens_in:,} in, {tokens_out:,} out", file=sys.stderr)


def cmd_run(args):
    """Process all new notes and optionally send email digest."""
    notes_dir = Path(args.notes_dir)
    print(f"\n{'=' * 60}")
    print(f"Boox Notes Processor - {datetime.now()}")
    print(f"Notes directory: {notes_dir}")
    print(f"{'=' * 60}\n")

    if not notes_dir.exists():
        notes_dir.mkdir(parents=True, exist_ok=True)
        print(f"Created {notes_dir} — place Boox exports here.")
        return

    tracker = ProcessedTracker(db_path=Path(args.db))
    new_files = tracker.find_new_files(notes_dir)

    if not new_files:
        print("No new notes to process.")
        return

    print(f"Found {len(new_files)} new note(s).\n")

    converter = Converter(provider=args.provider, model=args.model)
    results: list[ConversionResult] = []

    for filepath in new_files:
        print(f"Processing: {filepath.name}")
        pages = extract(filepath)
        print(f"  {len(pages)} page(s), sending to {args.provider}...")

        result = converter.convert_pages(pages)
        results.append(result)

        if result.error:
            print(f"  ERROR: {result.error}")
        else:
            print(f"  OK — {len(result.text)} chars")
            tracker.mark_processed(filepath, result.text)

    # Print digest
    body = build_digest(results)
    print(f"\n{'=' * 60}\n{body}")

    # Send email if configured
    if args.email:
        send_digest(results, to=args.email)
    else:
        print("Tip: add --email you@example.com to send as email")


def cmd_status(args):
    """Show status of notes directory."""
    notes_dir = Path(args.notes_dir)
    tracker = ProcessedTracker(db_path=Path(args.db))

    if not notes_dir.exists():
        print(f"Notes directory {notes_dir} does not exist.")
        return

    new_files = tracker.find_new_files(notes_dir)
    print(f"Notes directory: {notes_dir}")
    print(f"Total processed: {tracker.total_processed}")
    print(f"New/unprocessed: {len(new_files)}")

    if new_files:
        print("\nUnprocessed files:")
        for f in new_files:
            size_kb = f.stat().st_size / 1024
            print(f"  {f.name} ({size_kb:.0f} KB)")


def main():
    parser = argparse.ArgumentParser(
        prog="boox-notes",
        description="Convert Boox Note Air handwriting to text and email daily digest",
    )
    parser.add_argument(
        "--provider", choices=["anthropic", "openai"], default="anthropic",
        help="AI provider for handwriting recognition (default: anthropic)",
    )
    parser.add_argument("--model", help="Model name override")

    sub = parser.add_subparsers(dest="command", required=True)

    # convert: single file
    p_convert = sub.add_parser("convert", help="Convert a single note file")
    p_convert.add_argument("file", help="Path to PDF/PNG/JPG note file")
    p_convert.add_argument("-o", "--output", help="Save text to file instead of stdout")

    # run: batch process + email
    p_run = sub.add_parser("run", help="Process all new notes and send email digest")
    p_run.add_argument("--notes-dir", default="./notes", help="Directory with Boox exports (default: ./notes)")
    p_run.add_argument("--email", help="Email address for digest (or set BOOX_EMAIL_TO)")
    p_run.add_argument("--db", default="processed_notes.json", help="Processed files database path")

    # status: check what's new
    p_status = sub.add_parser("status", help="Show status of notes directory")
    p_status.add_argument("--notes-dir", default="./notes", help="Directory with Boox exports")
    p_status.add_argument("--db", default="processed_notes.json", help="Processed files database path")

    args = parser.parse_args()

    if args.command == "convert":
        cmd_convert(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "status":
        cmd_status(args)


if __name__ == "__main__":
    main()
