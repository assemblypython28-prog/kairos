"""Corte de clipes via ffmpeg. Usa subprocess direto — sem dependência extra."""
from __future__ import annotations

import os
import subprocess


def cut_clip(input_path: str, start: float, end: float, output_path: str) -> None:
    duration = max(end - start, 0.1)
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(start),
        "-i", input_path,
        "-t", str(duration),
        "-c", "copy",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not os.path.exists(output_path):
        # fallback: -c copy pode falhar em keyframes não alinhados; reencoda
        cmd_reencode = [
            "ffmpeg",
            "-y",
            "-ss", str(start),
            "-i", input_path,
            "-t", str(duration),
            "-c:v", "libx264",
            "-c:a", "aac",
            output_path,
        ]
        result2 = subprocess.run(cmd_reencode, capture_output=True, text=True)
        if result2.returncode != 0:
            raise RuntimeError(f"ffmpeg falhou ao cortar o clipe: {result2.stderr[-500:]}")


def get_duration_seconds(input_path: str) -> float | None:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except (ValueError, AttributeError):
        return None
