"""NumPy-only signal processing, so the engine runs on phones (no SciPy needed).

Filters are applied in the frequency domain with Butterworth magnitude responses
(zero-phase). For offline music rendering this sounds the same as IIR filtering
and is fast because it uses one FFT per call.
"""
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


def next_fast_len(n):
    """Smallest 2^a 3^b 5^c >= n (fast FFT sizes)."""
    best = 1 << max(0, int(n - 1).bit_length())
    f5 = 1
    while f5 < best:
        f35 = f5
        while f35 < best:
            f = f35
            while f < n:
                f *= 2
            best = min(best, f)
            f35 *= 3
        f5 *= 5
    return best


def butter_mag(freqs, kind, fc, order=2):
    f = np.maximum(np.abs(freqs), 1e-6)
    if kind == "lowpass":
        return 1 / np.sqrt(1 + (f / fc) ** (2 * order))
    if kind == "highpass":
        return 1 / np.sqrt(1 + (fc / f) ** (2 * order))
    if kind == "bandpass":
        lo, hi = fc
        return butter_mag(freqs, "highpass", lo, order) * butter_mag(freqs, "lowpass", hi, order)
    raise ValueError(kind)


def apply_response(x, sr, resp_fn, pad):
    """Multiply the spectrum of x (along axis 0) by resp_fn(freqs)."""
    x = np.asarray(x, dtype=np.float32)
    n = x.shape[0]
    if n == 0:
        return x
    nfft = next_fast_len(n + pad)
    X = np.fft.rfft(x, nfft, axis=0)
    H = resp_fn(np.fft.rfftfreq(nfft, 1 / sr)).astype(np.float32)
    if x.ndim > 1:
        H = H[:, None]
    return np.fft.irfft(X * H, nfft, axis=0)[:n].astype(np.float32)


def filt(x, sr, kind, freq, order=2):
    lowest = min(freq) if isinstance(freq, (list, tuple)) else freq
    pad = int(min(2 * sr, max(2048, 6 * sr / max(lowest, 1.0))))
    return apply_response(x, sr, lambda f: butter_mag(f, kind, freq, order), pad)


def biquad_mag(b, a, freqs, sr):
    z = np.exp(-1j * 2 * np.pi * freqs / sr)
    num = b[0] + b[1] * z + b[2] * z * z
    den = a[0] + a[1] * z + a[2] * z * z
    return np.abs(num / den)


def fftconvolve(a, b):
    """Full linear convolution of 1-D arrays."""
    n = len(a) + len(b) - 1
    nfft = next_fast_len(n)
    return np.fft.irfft(np.fft.rfft(a, nfft) * np.fft.rfft(b, nfft), nfft)[:n]


def onepole(x, sr, tc):
    """Causal one-pole smoother (like lfilter([1-a],[1,-a])), via an exponential kernel."""
    a = np.exp(-1 / (tc * sr))
    k = (1 - a) * a ** np.arange(int(tc * sr * 8) + 1)
    return fftconvolve(x, k)[: len(x)].astype(np.float32)


def running_min(x, size):
    """Centred running minimum (like ndimage.minimum_filter1d), O(n) van Herk/Gil-Werman."""
    x = np.asarray(x, dtype=np.float32)
    w = max(1, int(size))
    if w == 1:
        return x.copy()
    half = w // 2
    padded = np.concatenate([np.full(half, x[0]), x, np.full(w - half - 1 + w, x[-1])]).astype(np.float32)
    nb = int(np.ceil(len(padded) / w))
    padded = np.concatenate([padded, np.full(nb * w - len(padded), x[-1], np.float32)])
    blocks = padded.reshape(nb, w)
    pre = np.minimum.accumulate(blocks, axis=1).ravel()
    suf = np.minimum.accumulate(blocks[:, ::-1], axis=1)[:, ::-1].ravel()
    i = np.arange(len(x))
    return np.minimum(suf[i], pre[i + w - 1])


def moving_average(x, size):
    """Centred moving average (like ndimage.uniform_filter1d)."""
    x = np.asarray(x, dtype=np.float64)
    w = max(1, int(size))
    half = w // 2
    padded = np.concatenate([np.full(half, x[0]), x, np.full(w - half, x[-1])])
    c = np.concatenate([[0], np.cumsum(padded)])
    return ((c[w:w + len(x)] - c[:len(x)]) / w).astype(np.float32)


def median_filter_axis(S, size, axis, chunk=512):
    """Median over a window along one axis of a 2-D array (chunked to save memory)."""
    S = np.asarray(S, dtype=np.float32)
    half = size // 2
    if axis == 0:
        P = np.pad(S, ((half, size - 1 - half), (0, 0)), mode="edge")
        out = np.empty_like(S)
        for i in range(0, S.shape[0], chunk):
            win = sliding_window_view(P[i:i + chunk + size - 1], size, axis=0)
            out[i:i + chunk] = np.median(win, axis=-1)
        return out
    return median_filter_axis(S.T, size, 0, chunk).T


def resample(x, n_out):
    """Band-limited resampling to n_out samples (FFT method)."""
    x = np.asarray(x, dtype=np.float32)
    n = len(x)
    if n == n_out or n == 0:
        return x.copy()
    X = np.fft.rfft(x)
    m = n_out // 2 + 1
    Y = np.zeros(m, dtype=np.complex64)
    k = min(m, len(X))
    Y[:k] = X[:k]
    return (np.fft.irfft(Y, n_out) * (n_out / n)).astype(np.float32)


def resample_rate(x, sr_in, sr_out):
    if sr_in == sr_out:
        return np.asarray(x, dtype=np.float32)
    n_out = int(round(len(x) * sr_out / sr_in))
    if x.ndim == 1:
        return resample(x, n_out)
    return np.stack([resample(x[:, c], n_out) for c in range(x.shape[1])], axis=1)


def decimate(x, sr, q):
    y = filt(x, sr, "lowpass", 0.8 * sr / (2 * q), order=8)
    return y[::q].astype(np.float32)


def sawtooth(phase):
    return (2 * ((phase / (2 * np.pi)) % 1.0) - 1).astype(np.float32)
