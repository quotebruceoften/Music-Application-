"""Mixing and mastering effects (NumPy only)."""
import numpy as np

from . import dsp
from .synth import SR


def db(x):
    return 10 ** (x / 20.0)


def filt(x, kind, freq, order=2):
    nyq = SR / 2 * 0.98
    freq = min(max(20.0, freq), nyq)
    return dsp.filt(x, SR, kind, freq, order)


def pan_stereo(mono, pan=0.0, width=0.0):
    """Constant-power pan; `width` adds mono-safe stereo spread."""
    a = (np.clip(pan, -1, 1) + 1) * np.pi / 4
    l, r = mono * np.cos(a), mono * np.sin(a)
    if width > 0:
        d = int(0.015 * SR)
        side = np.zeros_like(mono)
        side[d:] = mono[:-d]
        side = filt(side, "highpass", 300) * width * 0.5
        l, r = l + side, r - side
    return np.stack([l, r], axis=1).astype(np.float32)


def sidechain_curve(n, kick_times, amount, release=0.12):
    g = np.ones(n, dtype=np.float32)
    if amount <= 0 or not kick_times:
        return g
    L = int(release * 4 * SR)
    tt = np.arange(L) / SR
    shape = 1 - amount * np.exp(-tt / release)
    a = int(0.003 * SR)
    shape[:a] = np.linspace(1, shape[a], a)
    for t in kick_times:
        s = int(t * SR)
        if s >= n:
            continue
        e = min(n, s + L)
        g[s:e] = np.minimum(g[s:e], shape[: e - s])
    return g


def reverb(x, size=2.0, seed=21):
    """Convolution reverb with a generated stereo room tail."""
    n = int(size * SR)
    rng = np.random.default_rng(seed)
    t = np.arange(n) / SR
    env = np.exp(-t * 6.9 / size)
    pre = int(0.02 * SR)
    out = np.zeros_like(x)
    for ch in range(2):
        ir = rng.standard_normal(n) * env
        ir = dsp.filt(ir, SR, "lowpass", 6500).astype(np.float64)
        ir[:pre] = 0
        ir /= np.sqrt(np.sum(ir ** 2))
        wet = dsp.fftconvolve(x[:, ch], ir)[: len(x)]
        out[:, ch] = wet
    return filt(out, "highpass", 200)


def delay(x, bpm, feedback=0.45, taps=6):
    """Tempo-synced dotted-eighth ping-pong delay."""
    d = int(60 / bpm * 0.75 * SR)
    out = np.zeros_like(x)
    mono = x.mean(axis=1)
    for i in range(1, taps + 1):
        s = d * i
        if s >= len(x):
            break
        ch = i % 2
        out[s:, ch] += mono[: len(x) - s] * feedback ** (i - 1)
    return filt(filt(out, "highpass", 300), "lowpass", 6000)


def compressor(x, threshold_db=-18, ratio=2.0, attack=0.01, release=0.15):
    lvl = np.max(np.abs(x), axis=1)
    # envelope follower (one-pole smoothing, single time constant blend)
    tc = (attack + release) / 2
    env = dsp.onepole(lvl, SR, tc)
    env_db = 20 * np.log10(np.maximum(env, 1e-6))
    gr = np.minimum(0, -(env_db - threshold_db) * (1 - 1 / ratio))
    return (x * db(gr)[:, None]).astype(np.float32)


def saturate(x, amount):
    if amount <= 0:
        return x
    drive = 1 + amount * 3
    wet = np.tanh(x * drive) / np.tanh(drive)
    return ((1 - amount) * x + amount * wet).astype(np.float32)


def stereo_width(x, width):
    m = (x[:, 0] + x[:, 1]) / 2
    s = (x[:, 0] - x[:, 1]) / 2 * width
    # keep the low end mono for club/phone compatibility
    s = filt(s, "highpass", 150)
    return np.stack([m + s, m - s], axis=1).astype(np.float32)


# ---------------------------------------------------------------- loudness (ITU-R BS.1770)
def _biquad_highshelf(fc, gain_db, q):
    A = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * fc / SR
    al = np.sin(w0) / (2 * q)
    c = np.cos(w0)
    b = [A * ((A + 1) + (A - 1) * c + 2 * np.sqrt(A) * al),
         -2 * A * ((A - 1) + (A + 1) * c),
         A * ((A + 1) + (A - 1) * c - 2 * np.sqrt(A) * al)]
    a = [(A + 1) - (A - 1) * c + 2 * np.sqrt(A) * al,
         2 * ((A - 1) - (A + 1) * c),
         (A + 1) - (A - 1) * c - 2 * np.sqrt(A) * al]
    return np.array(b) / a[0], np.array(a) / a[0]


def _biquad_highpass(fc, q):
    w0 = 2 * np.pi * fc / SR
    al = np.sin(w0) / (2 * q)
    c = np.cos(w0)
    b = [(1 + c) / 2, -(1 + c), (1 + c) / 2]
    a = [1 + al, -2 * c, 1 - al]
    return np.array(b) / a[0], np.array(a) / a[0]


def lufs(x):
    b1, a1 = _biquad_highshelf(1500.0, 4.0, 1 / np.sqrt(2))
    b2, a2 = _biquad_highpass(38.0, 0.5)
    y = dsp.apply_response(x, SR, lambda f: dsp.biquad_mag(b1, a1, f, SR) * dsp.biquad_mag(b2, a2, f, SR), 4096)
    blk = int(0.4 * SR)
    hop = int(0.1 * SR)
    if len(y) < blk:
        return -70.0
    sq = y.astype(np.float64) ** 2
    cs = np.concatenate([np.zeros((1, 2)), np.cumsum(sq, axis=0)])
    starts = np.arange(0, len(y) - blk + 1, hop)
    z = (cs[starts + blk] - cs[starts]) / blk
    l = -0.691 + 10 * np.log10(np.maximum(z.sum(axis=1), 1e-12))
    z = z[l > -70]
    if len(z) == 0:
        return -70.0
    rel = -0.691 + 10 * np.log10(z.sum(axis=1).mean()) - 10
    lz = -0.691 + 10 * np.log10(np.maximum(z.sum(axis=1), 1e-12))
    z = z[lz > rel]
    return float(-0.691 + 10 * np.log10(z.sum(axis=1).mean()))


def limiter(x, ceiling_db=-1.0, lookahead=0.005):
    ceil = db(ceiling_db)
    peak = np.max(np.abs(x), axis=1)
    need = np.minimum(1.0, ceil / np.maximum(peak, 1e-9))
    L = max(2, int(lookahead * SR))
    g = dsp.running_min(need, 2 * L - 1)
    g = dsp.moving_average(g, L)
    g_rel = dsp.moving_average(g, int(0.05 * SR))
    g = np.minimum(g, g_rel)
    y = x * g[:, None]
    return np.clip(y, -ceil, ceil).astype(np.float32)


def master(x, target_lufs=-14.0, ceiling_db=-1.0):
    """Hit a streaming loudness target without clipping."""
    gain = 0.0
    y = x
    for _ in range(4):
        y = limiter(x * db(gain), ceiling_db)
        cur = lufs(y)
        diff = target_lufs - cur
        if abs(diff) < 0.2:
            break
        gain += diff
    return y, lufs(y)
