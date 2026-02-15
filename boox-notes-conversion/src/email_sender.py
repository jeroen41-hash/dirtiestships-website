"""
Send converted notes as a daily email digest via msmtp or SMTP.
"""

import os
import subprocess
from datetime import date, datetime

from .convert import ConversionResult


EMAIL_TO = os.environ.get("BOOX_EMAIL_TO", "")
EMAIL_FROM = os.environ.get("BOOX_EMAIL_FROM", "boox-notes@localhost")


def build_digest(results: list[ConversionResult]) -> str:
    """Build a plain-text email body from conversion results."""
    today_str = date.today().strftime("%A, %B %d, %Y")
    successful = [r for r in results if not r.error]
    failed = [r for r in results if r.error]

    body = f"Boox Notes - {today_str}\n"
    body += "=" * 60 + "\n\n"
    body += f"{len(successful)} note(s) converted"
    if failed:
        body += f", {len(failed)} failed"
    body += ".\n"

    for i, result in enumerate(successful, 1):
        body += f"\n{'─' * 60}\n"
        body += f"Note {i}: {result.source_file}"
        body += f" ({result.pages_processed} page(s), {result.model_used})\n"
        body += "─" * 60 + "\n\n"
        body += result.text + "\n"

    if failed:
        body += f"\n{'─' * 60}\n"
        body += "ERRORS\n"
        body += "─" * 60 + "\n"
        for result in failed:
            body += f"  {result.source_file}: {result.error}\n"

    # Token usage summary
    total_in = sum(r.token_usage.get("input_tokens", 0) for r in results)
    total_out = sum(r.token_usage.get("output_tokens", 0) for r in results)
    if total_in or total_out:
        body += f"\nTokens used: {total_in:,} input, {total_out:,} output\n"

    body += f"\nProcessed at {datetime.now().strftime('%H:%M:%S')}\n"
    return body


def send_msmtp(subject: str, body: str, to: str = "", from_addr: str = "") -> bool:
    """Send email via msmtp (local MTA)."""
    to = to or EMAIL_TO
    from_addr = from_addr or EMAIL_FROM

    if not to:
        print("ERROR: No recipient. Set BOOX_EMAIL_TO environment variable.")
        return False

    email_content = f"To: {to}\nFrom: {from_addr}\nSubject: {subject}\n"
    email_content += "Content-Type: text/plain; charset=utf-8\n"
    email_content += f"\n{body}\n"

    try:
        proc = subprocess.Popen(
            ["msmtp", "-t"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _, stderr = proc.communicate(input=email_content.encode("utf-8"))

        if proc.returncode == 0:
            print(f"Email sent to {to}")
            return True
        else:
            print(f"msmtp error: {stderr.decode()}")
            return False
    except FileNotFoundError:
        print("ERROR: msmtp not installed. Run: sudo apt install msmtp msmtp-mta")
        return False


def send_digest(results: list[ConversionResult], to: str = "") -> bool:
    """Build and send the daily notes digest email."""
    if not results:
        print("No results to email.")
        return False

    successful = sum(1 for r in results if not r.error)
    subject = f"[Boox Notes] {successful} note(s) - {date.today().isoformat()}"
    body = build_digest(results)

    return send_msmtp(subject, body, to=to)
