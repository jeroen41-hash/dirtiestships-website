"""
Extract pages/images from Boox Note Air exports.

Boox exports notes as:
- PDF files (most common, from Menu → Share → Export as PDF)
- PNG images (screenshot exports)

This module converts any supported file into a list of base64-encoded
images ready for the AI vision API.
"""

import base64
import io
from pathlib import Path
from dataclasses import dataclass

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    from PIL import Image
except ImportError:
    Image = None


# Claude vision recommended limits
IMAGE_MAX_LONG_EDGE = 1568
IMAGE_MAX_SHORT_EDGE = 768
MAX_PAGES_PER_PDF = 50

SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif"}


@dataclass
class ExtractedPage:
    """A single page/image extracted from a note file."""
    data: bytes  # raw image bytes (PNG or JPEG)
    media_type: str  # "image/png" or "image/jpeg"
    page_number: int
    source_file: str

    @property
    def base64(self) -> str:
        return base64.standard_b64encode(self.data).decode("utf-8")

    @property
    def size_kb(self) -> float:
        return len(self.data) / 1024


def _optimize_image_bytes(img_bytes: bytes, media_type: str) -> tuple[bytes, str]:
    """Resize image if it exceeds Claude vision limits. Returns (bytes, media_type)."""
    if Image is None:
        return img_bytes, media_type

    img = Image.open(io.BytesIO(img_bytes))

    # Determine if resize is needed
    w, h = img.size
    long_edge = max(w, h)
    short_edge = min(w, h)

    needs_resize = long_edge > IMAGE_MAX_LONG_EDGE or short_edge > IMAGE_MAX_SHORT_EDGE

    if not needs_resize:
        return img_bytes, media_type

    # Calculate scale factor (most restrictive wins)
    scale = min(
        IMAGE_MAX_LONG_EDGE / long_edge,
        IMAGE_MAX_SHORT_EDGE / short_edge,
    )
    new_w = int(w * scale)
    new_h = int(h * scale)

    img = img.resize((new_w, new_h), Image.LANCZOS)

    buf = io.BytesIO()
    # Convert to RGB if RGBA (for JPEG compat), keep PNG for now
    if img.mode == "RGBA":
        img = img.convert("RGB")
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), "image/png"


def extract_pdf(filepath: Path, max_pages: int = MAX_PAGES_PER_PDF) -> list[ExtractedPage]:
    """Extract pages from a PDF as PNG images."""
    if fitz is None:
        raise ImportError("PyMuPDF (fitz) is required for PDF support. Run: pip install pymupdf")

    pages = []
    doc = fitz.open(str(filepath))
    page_count = min(len(doc), max_pages)

    for page_num in range(page_count):
        page = doc[page_num]
        # 200 DPI gives good quality for handwriting recognition
        mat = fitz.Matrix(200 / 72, 200 / 72)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")

        img_bytes, media_type = _optimize_image_bytes(img_bytes, "image/png")

        pages.append(ExtractedPage(
            data=img_bytes,
            media_type=media_type,
            page_number=page_num + 1,
            source_file=filepath.name,
        ))

    doc.close()
    return pages


def extract_image(filepath: Path) -> list[ExtractedPage]:
    """Load a single image file."""
    suffix = filepath.suffix.lower()

    # For BMP/TIFF, convert to PNG first
    if suffix in {".bmp", ".tiff", ".tif"} and Image is not None:
        img = Image.open(filepath)
        if img.mode == "RGBA":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        img_bytes = buf.getvalue()
        media_type = "image/png"
    else:
        img_bytes = filepath.read_bytes()
        media_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }.get(suffix, "image/png")

    img_bytes, media_type = _optimize_image_bytes(img_bytes, media_type)

    return [ExtractedPage(
        data=img_bytes,
        media_type=media_type,
        page_number=1,
        source_file=filepath.name,
    )]


def extract(filepath: Path) -> list[ExtractedPage]:
    """Extract pages/images from any supported note file.

    Args:
        filepath: Path to a PDF, PNG, JPG, BMP, or TIFF file.

    Returns:
        List of ExtractedPage objects ready for AI processing.

    Raises:
        ValueError: If file extension is not supported.
        FileNotFoundError: If file doesn't exist.
    """
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    suffix = filepath.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {suffix}. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    if suffix == ".pdf":
        return extract_pdf(filepath)
    else:
        return extract_image(filepath)
