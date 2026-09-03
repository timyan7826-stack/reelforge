"""Stage 1 — Script generation (topic -> spoken lines)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from reelforge.backends.llm import LLMBackend
from reelforge.stages import PipelineContext, Stage

_SYSTEM = (
    "You are an expert short-video scriptwriter. Write a punchy, spoken-style "
    "short script (about 6-9 short lines, each line under 30 Chinese characters "
    "or 200 English characters). Return ONLY valid JSON:\n"
    '{"title": "<video title>", "lines": [{"text": "<line text>"}, ...]}'
)


def _parse_json(text: str) -> dict | None:
    """Tolerant JSON parse: strips code fences and finds the first object."""
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


class ScriptStage(Stage):
    name = "script"

    def run(self, ctx: PipelineContext) -> None:
        llm: LLMBackend = ctx.data["llm"]
        topic: str = ctx.data["topic"]
        prompt = json.dumps({"topic": topic}, ensure_ascii=False)

        result = llm.complete(
            prompt,
            system=_SYSTEM,
            max_tokens=int(ctx.cfg["script"].get("max_tokens", 1500)),
            temperature=float(ctx.cfg["script"].get("temperature", 0.7)),
            seed=ctx.data.get("seed"),
        )
        ctx.ledger.add("script", result.usage)

        parsed = _parse_json(result.text)
        if (not parsed or not parsed.get("lines")):
            # Tolerant fallback: treat non-JSON output as one line per paragraph.
            lines = [ln.strip() for ln in result.text.splitlines() if ln.strip()]
            if lines:
                parsed = {"title": topic, "lines": [{"text": ln} for ln in lines]}
        if not parsed or not parsed.get("lines"):
            raise RuntimeError(f"script stage got unparsable output:\n{result.text[:300]}")

        title = str(parsed.get("title") or topic).strip()
        lines = [str(item["text"]).strip() for item in parsed["lines"] if item.get("text", "").strip()]
        if not lines:
            raise RuntimeError("script stage produced zero non-empty lines.")

        script = {"title": title, "topic": topic, "lines": [{"text": t} for t in lines]}
        out = ctx.run_dir / "script.json"
        out.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
        ctx.data["script"] = script
        print(f"  [script] {len(lines)} lines, title='{title}'")


class ScriptStage_Template(ScriptStage):
    """Template backend already returns lines; reuse the same logic."""
