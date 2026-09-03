"""Stage 2 — Storyboard (script lines -> visual scenes)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from reelforge.backends.llm import LLMBackend
from reelforge.stages import PipelineContext, Stage

_SYSTEM = (
    "You convert script lines into a video storyboard. For each line, produce a "
    "visual scene description for a short-form video. Return ONLY valid JSON:\n"
    '{"scenes": [{"text": "<original line>", "visual": "<detailed visual description>"}]}\n'
    "Visuals must be concrete, camera-friendly (composition, subject, lighting, mood)."
)


def _parse_json(text: str) -> dict | None:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


class StoryboardStage(Stage):
    name = "storyboard"

    def run(self, ctx: PipelineContext) -> None:
        script = ctx.data["script"]
        llm: LLMBackend = ctx.data["llm"]
        lines = [item["text"] for item in script["lines"]]

        prompt = json.dumps({"script": script}, ensure_ascii=False)
        result = llm.complete(
            prompt,
            system=_SYSTEM,
            max_tokens=int(ctx.cfg["storyboard"].get("max_tokens", 2000)),
            temperature=float(ctx.cfg["storyboard"].get("temperature", 0.7)),
            seed=ctx.data.get("seed"),
        )
        ctx.ledger.add("storyboard", result.usage)

        parsed = _parse_json(result.text)
        scenes = []
        if parsed and parsed.get("scenes"):
            for i, sc in enumerate(parsed["scenes"]):
                scenes.append({
                    "index": i,
                    "text": str(sc.get("text") or lines[i] if i < len(lines) else sc.get("text", "")).strip(),
                    "visual": str(sc.get("visual", "")).strip(),
                })
        if not scenes:
            # Offline fallback: one scene per line, empty visual.
            scenes = [{"index": i, "text": t, "visual": ""} for i, t in enumerate(lines)]

        # If a visual is empty (template backend), derive a neutral visual.
        for sc in scenes:
            if not sc["visual"]:
                sc["visual"] = f"Clean flat-lay composition about: {sc['text'][:40]}"

        storyboard = {"title": script["title"], "scenes": scenes}
        out = ctx.run_dir / "storyboard.json"
        out.write_text(json.dumps(storyboard, ensure_ascii=False, indent=2), encoding="utf-8")
        ctx.data["storyboard"] = storyboard
        print(f"  [storyboard] {len(scenes)} scenes")
