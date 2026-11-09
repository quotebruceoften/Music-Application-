"""Plays the recorded instruments in beatengine/samples/ (VCSL, CC0 public domain).

Pitched instruments are multi-sampled: each note is played from the nearest recorded
root, re-pitched by at most a few semitones. Percussion has several recorded takes that
are rotated, so repeated hits don't sound like a machine gun.
"""
import json
import os
from functools import lru_cache

import numpy as np

from . import wavio

SR = 44100
DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")

# Instruments that keep ringing after the key is let go vs. ones that stop with the note.
RING = {"marimba": 0.35, "vibes": 0.5, "glock": 0.6, "kalimba": 0.4}
RELEASE = {"piano": 0.25, "flute": 0.08, "sax": 0.08}


@lru_cache(maxsize=1)
def _index():
    try:
        with open(os.path.join(DIR, "index.json"), encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        return {"pitched": {}, "hits": {}}


def pitched_names():
    return set(_index()["pitched"])


def hit_names():
    return set(_index()["hits"])


def available(name):
    return name in _index()["pitched"] or name in _index()["hits"]


@lru_cache(maxsize=256)
def _load(rel):
    sr, y = wavio.read(os.path.join(DIR, rel))
    if y.ndim > 1:
        y = y.mean(axis=1)
    return y.astype(np.float32)


def _repitch(y, ratio):
    if abs(ratio - 1) < 1e-4:
        return y.copy()
    n = int(len(y) / ratio)
    pos = np.arange(n) * ratio
    return np.interp(pos, np.arange(len(y)), y).astype(np.float32)


def note(name, freq, dur, brightness=0.6):
    """One note of a recorded instrument, at any pitch, held for `dur` seconds."""
    roots = _index()["pitched"][name]
    midi = 69 + 12 * np.log2(freq / 440.0)
    # keep notes within the instrument's real range (by octaves), like a player would
    lo = min(r["pitch"] for r in roots.values())
    hi = max(r["pitch"] for r in roots.values())
    while midi < lo - 5:
        midi += 12
    while midi > hi + 5:
        midi -= 12
    key = min(roots, key=lambda k: abs(roots[k]["pitch"] - midi))
    root = roots[key]
    y = _repitch(_load(root["file"]), 2 ** ((midi - root["pitch"]) / 12))
    t = np.arange(len(y)) / SR
    if name in RING:
        # mallets and tines ring on, but a long tail would blur fast melodies
        tail = RING[name] + 0.5 * min(dur, 1.0)
        env = np.where(t > dur, np.exp(-(t - dur) / tail), 1.0)
    else:
        rel = RELEASE.get(name, 0.15)
        env = np.where(t > dur, np.exp(-(t - dur) / rel), 1.0)
    y = y * env
    end = int((dur + 6 * (RING.get(name) or RELEASE.get(name, 0.15)) + 0.5) * SR)
    y = y[: min(len(y), end)]
    n = min(len(y), int(0.005 * SR))
    if n:
        y[-n:] *= np.linspace(1, 0, n)
    return y.astype(np.float32)


def hits(name):
    """All recorded takes of a percussion sound."""
    return [_load(rel) for rel in _index()["hits"].get(name, [])]
