"""Tests for the extraction module."""

import io
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from src.extract import (
    extract,
    extract_image,
    extract_pdf,
    ExtractedPage,
    SUPPORTED_EXTENSIONS,
    _optimize_image_bytes,
)


@pytest.fixture
def sample_png(tmp_path):
    """Create a simple test PNG image."""
    img = Image.new("RGB", (800, 600), color=(255, 255, 255))
    # Draw some dark pixels to simulate handwriting
    for x in range(100, 700):
        for y in range(280, 320):
            img.putpixel((x, y), (30, 30, 30))
    path = tmp_path / "test_note.png"
    img.save(path, format="PNG")
    return path


@pytest.fixture
def sample_jpg(tmp_path):
    """Create a simple test JPEG image."""
    img = Image.new("RGB", (640, 480), color=(245, 245, 245))
    path = tmp_path / "test_note.jpg"
    img.save(path, format="JPEG")
    return path


@pytest.fixture
def sample_bmp(tmp_path):
    """Create a simple test BMP image."""
    img = Image.new("RGB", (400, 300), color=(255, 255, 255))
    path = tmp_path / "test_note.bmp"
    img.save(path, format="BMP")
    return path


@pytest.fixture
def sample_pdf(tmp_path):
    """Create a simple 2-page test PDF using PyMuPDF."""
    import fitz

    doc = fitz.open()
    for i in range(2):
        page = doc.new_page(width=595, height=842)  # A4
        page.insert_text((72, 100), f"Test handwriting page {i + 1}", fontsize=16)
    path = tmp_path / "test_note.pdf"
    doc.save(str(path))
    doc.close()
    return path


class TestExtractImage:
    def test_extract_png(self, sample_png):
        pages = extract_image(sample_png)
        assert len(pages) == 1
        assert pages[0].media_type == "image/png"
        assert pages[0].page_number == 1
        assert pages[0].source_file == "test_note.png"
        assert len(pages[0].data) > 0

    def test_extract_jpg(self, sample_jpg):
        pages = extract_image(sample_jpg)
        assert len(pages) == 1
        assert pages[0].media_type == "image/jpeg"

    def test_extract_bmp_converts_to_png(self, sample_bmp):
        pages = extract_image(sample_bmp)
        assert len(pages) == 1
        assert pages[0].media_type == "image/png"

    def test_base64_property(self, sample_png):
        pages = extract_image(sample_png)
        b64 = pages[0].base64
        assert isinstance(b64, str)
        assert len(b64) > 0

    def test_size_kb(self, sample_png):
        pages = extract_image(sample_png)
        assert pages[0].size_kb > 0


class TestExtractPdf:
    def test_extract_pdf_pages(self, sample_pdf):
        pages = extract_pdf(sample_pdf)
        assert len(pages) == 2
        assert pages[0].page_number == 1
        assert pages[1].page_number == 2
        assert pages[0].media_type == "image/png"

    def test_max_pages_limit(self, sample_pdf):
        pages = extract_pdf(sample_pdf, max_pages=1)
        assert len(pages) == 1


class TestExtract:
    def test_extract_dispatches_png(self, sample_png):
        pages = extract(sample_png)
        assert len(pages) == 1

    def test_extract_dispatches_pdf(self, sample_pdf):
        pages = extract(sample_pdf)
        assert len(pages) == 2

    def test_unsupported_extension(self, tmp_path):
        bad_file = tmp_path / "notes.docx"
        bad_file.write_text("not a real docx")
        with pytest.raises(ValueError, match="Unsupported file type"):
            extract(bad_file)

    def test_file_not_found(self, tmp_path):
        missing = tmp_path / "nonexistent.pdf"
        with pytest.raises(FileNotFoundError):
            extract(missing)


class TestOptimizeImage:
    def test_small_image_unchanged(self):
        img = Image.new("RGB", (500, 400), color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        original = buf.getvalue()

        result, media_type = _optimize_image_bytes(original, "image/png")
        assert result == original  # no resize needed

    def test_large_image_resized(self):
        img = Image.new("RGB", (3000, 2000), color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        original = buf.getvalue()

        result, media_type = _optimize_image_bytes(original, "image/png")
        # Should be smaller after resize
        result_img = Image.open(io.BytesIO(result))
        assert result_img.width <= 1568
        assert result_img.height <= 768
