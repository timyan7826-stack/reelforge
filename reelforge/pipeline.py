"""Pipeline orchestration.

Binds the configuration to concrete backends, runs the six stages in order,
and writes a machine-readable manifest so every run is reproducible and
auditable (which is the whole point of ReelForge).
"""

from __future__ import annotations

import hashlib
import json
import time
import re
from pathlib import Path

from reelforge import __version__
from reelforge.backends.llm import create_backend as create_llm
from reelforge.backends.tts import create_tts
from reelforge.stages import PipelineContext
from reelforge.stages.assets import AssetsStage
from reelforge.stages.captions import CaptionsStage
from reelforge.stages.render import RenderStage
from reelforge.stages.script import ScriptStage
from reelforge.stages.storyboard import StoryboardStage
from reelforge.stages.voiceover import VoiceoverStage
from reelforge.utils.cost import CostLedger

_STAGES = [
    ScriptStage,
    StoryboardStage,
    AssetsStage,
    VoiceoverStage,
    CaptionsStage,
    RenderStage,
]


def _slugify(text: str, limit: int = 24) -> str:
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", text.strip()).strip("-")
    return (slug or "topic")[:limit]


def _derive_seed(cfg_seed: int, topic: str) -> int:
    if cfg_seed:
        return cfg_seed
    return int(hashlib.sha256(topic.encode("utf-8")).hexdigest()[:8], 16)


def _display_path(p: Path) -> str:
    """Best-effort cwd-relative path for pretty printing."""
    try:
        return str(p.relative_to(Path.cwd()))
    except ValueError:
        return str(p)


def run_pipeline(cfg: dict, topic: str, out_root: str | Path | None = None,
                 run_id: str | None = None) -> dict:
    """Run the full pipeline for a topic and return result metadata."""
    topic = topic.strip()
    if not topic:
        raise ValueError("topic must not be empty (pass --topic or set [topic].default)")

    out_root = Path(out_root or cfg["output"]["dir"])
    out_root.mkdir(parents=True, exist_ok=True)
    seed = _derive_seed(int(cfg["reproducibility"].get("seed", 0)), topic)
    run_id = run_id or f"{time.strftime('%Y%m%d-%H%M%S')}-{_slugify(topic)}"
    run_dir = out_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Bind backends.
    llm = create_llm(cfg["llm"])
    tts = create_tts(cfg["voiceover"])

    ctx = PipelineContext(cfg=cfg, run_dir=run_dir, ledger=CostLedger())
    ctx.data.update({"llm": llm, "tts": tts, "topic": topic, "seed": seed})

    print(f"ReelForge v{__version__} — run '{run_id}'")
    print(f"  seed={seed}  llm={llm.name}  tts={tts.name}  assets={cfg['assets']['backend']}")
    for stage_cls in _STAGES:
        stage = stage_cls()
        stage.run(ctx)

    manifest = {
        "run_id": run_id,
        "version": __version__,
        "topic": topic,
        "seed": seed,
        "config": cfg,
        "stages": [s.name for s in _STAGES],
        "artifacts": {
            "script": "script.json",
            "storyboard": "storyboard.json",
            "captions_srt": "captions.srt",
            "captions_ass": "captions.ass",
            "final_video": str(ctx.data.get("final_video", "final.mp4").name),
            "cost_report": "cost-report.json",
        },
        "total_duration_s": ctx.data.get("total_duration"),
        "asset_seeds": ctx.data.get("asset_seeds"),
        "warnings": ctx.warnings,
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    ledger_path = ctx.ledger.write_report(run_dir)

    if ctx.warnings:
        print(f"  ⚠ {len(ctx.warnings)} warning(s)")
        for w in ctx.warnings:
            print(f"    - {w}")

    print(f"  ✓ manifest: {_display_path(manifest_path)}")
    print(f"  ✓ cost:    {_display_path(ledger_path)}")
    return {
        "run_id": run_id,
        "run_dir": run_dir,
        "final_video": ctx.data.get("final_video"),
        "manifest": manifest_path,
        "cost_report": ledger_path,
        "warnings": ctx.warnings,
    }
