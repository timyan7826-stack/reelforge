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


# ASS style presets: (fontsize, primary, outline, shadow, bold, outline_w)
_STYLES: dict[str, tuple] = {
    # name:      fontsize, primary(BGR), outline,    shadow, bold, outline_w
    "clean":     (64, "&H00FFFFFF", "&H00101010", 1, -1, 3),
    "pop":       (72, "&H0000FFFF", "&H00000000", 2, -1, 4),   # yellow on black
    "neon":      (66, "&H00FFFFE0", "&H00FF00AA", 3, -1, 3),   # cyan-ish glow
}


class CaptionsStage(Stage):
    name = "captions"

    def run(self, ctx: PipelineContext) -> None:
        scenes = ctx.data["storyboard"]["scenes"]
        run_dir = ctx.run_dir
        render_cfg = ctx.cfg["render"]

        style = str(render_cfg.get("caption_style", "clean")).lower()
        if style not in _STYLES:
            raise RuntimeError(
                f"unknown caption_style '{style}'. Known: {sorted(_STYLES)}"
            )
        transition = str(render_cfg.get("transition", "none"))
        transition_dur = float(render_cfg.get("transition_duration", 0.5))

        srt_lines: list[str] = []
        ass_lines = self._ass_header(style)
        t = 0.0
        for i, sc in enumerate(scenes):
            # Transitions overlap clips, so later scenes start earlier on the
            # final timeline: subtract one transition per overlap.
            if i > 0 and transition not in ("none", ""):
                t -= transition_dur
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
        print(f"  [captions] {len(scenes)} cues, style='{style}', total {t:.1f}s")

    @staticmethod
    def _fmt(sec: float) -> str:
        # ASS timestamps use centiseconds (2 digits), not milliseconds.
        ms = int(round(sec * 1000))
        h, rem = divmod(ms, 3600_000)
        m, rem = divmod(rem, 60_000)
        s, ms = divmod(rem, 1000)
        return f"{h}:{m:02d}:{s:02d}.{ms // 10:02d}"

    @staticmethod
    def _ass_header(style: str = "clean") -> list[str]:
        fontsize, primary, outline, shadow, bold, outline_w = _STYLES[style]
        return [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1920",
            "PlayResY: 1080",
            "WrapStyle: 0",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            (
                f"Style: Default,Noto Sans CJK SC,{fontsize},{primary},"
                f"&H000000FF,{outline},&H80000000,{bold},0,0,0,100,100,0,0,1,"
                f"{outline_w},{shadow},2,80,80,110,1"
            ),
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
