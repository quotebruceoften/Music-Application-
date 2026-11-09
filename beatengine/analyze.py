"""Listen to reference songs and pull out their musical DNA.

Only high-level traits are extracted: tempo, key, drum groove, chord movement,
swing, energy and tone. No audio or melody is copied into the new beat.
"""
import os
import re
import shutil
import subprocess
import urllib.request

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from . import dsp, media, theory
from .presets import get_preset

SR = 22050
N_FFT = 2048
HOP = 256
FPS = SR / HOP
MAX_SECONDS = 210

MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

GENRE_TEMPO = {"amapiano": 113, "trap": 140, "afrohouse": 122, "lofi": 85}


# ================================================================ loading
def load_audio(path):
    # Long songs: analyse a window from the middle (the intro is rarely typical).
    max_s = float(os.environ.get("BEATMAKER_MAX_ANALYSIS_S", MAX_SECONDS))
    dur = media.duration(path)
    start = max(0.0, (dur - max_s) / 2) if dur and dur > max_s else 0.0
    x = media.load_mono(path, SR, max_s=max_s, start_s=start)
    if len(x) == 0:
        raise ValueError("Couldn't find any audio in that file.")
    if len(x) < SR * 6:
        raise ValueError("That clip is shorter than 6 seconds, which is too short to read a groove from.")
    return x


STREAMING = ("open.spotify.com", "music.apple.com", "deezer.com", "tidal.com", "music.amazon",
             "tiktok.com/music/")  # TikTok sound pages: find the original song by name
AUDIO_EXT = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".webm", ".mp4", ".mov")
UA = {"User-Agent": "Mozilla/5.0 (BeatMaker)"}


def _ytdlp():
    exe = shutil.which("yt-dlp")
    if exe:
        return [exe]
    try:
        import yt_dlp  # noqa: F401
        import sys
        return [sys.executable, "-m", "yt_dlp"]
    except ImportError:
        return None


def _page_title(url):
    req = urllib.request.Request(url, headers=UA)
    html = urllib.request.urlopen(req, timeout=15).read(400_000).decode("utf-8", "ignore")
    m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html) or \
        re.search(r"<title>([^<]+)</title>", html)
    if not m:
        return None
    title = m.group(1)
    desc = re.search(r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"', html)
    if desc and "spotify" in url:  # Spotify puts the artist in the description
        title += " " + desc.group(1).split("·")[0]
    return re.sub(r"\s+", " ", title).strip()


def fetch_link(url, folder):
    """Download a song's audio for analysis. Returns (path, display_name)."""
    url = url.strip()
    if not re.match(r"^https?://", url):
        raise ValueError("Paste a full link starting with http:// or https://")
    low = url.lower().split("?")[0]

    if low.endswith(AUDIO_EXT):
        name = low.rsplit("/", 1)[-1]
        path = f"{folder}/link{name[name.rfind('.'):]}"
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r, open(path, "wb") as f:
            f.write(r.read(80_000_000))
        return path, name

    if os.environ.get("BEATMAKER_ALLOW_LINKS", "1") != "1":
        raise RuntimeError("Song links are turned off in this version. Upload the song or video file instead.")
    target = url
    if any(s in low for s in STREAMING):
        # Streaming services lock their audio, so find the same song by name instead.
        title = _page_title(url)
        if not title:
            raise ValueError("Couldn't read the song name from that link. Try uploading the file instead.")
        target = f"ytsearch1:{title}"

    try:
        import yt_dlp  # used as a library so it also works inside the phone app
    except ImportError:
        yt_dlp = None
    if yt_dlp is not None:
        opts = {"format": "bestaudio/best", "noplaylist": True, "quiet": True, "no_warnings": True,
                "max_filesize": 80_000_000, "outtmpl": f"{folder}/%(id)s.%(ext)s",
                "match_filter": yt_dlp.utils.match_filter_func("duration < 1200")}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(target, download=True)
                if info and info.get("entries"):
                    info = info["entries"][0]
                reqs = (info or {}).get("requested_downloads") or []
                path = reqs[0].get("filepath") if reqs else ydl.prepare_filename(info)
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"Couldn't get audio from that link. {str(e)[:200]}")
        if not path or not os.path.exists(path):
            raise ValueError("Couldn't get audio from that link.")
        return path, info.get("title") or "linked song"

    ytdlp = _ytdlp()
    if not ytdlp:
        raise RuntimeError("To use links from TikTok, YouTube, Instagram, SoundCloud, Spotify and others, install yt-dlp "
                           "(pip install yt-dlp). Direct links to .mp3/.wav files and uploads work without it.")
    cmd = ytdlp + ["-f", "bestaudio/best", "--no-playlist", "--max-filesize", "80M",
                   "--match-filter", "duration < 1200", "--print", "after_move:filepath",
                   "--print", "title", "-o", f"{folder}/%(id)s.%(ext)s", target]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    lines = [l for l in p.stdout.strip().splitlines() if l.strip()]
    if p.returncode != 0 or len(lines) < 2:
        err = (p.stderr or "").strip().splitlines()
        raise ValueError("Couldn't get audio from that link. " + (err[-1][:200] if err else ""))
    title, path = lines[0], lines[-1]
    return path, title


# ================================================================ features
def _spectrogram(x):
    pad = np.concatenate([np.zeros(N_FFT // 2, np.float32), x, np.zeros(N_FFT // 2, np.float32)])
    frames = sliding_window_view(pad, N_FFT)[::HOP]
    win = np.hanning(N_FFT).astype(np.float32)
    out = np.empty((len(frames), N_FFT // 2 + 1), np.float32)
    for i in range(0, len(frames), 2048):  # chunked to keep memory low
        out[i:i + 2048] = np.abs(np.fft.rfft(frames[i:i + 2048] * win, axis=1))
    return out


def _pitch_spectrogram(x, n_frames):
    """High-resolution (1.35 Hz) sustained-note spectrogram for reading bass, chords and key."""
    y = dsp.decimate(x, SR, 4)  # 5512.5 Hz
    sr, nfft, hop = SR / 4, 4096, HOP // 4
    pad = np.concatenate([np.zeros(nfft // 2, np.float32), y, np.zeros(nfft // 2, np.float32)])
    frames = sliding_window_view(pad, nfft)[::hop][:n_frames]
    freqs = np.fft.rfftfreq(nfft, 1 / sr)
    keep = (freqs >= 27) & (freqs <= 2000)
    win = np.hanning(nfft).astype(np.float32)
    out = np.empty((len(frames), keep.sum()), np.float32)
    for i in range(0, len(frames), 1024):
        out[i:i + 1024] = np.abs(np.fft.rfft(frames[i:i + 1024] * win, axis=1))[:, keep]
    out = dsp.median_filter_axis(out, 17, axis=0)  # keep sustained notes, drop drum hits
    return out, freqs[keep]


def _bass_chroma(Sp, fp, block_s=4.0):
    """Bass notes. Pitches that never change (the kick drum's tone) are removed block by block."""
    band = (fp >= 28) & (fp <= 260)
    X = Sp[:, band].copy()
    blk = int(block_s * FPS)
    for i in range(0, len(X), blk):
        seg = X[i:i + blk]
        seg -= np.median(seg, axis=0)
    X = np.maximum(X, 0)
    pcs = (np.round(69 + 12 * np.log2(fp[band] / 440)) % 12).astype(int)
    M = np.zeros((band.sum(), 12), np.float32)
    M[np.arange(band.sum()), pcs] = 1
    C = np.sqrt(X) @ M
    return C / (C.sum(axis=1, keepdims=True) + 1e-9)


def _onset_env(logS, freqs, lo, hi):
    band = (freqs >= lo) & (freqs < hi)
    d = np.maximum(0, np.diff(logS[:, band], axis=0)).sum(axis=1)
    d = np.concatenate([[0], d])
    k = int(FPS)  # remove slow loudness changes
    local = np.convolve(d, np.ones(k) / k, mode="same")
    d = np.maximum(0, d - local)
    return d / (d.std() + 1e-9)


def _tempo(env):
    e = env - env.mean()
    n = len(e)
    ac = np.fft.irfft(np.abs(np.fft.rfft(e, 2 * n)) ** 2)[:n]
    ac /= ac[0] + 1e-9
    bpms = np.arange(60, 180.01, 0.25)

    def at(lag):
        return np.interp(lag, np.arange(n), ac)

    lags = 60 * FPS / bpms
    score = at(lags) + 0.5 * at(2 * lags) + 0.25 * at(4 * lags)
    prior = np.exp(-0.5 * (np.log2(bpms / 115) / 0.9) ** 2)
    coarse = bpms[np.argmax(score * prior)]

    # refine tempo and beat phase with a comb over the onset envelope
    best = (-1, coarse, 0.0)
    t = np.arange(n) / FPS
    for bpm in np.arange(coarse - 1.5, coarse + 1.51, 0.05):
        period = 60 / bpm
        beats = np.arange(0, t[-1] - period, period)
        for ph in np.linspace(0, period, 48, endpoint=False):
            idx = ((beats + ph) * FPS).astype(int)
            idx = idx[idx < n]
            s = env[idx].mean()
            if s > best[0]:
                best = (s, bpm, ph)
    return float(best[1]), float(best[2])


def _grid_values(env, times, step):
    """Strongest onset around each 16th step; the window leans late to catch swing."""
    out = np.zeros(len(times))
    offs = np.zeros(len(times))
    for i, t in enumerate(times):
        lo = t - min(0.3 * step, 0.035)
        hi = t + min(0.45 * step, 0.065)
        a, b = int(lo * FPS), int(hi * FPS) + 1
        if a < 0 or b > len(env):
            continue
        seg = env[a:b]
        j = int(np.argmax(seg))
        out[i] = seg[j]
        offs[i] = (a + j) / FPS - t
    return out, offs


def _to_pattern(prof, x_th=0.6, o_th=0.33):
    return "".join("x" if v >= x_th else "o" if v >= o_th else "." for v in prof)


def _chroma(S, freqs, lo=100, hi=2000):
    band = (freqs >= lo) & (freqs <= hi)
    pcs = (np.round(69 + 12 * np.log2(freqs[band] / 440)) % 12).astype(int)
    M = np.zeros((band.sum(), 12), np.float32)
    M[np.arange(band.sum()), pcs] = 1
    C = np.sqrt(S[:, band]) @ M
    return C / (C.sum(axis=1, keepdims=True) + 1e-9)


def _key_scores(chroma_mean):
    c = (chroma_mean - chroma_mean.mean()) / (chroma_mean.std() + 1e-9)
    scores = []
    for prof in (MAJOR, MINOR):
        p = (prof - prof.mean()) / prof.std()
        for k in range(12):
            scores.append(float(np.dot(c, np.roll(p, k)) / 12))
    return np.array(scores)  # 0-11 major, 12-23 minor


def _progression(bar_chroma, key, scale, bar_bass=None):
    if len(bar_chroma) < 4:
        return None, 0.0
    degs, fits = [], []
    for bi, ch in enumerate(bar_chroma):
        best, fit = 1, -9
        for d in range(1, 8):
            pcs = theory.chord_pcs(key, scale, d, "triad")
            tmpl = np.full(12, -0.25)
            tmpl[pcs] = 1.0
            tmpl[pcs[0]] = 1.3
            f = float(np.dot(ch, tmpl))
            if bar_bass is not None:
                f += 0.6 * float(bar_bass[bi][pcs[0]])  # the bass usually plays the root
            if f > fit:
                best, fit = d, f
        degs.append(best)
        fits.append(fit)
    counts = {}
    for L in (4, 2):
        for i in range(0, len(degs) - L + 1, L):
            g = tuple(degs[i:i + L])
            counts[g] = counts.get(g, 0) + 1
        top = max((g for g in counts if len(g) == L), key=lambda g: counts[g], default=None)
        if top and counts[top] >= 2:
            conf = min(1.0, counts[top] * L / len(degs))
            prog = list(top)
            if len(set(prog)) == 1:
                continue
            return prog, round(conf, 2)
    return None, 0.0


def _genre_scores(bpm, kick, hat, swing, energy):
    four_floor = float(min(kick[0], kick[4], kick[8], kick[12]))
    hat_busy = float((hat >= 0.33).sum()) / 16

    def tempo_fit(center, width):
        best = min(abs(c - center) for c in (bpm, bpm * 2, bpm / 2))
        return np.exp(-0.5 * (best / width) ** 2)

    return {
        "amapiano": tempo_fit(113, 5) * 1.0 + 0.4 * hat_busy + 0.2 * swing,
        "trap": tempo_fit(140, 10) * 1.0 + 0.4 * hat_busy + 0.4 * (1 - four_floor),
        "afrohouse": tempo_fit(122, 4) * 1.0 + 0.9 * four_floor,
        "lofi": tempo_fit(85, 9) * 1.0 + 0.5 * swing + 0.4 * (1 - energy),
    }


def _groove(env_low, env_mid, env_high, bpm, phase, dur, force_r=None):
    step = 60 / bpm / 4
    times = np.arange(phase % step, dur - step, step)
    n_bars = len(times) // 16 - 1
    if n_bars < 1:
        raise ValueError("That song is too short to read a groove from.")
    lows, offl = _grid_values(env_low, times, step)
    mids, offm = _grid_values(env_mid, times, step)
    highs, offh = _grid_values(env_high, times, step)

    def profile(v, r):
        bars = v[r:r + n_bars * 16].reshape(n_bars, 16)
        w = bars.sum(axis=1)
        w = (w > np.percentile(w, 30)).astype(float) + 1e-6  # ignore quiet intros/breaks
        p = (bars * w[:, None]).sum(axis=0) / w.sum()
        return p / (p.max() + 1e-9)

    # find the downbeat at any 16th: kick on 1, snare/clap on 2 and 4 (or 3 for half-time)
    def rot_score(r):
        k, sn = profile(lows, r), profile(mids, r)
        return (2 * k[0] + 0.5 * k[8] + 0.3 * (k[4] + k[12]) - 0.4 * (k[1] + k[15])
                + max(sn[4] + sn[12], 1.6 * sn[8]) - 0.6 * sn[0])

    drum_scores = np.array([rot_score(i) for i in range(16)])
    r = int(np.argmax(drum_scores)) if force_r is None else force_r
    kick, snare, hat = profile(lows, r), profile(mids, r), profile(highs, r)

    # swing: how much later the off-16ths land than the on-16ths, vs. a full triplet push
    idx = np.arange(len(times))
    odd = (idx - r) % 2 == 1
    def late(offs, vals, mask):
        m = mask & (vals > np.percentile(vals, 60))
        return float(np.average(offs[m], weights=vals[m])) if m.any() else 0.0
    shift = []
    for offs, vals in ((offh, highs), (offm, mids)):
        if vals[odd].sum() > 0.15 * vals.sum():
            shift.append(late(offs, vals, odd) - late(offs, vals, ~odd))
    raw = np.mean(shift) / (step / 3) if shift else 0.0
    swing = float(np.clip((raw - 0.1) * 1.25, 0, 1))  # calibrated on beats with known swing
    return {"step": step, "times": times, "r": r, "kick": kick, "snare": snare,
            "hat": hat, "swing": swing, "drum_scores": drum_scores}


def _bar_change_score(C, times, step, r):
    """How well chord changes line up with bar lines if bars start at offset r."""
    half = int(8 * step * FPS)
    within, across = [], []
    starts = times[r::16]
    for t0, t1 in zip(starts[:-1], starts[1:]):
        a, m, b = int(t0 * FPS), int((t0 + 8 * step) * FPS), int(t1 * FPS)
        if b + half > len(C):
            break
        h1, h2, n1 = C[a:m].mean(0), C[m:b].mean(0), C[b:b + half].mean(0)
        cos = lambda u, v: float(u @ v / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-9))
        within.append(cos(h1, h2))
        across.append(cos(h2, n1))
    return float(np.mean(within) - np.mean(across)) if within else 0.0


def analyze(path, name="song"):
    x = load_audio(path)
    x = x / (np.max(np.abs(x)) + 1e-9)
    S = _spectrogram(x)
    freqs = np.fft.rfftfreq(N_FFT, 1 / SR)
    # split into sustained (notes, chords) and percussive (drums) layers
    H = dsp.median_filter_axis(S, 17, axis=0)
    P = dsp.median_filter_axis(S, 17, axis=1)
    hmask = H ** 2 / (H ** 2 + P ** 2 + 1e-12)
    S_harm, S_perc = S * hmask, S * (1 - hmask)
    del H, P, hmask
    logS = np.log1p(100 * S_perc / (S_perc.max() + 1e-9))

    env_all = _onset_env(logS, freqs, 30, 11000)
    env_low = _onset_env(logS, freqs, 35, 150)
    env_mid = _onset_env(logS, freqs, 1000, 4500)
    env_high = _onset_env(logS, freqs, 6500, 11000)

    bpm, phase = _tempo(env_all)
    dur = len(x) / SR
    g = _groove(env_low, env_mid, env_high, bpm, phase, dur)
    gscores = _genre_scores(bpm, g["kick"], g["hat"], g["swing"], 0.6)
    genre = max(gscores, key=gscores.get)
    near = _near(bpm, GENRE_TEMPO[genre])
    if abs(near - bpm) > 1:  # e.g. trap read at half-time: re-grid at full tempo
        bpm = near
        g = _groove(env_low, env_mid, env_high, bpm, phase, dur)
    step, times, r = g["step"], g["times"], g["r"]
    kick, snare, hat, swing = g["kick"], g["snare"], g["hat"], g["swing"]

    # key and chords
    C = _chroma(S_harm, freqs, 100, 2000)
    Sp, fp = _pitch_spectrogram(x, len(S))
    Cb = _bass_chroma(Sp, fp)

    # drums can't always tell beat 1 from beat 3; chord changes on bar lines can
    harm = np.hstack([C, Cb])
    cands = [(r + k) % 16 for k in (0, 4, 8, 12)]
    ds = np.array([g["drum_scores"][c] for c in cands])
    hs = np.array([_bar_change_score(harm, times, step, c) for c in cands])
    total = (ds - ds.max()) / (np.ptp(ds) + 1e-9) + 0.8 * (hs - hs.max()) / (np.ptp(hs) + 1e-9)
    best = cands[int(np.argmax(total))]
    if best != r:
        g = _groove(env_low, env_mid, env_high, bpm, phase, dur, force_r=best)
        r, kick, snare, hat, swing = g["r"], g["kick"], g["snare"], g["hat"], g["swing"]
    kscores = _key_scores(C.mean(axis=0))
    # relative major/minor share the same notes: let the bass decide which is home
    bass = Cb.mean(axis=0)
    bass = bass / (bass.max() + 1e-9)
    ki = int(np.argmax(kscores))
    rel = (ki % 12 + 9) % 12 + 12 if ki < 12 else (ki % 12 + 3) % 12
    if kscores[rel] + 0.3 * bass[rel % 12] > kscores[ki] + 0.3 * bass[ki % 12]:
        kscores[rel], kscores[ki] = kscores[ki] + 1e-3, kscores[rel]
        ki = rel
    key, scale = theory.NOTE_NAMES[ki % 12], ("major" if ki < 12 else "minor")
    bar_starts = times[r::16]
    bar_chroma, bar_bass = [], []
    for t0 in bar_starts:
        a, b = int(t0 * FPS), int((t0 + 16 * step) * FPS)
        if b <= len(C):
            bar_chroma.append(C[a:b].mean(axis=0))
            bb = Cb[a:b].mean(axis=0)
            bar_bass.append(bb / (bb.max() + 1e-9))
    prog, prog_conf = _progression(bar_chroma, key, scale, bar_bass)
    # Relative keys share notes; the chord a loop starts on is usually "home".
    if prog and scale == "major" and prog[0] == 6:
        key, scale = theory.NOTE_NAMES[(theory.key_pc(key) + 9) % 12], "minor"
        prog = [(d - 6) % 7 + 1 for d in prog]
    elif prog and scale == "minor" and prog[0] == 3:
        key, scale = theory.NOTE_NAMES[(theory.key_pc(key) + 3) % 12], "major"
        prog = [(d - 3) % 7 + 1 for d in prog]
    ki = theory.key_pc(key) + (0 if scale == "major" else 12)
    if int(np.argmax(kscores)) != ki:  # keep the scores consistent for blending
        kscores[ki] = kscores.max() + 1e-3

    # energy and tone
    rms_db = 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)
    density = float((np.maximum.reduce([kick, snare, hat]) >= 0.33).sum()) / 16
    energy = float(np.clip(0.5 * np.clip((rms_db + 24) / 14, 0, 1) + 0.5 * density, 0.1, 1))
    mag = S.mean(axis=0)
    centroid = float((freqs * mag).sum() / (mag.sum() + 1e-9))
    brightness = float(np.clip(np.log2(max(centroid, 1) / 800) / 2.5, 0, 1))
    low_share = float(mag[freqs < 120].sum() / (mag.sum() + 1e-9))

    gscores = _genre_scores(bpm, kick, hat, swing, energy)
    genre = max(gscores, key=gscores.get)

    return {
        "name": name,
        "duration": round(dur, 1),
        "bpm": round(bpm, 1),
        "key": key, "scale": scale,
        "key_scores": [round(v, 4) for v in kscores],
        "swing": round(swing, 2), "energy": round(energy, 2),
        "brightness": round(brightness, 2), "low_share": round(low_share, 3),
        "progression": prog, "progression_confidence": prog_conf,
        "profiles": {"kick": [round(v, 3) for v in kick], "snare": [round(v, 3) for v in snare],
                     "hat": [round(v, 3) for v in hat]},
        "patterns": {"kick": _to_pattern(kick), "snare": _to_pattern(snare, 0.65, 0.4),
                     "hat": _to_pattern(hat, 0.55, 0.25)},
        "genre": genre, "genre_scores": {k: round(float(v), 3) for k, v in gscores.items()},
    }


def summary(a):
    short = " · short clip" if a.get("duration", 99) < 40 else ""
    return f"{a['bpm']:g} BPM · {a['key']} {a['scale']} · {a['genre']} feel{short}"


# ================================================================ blending into settings
USE_KEYS = ("style", "tempo", "key", "groove", "chords", "feel", "tone")


def _near(bpm, ref, tol=None):
    """Double/halve a tempo to sit near `ref` (only if that lands within `tol` octaves)."""
    best = min((bpm, bpm * 2, bpm / 2), key=lambda b: abs(np.log2(b / ref)))
    if tol is not None and best != bpm and abs(np.log2(best / ref)) > tol:
        return bpm
    return best


def blend(refs, base, use=None):
    """refs: list of (analysis, weight). base: current settings. Returns (settings, notes)."""
    use = {k: True for k in USE_KEYS} | (use or {})
    refs = [(a, max(0.0, float(w))) for a, w in refs if a]
    refs = [(a, w) for a, w in refs if w > 0] or [(a, 1.0) for a, _ in refs]
    if not refs:
        return base, ["No songs to take inspiration from yet."]
    W = sum(w for _, w in refs)
    lead = max(refs, key=lambda r: r[1])[0]
    names = lambda f: ", ".join(f"{a['name']} {f(a)}" for a, _ in refs)
    notes = []

    gs = {g: sum(a["genre_scores"][g] * w for a, w in refs) for g in GENRE_TEMPO}
    genre = max(gs, key=gs.get)
    if use["style"]:
        s = get_preset(genre)
        s["melody"]["seed"] = base.get("melody", {}).get("seed", s["melody"]["seed"])
        notes.append(f"Style: {s['label']} (closest match to your songs)")
    else:
        s = dict(base)
        genre = s.get("genre", genre)

    if use["tempo"]:
        ref = GENRE_TEMPO.get(genre, lead["bpm"]) if use["style"] else _near(lead["bpm"], s.get("bpm", 110))
        anchor = _near(lead["bpm"], ref)
        bpm = sum(_near(a["bpm"], anchor, tol=0.25) * w for a, w in refs) / W
        s["bpm"] = round(bpm)
        notes.append(f"Tempo: {s['bpm']} BPM (from {names(lambda a: str(round(a['bpm'])))})")

    if use["key"]:
        votes = {}
        for a, w in refs:
            votes[(a["key"], a["scale"])] = votes.get((a["key"], a["scale"]), 0) + w
        top = max(votes.values())
        s["key"], s["scale"] = next(k for k in [(lead["key"], lead["scale"])] + list(votes)
                                    if votes.get(k, 0) == top)
        notes.append(f"Key: {s['key']} {s['scale']} (from {names(lambda a: a['key'] + ' ' + a['scale'])})")

    if use["groove"]:
        prof = {k: sum(np.array(a["profiles"][k]) * w for a, w in refs) / W for k in ("kick", "snare", "hat")}
        prof = {k: v / (v.max() + 1e-9) for k, v in prof.items()}
        drums = s["drums"]
        changed = []
        low = _to_pattern(prof["kick"])
        kp = low
        hits = sum(c != "." for c in low)
        if hits > 5:
            # a busy low end is kick + bass together: kick keeps the beats, bass gets the rhythm
            kp = "".join(c if i % 4 == 0 else "." for i, c in enumerate(low))
            if kp.count("x") == 0:
                kp = "x...x...x...x..."
            s["bass"]["pattern"] = "".join("x" if c == "x" else "o" if c == "o" else "." for c in low)
            changed.append("bass")
        if kp.count("x") >= 1:
            drums["kick"]["pattern"] = kp
            drums["kick"]["mute"] = False
            changed.append("kick")
        sp = _to_pattern(prof["snare"], 0.65, 0.4)
        if sp.count("x") >= 1:
            target = "snare" if not drums["snare"]["mute"] and drums["snare"]["pattern"].strip(".") else "clap"
            drums[target]["pattern"] = sp
            changed.append(target)
        hp = _to_pattern(prof["hat"], 0.55, 0.25)
        if hp.count("x") + hp.count("o") >= 2:
            drums["hat"]["pattern"] = hp
            drums["hat"]["mute"] = False
            changed.append("hi-hat")
        if hits <= 5 and s["bass"]["sound"] == "808" and kp.count("x") >= 1:
            s["bass"]["pattern"] = kp
            changed.append("808 (follows kick)")
        if changed:
            notes.append("Groove: " + ", ".join(changed) + " rhythm taken from your songs")

    if use["chords"]:
        withp = [(a, w) for a, w in refs if a.get("progression")]
        if withp:
            a = max(withp, key=lambda r: r[1] * (0.5 + r[0]["progression_confidence"]))[0]
            s["progression"] = a["progression"]
            s["chord_bars"] = 1
            notes.append(f"Chords: {'-'.join(map(str, a['progression']))} movement (from {a['name']})")
        else:
            notes.append("Chords: couldn't hear a clear repeating progression, kept yours")

    if use["feel"]:
        s["swing"] = round(sum(a["swing"] * w for a, w in refs) / W, 2)
        s["energy"] = round(sum(a["energy"] * w for a, w in refs) / W, 2)
        notes.append(f"Feel: swing {round(s['swing'] * 100)}%, energy {round(s['energy'] * 100)}%")

    if use["tone"]:
        b = sum(a["brightness"] * w for a, w in refs) / W
        s["chords"]["brightness"] = round(0.25 + 0.6 * b, 2)
        s["melody"]["brightness"] = round(0.3 + 0.6 * b, 2)
        s["mix"]["air"] = round(0.2 + 0.6 * b, 2)
        s["mix"]["warmth"] = round(0.15 + 0.5 * (1 - b), 2)
        notes.append("Tone: " + ("bright and crisp" if b > 0.7 else "warm and dark" if b < 0.35 else "balanced"))

    s["genre"] = genre if use["style"] else s.get("genre", genre)
    return s, notes
