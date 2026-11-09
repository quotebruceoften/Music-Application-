"""Sound synthesis: every drum and instrument is generated from scratch with numpy.

No samples are needed, so the app runs anywhere. Each function returns a mono
float32 array at SR. Results are cached, because a beat re-uses the same hits.
"""
from functools import lru_cache

import numpy as np

from . import dsp

SR = 44100
TWO_PI = 2 * np.pi


# ---------------------------------------------------------------- helpers
def _t(dur):
    return np.arange(max(1, int(dur * SR))) / SR


def _noise(n, seed):
    return np.random.default_rng(seed).standard_normal(n)


def _filt(x, kind, freq, order=2):
    nyq = SR / 2 * 0.98
    if kind == "bandpass":
        lo, hi = max(20.0, freq[0]), min(nyq, freq[1])
        if lo >= hi:
            return x
        freq = [lo, hi]
    else:
        freq = min(max(20.0, freq), nyq)
    return dsp.filt(x, SR, kind, freq, order)


def _sweep(freqs):
    return np.sin(TWO_PI * np.cumsum(freqs) / SR)


def _norm(y, peak=1.0):
    m = np.max(np.abs(y))
    return (y / m * peak if m > 0 else y).astype(np.float32)


def _gate(t, dur, release):
    """1.0 while the note is held, then an exponential release."""
    g = np.ones_like(t)
    after = t > dur
    g[after] = np.exp(-(t[after] - dur) / max(release, 1e-3))
    return g


def _attack(t, a):
    return np.clip(t / max(a, 1e-4), 0, 1)


def _fade_out(y, ms=4):
    n = min(len(y), int(SR * ms / 1000))
    if n > 0:
        y[-n:] *= np.linspace(1, 0, n)
    return y


# ---------------------------------------------------------------- drums
@lru_cache(maxsize=256)
def kick(sound="punchy", tune=0.0, decay=1.0):
    r = 2 ** (tune / 12)
    p = {
        "punchy": (52, 0.32, 3.5, 0.035, 0.35),
        "808kick": (45, 0.90, 2.5, 0.040, 0.20),
        "soft": (58, 0.22, 2.0, 0.025, 0.12),
    }.get(sound, (52, 0.32, 3.5, 0.035, 0.35))
    f0, d, sweep, tau, click = p
    f0 *= r
    d *= decay
    t = _t(min(3.0, d * 5))
    y = _sweep(f0 * (1 + sweep * np.exp(-t / tau))) * np.exp(-t / d)
    c = _filt(_noise(len(t), 1), "highpass", 1500) * np.exp(-t / 0.004) * click
    return _fade_out(_norm(np.tanh(1.6 * (y + c))))


@lru_cache(maxsize=256)
def snare(sound="tight", tune=0.0, decay=1.0):
    r = 2 ** (tune / 12)
    f, d = (185, 0.16) if sound == "tight" else (160, 0.26)
    f *= r
    d *= decay
    t = _t(d * 5)
    body = _sweep(f * (1 + 0.6 * np.exp(-t / 0.01))) * np.exp(-t / 0.06) * 0.6
    n = _filt(_noise(len(t), 2), "bandpass", [1800 * r, 9000]) * np.exp(-t / d)
    return _fade_out(_norm(np.tanh(1.3 * (body + 0.9 * n))))


@lru_cache(maxsize=256)
def clap(sound="clap", tune=0.0, decay=1.0):
    r = 2 ** (tune / 12)
    t = _t(0.8 * decay + 0.1)
    n = _filt(_noise(len(t), 3), "bandpass", [900 * r, 3200 * r])
    env = np.zeros_like(t)
    for off in (0.0, 0.011, 0.022):
        e = np.where(t >= off, np.exp(-(t - off) / 0.006), 0)
        env = np.maximum(env, e)
    tail = np.where(t >= 0.03, np.exp(-(t - 0.03) / (0.15 * decay)), 0)
    env = np.maximum(env, tail * 0.8)
    return _fade_out(_norm(n * env))


@lru_cache(maxsize=256)
def hat(open_=False, tune=0.0, decay=1.0):
    r = 2 ** (tune / 12)
    d = (0.28 if open_ else 0.045) * decay
    t = _t(d * 5 + 0.01)
    metal = sum(np.sign(np.sin(TWO_PI * f * r * t)) for f in (205.3, 304.4, 369.6, 522.7, 540.0, 800.0))
    x = metal * 0.5 + _noise(len(t), 4) * 0.6
    x = _filt(x, "highpass", 7000 * min(r, 1.6), order=4)
    return _fade_out(_norm(x * np.exp(-t / d)))


@lru_cache(maxsize=256)
def shaker(sound="shaker", tune=0.0, decay=1.0):
    r = 2 ** (tune / 12)
    t = _t(0.35 * decay + 0.02)
    n = _filt(_noise(len(t), 5), "bandpass", [4500 * r, 13000])
    env = (1 - np.exp(-t / 0.008)) * np.exp(-t / (0.05 * decay))
    return _fade_out(_norm(n * env))


@lru_cache(maxsize=256)
def perc(sound="rim", tune=0.0, decay=1.0):
    r = 2 ** (tune / 12)
    if sound == "conga":
        t = _t(0.18 * decay * 5)
        y = _sweep(320 * r * (1 + 0.3 * np.exp(-t / 0.02)) * 0.72) * np.exp(-t / (0.18 * decay))
    elif sound == "wood":
        t = _t(0.03 * decay * 6)
        e = np.exp(-t / (0.03 * decay))
        y = (np.sin(TWO_PI * 900 * r * t) + 0.5 * np.sin(TWO_PI * 2400 * r * t)) * e
    elif sound == "cowbell":
        t = _t(0.12 * decay * 5)
        sq = np.sign(np.sin(TWO_PI * 540 * r * t)) + np.sign(np.sin(TWO_PI * 800 * r * t))
        y = _filt(sq, "bandpass", [500 * r, 3000 * r]) * np.exp(-t / (0.12 * decay))
    else:  # rim
        t = _t(0.06 * decay * 4 + 0.01)
        e = np.exp(-t / (0.012 * decay))
        y = (np.sin(TWO_PI * 1750 * r * t) + 0.6 * np.sin(TWO_PI * 480 * r * t)) * e
        y += _filt(_noise(len(t), 6), "bandpass", [2000, 8000]) * np.exp(-t / 0.004) * 0.5
    return _fade_out(_norm(y))


# ---------------------------------------------------------------- bass
@lru_cache(maxsize=1024)
def bass_note(sound, freq, dur, decay=1.0, start_freq=0.0, glide_time=0.0):
    if sound == "logdrum":
        # The amapiano log drum: a pitched, bouncy, slightly distorted thump.
        length = min(dur, 1.4 * decay) + 0.05
        t = _t(length)
        ph = np.cumsum(freq * (1 + 1.2 * np.exp(-t / 0.035))) / SR * TWO_PI
        y = np.sin(ph) + 0.35 * np.sin(2 * ph) + 0.15 * np.sin(3 * ph)
        y *= np.exp(-t / (0.28 * decay)) * _gate(t, length - 0.04, 0.02)
        y = _filt(np.tanh(2.5 * y), "lowpass", 3000)
    elif sound == "808":
        length = dur + 0.1
        t = _t(length)
        if start_freq > 0 and glide_time > 0:
            k = np.clip(t / glide_time, 0, 1)
            f = start_freq * (freq / start_freq) ** k
        else:
            f = freq * (1 + 0.4 * np.exp(-t / 0.02))
        y = _sweep(f) * np.exp(-t / (1.2 * decay)) * _gate(t, dur, 0.05)
        y = np.tanh(2.2 * y) / np.tanh(2.2)
    elif sound == "pluck":
        length = min(dur, 2.0) + 0.06
        t = _t(length)
        y = np.zeros_like(t)
        k = 1
        while k <= 20 and k * freq < SR / 2.2:
            y += np.sin(TWO_PI * k * freq * t) / k * np.exp(-t * (1 + 0.8 * k) / (0.5 * decay))
            k += 1
        y *= _gate(t, length - 0.05, 0.02)
    else:  # sub
        length = dur + 0.08
        t = _t(length)
        y = (np.sin(TWO_PI * freq * t) + 0.1 * np.sin(TWO_PI * 2 * freq * t))
        y *= _attack(t, 0.004) * _gate(t, dur, 0.05)
    return _fade_out(_norm(y))


# ---------------------------------------------------------------- keys / leads
def _additive(freq, t, n_harm, amp_fn, decay_fn, inharm=0.0):
    y = np.zeros_like(t)
    for k in range(1, n_harm + 1):
        fk = k * freq * np.sqrt(1 + inharm * k * k)
        if fk > SR / 2.2:
            break
        y += amp_fn(k) * np.sin(TWO_PI * fk * t) * np.exp(-t / decay_fn(k))
    return y


@lru_cache(maxsize=2048)
def tone_note(sound, freq, dur, brightness=0.6):
    """Chord and melody instruments."""
    if sound == "piano":
        t = _t(min(dur, 4.0) + 0.3)
        y = _additive(freq, t, 10, lambda k: 1 / k ** 1.3, lambda k: 1.8 / k ** 0.5, 0.0004)
        y += _filt(_noise(len(t), 7), "lowpass", 3000) * np.exp(-t / 0.005) * 0.05
        y *= _gate(t, dur, 0.15)
    elif sound == "rhodes":
        t = _t(min(dur, 4.0) + 0.3)
        idx = 1.8 * np.exp(-t / 0.25) + 0.3
        y = np.sin(TWO_PI * freq * t + idx * np.sin(TWO_PI * freq * t)) * np.exp(-t / 1.6)
        y += 0.15 * np.sin(TWO_PI * freq * 7 * t) * np.exp(-t / 0.05)
        y *= _gate(t, dur, 0.25)
    elif sound == "pad":
        t = _t(dur + 0.7)
        y = np.zeros_like(t)
        for cents in (-8, 0, 8):
            f = freq * 2 ** (cents / 1200)
            y += 2 * ((f * t + cents * 0.13) % 1.0) - 1
        y = _filt(y / 3, "lowpass", 500 + brightness ** 2 * 5000)
        y *= _attack(t, 0.25) * _gate(t, dur, 0.6)
    elif sound == "organ":
        t = _t(dur + 0.15)
        vib = 1 + 0.003 * np.sin(TWO_PI * 6 * t)
        y = sum(a * _sweep(freq * m * vib) for m, a in ((1, 1), (2, 0.6), (3, 0.4), (4, 0.25)))
        y *= _attack(t, 0.01) * _gate(t, dur, 0.08)
    elif sound == "pluck":
        t = _t(min(dur, 2.0) + 0.1)
        y = _additive(freq, t, 16, lambda k: 1 / k, lambda k: 0.6 / (1 + 0.5 * k))
        y *= _gate(t, dur, 0.08)
    elif sound == "bell":
        t = _t(min(dur, 3.0) + 0.8)
        idx = 3 * np.exp(-t / 0.3)
        y = np.sin(TWO_PI * freq * t + idx * np.sin(TWO_PI * freq * 3.5 * t)) * np.exp(-t / 1.2)
        y *= _gate(t, dur + 0.5, 0.3)
    elif sound == "flute":
        t = _t(dur + 0.15)
        vib = 1 + 0.006 * np.sin(TWO_PI * 5 * t) * np.clip((t - 0.2) / 0.3, 0, 1)
        y = _sweep(freq * vib) + 0.2 * _sweep(2 * freq * vib)
        y += _filt(_noise(len(t), 8), "bandpass", [freq * 0.8, freq * 3]) * 0.25
        y *= _attack(t, 0.06) * _gate(t, dur, 0.12)
    elif sound == "marimba":
        t = _t(min(dur, 1.5) + 0.5)
        y = np.sin(TWO_PI * freq * t) * np.exp(-t / 0.4)
        y += 0.3 * np.sin(TWO_PI * freq * 4 * t) * np.exp(-t / 0.06)
        y += 0.1 * np.sin(TWO_PI * freq * 10 * t) * np.exp(-t / 0.015)
    else:  # lead
        t = _t(dur + 0.12)
        vib = 1 + 0.004 * np.sin(TWO_PI * 5.5 * t)
        y = np.zeros_like(t)
        for k in range(1, 16):
            if k * freq > SR / 2.2:
                break
            y += _sweep(freq * k * vib) / k
        y = _filt(y, "lowpass", 1200 + brightness ** 2 * 8000)
        y *= _attack(t, 0.01) * _gate(t, dur, 0.1)
    return _fade_out(_norm(y))


# ---------------------------------------------------------------- fx / texture
@lru_cache(maxsize=32)
def riser(dur):
    t = _t(dur)
    k = t / dur
    f = 200 * (10 ** (k * 1.0))
    y = _sweep(f) * 0.4 + _filt(_noise(len(t), 9), "highpass", 2000) * 0.6
    y *= k ** 2
    return _fade_out(_norm(y, 0.8))


@lru_cache(maxsize=8)
def crash():
    t = _t(2.5)
    y = _filt(_noise(len(t), 10), "highpass", 4000) * np.exp(-t / 0.7)
    return _fade_out(_norm(y, 0.7))


@lru_cache(maxsize=8)
def boom():
    t = _t(2.0)
    y = _sweep(40 * (1 + 1.5 * np.exp(-t / 0.08))) * np.exp(-t / 0.6)
    return _fade_out(_norm(np.tanh(1.5 * y)))


def vinyl(n, seed=11):
    rng = np.random.default_rng(seed)
    hiss = _filt(rng.standard_normal(n), "bandpass", [1000, 9000]) * 0.08
    clicks = np.zeros(n)
    idx = rng.integers(0, n, size=max(1, n // 2500))
    clicks[idx] = rng.uniform(-1, 1, size=len(idx))
    clicks = _filt(clicks, "highpass", 1500)
    return (hiss + clicks).astype(np.float32)
