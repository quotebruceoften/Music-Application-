"""Build beatengine/samples/ from the VCSL sample library (CC0 1.0, public domain).

    git clone --filter=blob:none --no-checkout https://github.com/sgossner/VCSL /tmp/vcsl
    python tool/build_samples.py /tmp/vcsl

Picks a small set of notes per instrument, checks out only those files, then makes each
one mono 44.1 kHz 16-bit, trims the silence before the attack, shortens it with a fade,
and normalises it. Pitched samples are re-measured so the root note is exact (libraries
don't agree on octave numbering). Writes beatengine/samples/index.json for the engine.
"""
import json
import os
import re
import subprocess
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from beatengine import dsp, wavio  # noqa: E402

SR = 44100
OUT = os.path.join(ROOT, "beatengine", "samples")
NOTE = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}

# name: (folder, filename regex with the note as group 1, lowest/highest MIDI kept,
#        min spacing in semitones between kept roots, max seconds)
PITCHED = {
    "piano": ("Chordophones/Zithers/Grand Piano, Kawai", r"GPiano_sus_([A-G]#?-?\d)_v3_rr1_Player\.wav$", 36, 96, 5, 3.2),
    "marimba": ("Idiophones/Struck Idiophones/Marimba", r"Marimba_hit_Outrigger_([A-G]#?\d)_med_01\.wav$", 40, 96, 4, 2.0),
    "vibes": ("Idiophones/Struck Idiophones/Vibraphone", r"Vibes_hard_([A-G]#?\d)_v2_rr1_Main\.wav$", 48, 96, 4, 2.8),
    "glock": ("Idiophones/Struck Idiophones/Glockenspiel", r"glock_medium_([A-G]#?\d)_01\.wav$", 60, 108, 5, 2.2),
    "kalimba": ("Idiophones/Plucked Idiophones/Kalimba, Tanzania", r"MBira3_pluck_Main_([A-G]#?\d)_k\d+(?:alt)?_50_100_rr2\.wav$", 40, 96, 4, 2.2),
    "flute": ("Aerophones/Edge-blown Aerophones/Baroque Alto Recorder", r"AltRecorder_Sus_([A-G]#?\d)_rr1_Main\.wav$", 60, 96, 3, 2.6),
    "sax": ("Aerophones/Reed Aerophones/Tenor Saxophone", r"BrettTenor_NV_Main_([A-G]#?\d)_vl2_rr1\.wav$", 40, 84, 4, 2.6),
}

# name: (folder, list of filename regexes (round-robin variations), max seconds)
HITS = {
    "clap": ("Idiophones/Struck Idiophones/Claps", [r"Clap_rr[1-4]\.wav$"], 0.7),
    "shaker": ("Idiophones/Struck Idiophones/Shaker, Small", [r"Mid_ShakerHighFaster_(Down|Up)_rr[12]\.wav$"], 0.45),
    "conga": ("Membranophones/Struck Membranophones/Conga", [r"Conga_HitN_v2_rr[12]_Sum\.wav$", r"Quinto_HitN_v2_rr1_Sum\.wav$"], 0.8),
    "bongo": ("Membranophones/Struck Membranophones/Bongos", [r"BongoH_Hit1_v2_rr[12]_Mid\.wav$", r"BongoL_Hit1_v2_rr1_Mid\.wav$"], 0.6),
    "cowbell": ("Idiophones/Struck Idiophones/Cowbells", [r"Cowbell1_Normal_v[23]_rr1_Mid\.wav$"], 0.8),
    "wood": ("Idiophones/Struck Idiophones/Woodblock", [r"wood_click_f_rr[12]\.wav$", r"wood_click_mp\.wav$"], 0.35),
    "tambourine": ("Idiophones/Struck Idiophones/Tambourine 1", [r"Tamb1_Hit_v[12]_rr1_Mid\.wav$"], 0.8),
}


def note_to_midi(name):
    m = re.match(r"([A-G]#?)(-?\d)$", name)
    return NOTE[m.group(1)] + 12 * (int(m.group(2)) + 1)


def checkout(repo, paths):
    if paths:
        subprocess.run(["git", "-C", repo, "checkout", "HEAD", "--", *paths], check=True)


def load(path):
    sr, y = wavio.read(path)
    if y.ndim > 1:
        y = y.mean(axis=1)
    y = y.astype(np.float64)
    if sr != SR:  # band-limited resample in the frequency domain
        n = int(round(len(y) * SR / sr))
        spec = np.fft.rfft(y)
        keep = min(len(spec), n // 2 + 1)
        out = np.zeros(n // 2 + 1, complex)
        out[:keep] = spec[:keep]
        y = np.fft.irfft(out, n) * (n / len(y))
    return y


def prepare(y, max_s):
    y = y - np.mean(y)
    env = np.abs(y)
    thr = np.max(env) * 0.02
    start = int(np.argmax(env > thr))
    start = max(0, start - int(0.002 * SR))  # keep 2 ms before the attack
    y = y[start:start + int(max_s * SR)]
    fade = min(len(y), int(0.25 * SR) if max_s > 1 else int(0.05 * SR))
    y[-fade:] *= np.linspace(1, 0, fade) ** 2
    y[: int(0.001 * SR)] *= np.linspace(0, 1, int(0.001 * SR))
    peak = np.max(np.abs(y)) or 1
    return (y / peak * 0.89).astype(np.float32)


def measure_f0(y, guess_hz):
    """Pitch of a sample, searched within ±7 semitones of what the file name says."""
    seg = y[int(0.05 * SR): int(0.45 * SR)]
    if len(seg) < 2048:
        seg = y[: int(0.4 * SR)]
    seg = seg * np.hanning(len(seg))
    n = dsp.next_fast_len(len(seg) * 8)
    mag = np.abs(np.fft.rfft(seg, n))
    freqs = np.fft.rfftfreq(n, 1 / SR)
    best, best_score = guess_hz, -1
    for octave in (-1, 0, 1):
        for cents in range(-700, 701, 5):
            f = guess_hz * 2 ** octave * 2 ** (cents / 1200)
            if f < 25 or f > 5000:
                continue
            idx = np.searchsorted(freqs, [f * k for k in range(1, 6)])
            idx = idx[idx < len(mag)]
            score = sum(mag[i] / k for k, i in enumerate(idx, 1))
            if score > best_score:
                best, best_score = f, score
    return best


def main(repo):
    files = subprocess.run(
        ["git", "-C", repo, "ls-tree", "-r", "--name-only", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    os.makedirs(OUT, exist_ok=True)
    index = {"source": "VCSL (https://github.com/sgossner/VCSL), CC0 1.0 public domain",
             "sr": SR, "pitched": {}, "hits": {}}

    for name, (folder, rx, lo, hi, spacing, max_s) in PITCHED.items():
        cands = []
        for f in files:
            if f.startswith(folder + "/"):
                m = re.search(rx, f)
                if m:
                    cands.append((note_to_midi(m.group(1)), f))
        cands.sort()
        # the library's octave numbering may be off by one; measure one sample to find out
        checkout(repo, [f for _, f in cands])
        mid = cands[len(cands) // 2]
        y = load(os.path.join(repo, mid[1]))
        f0 = measure_f0(y, 440 * 2 ** ((mid[0] - 69) / 12))
        shift = int(round((12 * np.log2(f0 / 440) + 69 - mid[0]) / 12)) * 12
        kept, last = [], -99
        for midi, f in cands:
            midi += shift
            if lo <= midi <= hi and midi - last >= spacing:
                kept.append((midi, f))
                last = midi
        os.makedirs(os.path.join(OUT, name), exist_ok=True)
        roots = {}
        for midi, f in kept:
            y = prepare(load(os.path.join(repo, f)), max_s)
            # fine-tune: store the measured pitch so playback is in tune
            f0 = measure_f0(y, 440 * 2 ** ((midi - 69) / 12))
            exact = 12 * np.log2(f0 / 440) + 69
            if abs(exact - midi) > 0.6:  # measurement disagrees: trust the name
                exact = float(midi)
            out = f"{name}/{midi}.wav"
            wavio.write(os.path.join(OUT, out), SR, (y * 32767).astype(np.int16))
            roots[str(midi)] = {"file": out, "pitch": round(float(exact), 3)}
        index["pitched"][name] = roots
        print(f"{name}: octave shift {shift:+d}, roots {sorted(int(k) for k in roots)}")

    for name, (folder, rxs, max_s) in HITS.items():
        chosen = []
        for rx in rxs:
            chosen += sorted(f for f in files if f.startswith(folder + "/") and re.search(rx, f))
        checkout(repo, chosen)
        os.makedirs(os.path.join(OUT, name), exist_ok=True)
        outs = []
        for i, f in enumerate(chosen):
            y = prepare(load(os.path.join(repo, f)), max_s)
            out = f"{name}/{i + 1}.wav"
            wavio.write(os.path.join(OUT, out), SR, (y * 32767).astype(np.int16))
            outs.append(out)
        index["hits"][name] = outs
        print(f"{name}: {len(outs)} variations")

    with open(os.path.join(OUT, "index.json"), "w") as fh:
        json.dump(index, fh, indent=1)
    with open(os.path.join(OUT, "LICENSE.txt"), "w") as fh:
        fh.write("These samples come from the Versilian Community Sample Library (VCSL)\n"
                 "https://github.com/sgossner/VCSL, released under CC0 1.0 Universal\n"
                 "(public domain). They were trimmed, converted to mono and normalised.\n")
    total = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(OUT) for f in fs)
    print(f"total {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/vcsl")
