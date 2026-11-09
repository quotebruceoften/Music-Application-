"""Sound synthesis: every drum and instrument is generated from scratch with numpy.

No samples are needed, so the app runs anywhere. Each function returns a mono
float32 array at SR. Results are cached, because a beat re-uses the same hits.
"""
from functools import lru_cache

import numpy as np

from . import dsp, sampler

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
# Every drum takes `var` (0, 1, 2...): small differences between hits, like a real
# player or a sampler's round-robin, so repeated hits don't sound like a machine gun.
def _var(var, seed):
    rng = np.random.default_rng(1000 * seed + var)
    return rng, 1 + (rng.uniform(-1, 1) * 0.012 if var else 0.0)


@lru_cache(maxsize=256)
def kick(sound="punchy", tune=0.0, decay=1.0, var=0):
    r = 2 ** (tune / 12)
    p = {
        # f0, body decay, pitch sweep, sweep time, click, drive
        "punchy": (50, 0.30, 4.0, 0.030, 0.55, 2.2),
        "808kick": (44, 0.85, 2.6, 0.045, 0.30, 1.6),
        "soft": (56, 0.24, 2.4, 0.022, 0.25, 1.5),
    }.get(sound, (50, 0.30, 4.0, 0.030, 0.55, 2.2))
    f0, d, sweep, tau, click, drive = p
    f0 *= r
    d *= decay
    t = _t(min(3.0, d * 5) + 0.02)
    body = _sweep(f0 * (1 + sweep * np.exp(-t / tau))) * np.exp(-t / d)
    sub = np.sin(TWO_PI * f0 * t) * (1 - np.exp(-t / 0.02)) * np.exp(-t / (d * 1.1)) * 0.15
    beater = np.sin(TWO_PI * 2800 * t) * np.exp(-t / 0.0025) * 0.3
    c = _filt(_noise(len(t), 1 + var), "bandpass", [1200, 9000]) * np.exp(-t / 0.003) * click
    y = np.tanh(drive * (body + sub + beater + c)) / np.tanh(drive)
    return _fade_out(_norm(y))


@lru_cache(maxsize=256)
def snare(sound="tight", tune=0.0, decay=1.0, var=0):
    rng, j = _var(var, 2)
    r = 2 ** (tune / 12) * j
    f, d = (190, 0.15) if sound == "tight" else (165, 0.24)
    f *= r
    d *= decay
    t = _t(d * 5 + 0.02)
    shell = (np.sin(TWO_PI * f * t * (1 + 0.5 * np.exp(-t / 0.008)))
             + 0.55 * np.sin(TWO_PI * f * 1.72 * t)) * np.exp(-t / 0.055)
    wires = _filt(_noise(len(t), 20 + var), "bandpass", [1500 * r, 11000]) * np.exp(-t / d)
    crack = _filt(_noise(len(t), 40 + var), "highpass", 4000) * np.exp(-t / 0.004)
    y = np.tanh(1.6 * (0.55 * shell + 0.85 * wires + 0.5 * crack))
    return _fade_out(_norm(y))


@lru_cache(maxsize=256)
def clap(sound="clap", tune=0.0, decay=1.0, var=0):
    r = 2 ** (tune / 12)
    t = _t(0.8 * decay + 0.1)
    n = _filt(_noise(len(t), 3 + var), "bandpass", [900 * r, 4200 * r])
    env = np.zeros_like(t)
    rng, _ = _var(var, 3)
    offs = [0.0] + list(np.cumsum(rng.uniform(0.008, 0.013, 2)))
    for off in offs:
        e = np.where(t >= off, np.exp(-(t - off) / 0.006), 0)
        env = np.maximum(env, e)
    tail = np.where(t >= offs[-1], np.exp(-(t - offs[-1]) / (0.13 * decay)), 0)
    y = n * np.maximum(env, tail * 0.75)
    takes = sampler.hits("clap")
    if takes:  # layer real hand claps under the electronic one
        real = _repitch_hit(takes[var % len(takes)], r)
        m = min(len(real), len(y))
        y = _norm(y) * 0.7
        y[:m] += _norm(real[:m]) * 0.6 * np.exp(-t[:m] / (0.25 * decay))
    return _fade_out(_norm(y))


@lru_cache(maxsize=256)
def hat(open_=False, tune=0.0, decay=1.0, var=0):
    rng, j = _var(var, 4)
    r = 2 ** (tune / 12) * j
    d = (0.30 if open_ else 0.042) * decay * (1 + (rng.uniform(-0.12, 0.12) if var else 0))
    t = _t(d * 5 + 0.01)
    # six detuned square waves: the classic analog-machine metal sound
    metal = sum(np.sign(np.sin(TWO_PI * f * r * t + rng.uniform(0, 6.28)))
                for f in (205.3, 304.4, 369.6, 522.7, 540.0, 800.0))
    x = metal * 0.45 + _noise(len(t), 4 + var) * 0.5
    x = _filt(x, "bandpass", [6500 * min(r, 1.6), 16000], order=3)
    env = np.exp(-t / d) * (1 - np.exp(-t / 0.0008))
    return _fade_out(_norm(x * env))


def _repitch_hit(y, r):
    if abs(r - 1) < 1e-3:
        return y.copy()
    n = int(len(y) / r)
    return np.interp(np.arange(n) * r, np.arange(len(y)), y).astype(np.float32)


def _recorded(name, tune, decay, var):
    takes = sampler.hits(name)
    if not takes:
        return None
    y = _repitch_hit(takes[var % len(takes)], 2 ** (tune / 12))
    if decay != 1.0:
        t = np.arange(len(y)) / SR
        y = y * np.exp(-t * max(0.0, 1 / decay - 1) * 6)
    return _fade_out(_norm(y))


@lru_cache(maxsize=256)
def shaker(sound="shaker", tune=0.0, decay=1.0, var=0):
    y = _recorded("shaker", tune, decay, var)
    if y is not None:
        return y
    r = 2 ** (tune / 12)
    t = _t(0.35 * decay + 0.02)
    n = _filt(_noise(len(t), 5 + var), "bandpass", [4500 * r, 13000])
    env = (1 - np.exp(-t / 0.008)) * np.exp(-t / (0.05 * decay))
    return _fade_out(_norm(n * env))


@lru_cache(maxsize=256)
def perc(sound="rim", tune=0.0, decay=1.0, var=0):
    if sound in ("conga", "bongo", "cowbell", "wood", "tambourine"):
        y = _recorded(sound, tune, decay, var)
        if y is not None:
            return y
    r = 2 ** (tune / 12)
    if sound in ("conga", "bongo"):
        t = _t(0.18 * decay * 5)
        y = _sweep(320 * r * (1 + 0.3 * np.exp(-t / 0.02)) * 0.72) * np.exp(-t / (0.18 * decay))
    elif sound == "wood":
        t = _t(0.03 * decay * 6)
        e = np.exp(-t / (0.03 * decay))
        y = (np.sin(TWO_PI * 900 * r * t) + 0.5 * np.sin(TWO_PI * 2400 * r * t)) * e
    elif sound in ("cowbell", "tambourine"):
        t = _t(0.12 * decay * 5)
        sq = np.sign(np.sin(TWO_PI * 540 * r * t)) + np.sign(np.sin(TWO_PI * 800 * r * t))
        y = _filt(sq, "bandpass", [500 * r, 3000 * r]) * np.exp(-t / (0.12 * decay))
    else:  # rim
        rng, j = _var(var, 6)
        r *= j
        t = _t(0.06 * decay * 4 + 0.01)
        e = np.exp(-t / (0.012 * decay))
        y = (np.sin(TWO_PI * 1750 * r * t) + 0.6 * np.sin(TWO_PI * 480 * r * t)) * e
        y += _filt(_noise(len(t), 6 + var), "bandpass", [2000, 8000]) * np.exp(-t / 0.004) * 0.5
    return _fade_out(_norm(y))


# ---------------------------------------------------------------- plucked string
def _ks(freq, length, decay_s=1.0, bright=0.6, seed=0):
    """Karplus-Strong plucked string, computed one delay-line period at a time."""
    n_total = max(1, int(length * SR))
    period = max(2, int(round(SR / freq)))
    frac = SR / freq - period
    rng = np.random.default_rng(seed)
    exc = rng.uniform(-1, 1, period)
    exc = _filt(np.tile(exc, 4), "lowpass", 800 + bright ** 2 * 9000)[:period]  # softer pick
    # loss per period so the note decays by 60 dB in about decay_s seconds
    g = 10 ** (-3 / (decay_s * freq))
    out = np.zeros(n_total + period + 1)
    out[:period] = exc
    pos = period
    a = 0.5 + 0.35 * (1 - bright)  # more averaging = darker string
    while pos < len(out) - 1:
        end = min(len(out) - 1, pos + period)
        k = end - pos
        prev = out[pos - period: pos - period + k + 1]
        out[pos:end] = g * (a * prev[:k] + (1 - a) * prev[1:k + 1])
        pos = end
    y = out[:n_total]
    if frac > 0.01:  # fine-tune the pitch the delay line can't hit exactly
        y = np.interp(np.arange(n_total) * (period / (period + frac)), np.arange(n_total), y)
    return y


# ---------------------------------------------------------------- bass
@lru_cache(maxsize=1024)
def bass_note(sound, freq, dur, decay=1.0, start_freq=0.0, glide_time=0.0):
    if sound == "logdrum":
        # The amapiano log drum: a pitched, bouncy, slightly distorted thump.
        length = min(dur, 1.4 * decay) + 0.05
        t = _t(length)
        ph = np.cumsum(freq * (1 + 1.4 * np.exp(-t / 0.03))) / SR * TWO_PI
        y = np.sin(ph) + 0.45 * np.sin(2 * ph + 0.6) + 0.2 * np.sin(3 * ph)
        knock = _filt(_noise(len(t), 30), "bandpass", [freq * 3, freq * 12]) * np.exp(-t / 0.012) * 0.35
        y = (y + knock) * np.exp(-t / (0.3 * decay)) * _gate(t, length - 0.04, 0.02)
        y = _filt(np.tanh(3.0 * y), "lowpass", 2400)
        y += np.sin(TWO_PI * freq * t) * np.exp(-t / (0.35 * decay)) * 0.2 * _gate(t, length - 0.04, 0.02)
    elif sound == "808":
        length = dur + 0.1
        t = _t(length)
        if start_freq > 0 and glide_time > 0:
            k = np.clip(t / glide_time, 0, 1)
            f = start_freq * (freq / start_freq) ** k
        else:
            f = freq * (1 + 0.4 * np.exp(-t / 0.02))
        y = _sweep(f) * np.exp(-t / (1.2 * decay)) * _gate(t, dur, 0.05)
        y += np.sin(TWO_PI * 2800 * t) * np.exp(-t / 0.002) * 0.15  # attack click
        y = np.tanh(2.6 * y) / np.tanh(2.6)
    elif sound == "pluck":
        length = min(dur, 2.0) + 0.06
        t = _t(length)
        y = _ks(freq, length, 0.9 * decay, 0.45) + 0.4 * np.sin(TWO_PI * freq * t) * np.exp(-t / (0.6 * decay))
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


def _supersaw(freq, t, voices=7, spread=18.0, seed=0):
    rng = np.random.default_rng(seed)
    y = np.zeros_like(t)
    for i in range(voices):
        cents = (i - (voices - 1) / 2) / ((voices - 1) / 2) * spread
        f = freq * 2 ** (cents / 1200)
        y += 2 * ((f * t + rng.uniform()) % 1.0) - 1
    return y / np.sqrt(voices)


@lru_cache(maxsize=2048)
def tone_note(sound, freq, dur, brightness=0.6):
    """Chord and melody instruments: recorded ones where possible, modelled synths otherwise."""
    if sound in sampler.pitched_names():
        return _fade_out(_norm(sampler.note(sound, freq, dur, brightness)))
    if sound == "piano":  # fallback if the samples are missing
        t = _t(min(dur, 4.0) + 0.3)
        y = _additive(freq, t, 10, lambda k: 1 / k ** 1.3, lambda k: 1.8 / k ** 0.5, 0.0004)
        y *= _gate(t, dur, 0.15)
    elif sound == "rhodes":
        # electric piano: a tine (FM pair) whose bark depends on brightness, plus a
        # low "body" partial, the tine ping, tremolo and a touch of amp warmth
        t = _t(min(dur, 4.0) + 0.4)
        low = np.clip(1.5 - np.log2(freq / 130.0) * 0.25, 0.6, 1.6)
        idx = (0.4 + 1.4 * brightness) * np.exp(-t / 0.18) + 0.25
        y = np.zeros_like(t)
        for cents, amp in ((-3, 0.5), (3, 0.5)):  # gentle chorus
            f = freq * 2 ** (cents / 1200)
            y += amp * np.sin(TWO_PI * f * t + idx * np.sin(TWO_PI * f * t))
        y *= np.exp(-t / (1.4 * low))
        y += 0.25 * np.sin(TWO_PI * freq * 2 * t) * np.exp(-t / 0.5)
        y += 0.08 * np.sin(TWO_PI * freq * 14.1 * t) * np.exp(-t / 0.02)  # tine ping
        y *= 1 - 0.12 * (1 - np.cos(TWO_PI * 4.6 * t)) / 2  # tremolo
        y = np.tanh(1.4 * y) * _attack(t, 0.002) * _gate(t, dur, 0.18)
    elif sound == "pad":
        t = _t(dur + 0.9)
        y = _supersaw(freq, t, 7, 14, seed=int(freq))
        y = y + 0.5 * np.sin(TWO_PI * freq / 2 * t)  # warmth from a sub octave
        y = _filt(y, "lowpass", 400 + brightness ** 2 * 4500)
        y *= _attack(t, 0.35) * _gate(t, dur, 0.8)
    elif sound == "organ":
        t = _t(dur + 0.15)
        rot = 1 + 0.004 * np.sin(TWO_PI * 6.2 * t)  # rotating-speaker wobble
        y = sum(a * _sweep(freq * m * rot) for m, a in ((0.5, 0.5), (1, 1), (2, 0.7), (3, 0.35), (4, 0.25), (6, 0.12)))
        y *= 1 - 0.15 * (1 - np.cos(TWO_PI * 6.2 * t)) / 2
        y += _filt(_noise(len(t), 12), "bandpass", [1500, 6000]) * np.exp(-t / 0.004) * 0.3  # key click
        y = np.tanh(1.3 * y)
        y *= _attack(t, 0.006) * _gate(t, dur, 0.08)
    elif sound == "pluck":
        t = _t(min(dur, 2.5) + 0.2)
        y = _ks(freq, len(t) / SR, 1.2, brightness, seed=int(freq))
        y *= _gate(t, dur, 0.12)
    elif sound == "bell":
        # soft FM bell: two carriers so it sounds like a struck bar, not a ringtone beep
        t = _t(min(dur, 3.0) + 1.0)
        idx = (1.2 + brightness) * np.exp(-t / 0.25)
        y = np.sin(TWO_PI * freq * t + idx * np.sin(TWO_PI * freq * 3.5 * t)) * np.exp(-t / 1.4)
        y += 0.4 * np.sin(TWO_PI * freq * t + 0.8 * np.sin(TWO_PI * freq * t)) * np.exp(-t / 0.6)
        y += 0.15 * np.sin(TWO_PI * freq * 2.76 * t) * np.exp(-t / 0.3)
        y *= _attack(t, 0.0015) * _gate(t, dur + 0.5, 0.35)
    elif sound == "flute":  # fallback if the samples are missing
        t = _t(dur + 0.15)
        vib = 1 + 0.006 * np.sin(TWO_PI * 5 * t) * np.clip((t - 0.2) / 0.3, 0, 1)
        y = _sweep(freq * vib) + 0.2 * _sweep(2 * freq * vib)
        y += _filt(_noise(len(t), 8), "bandpass", [freq * 0.8, freq * 3]) * 0.25
        y *= _attack(t, 0.06) * _gate(t, dur, 0.12)
    elif sound == "marimba":  # fallback if the samples are missing
        t = _t(min(dur, 1.5) + 0.5)
        y = np.sin(TWO_PI * freq * t) * np.exp(-t / 0.4)
        y += 0.3 * np.sin(TWO_PI * freq * 4 * t) * np.exp(-t / 0.06)
    else:  # lead: detuned saws with a filter that opens on each note
        t = _t(dur + 0.15)
        vib = 1 + 0.004 * np.sin(TWO_PI * 5.5 * t) * np.clip((t - 0.25) / 0.3, 0, 1)
        y = np.zeros_like(t)
        for cents in (-7, 0, 7):
            f = freq * 2 ** (cents / 1200) * vib
            ph = np.cumsum(f) / SR
            y += 2 * (ph % 1.0) - 1
        y = y / 3 + 0.3 * np.sign(np.sin(TWO_PI * freq / 2 * t))
        cutoff = 700 + brightness ** 2 * 6000
        y = 0.6 * _filt(y, "lowpass", cutoff) + 0.4 * _filt(y, "lowpass", cutoff * 2.5) * np.exp(-t / 0.15)
        y *= _attack(t, 0.008) * _gate(t, dur, 0.12)
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
