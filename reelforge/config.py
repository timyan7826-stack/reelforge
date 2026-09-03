"""Configuration loading, validation and defaults.

ReelForge is configured by a single TOML file. The built-in defaults make an
offline demo run work out of the box (template LLM + placeholder assets +
silence TTS). Everything else is an upgrade you opt into.
"""

from __future__ import annotations

import copy
import tomllib
from pathlib import Path

DEFAULTS: dict = {
    "project": {"name": "reelforge"},
    "topic": {"default": ""},
    "llm": {"backend": "openai", "model": "gpt-4o-mini", "base_url": "", "api_key": ""},
    "script": {"max_tokens": 1500, "temperature": 0.7},
    "storyboard": {"max_tokens": 2000, "temperature": 0.7},
    "assets": {"backend": "placeholder", "api_key": "", "dir": ""},
    "voiceover": {"backend": "silence", "model": "gpt-4o-mini-tts", "voice": "alloy"},
    "render": {
        "subtitles": True,
        "bgm": "",
        "transition": "none",          # none | fade | slideleft | circleopen | ...
        "transition_duration": 0.5,
        "caption_style": "clean",      # clean | pop | neon
    },
    "output": {"dir": "output"},
    "reproducibility": {"seed": 0},
}


def _merge(base: dict, override: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: str | Path) -> dict:
    """Load a TOML config and merge it over the defaults."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    cfg = _merge(DEFAULTS, raw)

    # Validate backend names early with friendly errors (key presence is
    # checked at run time — keys may come from environment variables).
    from reelforge.backends.llm import _BACKENDS as _LLM_BACKENDS
    from reelforge.backends.tts import _BACKENDS as _TTS_BACKENDS

    llm_kind = str(cfg["llm"].get("backend", "")).lower()
    tts_kind = str(cfg["voiceover"].get("backend", "")).lower()
    assets_kind = str(cfg["assets"].get("backend", "")).lower()

    if llm_kind not in _LLM_BACKENDS:
        raise ValueError(f"unknown LLM backend '{llm_kind}'. Known: {sorted(_LLM_BACKENDS)}")
    if tts_kind not in _TTS_BACKENDS:
        raise ValueError(f"unknown TTS backend '{tts_kind}'. Known: {sorted(_TTS_BACKENDS)}")
    if assets_kind not in {"placeholder", "pexels", "local"}:
        raise ValueError(
            f"unknown assets backend '{assets_kind}'. Known: ['placeholder', 'pexels', 'local']"
        )

    if not cfg["topic"]["default"] and not raw.get("topic"):
        # keep empty; CLI --topic is mandatory then
        pass
    return cfg


def write_example_config(path: str | Path) -> Path:
    """Write a commented example config file."""
    text = '''# ReelForge configuration
# Run `reelforge run -c config.toml --topic "你的主题"` after editing.

[project]
name = "reelforge"

[topic]
default = ""            # optional default topic; CLI --topic overrides it

# ---- LLM (script + storyboard) -----------------------------------------
[llm]
backend = "openai"      # openai | template   (template = offline demo, no key)
model = "gpt-4o-mini"   # any OpenAI-compatible model id
base_url = ""           # optional: point to DeepSeek/Moonshot/Ollama OpenAI bridge
api_key = ""            # or set env OPENAI_API_KEY

[script]
max_tokens = 1500
temperature = 0.7

[storyboard]
max_tokens = 2000
temperature = 0.7

# ---- Visual assets ------------------------------------------------------
[assets]
backend = "placeholder" # placeholder | pexels | local
api_key = ""            # Pexels key required for backend="pexels"
dir = ""                # local image folder for backend="local"

# ---- Voiceover ----------------------------------------------------------
[voiceover]
backend = "silence"     # openai | silence  (silence = offline placeholder)
model = "gpt-4o-mini-tts"
voice = "alloy"

# ---- Render -------------------------------------------------------------
[render]
subtitles = true        # burn captions into the final video
bgm = ""                # optional path to a background music file
transition = "none"     # none | fade | slideleft | circleopen | ... (ffmpeg xfade)
transition_duration = 0.5
caption_style = "clean" # clean | pop | neon

# ---- Output & reproducibility -------------------------------------------
[output]
dir = "output"

[reproducibility]
seed = 0                # 0 = derive seed from topic (deterministic per topic)
'''
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
