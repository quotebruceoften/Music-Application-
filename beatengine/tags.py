"""Producer tag generator: catchy phrases, a voice, and a professional effects chain."""
import os
import random
import re
import shutil
import subprocess
import sys

import numpy as np

from . import dsp, fx, media, synth
from . import wavio as wavfile

SR = synth.SR

# ================================================================ phrases
GENERAL = [
    ("{n} on the beat", "clean"), ("It's {n}!", "dark"), ("{n}, cook it up", "echo"),
    ("{n} made this one", "clean"), ("Another {n} banger", "radio"), ("Ladies and gentlemen... {n}", "dark"),
    ("{n} in the building", "echo"), ("Only {n} could do this", "dark"), ("{n}, run it back", "stutter"),
    ("This is a {n} production", "clean"), ("{n} got the sauce", "radio"), ("Certified {n} heat", "dark"),
    ("Hold up... it's {n}", "echo"), ("{n}! You already know", "echo"), ("Wake up, {n} is cooking", "radio"),
    ("Turn it up, {n}", "stutter"), ("{n} did it again", "clean"), ("Straight from {n}'s studio", "angelic"),
]
GENRE = {
    "amapiano": [("Ke {n}!", "echo"), ("Sharp sharp, {n}", "radio"), ("{n} on the log drum", "dark"),
                 ("Yanos by {n}", "echo"), ("Dlala {n}!", "stutter"), ("{n}, shaya!", "dark"),
                 ("Amapiano to the world... {n}", "angelic")],
    "trap": [("{n} on the track", "dark"), ("{n} cooked this up", "stutter"), ("Turn the 808 up, {n}", "dark"),
             ("Cut it up, {n}", "stutter"), ("{n}, the trap don't stop", "echo")],
    "afrohouse": [("{n} on the drums", "echo"), ("Feel the rhythm... {n}", "angelic"),
                  ("From Africa with love, {n}", "angelic"), ("{n}, let the drums talk", "dark")],
    "lofi": [("Late night with {n}", "angelic"), ("Stay cozy... {n}", "radio"), ("{n}, take it slow", "angelic"),
             ("Rain, coffee and {n}", "radio")],
    "tiktok": [("{n}, make it go viral", "stutter"), ("Run that back... {n}", "echo"),
               ("Use this sound! {n}", "radio")],
}

STYLES = {
    "clean": "Clean & punchy: doubled voice, short plate, reverse swell",
    "dark": "Dark & deep: pitched-down layers, saturation, big hall",
    "echo": "Echo out: the last word throws into ping-pong echoes",
    "stutter": "Stutter & tape stop: chopped start, slowed ending",
    "radio": "Radio: telephone EQ, grit and slapback",
    "angelic": "Angelic: octave-up shimmer, wide chorus, huge reverb",
}


def _stretch_name(n):
    m = re.search(r"[aeiouAEIOU]+", n)
    return n[: m.end()] + m.group(0)[-1] * 2 + n[m.end():] if m else n


def suggest(name, genre="amapiano", count=10, seed=None):
    """Catchy tag ideas built around the producer's name."""
    name = (name or "").strip() or "Producer"
    rng = random.Random(seed)
    pool = GENERAL + GENRE.get(genre, []) * 2 + GENRE["tiktok"]
    rng.shuffle(pool)
    out, seen = [], set()
    for text, style in pool:
        t = text.format(n=name)
        if t.lower() not in seen:
            out.append({"text": t, "style": style})
            seen.add(t.lower())
        if len(out) >= count - 3:
            break
    # name-only tricks that stick in the ear
    extra = [{"text": f"{_stretch_name(name)}!", "style": "dark"},
             {"text": f"{name}... {name}... {name}", "style": "echo"},
             {"text": "-".join(name.upper()) + f"... {name}!", "style": "stutter"}]
    out += rng.sample(extra, min(3, count - len(out)))
    return out


# ================================================================ voices
EDGE_VOICES = [
    ("en-US-GuyNeural", "US male, deep"), ("en-US-ChristopherNeural", "US male"),
    ("en-US-AriaNeural", "US female"), ("en-US-JennyNeural", "US female, warm"),
    ("en-GB-RyanNeural", "UK male"), ("en-GB-SoniaNeural", "UK female"),
    ("en-ZA-LukeNeural", "South African male"), ("en-ZA-LeahNeural", "South African female"),
    ("en-NG-AbeoNeural", "Nigerian male"), ("en-NG-EzinneNeural", "Nigerian female"),
    ("en-AU-WilliamNeural", "Australian male"),
]


def _has_module(name):
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def voices():
    """Voices available on this computer, best quality first."""
    out = []
    if _has_module("edge_tts"):
        out += [{"engine": "edge", "id": v, "label": f"{lbl} (neural)"} for v, lbl in EDGE_VOICES]
    if _has_module("pyttsx3"):
        try:
            import pyttsx3
            eng = pyttsx3.init()
            for v in eng.getProperty("voices")[:12]:
                out.append({"engine": "pyttsx3", "id": v.id, "label": f"{v.name} (computer voice)"})
        except Exception:  # noqa: BLE001 - broken system speech shouldn't break the app
            pass
    esp = shutil.which("espeak-ng") or shutil.which("espeak")
    if esp:
        out += [{"engine": "espeak", "id": v, "label": f"{lbl} (robotic)"}
                for v, lbl in (("en+m3", "Male"), ("en-us+m7", "Deep male"), ("en+f3", "Female"))]
    return out


def speak(text, engine, voice, out_base):
    """Text to speech. Returns the path of the audio file written."""
    text = text.strip()[:140]
    if not text:
        raise ValueError("Type the words for your tag first.")
    if engine == "edge":
        if not _has_module("edge_tts"):
            raise RuntimeError("Neural voices need edge-tts. Run: pip install edge-tts")
        path = out_base + ".mp3"
        cmd = [sys.executable, "-m", "edge_tts", "--voice", voice, "--text", text,
               "--rate=-5%", "--write-media", path]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if p.returncode != 0 or not os.path.exists(path):
            raise RuntimeError("The neural voice service didn't answer. Check your internet connection. "
                               + (p.stderr or "").strip()[-200:])
        return path
    if engine == "pyttsx3":
        import pyttsx3
        path = out_base + ".wav"
        eng = pyttsx3.init()
        eng.setProperty("voice", voice)
        eng.setProperty("rate", 165)
        eng.save_to_file(text, path)
        eng.runAndWait()
        return path
    if engine == "espeak":
        path = out_base + ".wav"
        exe = shutil.which("espeak-ng") or shutil.which("espeak")
        subprocess.run([exe, "-v", voice, "-s", "150", "-w", path, text], check=True)
        return path
    raise RuntimeError("No voice engine found. Install one (pip install edge-tts), or record/upload your own voice.")


# ================================================================ audio helpers
def load(path, max_s=12):
    y = media.load_mono(path, SR, max_s=max_s)
    if len(y) < SR * 0.3:
        raise ValueError("Couldn't hear a voice in that recording.")
    return y


def trim(y, thresh_db=-38, pad=0.03):
    env = np.convolve(np.abs(y), np.ones(441) / 441, mode="same")
    on = np.nonzero(env > np.max(env) * fx.db(thresh_db))[0]
    if not len(on):
        return y
    a, b = max(0, on[0] - int(pad * SR)), min(len(y), on[-1] + int(pad * SR * 4))
    return y[a:b]


def _f(x, kind, freq, order=2):
    return fx.filt(x.astype(np.float32), kind, freq, order)


def _delay(x, sec, n=None):
    d = int(sec * SR)
    out = np.zeros(n or len(x) + d, np.float32)
    out[d:d + len(x)] = x[: len(out) - d]
    return out


def _pad(x, n):
    return np.concatenate([x, np.zeros(max(0, n - len(x)), np.float32)])[:n]


def stretch(y, rate, n_fft=2048, hop=512):
    """Phase-vocoder time stretch (rate > 1 = faster) that keeps the pitch."""
    win = np.hanning(n_fft).astype(np.float32)
    L0 = len(y)
    y = np.concatenate([np.zeros(n_fft, np.float32), y, np.zeros(n_fft, np.float32)])
    frames = np.lib.stride_tricks.sliding_window_view(y, n_fft)[::hop] * win
    D = np.fft.rfft(frames, axis=1)
    steps = np.arange(0, D.shape[0] - 1, rate)
    omega = 2 * np.pi * hop * np.arange(D.shape[1]) / n_fft
    phase = np.angle(D[0])
    out = np.zeros(int(len(steps) * hop + n_fft), np.float32)
    for k, t in enumerate(steps):
        i = int(t)
        frac = t - i
        mag = (1 - frac) * np.abs(D[i]) + frac * np.abs(D[i + 1])
        frame = np.fft.irfft(mag * np.exp(1j * phase)).astype(np.float32) * win
        out[k * hop:k * hop + n_fft] += frame
        dphi = np.angle(D[i + 1]) - np.angle(D[i]) - omega
        dphi -= 2 * np.pi * np.round(dphi / (2 * np.pi))
        phase += omega + dphi
    out /= (np.sum(win ** 2) / hop)
    a = int(n_fft / rate)
    return _pad(out[a:a + int(L0 / rate)], int(L0 / rate))


def pitch_shift(y, semitones):
    if abs(semitones) < 0.01:
        return y.copy()
    f = 2 ** (semitones / 12)
    longer = stretch(y, 1 / f)
    return dsp.resample(longer, len(y))


def tape_stop(y, dur=0.45):
    n = min(len(y), int(dur * SR))
    head, tail = y[:-n], y[-n:]
    speed = np.linspace(1, 0.05, n) ** 1.6
    pos = np.cumsum(speed)
    pos = pos[pos < n - 1]
    slowed = np.interp(pos, np.arange(n), tail).astype(np.float32)
    slowed *= np.linspace(1, 0, len(slowed)) ** 0.5
    return np.concatenate([head, slowed])


def stutter(y, chop=0.12, repeats=3):
    n = int(chop * SR)
    piece = y[:n].copy()
    f = int(0.008 * SR)
    piece[:f] *= np.linspace(0, 1, f)
    piece[-f:] *= np.linspace(1, 0, f)
    return np.concatenate([piece] * repeats + [y])


def reverse_swell(y, length=1.2):
    """A reversed reverb that swells up into the first word."""
    head = _pad(y[: int(0.45 * SR)], int(0.45 * SR))
    wet = fx.reverb(np.stack([head, head], axis=1), size=2.5)
    wet = wet[: int(length * SR) + len(head)][::-1].copy()
    wet = wet[: int(length * SR)]
    wet *= np.linspace(0, 1, len(wet))[:, None] ** 2
    return wet


def echo_throw(y, beat=0.32, repeats=5, fb=0.62):
    """Repeat the last word into the distance (ping-pong)."""
    seg_len = int(min(0.6, max(0.25, len(y) / SR * 0.3)) * SR)
    seg = y[-seg_len:].copy()
    seg[: int(0.01 * SR)] *= np.linspace(0, 1, int(0.01 * SR))
    rms = lambda v: np.sqrt(np.mean(v ** 2)) + 1e-9
    loud = y[np.abs(y) > 0.05 * np.max(np.abs(y))]
    seg *= min(4.0, 0.8 * rms(loud if len(loud) else y) / rms(seg))  # the thrown word as loud as the voice
    d = int(beat * SR)
    out = np.zeros((len(y) + d * repeats + seg_len, 2), np.float32)
    start = len(y) - seg_len
    for i in range(1, repeats + 1):
        rep = _f(seg, "highpass", 200 + 250 * i) * fb ** i
        a = start + d * i
        out[a:a + seg_len, i % 2] += rep
    return out


def _stereo(m):
    return np.stack([m, m], axis=1).astype(np.float32)


def _fit(*parts):
    n = max(len(p) for p in parts)
    return [np.pad(p, [(0, n - len(p))] + [(0, 0)] * (p.ndim - 1)) for p in parts]


# ================================================================ the chain
def process(y, style="clean", pitch=0.0, swell=True, impact=False, riser=False, bpm=120):
    y = trim(y)
    y = y / (np.max(np.abs(y)) + 1e-9) * 0.9
    if pitch:
        y = pitch_shift(y, pitch)
    # broadcast-style vocal chain: clean lows, control dynamics, add presence
    y = _f(y, "highpass", 90)
    st = fx.compressor(_stereo(y), threshold_db=-20, ratio=4, attack=0.004, release=0.08)[:, 0]
    y = st + _f(_f(st, "highpass", 2500), "lowpass", 6000) * 0.35
    beat = 60 / bpm * 0.75  # dotted eighth

    if style == "stutter":
        y = tape_stop(stutter(y, chop=60 / bpm / 4 * 1.5))
    if style == "dark":
        low = pitch_shift(y, -5)
        sub = pitch_shift(y, -12)
        y = np.tanh(2 * (0.5 * y + 0.9 * low + 0.25 * sub)) * 0.6
        y = _f(y, "lowpass", 7000)
    if style == "radio":
        y = np.tanh(3 * _f(_f(y, "highpass", 450), "lowpass", 3800)) * 0.6
    if style == "angelic":
        up = _f(pitch_shift(y, 12), "lowpass", 9000)
        y = y + 0.3 * up

    dry = _stereo(y)
    if style in ("clean", "angelic", "stutter", "echo"):  # doubler / chorus for width
        dbl = pitch_shift(y, 0.12 if style != "angelic" else 0.2)
        dl, dr = _delay(dbl, 0.017, len(y)), _delay(dbl, 0.023, len(y))
        w = 0.45 if style == "angelic" else 0.3
        dry = dry + np.stack([dl * w, dr * w], axis=1) * 0.6
    if style == "radio":
        dry = dry + _stereo(_delay(y, 0.075, len(y))) * 0.3

    size, amt = {"clean": (1.2, 0.18), "dark": (3.0, 0.35), "echo": (1.8, 0.25), "stutter": (1.4, 0.2),
                 "radio": (0.8, 0.1), "angelic": (4.0, 0.5)}[style]
    tail = int(size * SR)
    dry = np.pad(dry, [(0, tail), (0, 0)])
    wet = fx.reverb(dry, size=size) * amt
    out = dry + wet
    if style in ("echo", "stutter"):
        e = echo_throw(y, beat=beat)
        out, e = _fit(out, e)
        out = out + e * 1.3
        out = out + fx.reverb(e, size=2.0) * 0.2

    pre = []
    if swell and style != "radio":
        pre.append(reverse_swell(y) * 0.5)
    if riser:
        r = _stereo(synth.riser(1.0)) * 0.25
        pre.append(r)
    if pre:
        pre = _fit(*pre)
        lead = sum(pre)
        out = np.concatenate([lead, out])
        voice_start = len(lead)
    else:
        voice_start = 0
    if impact:
        b1, b2 = _fit(_stereo(synth.boom()) * 0.28, _stereo(synth.crash()) * 0.12)
        b = b1 + b2
        out, b3 = _fit(out, np.concatenate([np.zeros((voice_start, 2), np.float32), b]))
        out = out + b3

    # finish: trim the tail, fade, and bring to a strong but clean level
    env = np.max(np.abs(out), axis=1)
    last = np.nonzero(env > np.max(env) * fx.db(-50))[0]
    out = out[: (last[-1] if len(last) else len(out)) + int(0.05 * SR)]
    f = min(len(out), int(0.08 * SR))
    out[-f:] *= np.linspace(1, 0, f)[:, None]
    out = out / (np.max(np.abs(out)) + 1e-9)
    out = fx.limiter(fx.compressor(out, -14, 2.5) * fx.db(3), -1.0)
    return out.astype(np.float32)


def make_tag(out_dir, style="clean", text=None, engine=None, voice=None, voice_file=None,
             pitch=0.0, swell=True, impact=False, riser=False, bpm=120):
    os.makedirs(out_dir, exist_ok=True)
    src = voice_file or speak(text, engine, voice, os.path.join(out_dir, "voice_raw"))
    y = load(src)
    out = process(y, style if style in STYLES else "clean", pitch, swell, impact, riser, bpm)
    wav = os.path.join(out_dir, "tag.wav")
    wavfile.write(wav, SR, out)
    mp3 = media.to_mp3(wav, os.path.join(out_dir, "tag.mp3"))
    return {"wav": wav, "mp3": mp3, "duration": round(len(out) / SR, 2)}
