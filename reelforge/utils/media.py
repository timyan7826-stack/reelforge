"""Low-level media helpers built on top of the external ``ffmpeg`` binary.

ReelForge deliberately depends on no Python media library: the heavy lifting
(decoding, scaling, audio muxing, subtitle burning, concat) is delegated to
ffmpeg, which is required once per machine. This keeps the package install
tiny and the render pipeline deterministic.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def require_ffmpeg() -> str:
    """Return the ffmpeg binary path or raise a friendly error."""
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError(
            "ffmpeg was not found on PATH. Install ffmpeg first "
            "(https://ffmpeg.org) and make sure it is callable as `ffmpeg`."
        )
    return path


def run_ffmpeg(args: list[str], *, timeout: int = 600) -> None:
    """Run ffmpeg with the given args, raising on non-zero exit."""
    binary = require_ffmpeg()
    cmd = [binary, "-y", *args]
    proc = subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-8:])
        raise RuntimeError(f"ffmpeg failed with exit code {proc.returncode}:\n{tail}")


def probe_duration(path: Path) -> float:
    """Return the duration in seconds of an audio/video file via ffprobe."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe was not found on PATH.")
    out = subprocess.run(
        [
            ffprobe,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError as exc:  # noqa: BLE001
        raise RuntimeError(f"could not probe duration of {path}") from exc


def make_placeholder_image(path: Path, width: int = 1920, height: int = 1080,
                           color: str = "0x1f2430", label: str = "") -> Path:
    """Generate a solid-color JPEG via ffmpeg (used in demo/no-asset mode).

    Deliberately text-free: the drawtext filter needs fontconfig and crashes on
    bare Windows builds, so placeholders stay as clean color frames — the
    readable content comes from the caption track anyway.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg([
        "-f", "lavfi",
        "-i", f"color=c={color}:s={width}x{height}:d=1",
        "-frames:v", "1",
        "-q:v", "2",
        str(path),
    ])
    return path


def download(url: str, dest: Path, *, timeout: int = 60) -> Path:
    """Download a remote asset with a sane size guard (standard library only)."""
    import urllib.request

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "ReelForge/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        # Guard against absurd files (cap at 200 MB).
        content = resp.read(200 * 1024 * 1024 + 1)
        if len(content) > 200 * 1024 * 1024:
            raise RuntimeError(f"asset too large: {url}")
        dest.write_bytes(content)
    return dest


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def env_or_default(key: str, default: str = "") -> str:
    return os.environ.get(key, default) or default
