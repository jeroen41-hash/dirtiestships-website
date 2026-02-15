"""Tests for the conversion module (mocked API calls)."""

from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest
from PIL import Image

from src.extract import ExtractedPage, extract
from src.convert import Converter, ConversionResult, HANDWRITING_PROMPT


@pytest.fixture
def sample_page():
    """Create a minimal ExtractedPage for testing."""
    img = Image.new("RGB", (200, 100), color="white")
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return ExtractedPage(
        data=buf.getvalue(),
        media_type="image/png",
        page_number=1,
        source_file="test.png",
    )


class TestConverter:
    @patch("src.convert.anthropic")
    def test_anthropic_success(self, mock_anthropic_mod, sample_page):
        mock_client = MagicMock()
        mock_anthropic_mod.Anthropic.return_value = mock_client
        mock_anthropic_mod.APIError = Exception

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Hello world - transcribed notes")]
        mock_response.usage.input_tokens = 1000
        mock_response.usage.output_tokens = 50
        mock_client.messages.create.return_value = mock_response

        converter = Converter(provider="anthropic", api_key="test-key")
        result = converter.convert_pages([sample_page])

        assert result.text == "Hello world - transcribed notes"
        assert result.error is None
        assert result.pages_processed == 1
        assert result.source_file == "test.png"
        assert result.token_usage["input_tokens"] == 1000

        # Verify API was called with correct structure
        call_args = mock_client.messages.create.call_args
        messages = call_args.kwargs["messages"]
        content = messages[0]["content"]
        # Should have 1 image + 1 text block
        assert len(content) == 2
        assert content[0]["type"] == "image"
        assert content[1]["type"] == "text"

    @patch("src.convert.anthropic")
    def test_anthropic_api_error(self, mock_anthropic_mod, sample_page):
        mock_client = MagicMock()
        mock_anthropic_mod.Anthropic.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API rate limit")

        converter = Converter(provider="anthropic", api_key="test-key")
        result = converter.convert_pages([sample_page])

        assert result.error is not None
        assert "rate limit" in result.error
        assert result.text == ""

    def test_empty_pages(self):
        converter = Converter.__new__(Converter)
        converter.provider = "anthropic"
        converter.model = "test"
        result = converter.convert_pages([])
        assert result.error == "No pages to process"
        assert result.pages_processed == 0

    @patch("src.convert.openai")
    def test_openai_success(self, mock_openai_mod, sample_page):
        mock_client = MagicMock()
        mock_openai_mod.OpenAI.return_value = mock_client

        mock_choice = MagicMock()
        mock_choice.message.content = "OpenAI transcription result"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage.prompt_tokens = 800
        mock_response.usage.completion_tokens = 40
        mock_client.chat.completions.create.return_value = mock_response

        converter = Converter(provider="openai", api_key="test-key")
        result = converter.convert_pages([sample_page])

        assert result.text == "OpenAI transcription result"
        assert result.error is None

    def test_invalid_provider(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            Converter(provider="gemini", api_key="test")

    @patch("src.convert.anthropic")
    def test_multi_page(self, mock_anthropic_mod, sample_page):
        mock_client = MagicMock()
        mock_anthropic_mod.Anthropic.return_value = mock_client
        mock_anthropic_mod.APIError = Exception

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Page 1 and page 2 content")]
        mock_response.usage.input_tokens = 2000
        mock_response.usage.output_tokens = 100
        mock_client.messages.create.return_value = mock_response

        pages = [sample_page, sample_page]
        converter = Converter(provider="anthropic", api_key="test-key")
        result = converter.convert_pages(pages)

        assert result.pages_processed == 2
        # Should send all pages in one call
        call_args = mock_client.messages.create.call_args
        content = call_args.kwargs["messages"][0]["content"]
        # 2 images + 1 text prompt
        assert len(content) == 3
