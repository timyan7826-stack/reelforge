"""Stage 5 — Captions (timeline -> SRT + ASS).

Builds a timeline from the probed per-scene durations and writes both a plain
SRT and a styled ASS file (used by the renderer for burning subtitles).
"""

from __future__ import annotations

from pathlib import Path

from reelforge.stages import PipelineContext, Stage


def _ts(total_sec: float) -> str:
    ms = int(round(total_sec * 1000))
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


class CaptionsStage(Stage):
    name = "captions"

    def run(self, ctx: PipelineContext) -> None:
        scenes = ctx.data["storyboard"]["scenes"]
        run_dir = ctx.run_dir

        srt_lines: list[str] = []
        ass_lines = self._ass_header()
        t = 0.0
        for sc in scenes:
            dur = float(sc.get("duration", 3.0))
            text = sc.get("text", "").strip()
            if text:
                idx = len(srt_lines) // 4 + 1
                srt_lines += [str(idx), f"{_ts(t)} --> {_ts(t + dur)}", text, ""]
                # ASS dialogue (escaped)
                safe = text.replace("{", "\\{").replace("}", "\\}")
                ass_lines.append(f"Dialogue: 0,{self._fmt(t)},{self._fmt(t + dur)},Default,,0,0,0,,{safe}")
            t += dur

        (run_dir / "captions.srt").write_text("\n".join(srt_lines), encoding="utf-8")
        (run_dir / "captions.ass").write_text("\n".join(ass_lines), encoding="utf-8")
        ctx.data["total_duration"] = round(t, 3)
        print(f"  [captions] {len(scenes)} cues, total {t:.1f}s")

    @staticmethod
    def _fmt(sec: float) -> str:
        ms = int(round(sec * 1000))
        h, rem = divmod(ms, 3600_000)
        m, rem = divmod(rem, 60_000)
        s, ms = divmod(rem, 1000)
        return f"{h}:{m:02d}:{s:02d}.{ms:02d}"

    @staticmethod
    def _ass_header() -> list[str]:
        return [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1920",
            "PlayResY: 1080",
            "WrapStyle: 0",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            "Style: Default,Noto Sans CJK SC,64,&H00FFFFFF,&H000000FF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,80,80,110,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
