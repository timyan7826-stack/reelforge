"""Tests for LLM / TTS backends (offline parts only)."""

from __future__ import annotations

import json
import pytest

from reelforge.backends.llm import LLMError, TemplateBackend, create_backend
from reelforge.backends.tts import SilenceTTS, create_tts


def test_template_backend_returns_lines():
    llm = TemplateBackend()
    res = llm.complete(json.dumps({"topic": "transistors"}, ensure_ascii=False))
    payload = json.loads(res.text)
    assert len(payload["lines"]) >= 6
    assert res.usage.calls == 1


def test_template_backend_storyboard_protocol():
    llm = TemplateBackend()
    script = {"title": "t", "lines": [{"text": "line one"}, {"text": "line two"}]}
    res = llm.complete(json.dumps({"script": script}, ensure_ascii=False))
    payload = json.loads(res.text)
    assert len(payload["scenes"]) == 2
    assert payload["scenes"][0]["visual"]


def test_openai_backend_requires_key():
    with pytest.raises(LLMError):
        create_backend({"backend": "openai", "model": "gpt-4o-mini", "api_key": ""})


def test_create_backend_factory():
    llm = create_backend({"backend": "template"})
    assert isinstance(llm, TemplateBackend)
    with pytest.raises(LLMError):
        create_backend({"backend": "bogus"})


def test_silence_tts_produces_wav(tmp_path):
    tts = SilenceTTS()
    out, usage = tts.synthesize("hello world this is a test line of voiceover", tmp_path / "a.wav")
    assert out.exists()
    assert out.stat().st_size > 0
    assert usage.calls == 1


def test_create_tts_factory():
    assert isinstance(create_tts({"backend": "silence"}), SilenceTTS)
    with pytest.raises(RuntimeError):
        create_tts({"backend": "bogus"})
