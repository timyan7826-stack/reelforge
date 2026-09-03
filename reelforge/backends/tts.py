"""TTS backends.

Like LLMs, the voice is a swappable component:

* ``openai``  — OpenAI Audio Speech API (gpt-4o-mini-tts / tts-1).
* ``silence`` — offline placeholder voice for demo runs (no credentials).

Extend by subclassing :class:`TTSBackend` and registering in ``create_tts``.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path

from reelforge.utils.cost import Usage
from reelforge.utils.media import run_ffmpeg

# Rough speaking rate for the silence placeholder: chars per second.
_CHARS_PER_SEC = 4.2


class TTSBackend(ABC):
    """Interface every TTS backend implements."""

    name = "base"

    @abstractmethod
    def synthesize(self, text: str, dest: Path, *, voice: str = "") -> tuple[Path, Usage]:
        """Render ``text`` to an audio file at ``dest`` (wav). Return (path, usage)."""


class OpenAITTS(TTSBackend):
    name = "openai"

    def __init__(self, model: str = "gpt-4o-mini-tts", base_url: str | None = None,
                 api_key: str | None = None, *, timeout: int = 120) -> None:
        self.model = model
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY") or ""
        self.timeout = timeout
        if not self.api_key:
            raise RuntimeError(
                "TTS backend 'openai' needs an API key. Set OPENAI_API_KEY "
                "or switch tts.backend to 'silence'."
            )

    def synthesize(self, text: str, dest: Path, *, voice: str = "") -> tuple[Path, Usage]:
        payload = {
            "model": self.model,
            "input": text,
            "voice": voice or "alloy",
            "response_format": "wav",
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/audio/speech",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise RuntimeError(f"TTS HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"TTS connection error: {exc.reason}") from exc

        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        # OpenAI speech usage isn't token-based; count it as an audited unit.
        return dest, Usage(calls=1, other_units=1)


class SilenceTTS(TTSBackend):
    """Offline placeholder voice: a clean silence WAV whose length matches the
    estimated reading time of the line. Used in demo mode."""

    name = "silence"

    def __init__(self, chars_per_sec: float = _CHARS_PER_SEC) -> None:
        self.cps = chars_per_sec

    def synthesize(self, text: str, dest: Path, *, voice: str = "") -> tuple[Path, Usage]:
        duration = max(1.0, len(text) / self.cps)
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        run_ffmpeg([
            "-f", "lavfi",
            "-i", f"anullsrc=r=44100:cl=stereo",
            "-t", f"{duration:.2f}",
            "-c:a", "pcm_s16le",
            str(dest),
        ])
        return dest, Usage(calls=1)


_BACKENDS: dict[str, type[TTSBackend]] = {
    "openai": OpenAITTS,
    "silence": SilenceTTS,
}


def create_tts(cfg: dict) -> TTSBackend:
    kind = (cfg.get("backend") or "silence").lower()
    if kind not in _BACKENDS:
        raise RuntimeError(f"unknown TTS backend '{kind}'. Known: {sorted(_BACKENDS)}")
    cls = _BACKENDS[kind]
    if kind == "openai":
        return cls(
            model=cfg.get("model", "gpt-4o-mini-tts"),
            base_url=cfg.get("base_url"),
            api_key=cfg.get("api_key"),
        )
    return cls()
