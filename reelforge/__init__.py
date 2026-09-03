"""ReelForge — a deterministic, modular, batch-first AI short-video generation engine.

Pipeline: topic -> script -> storyboard -> assets -> voiceover -> captions -> render.
Every stage is a swappable step; backends (LLM/TTS/assets) are pluggable.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
