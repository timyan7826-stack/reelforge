"""Stage 4 — Voiceover (scene text -> per-scene audio).

Renders one WAV per scene, then probes its real duration so the renderer can
align pictures, captions and the final timeline precisely.
"""

from __future__ import annotations

from pathlib import Path

from reelforge.backends.tts import TTSBackend
from reelforge.stages import PipelineContext, Stage
from reelforge.utils.media import probe_duration


class VoiceoverStage(Stage):
    name = "voiceover"

    def run(self, ctx: PipelineContext) -> None:
        scenes = ctx.data["storyboard"]["scenes"]
        tts: TTSBackend = ctx.data["tts"]
        audio_dir = ctx.run_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        durations: list[float] = []
        for i, sc in enumerate(scenes):
            text = sc["text"] or " "
            wav = audio_dir / f"scene_{i + 1:03d}.wav"
            _, usage = tts.synthesize(text, wav, voice=ctx.cfg["voiceover"].get("voice", "alloy"))
            ctx.ledger.add("voiceover", usage)
            durations.append(probe_duration(wav))

        # Record durations back onto the storyboard for later stages.
        for sc, dur in zip(scenes, durations):
            sc["duration"] = round(dur, 3)

        ctx.data["audio_dir"] = audio_dir
        total = sum(durations)
        print(f"  [voiceover] {len(scenes)} clips, total {total:.1f}s")
