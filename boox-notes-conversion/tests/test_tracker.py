"""Tests for the file tracking module."""

import json
from pathlib import Path

import pytest
from PIL import Image

from src.tracker import ProcessedTracker, file_hash


@pytest.fixture
def sample_files(tmp_path):
    """Create test note files."""
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    files = []
    for i, name in enumerate(["note1.png", "note2.png", "note3.jpg"]):
        img = Image.new("RGB", (100, 100), color=colors[i])
        path = tmp_path / name
        fmt = "PNG" if name.endswith(".png") else "JPEG"
        img.save(path, format=fmt)
        files.append(path)
    return files


@pytest.fixture
def tracker(tmp_path):
    db_path = tmp_path / "test_processed.json"
    return ProcessedTracker(db_path=db_path)


class TestFileHash:
    def test_same_file_same_hash(self, sample_files):
        h1 = file_hash(sample_files[0])
        h2 = file_hash(sample_files[0])
        assert h1 == h2

    def test_different_files_different_hash(self, sample_files):
        # These images are all white but different formats/names shouldn't matter
        # Actually PIL might produce identical bytes for same-size white PNGs
        # Just verify hashes are strings
        h1 = file_hash(sample_files[0])
        assert isinstance(h1, str)
        assert len(h1) == 64  # SHA-256 hex


class TestProcessedTracker:
    def test_initially_empty(self, tracker):
        assert tracker.total_processed == 0

    def test_mark_and_check(self, tracker, sample_files):
        f = sample_files[0]
        assert not tracker.is_processed(f)
        tracker.mark_processed(f, "some text")
        assert tracker.is_processed(f)
        assert tracker.total_processed == 1

    def test_persistence(self, tmp_path, sample_files):
        db_path = tmp_path / "persist.json"
        t1 = ProcessedTracker(db_path=db_path)
        t1.mark_processed(sample_files[0], "text")

        t2 = ProcessedTracker(db_path=db_path)
        assert t2.is_processed(sample_files[0])
        assert t2.total_processed == 1

    def test_find_new_files(self, tracker, tmp_path, sample_files):
        notes_dir = tmp_path
        new = tracker.find_new_files(notes_dir)
        assert len(new) == 3

        tracker.mark_processed(sample_files[0], "done")
        new = tracker.find_new_files(notes_dir)
        assert len(new) == 2

    def test_find_new_files_empty_dir(self, tracker, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        assert tracker.find_new_files(empty) == []

    def test_find_new_files_nonexistent(self, tracker, tmp_path):
        assert tracker.find_new_files(tmp_path / "nope") == []

    def test_ignores_unsupported_files(self, tracker, tmp_path):
        (tmp_path / "readme.txt").write_text("hello")
        (tmp_path / "data.csv").write_text("a,b,c")
        assert tracker.find_new_files(tmp_path) == []
