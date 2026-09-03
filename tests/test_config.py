"""Tests for configuration loading and validation."""

from __future__ import annotations

import pytest

from reelforge.config import load_config, write_example_config


def test_example_config_roundtrip(tmp_path):
    path = write_example_config(tmp_path / "config.toml")
    cfg = load_config(path)
    assert cfg["llm"]["backend"] == "openai"
    assert cfg["voiceover"]["backend"] == "silence"
    assert cfg["assets"]["backend"] == "placeholder"


def test_demo_config_loads_offline():
    from pathlib import Path
    demo = Path(__file__).resolve().parents[1] / "examples" / "demo.toml"
    cfg = load_config(demo)
    assert cfg["llm"]["backend"] == "template"
    assert cfg["voiceover"]["backend"] == "silence"
    assert cfg["reproducibility"]["seed"] == 42


def test_unknown_llm_backend_rejected(tmp_path):
    path = write_example_config(tmp_path / "c.toml")
    text = path.read_text(encoding="utf-8").replace(
        'backend = "openai"', 'backend = "does-not-exist"'
    )
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(path)


def test_missing_config_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.toml")
