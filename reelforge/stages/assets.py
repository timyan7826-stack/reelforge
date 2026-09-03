"""Stage 3 — Visual assets (scene -> background image).

Backends:
* ``placeholder`` — deterministic solid-color frames (default, no credentials).
* ``pexels``      — fetch a real stock photo per scene from Pexels (needs key).
* ``local``       — reuse images from a local directory (round-robin).
"""

from __future__ import annotations

import os
from pathlib import Path

from reelforge.stages import PipelineContext, Stage
from reelforge.utils.media import download, make_placeholder_image

_PALETTE = [
    "0x1f2430", "0x2d3a55", "0x3d2b56", "0x1e3a3a",
    "0x4a2f2f", "0x2f3f4f", "0x3a3a5c", "0x303a2f",
]


def _safe_label(text: str, limit: int = 14) -> str:
    text = text.strip().replace("\n", " ")
    return text[:limit] if text else "ReelForge"


class AssetsStage(Stage):
    name = "assets"

    def run(self, ctx: PipelineContext) -> None:
        scenes = ctx.data["storyboard"]["scenes"]
        cfg = ctx.cfg["assets"]
        backend = (cfg.get("backend") or "placeholder").lower()
        out_dir = ctx.run_dir / "assets"
        out_dir.mkdir(parents=True, exist_ok=True)

        if backend == "pexels":
            self._run_pexels(ctx, scenes, out_dir)
        elif backend == "local":
            self._run_local(ctx, scenes, out_dir)
        else:
            self._run_placeholder(ctx, scenes, out_dir)

        for i in range(len(scenes)):
            asset = out_dir / f"scene_{i + 1:03d}.jpg"
            if not asset.exists():
                raise RuntimeError(f"assets stage did not produce {asset.name}")
        ctx.data["asset_dir"] = out_dir
        print(f"  [assets] backend='{backend}', {len(scenes)} images")

    # --- backends ---------------------------------------------------------

    def _run_placeholder(self, ctx: PipelineContext, scenes: list[dict], out_dir: Path) -> None:
        for i, sc in enumerate(scenes):
            make_placeholder_image(
                out_dir / f"scene_{i + 1:03d}.jpg",
                color=_PALETTE[i % len(_PALETTE)],
                label=_safe_label(sc["text"]),
            )

    def _run_local(self, ctx: PipelineContext, scenes: list[dict], out_dir: Path) -> None:
        import shutil

        src_dir = Path(ctx.cfg["assets"].get("dir") or "assets")
        if not src_dir.is_dir():
            raise RuntimeError(f"assets.backend='local' but assets.dir '{src_dir}' is not a directory.")
        images = sorted(
            [p for p in src_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]
        )
        if not images:
            raise RuntimeError(f"no images found in assets.dir '{src_dir}'.")
        for i, sc in enumerate(scenes):
            src = images[i % len(images)]
            dst = out_dir / f"scene_{i + 1:03d}.jpg"
            shutil.copyfile(src, dst)

    def _run_pexels(self, ctx: PipelineContext, scenes: list[dict], out_dir: Path) -> None:
        import json
        import urllib.error
        import urllib.request

        api_key = ctx.cfg["assets"].get("api_key") or os.environ.get("PEXELS_API_KEY", "")
        if not api_key:
            raise RuntimeError("assets.backend='pexels' needs api_key or PEXELS_API_KEY.")
        for i, sc in enumerate(scenes):
            query = sc.get("visual") or sc["text"]
            url = (
                "https://api.pexels.com/v1/search"
                f"?query={urllib.parse.quote(query)}&per_page=3&orientation=landscape"
            )
            req = urllib.request.Request(url, headers={"Authorization": api_key})
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                photo = (data.get("photos") or [None])[0]
                if not photo:
                    raise RuntimeError(f"no Pexels photo for scene {i + 1}")
                src = photo["src"]["large2x"]
            except (urllib.error.HTTPError, urllib.error.URLError) as exc:
                raise RuntimeError(f"pexels request failed for scene {i + 1}: {exc}") from exc
            download(src, out_dir / f"scene_{i + 1:03d}.jpg")
