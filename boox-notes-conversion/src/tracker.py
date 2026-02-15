"""
Track which note files have already been processed.

Uses a JSON file to store SHA-256 hashes of processed files,
so the same note is never converted twice (even if renamed/moved).
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

from .extract import SUPPORTED_EXTENSIONS


DEFAULT_DB_PATH = Path("processed_notes.json")


def file_hash(filepath: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


class ProcessedTracker:
    """Tracks which files have been processed to avoid duplicates."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._data = self._load()

    def _load(self) -> dict:
        if self.db_path.exists():
            try:
                with open(self.db_path) as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def save(self):
        with open(self.db_path, "w") as f:
            json.dump(self._data, f, indent=2)

    def is_processed(self, filepath: Path) -> bool:
        """Check if a file has already been processed."""
        fhash = file_hash(filepath)
        return fhash in self._data

    def mark_processed(self, filepath: Path, result_preview: str = ""):
        """Mark a file as processed."""
        fhash = file_hash(filepath)
        self._data[fhash] = {
            "file": str(filepath),
            "name": filepath.name,
            "processed_at": datetime.now().isoformat(),
            "preview": result_preview[:200],
        }
        self.save()

    def find_new_files(self, notes_dir: Path) -> list[Path]:
        """Scan a directory for unprocessed note files."""
        new_files = []
        if not notes_dir.exists():
            return new_files

        for filepath in sorted(notes_dir.rglob("*")):
            if filepath.is_file() and filepath.suffix.lower() in SUPPORTED_EXTENSIONS:
                if not self.is_processed(filepath):
                    new_files.append(filepath)

        return new_files

    @property
    def total_processed(self) -> int:
        return len(self._data)
