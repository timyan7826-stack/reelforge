"""Stage 6 — Render (scenes -> final MP4).

Composites each picture + voiceover clip into a uniform MP4 segment, concatenates
them, optionally burns in the ASS captions and mixes in background music.

Robustness rules:
* Every clip is encoded identically (h264 / yuv420p / aac 44.1kHz stereo) so the
  concat demuxer never chokes on mixed parameters.
* Subtitle burning degrades gracefully: if it fails (e.g. missing CJK font on a
  bare CI runner), we ship the unburned cut and record a warning.
* BGM mixing is optional and failure is non-fatal.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from reelforge.stages import PipelineContext, Stage
from reelforge.utils.media import probe_duration, run_ffmpeg

_FONT_CANDIDATES = [
    # Windows
    r"C:\Windows\Fonts\msyh.ttc",        # Microsoft YaHei
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    # Linux
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
]


def _find_cjk_font() -> str | None:
    for p in _FONT_CANDIDATES:
        if Path(p).exists():
            return p
    return None


class RenderStage(Stage):
    name = "render"

    def run(self, ctx: PipelineContext) -> None:
        scenes = ctx.data["storyboard"]["scenes"]
        asset_dir: Path = ctx.data["asset_dir"]
        audio_dir: Path = ctx.data["audio_dir"]
        run_dir: Path = ctx.run_dir
        cfg = ctx.cfg["render"]

        clips_dir = run_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)

        # 1) per-scene clip
        for i, sc in enumerate(scenes):
            img = asset_dir / f"scene_{i + 1:03d}.jpg"
            wav = audio_dir / f"scene_{i + 1:03d}.wav"
            clip = clips_dir / f"scene_{i + 1:03d}.mp4"
            dur = max(float(sc.get("duration", 3.0)), 0.6)
            run_ffmpeg([
                "-loop", "1", "-i", str(img),
                "-i", str(wav),
                "-vf", (
                    "scale=1920:1080:force_original_aspect_ratio=decrease,"
                    "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black"
                ),
                "-t", f"{dur:.3f}",
                "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-ar", "44100", "-ac", "2",
                "-shortest",
                str(clip),
            ])

        # 2) concat (with optional scene transitions)
        transition = str(cfg.get("transition", "none"))
        td = float(cfg.get("transition_duration", 0.5))
        clips = sorted(clips_dir.glob("scene_*.mp4"))
        joined = run_dir / "final_joined.mp4"
        if transition in ("none", "") or len(clips) < 2:
            concat_list = clips_dir / "concat.txt"
            concat_list.write_text(
                "\n".join(f"file '{c.name}'" for c in clips), encoding="utf-8"
            )
            run_ffmpeg([
                "-f", "concat", "-safe", "0", "-i", str(concat_list),
                "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart",
                str(joined),
            ])
        else:
            durations = [float(sc.get("duration", 3.0)) for sc in scenes]
            self._concat_with_transitions(clips, durations, td, transition, joined)
            print(f"  [render] transitions: {transition} ({td:.1f}s)")

        # 3) optional captions burn
        final = run_dir / "final.mp4"
        burn = bool(cfg.get("subtitles", True))
        if burn and (run_dir / "captions.ass").exists():
            try:
                self._burn_subtitles(joined, run_dir / "captions.ass", final)
                print("  [render] subtitles burned")
            except (RuntimeError, subprocess.CalledProcessError) as exc:
                ctx.warnings.append(f"subtitle burn skipped: {exc}")
                shutil.copyfile(joined, final)
        else:
            shutil.copyfile(joined, final)

        # 4) optional background music
        bgm = cfg.get("bgm") or ""
        if bgm and Path(bgm).exists():
            try:
                final = self._mix_bgm(final, Path(bgm), run_dir)
                print("  [render] background music mixed")
            except (RuntimeError, subprocess.CalledProcessError) as exc:
                ctx.warnings.append(f"bgm mix skipped: {exc}")

        ctx.data["final_video"] = final
        dur = probe_duration(final)
        print(f"  [render] final.mp4 ready ({dur:.1f}s, {final.stat().st_size / 1e6:.1f} MB)")

    # --- helpers ----------------------------------------------------------

    def _concat_with_transitions(self, clips: list[Path], durations: list[float],
                                 td: float, transition: str, dst: Path) -> None:
        """Chain all clips with xfade (video) + acrossfade (audio)."""
        n = len(clips)
        parts: list[str] = []
        prev_v = "[0:v]"
        prev_a = "[0:a]"
        for i in range(1, n):
            off = sum(durations[:i]) - i * td
            v_out, a_out = f"[v{i}]", f"[a{i}]"
            parts.append(
                f"{prev_v}[{i}:v]xfade=transition={transition}"
                f":duration={td}:offset={off:.3f}{v_out}"
            )
            parts.append(f"{prev_a}[{i}:a]acrossfade=d={td}{a_out}")
            prev_v, prev_a = v_out, a_out

        cmd = [shutil.which("ffmpeg"), "-y"]
        for c in clips:
            cmd += ["-i", str(c)]
        cmd += [
            "-filter_complex", ";".join(parts),
            "-map", prev_v, "-map", prev_a,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
            "-c:a", "aac", "-movflags", "+faststart",
            str(dst),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            tail = "\n".join(proc.stderr.strip().splitlines()[-8:])
            raise RuntimeError(f"xfade transition failed:\n{tail}")

    def _burn_subtitles(self, src: Path, ass: Path, dst: Path) -> None:
        font = _find_cjk_font()
        vf = "subtitles=captions.ass"
        if font:
            # Windows paths need forward slashes + escaped colons in filters.
            fonts_dir = str(Path(font).parent).replace("\\", "/").replace(":", "\\:")
            vf = f"subtitles=captions.ass:fontsdir='{fonts_dir}'"
        # Work from run_dir so the relative ass path is valid.
        subprocess.run(
            [shutil.which("ffmpeg"), "-y", "-i", "final_joined.mp4",
             "-vf", vf, "-c:a", "copy", "final.mp4"],
            cwd=src.parent,
            capture_output=True,
            text=True,
            check=True,
        )

    def _mix_bgm(self, video: Path, bgm: Path, run_dir: Path) -> Path:
        out = run_dir / "final_with_bgm.mp4"
        subprocess.run(
            [shutil.which("ffmpeg"), "-y",
             "-i", str(video),
             "-stream_loop", "-1", "-i", str(bgm),
             "-filter_complex",
             "[1:a]volume=0.12[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[a]",
             "-map", "0:v", "-map", "[a]",
             "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart",
             str(out)],
            capture_output=True,
            text=True,
            check=True,
        )
        final = run_dir / "final.mp4"
        shutil.move(str(out), str(final))
        return final
