"""
Convert extracted handwriting images to text using AI vision APIs.

Supports:
- Anthropic Claude (primary, best for handwriting)
- OpenAI GPT-4o (fallback)

The converter sends page images to the vision model with a prompt
optimized for handwriting recognition from e-ink note devices.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from .extract import ExtractedPage

try:
    import anthropic
except ImportError:
    anthropic = None

try:
    import openai
except ImportError:
    openai = None


HANDWRITING_PROMPT = (
    "This is a scan of handwritten notes from a Boox Note Air e-reader. "
    "The writing is on a white/light background with dark ink strokes. "
    "Please transcribe ALL the handwritten text you can see.\n\n"
    "Rules:\n"
    "- Preserve the original structure: headings, bullet points, numbered lists, paragraphs\n"
    "- If there are diagrams, sketches, or drawings, describe them briefly in [brackets]\n"
    "- If text is unclear, give your best guess and mark with [?]\n"
    "- Preserve any underlined or emphasized text using **bold** or _italic_ markdown\n"
    "- Keep mathematical formulas or equations in their original notation\n"
    "- Output ONLY the transcribed text, no commentary or preamble"
)


@dataclass
class ConversionResult:
    """Result of converting a single note file."""
    source_file: str
    text: str
    pages_processed: int
    model_used: str
    error: str | None = None
    token_usage: dict = field(default_factory=dict)


class Converter:
    """Converts handwriting images to text using AI vision APIs."""

    def __init__(
        self,
        provider: str = "anthropic",
        api_key: str | None = None,
        model: str | None = None,
    ):
        """
        Args:
            provider: "anthropic" or "openai"
            api_key: API key. Falls back to env vars ANTHROPIC_API_KEY / OPENAI_API_KEY.
            model: Model name override. Defaults to best available for provider.
        """
        self.provider = provider

        if provider == "anthropic":
            if anthropic is None:
                raise ImportError("anthropic package required. Run: pip install anthropic")
            self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
            self.model = model or "claude-sonnet-4-20250514"
            self._client = anthropic.Anthropic(api_key=self.api_key)
        elif provider == "openai":
            if openai is None:
                raise ImportError("openai package required. Run: pip install openai")
            self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
            self.model = model or "gpt-4o"
            self._client = openai.OpenAI(api_key=self.api_key)
        else:
            raise ValueError(f"Unknown provider: {provider}. Use 'anthropic' or 'openai'.")

    def convert_pages(self, pages: list[ExtractedPage]) -> ConversionResult:
        """Convert a list of extracted pages to text.

        Sends all pages in a single API call for context continuity
        (handwriting on page 2 may reference page 1).

        Args:
            pages: List of ExtractedPage objects from extract module.

        Returns:
            ConversionResult with the transcribed text.
        """
        if not pages:
            return ConversionResult(
                source_file="",
                text="",
                pages_processed=0,
                model_used=self.model,
                error="No pages to process",
            )

        source_file = pages[0].source_file

        if self.provider == "anthropic":
            return self._convert_anthropic(pages, source_file)
        else:
            return self._convert_openai(pages, source_file)

    def _convert_anthropic(self, pages: list[ExtractedPage], source_file: str) -> ConversionResult:
        """Convert using Anthropic Claude Vision."""
        content = []

        # Add each page as an image
        for page in pages:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": page.media_type,
                    "data": page.base64,
                },
            })

        # Add the transcription prompt
        page_info = f" ({len(pages)} pages)" if len(pages) > 1 else ""
        content.append({
            "type": "text",
            "text": HANDWRITING_PROMPT + f"\n\nFile: {source_file}{page_info}",
        })

        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=8192,
                messages=[{"role": "user", "content": content}],
            )

            text = response.content[0].text
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }

            return ConversionResult(
                source_file=source_file,
                text=text,
                pages_processed=len(pages),
                model_used=self.model,
                token_usage=usage,
            )

        except Exception as e:
            return ConversionResult(
                source_file=source_file,
                text="",
                pages_processed=len(pages),
                model_used=self.model,
                error=str(e),
            )

    def _convert_openai(self, pages: list[ExtractedPage], source_file: str) -> ConversionResult:
        """Convert using OpenAI GPT-4 Vision."""
        content = []

        for page in pages:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{page.media_type};base64,{page.base64}",
                    "detail": "high",
                },
            })

        page_info = f" ({len(pages)} pages)" if len(pages) > 1 else ""
        content.append({
            "type": "text",
            "text": HANDWRITING_PROMPT + f"\n\nFile: {source_file}{page_info}",
        })

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                max_tokens=8192,
                messages=[{"role": "user", "content": content}],
            )

            text = response.choices[0].message.content
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }

            return ConversionResult(
                source_file=source_file,
                text=text,
                pages_processed=len(pages),
                model_used=self.model,
                token_usage=usage,
            )

        except Exception as e:
            return ConversionResult(
                source_file=source_file,
                text="",
                pages_processed=len(pages),
                model_used=self.model,
                error=str(e),
            )


def convert_file(
    filepath: Path,
    provider: str = "anthropic",
    api_key: str | None = None,
    model: str | None = None,
) -> ConversionResult:
    """Convenience function: extract + convert in one call.

    Args:
        filepath: Path to a Boox note export (PDF/PNG/JPG).
        provider: "anthropic" or "openai".
        api_key: API key (or set via env var).
        model: Model override.

    Returns:
        ConversionResult with transcribed text.
    """
    from .extract import extract

    pages = extract(filepath)
    converter = Converter(provider=provider, api_key=api_key, model=model)
    return converter.convert_pages(pages)
