"""Unit tests for ``backend.service``."""

from __future__ import annotations

import pytest

from backend.service import detect_mode, parse_response


# ── detect_mode ──────────────────────────────────────────────────────────

class TestDetectMode:
    def test_azure_chat(self):
        uri = "https://x.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2025-01-01-preview"
        assert detect_mode(uri) == "azure-chat"

    def test_azure_responses(self):
        uri = "https://x.cognitiveservices.azure.com/openai/responses?api-version=2025-04-01-preview"
        assert detect_mode(uri) == "azure-responses"

    def test_openai(self):
        assert detect_mode("https://api.openai.com/v1/chat/completions") == "openai"

    def test_empty_string(self):
        assert detect_mode("") == "openai"

    def test_none(self):
        assert detect_mode(None) == "openai"  # type: ignore[arg-type]


# ── parse_response ───────────────────────────────────────────────────────

class TestParseResponse:
    def test_chat_completions(self):
        data = {
            "choices": [{"message": {"content": "Hi there!"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        reply, usage = parse_response("azure-chat", data)
        assert reply == "Hi there!"
        assert usage["total_tokens"] == 15

    def test_openai_same_shape(self):
        data = {
            "choices": [{"message": {"content": "Hello"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        }
        reply, usage = parse_response("openai", data)
        assert reply == "Hello"

    def test_azure_responses_output_text(self):
        data = {
            "output_text": "Response text",
            "usage": {"input_tokens": 5, "output_tokens": 10, "total_tokens": 15},
        }
        reply, usage = parse_response("azure-responses", data)
        assert reply == "Response text"
        assert usage["prompt_tokens"] == 5
        assert usage["completion_tokens"] == 10

    def test_azure_responses_chunked_output(self):
        data = {
            "output": [
                {"content": [{"text": "chunk1"}, {"text": "chunk2"}]},
            ],
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        }
        reply, usage = parse_response("azure-responses", data)
        assert reply == "chunk1chunk2"

    def test_missing_choices_raises(self):
        with pytest.raises(ValueError, match="choices"):
            parse_response("openai", {})

    def test_empty_choices_raises(self):
        with pytest.raises(ValueError, match="choices"):
            parse_response("azure-chat", {"choices": []})
