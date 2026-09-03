"""End-to-end pipeline test in offline mode (template LLM, no network).

Renders a real MP4 through ffmpeg when available; skips the render assertion
on runners without ffmpeg so the rest of the suite still validates.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from reelforge.config import load_config
from reelforge.pipeline import run_pipeline

DEMO_CONFIG = Path(__file__).resolve().parents[1] / "examples" / "demo.toml"

HAVE_FFMPEG = shutil.which("ffmpeg") is not None


def _offline_cfg(tmp_path, seed=7):
    cfg = load_config(DEMO_CONFIG)
    cfg["output"]["dir"] = str(tmp_path / "out")
    cfg["reproducibility"]["seed"] = seed
    return cfg


def test_pipeline_produces_artifacts(tmp_path):
    result = run_pipeline(_offline_cfg(tmp_path), "Determinism test")
    run_dir = result["run_dir"]

    for name in ("script.json", "storyboard.json", "captions.srt", "captions.ass",
                 "manifest.json", "cost-report.json"):
        assert (run_dir / name).exists(), f"missing {name}"

    script = json.loads((run_dir / "script.json").read_text(encoding="utf-8"))
    assert len(script["lines"]) >= 3

    story = json.loads((run_dir / "storyboard.json").read_text(encoding="utf-8"))
    assert len(story["scenes"]) == len(script["lines"])

    assert (run_dir / "assets" / "scene_001.jpg").exists()
    assert (run_dir / "audio" / "scene_001.wav").exists()

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["topic"] == "Determinism test"
    assert manifest["stages"] == ["script", "storyboard", "assets",
                                  "voiceover", "captions", "render"]


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not installed")
def test_pipeline_renders_real_mp4(tmp_path):
    result = run_pipeline(_offline_cfg(tmp_path, seed=9), "Render test")
    video = result["final_video"]
    assert video is not None and video.exists()
    assert video.stat().st_size > 1_000
    assert video.suffix == ".mp4"


def test_deterministic_script_for_same_topic(tmp_path):
    """Same topic + same seed ⇒ identical script artifact."""
    a = run_pipeline(_offline_cfg(tmp_path, seed=11), "Same topic")
    b = run_pipeline(_offline_cfg(tmp_path, seed=11), "Same topic")
    sa = (a["run_dir"] / "script.json").read_text(encoding="utf-8")
    sb = (b["run_dir"] / "script.json").read_text(encoding="utf-8")
    assert sa == sb


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not installed")
def test_transition_and_caption_style(tmp_path):
    """Transitions overlap clips and captions must shift accordingly."""
    cfg = _offline_cfg(tmp_path, seed=13)
    cfg["render"]["transition"] = "fade"
    cfg["render"]["transition_duration"] = 0.5
    cfg["render"]["caption_style"] = "pop"
    result = run_pipeline(cfg, "Transition test")

    video = result["final_video"]
    assert video is not None and video.exists()

    ass = (result["run_dir"] / "captions.ass").read_text(encoding="utf-8")
    assert "Style: Default,Noto Sans CJK SC,72," in ass  # pop style fontsize
    # ASS timestamps must use centiseconds, never milliseconds.
    assert not re.search(r"\d\.\d{3}", ass), "ASS timestamp used milliseconds"

    srt = (result["run_dir"] / "captions.srt").read_text(encoding="utf-8")
    cues = [ln for ln in srt.splitlines() if "-->" in ln]
    assert len(cues) >= 2
    # scene 2 must start exactly (scene1.end - 0.5s) on the final timeline
    def _sec(ts: str) -> float:
        return float(ts.split(":")[2].replace(",", "."))
    end1 = _sec(cues[0].split(" --> ")[1])
    start2 = _sec(cues[1].split(" --> ")[0])
    assert abs(start2 - (end1 - 0.5)) < 0.05


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not installed")
def test_batch_cli_produces_one_video_per_topic(tmp_path):
    from reelforge.cli import main

    topics = tmp_path / "topics.txt"
    topics.write_text(
        "# comment line\nBatch topic one\n\nBatch topic two\n", encoding="utf-8"
    )
    out = tmp_path / "out"
    rc = main(["batch", "-c", str(DEMO_CONFIG), "-t", str(topics), "-o", str(out)])
    assert rc == 0
    runs = [p for p in out.iterdir() if p.is_dir()]
    assert len(runs) == 2
    for r in runs:
        assert (r / "final.mp4").exists()
        assert (r / "cost-report.json").exists()


def test_empty_topic_rejected(tmp_path):
    with pytest.raises(ValueError):
        run_pipeline(_offline_cfg(tmp_path), "   ")
