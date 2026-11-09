"""Reading and writing media files.

On a PC the engine can use ffmpeg if it is installed. Inside the phone app there is no
ffmpeg: the app decodes uploads to WAV with the phone's own media codecs before handing
them to the engine, and encodes shareable files (M4A, MP4) natively afterwards.
"""
import os
import shutil
import subprocess

import numpy as np

from . import dsp, wavio


class NeedsDecoding(RuntimeError):
    """Raised when a non-WAV file arrives and no ffmpeg is available."""


def has_ffmpeg():
    return os.environ.get("BEATMAKER_NO_FFMPEG") != "1" and shutil.which("ffmpeg") is not None


def load_mono(path, sr, max_s=None, start_s=0.0):
    """Decode any audio/video file to mono float32 at `sr`."""
    if path.lower().endswith(".wav"):
        file_sr, y = wavio.read(path)
        if y.ndim > 1:
            y = y.mean(axis=1)
        a = int(start_s * file_sr)
        b = len(y) if max_s is None else a + int(max_s * file_sr)
        return dsp.resample_rate(y[a:b], file_sr, sr)
    if not has_ffmpeg():
        raise NeedsDecoding("This file needs converting to WAV first.")
    cmd = ["ffmpeg", "-v", "error", "-ss", str(start_s), "-i", path]
    if max_s:
        cmd += ["-t", str(max_s)]
    cmd += ["-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0:
        raise ValueError("Couldn't read that file.")
    return np.frombuffer(p.stdout, dtype=np.float32).copy()


def duration(path):
    if path.lower().endswith(".wav"):
        sr, y = wavio.read(path)
        return len(y) / sr
    return None


def to_mp3(wav_path, mp3_path):
    if not has_ffmpeg():
        return None
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav_path,
                    "-codec:a", "libmp3lame", "-b:a", "192k", mp3_path], check=False)
    return mp3_path if os.path.exists(mp3_path) else None
