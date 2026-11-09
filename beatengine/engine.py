"""The producer engine: turns simple settings into a mixed and mastered beat."""
import copy
import json
import os
import zipfile

import numpy as np

from . import dsp, fx, media, synth, theory
from . import wavio as wavfile
import shutil
import subprocess
from .midi import GM_DRUMS, write_midi
from .presets import (DRUMS, GENRES, OPTIONS, SECTION_TYPES, TRACKS, get_preset)

SR = synth.SR
HIT_CHARS = set("xo")
FORMATS = {"full": None, "tiktok15": 15, "tiktok30": 30, "tiktok60": 60}
LENGTH_MIN, LENGTH_MAX = 3, 10  # minutes, for long full-length beats
TAG_POSITIONS = ["start", "start+hooks", "every8"]  # older single-choice setting
# Where a producer tag can go; any combination is allowed
TAG_PLACES = ["start", "hooks", "verses", "every8", "end"]
_LEGACY_PLACES = {"start": ["start"], "start+hooks": ["start", "hooks"], "every8": ["start", "every8"]}
BASS_CHARS = set("xo5^")


# ================================================================ settings
def _merge(base, over):
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict) and k != "sections":
            _merge(base[k], v)
        else:
            base[k] = copy.deepcopy(v)
    return base


def _num(v, lo, hi, default):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return float(min(hi, max(lo, v)))


def _pattern(p, allowed):
    p = "".join(c if c in allowed else "." for c in str(p or ""))
    return (p + "." * 16)[:16]


def parse_progression(p):
    if isinstance(p, str):
        p = [c for c in p.replace(",", " ").replace("-", " ").split()]
    out = []
    for c in p or []:
        try:
            d = int(c)
        except (TypeError, ValueError):
            continue
        if 1 <= d <= 7:
            out.append(d)
    return out[:8] or [1, 4, 6, 5]


def sanitize(settings):
    settings = settings or {}
    s = _merge(get_preset(settings.get("genre", "amapiano")), settings)
    if s.get("genre") not in GENRES:
        s["genre"] = "amapiano"
    s["bpm"] = _num(s["bpm"], 60, 180, 110)
    s["key"] = s["key"] if s["key"] in theory.NOTE_NAMES else "C"
    s["scale"] = s["scale"] if s["scale"] in theory.SCALES else "minor"
    for k in ("swing", "energy", "humanize"):
        s[k] = _num(s[k], 0, 1, 0.5)
    s["seed"] = int(_num(s.get("seed"), 0, 999999, 1))
    s["progression"] = parse_progression(s["progression"])
    s["chord_bars"] = min((0.5, 1, 2), key=lambda c: abs(c - _num(s["chord_bars"], 0.5, 2, 1)))

    arr = []
    for item in s.get("arrangement") or []:
        try:
            name, bars = item[0], int(item[1])
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        if name in SECTION_TYPES:
            arr.append([name, max(1, min(32, bars))])
    s["arrangement"] = arr[:16] or [["verse", 8], ["hook", 8]]

    secs = s.get("sections") or {}
    s["sections"] = {n: [t for t in secs.get(n, []) if t in TRACKS] for n in SECTION_TYPES}

    for d in DRUMS:
        c = s["drums"][d]
        c["pattern"] = _pattern(c.get("pattern"), HIT_CHARS)
        c["volume"] = _num(c.get("volume"), -40, 6, -8)
        c["tune"] = _num(c.get("tune"), -12, 12, 0)
        c["decay"] = _num(c.get("decay"), 0.25, 3, 1)
        c["pan"] = _num(c.get("pan"), -1, 1, 0)
        c["reverb"] = _num(c.get("reverb"), 0, 1, 0.05)
        c["mute"] = bool(c.get("mute"))
    if s["drums"]["kick"].get("sound") not in OPTIONS["kick_sounds"]:
        s["drums"]["kick"]["sound"] = "punchy"
    if s["drums"]["snare"].get("sound") not in OPTIONS["snare_sounds"]:
        s["drums"]["snare"]["sound"] = "tight"
    if s["drums"]["perc"].get("sound") not in OPTIONS["perc_sounds"]:
        s["drums"]["perc"]["sound"] = "rim"

    b = s["bass"]
    b["pattern"] = _pattern(b.get("pattern"), BASS_CHARS)
    b["sound"] = b["sound"] if b.get("sound") in OPTIONS["bass_sounds"] else "sub"
    b["volume"] = _num(b.get("volume"), -40, 6, -4)
    b["octave"] = int(_num(b.get("octave"), 0, 3, 2))
    b["decay"] = _num(b.get("decay"), 0.25, 3, 1)
    b["glide"] = _num(b.get("glide"), 0, 1, 0)

    c = s["chords"]
    c["pattern"] = _pattern(c.get("pattern"), HIT_CHARS)
    c["sound"] = c["sound"] if c.get("sound") in OPTIONS["chord_sounds"] else "piano"
    c["voicing"] = c["voicing"] if c.get("voicing") in theory.VOICINGS else "7th"
    c["octave"] = int(_num(c.get("octave"), 2, 6, 4))
    for k, lo, hi, dv in (("brightness", 0, 1, 0.5), ("volume", -40, 6, -9), ("stereo", 0, 1, 0.5),
                          ("reverb", 0, 1, 0.3), ("delay", 0, 1, 0)):
        c[k] = _num(c.get(k), lo, hi, dv)

    m = s["melody"]
    m["sound"] = m["sound"] if m.get("sound") in OPTIONS["melody_sounds"] else "bell"
    m["octave"] = int(_num(m.get("octave"), 3, 7, 5))
    m["seed"] = int(_num(m.get("seed"), 0, 999999, 1))
    for k, lo, hi, dv in (("density", 0.05, 1, 0.4), ("brightness", 0, 1, 0.5), ("volume", -40, 6, -11),
                          ("reverb", 0, 1, 0.3), ("delay", 0, 1, 0.25)):
        m[k] = _num(m.get(k), lo, hi, dv)

    s["fx"]["volume"] = _num(s["fx"].get("volume"), -40, 6, -14)
    t = s["texture"]
    t["sound"] = t["sound"] if t.get("sound") in OPTIONS["texture_sounds"] else "none"
    t["volume"] = _num(t.get("volume"), -40, 0, -26)

    s["format"] = s.get("format") if s.get("format") in FORMATS else "full"
    # Full-song length in minutes: 0 plays the arrangement as written, 3-10 extends it
    ln = _num(s.get("length"), 0, LENGTH_MAX, 0)
    s["length"] = 0 if ln < LENGTH_MIN else round(ln, 1)
    s["export_video"] = bool(s.get("export_video"))
    s["producer"] = str(s.get("producer") or "")[:40]
    s["title"] = str(s.get("title") or "")[:60]
    tg = s.get("tag") or {}
    position = tg.get("position") if tg.get("position") in TAG_POSITIONS else "start"
    places = tg.get("places")
    if isinstance(places, list):
        places = [p for p in TAG_PLACES if p in places]
    else:
        places = list(_LEGACY_PLACES[position])
    s["tag"] = {"id": (os.path.basename(str(tg.get("id")))[:40] if tg.get("id") else None),
                "position": position, "places": places,
                "volume": _num(tg.get("volume"), -20, 6, -1), "duck": _num(tg.get("duck"), 0, 1, 0.5),
                "mute": bool(tg.get("mute"))}

    mx = s["mix"]
    for k, lo, hi, dv in (("reverb", 0, 1, 0.5), ("reverb_size", 0.5, 5, 2), ("delay", 0, 1, 0.5),
                          ("sidechain", 0, 1, 0.5), ("warmth", 0, 1, 0.25), ("width", 0, 2, 1.1),
                          ("loudness", -20, -7, -14), ("air", 0, 1, 0.4), ("phone_bass", 0, 1, 0)):
        mx[k] = _num(mx.get(k), lo, hi, dv)
    return s


# ================================================================ timing
def tiktok_arrangement(bpm, seconds):
    """Hook-first short form: a teaser, then the drop lands early (the video's transition moment)."""
    bar = 240.0 / bpm
    total = max(4, int(round(seconds / bar)))
    if seconds <= 15:
        b = max(1, round(total * 0.3))
        return [["break", b], ["hook", total - b]]
    if seconds <= 30:
        h1 = max(2, round(total * 0.35))
        b = max(1, round(total * 0.15))
        return [["hook", h1], ["break", b], ["hook", max(1, total - h1 - b)]]
    v, h1, b = round(total * 0.25), round(total * 0.3), max(1, round(total * 0.1))
    return [["verse", v], ["hook", h1], ["break", b], ["hook", max(2, total - v - h1 - b)]]


def extend_arrangement(arr, bpm, minutes):
    """Stretch an arrangement to about `minutes`: keep the intro and outro, and repeat the
    body in between, adding a breakdown every other pass. Returns [name, bars, cycle] items;
    `cycle` counts the passes so later passes can vary (new melody, etc.)."""
    bar = 240.0 / bpm
    target = max(1, int(round(minutes * 60 / bar)))
    arr = [list(a) for a in arr]
    head = []
    while arr and arr[0][0] == "intro":
        head.append(arr.pop(0))
    tail = []
    while arr and arr[-1][0] == "outro":
        tail.insert(0, arr.pop())
    body = arr or [["verse", 8], ["hook", 8]]
    out = [[n, b, 0] for n, b in head]
    used = sum(b for _, b in head) + sum(b for _, b in tail)
    has_break = any(n == "break" for n, _ in body)
    cycle = 0
    while True:
        part = [[n, b, cycle] for n, b in body]
        if cycle % 2 == 1 and not has_break:
            part.insert(len(part) // 2, ["break", 8, cycle])
        added = False
        for item in part:
            # stop at the section that lands closest to the target length
            if cycle > 0 and used + item[1] - target > target - used:
                break
            out.append(item)
            used += item[1]
            added = True
        if not added or used >= target or len(out) and out[-1] is not part[-1]:
            break
        cycle += 1
        if cycle > 200:  # safety
            break
    # end on a hook before the outro when there's room, so the song resolves
    if out and out[-1][0] != "hook" and any(n == "hook" for n, _ in body):
        hb = next(b for n, b in body if n == "hook")
        if used + hb <= target + hb // 2:
            out.append(["hook", hb, cycle])
    out += [[n, b, cycle] for n, b in tail]
    return out


class Song:
    def __init__(self, s):
        self.s = s
        self.step = 60.0 / s["bpm"] / 4
        self.bar = self.step * 16
        self.sections = []
        cur = 0
        secs = FORMATS.get(s.get("format", "full"))
        self.short = secs is not None
        if self.short:
            arr = [[n, b, 0] for n, b in tiktok_arrangement(s["bpm"], secs)]
        elif s.get("length"):
            arr = extend_arrangement(s["arrangement"], s["bpm"], s["length"])
        else:
            arr = [[n, b, 0] for n, b in s["arrangement"]]
        self.arrangement = [[n, b] for n, b, _ in arr]
        for i, (name, bars, cycle) in enumerate(arr):
            self.sections.append({"i": i, "name": name, "bars": bars, "start": cur, "cycle": cycle})
            cur += bars
        self.total_bars = cur
        self.length = self.total_bars * self.bar + 4.0
        self.N = int(self.length * SR)
        self.rng = np.random.default_rng(s["seed"])
        prog = s["progression"]
        self.voiced = theory.voice_progression(s["key"], s["scale"], prog,
                                               s["chords"]["voicing"], s["chords"]["octave"])
        self.chord_steps = int(16 * s["chord_bars"])

    def next_name(self, sec):
        i = sec["i"] + 1
        return self.sections[i]["name"] if i < len(self.sections) else None

    def active(self, track, sec):
        return track in self.s["sections"].get(sec["name"], [])

    def time(self, sec, abs_step, humanize=True):
        t = sec["start"] * self.bar + abs_step * self.step
        if int(abs_step) % 2 == 1:
            t += self.s["swing"] * self.step / 3
        if humanize and self.s["humanize"] > 0:
            t += self.rng.normal(0, 0.004 * self.s["humanize"])
        return max(0.0, t)

    def vel(self, base):
        h = self.s["humanize"]
        return base * (1 - h * 0.15 * self.rng.random())

    def chord_index(self, abs_step):
        return int(abs_step // self.chord_steps) % len(self.s["progression"])

    def cut_before_hook(self, sec):
        return self.next_name(sec) == "hook" and self.s["energy"] > 0.3 and sec["bars"] >= 2


# ================================================================ event builders
def drum_events(song, name):
    s = song.s
    cfg = s["drums"][name]
    ev = []
    if cfg["mute"]:
        return ev
    for sec in song.sections:
        if not song.active(name, sec):
            continue
        for b in range(sec["bars"]):
            pat = list(cfg["pattern"])
            last = b == sec["bars"] - 1
            if name == "kick" and last and song.cut_before_hook(sec):
                pat[8:] = ["."] * 8
            if cfg.get("fills") and last and s["energy"] > 0.45 and sec["bars"] >= 2:
                for i in ([13, 15] + ([11, 14] if s["energy"] > 0.75 else [])):
                    if pat[i] == ".":
                        pat[i] = "o"
            roll = cfg.get("rolls") and s["energy"] > 0.55 and b % 4 == 3
            if roll:
                pat[12:] = ["."] * 4
            for i, c in enumerate(pat):
                if c in HIT_CHARS:
                    ev.append((song.time(sec, b * 16 + i), song.vel(1.0 if c == "x" else 0.55)))
            if roll:
                for k in range(8):
                    st = b * 16 + 12 + k * 0.5
                    t = sec["start"] * song.bar + st * song.step
                    ev.append((t, 0.4 + 0.07 * k))
    return ev


def _triggers(song, sec, pattern, chars, cut):
    """Absolute-step triggers in a section, each with its end step."""
    bars = sec["bars"]
    limit = bars * 16
    if cut:
        limit = (bars - 1) * 16 + 8
    trig = [(b * 16 + i, c) for b in range(bars) for i, c in enumerate(pattern)
            if c in chars and b * 16 + i < limit]
    out = []
    for k, (st, c) in enumerate(trig):
        nxt = trig[k + 1][0] if k + 1 < len(trig) else limit
        boundary = (st // song.chord_steps + 1) * song.chord_steps
        out.append((st, c, min(nxt, boundary, limit)))
    return out


def bass_events(song):
    s = song.s
    cfg = s["bass"]
    ev = []
    if cfg["mute"]:
        return ev
    for sec in song.sections:
        if not song.active("bass", sec):
            continue
        prev = None
        for st, c, end in _triggers(song, sec, cfg["pattern"], BASS_CHARS, song.cut_before_hook(sec)):
            deg = s["progression"][song.chord_index(st)]
            midi = 12 * (cfg["octave"] + 1) + theory.chord_root_pc(s["key"], s["scale"], deg)
            midi += {"5": 7, "^": 12}.get(c, 0)
            glide_from = 0.0
            if cfg["sound"] == "808" and cfg["glide"] > 0 and prev and prev[1] == st and prev[0] != midi:
                glide_from = theory.midi_to_hz(prev[0])
            dur = (end - st) * song.step
            ev.append((song.time(sec, st), midi, dur, song.vel(1.0 if c != "o" else 0.6), glide_from))
            prev = (midi, end)
    return ev


def chord_events(song):
    s = song.s
    cfg = s["chords"]
    ev = []
    if cfg["mute"]:
        return ev
    for sec in song.sections:
        if not song.active("chords", sec):
            continue
        for st, c, end in _triggers(song, sec, cfg["pattern"], HIT_CHARS, False):
            notes = song.voiced[song.chord_index(st)]
            t = song.time(sec, st)
            v = song.vel(0.9 if c == "x" else 0.55)
            for j, n in enumerate(notes):
                # tiny strum makes chords feel played, not pasted
                ev.append((t + j * 0.006 * s["humanize"], n, (end - st) * song.step, v))
    return ev


def make_phrase(song, rng, bars):
    s = song.s
    m = s["melody"]
    density = m["density"]
    lo = 12 * (m["octave"] + 1)
    hi = lo + 14
    spcs = theory.scale_pcs(s["key"], s["scale"])
    scale_notes = [n for n in range(lo - 2, hi + 1) if n % 12 in spcs]
    w = [1.0 if i % 4 == 0 else 0.6 if i % 2 == 0 else 0.35 for i in range(16)]

    def rhythm():
        r = [i for i in range(16) if rng.random() < min(0.95, density * w[i] * 1.6)]
        if len(r) < 2:
            r = sorted(set(r + [0, 8]))
        return r

    def mutate(r):
        r = list(r)
        if len(r) > 2 and rng.random() < 0.6:
            r.pop(int(rng.integers(1, len(r))))
        free = [i for i in range(16) if i not in r]
        if free:
            r.append(int(rng.choice(free)))
        return sorted(r)

    def chord_notes(bar, step):
        deg = s["progression"][song.chord_index(bar * 16 + step)]
        pcs = theory.chord_pcs(s["key"], s["scale"], deg, "triad")
        return [n for n in scale_notes if n % 12 in pcs] or scale_notes, pcs[0]

    def nearest(cands, target):
        return min(cands, key=lambda c: abs(c - target))

    def choose(prev, cands):
        cands = np.array(cands)
        wts = np.exp(-np.abs(cands - prev) / 3.0) * np.where(cands == prev, 0.35, 1.0)
        return int(rng.choice(cands, p=wts / wts.sum()))

    A, B = rhythm(), rhythm()
    A2 = mutate(A)
    prev = nearest(scale_notes, (lo + hi) // 2)
    first_a = None
    phrase = []
    for pb in range(bars):
        form = "B" if pb == bars - 1 else ("A2" if pb % 2 == 1 else "A")
        r = {"A": A, "A2": A2, "B": B}[form]
        notes = []
        for k, step in enumerate(r):
            cn, root_pc = chord_notes(pb, step)
            strong = step % 4 == 0
            if form == "A" and first_a is not None and k < len(first_a):
                p = first_a[k]
                p = nearest(cn, p) if step % 8 == 0 else nearest(scale_notes, p)
            elif strong and rng.random() < 0.75:
                p = choose(prev, cn)
            else:
                p = choose(prev, scale_notes)
            if form == "B" and k == len(r) - 1:
                roots = [n for n in cn if n % 12 == root_pc] or cn
                p = nearest(roots, prev)
            nxt = r[k + 1] if k + 1 < len(r) else 16
            dur = min(nxt - step, 8 if form == "B" else 6)
            vel = (0.9 if strong else 0.7) * (0.9 + 0.1 * rng.random())
            notes.append((step, p, dur, vel))
            prev = p
        if form == "A" and first_a is None:
            first_a = [n[1] for n in notes]
        phrase.append(notes)
    return phrase


def melody_events(song):
    s = song.s
    cfg = s["melody"]
    ev = []
    if cfg["mute"]:
        return ev
    cycle = len(s["progression"]) * song.chord_steps
    steps = cycle
    while steps % 16 or steps < 32:
        steps += cycle
    bars = min(16, steps // 16)
    phrases = {}
    for sec in song.sections:
        if not song.active("melody", sec):
            continue
        # Long beats get new melody ideas on later passes; the main theme returns every
        # other pass so the song still feels like one song.
        c = sec.get("cycle", 0)
        variant = 0 if c % 2 == 0 else 1 + (c // 2) % 2
        key = ("break" if sec["name"] == "break" else "main", variant)
        if key not in phrases:
            rng = np.random.default_rng(cfg["seed"] * 1000 + (1 if key[0] == "break" else 0) + 10 * variant)
            phrases[key] = make_phrase(song, rng, bars)
        ph = phrases[key]
        for b in range(sec["bars"]):
            for step, midi, dur, vel in ph[b % bars]:
                ev.append((song.time(sec, b * 16 + step), midi, dur * song.step, song.vel(vel)))
    return ev


# ================================================================ rendering
def _place(buf, y, t, gain=1.0):
    s = int(t * SR)
    if s >= len(buf):
        return
    e = min(len(buf), s + len(y))
    buf[s:e] += y[: e - s] * gain


DRUM_FN = {
    "kick": lambda c, v: synth.kick(c.get("sound", "punchy"), c["tune"], c["decay"], v),
    "snare": lambda c, v: synth.snare(c.get("sound", "tight"), c["tune"], c["decay"], v),
    "clap": lambda c, v: synth.clap("clap", c["tune"], c["decay"], v),
    "hat": lambda c, v: synth.hat(False, c["tune"], c["decay"], v),
    "openhat": lambda c, v: synth.hat(True, c["tune"], c["decay"], v),
    "shaker": lambda c, v: synth.shaker("shaker", c["tune"], c["decay"], v),
    "perc": lambda c, v: synth.perc(c.get("sound", "rim"), c["tune"], c["decay"], v),
}
# How many different takes each drum rotates through (kicks stay identical, like a producer's)
DRUM_VARIATIONS = {"kick": 1, "snare": 3, "clap": 4, "hat": 4, "openhat": 2, "shaker": 4, "perc": 3}


# Gain staging: the level each track sits at when its volume slider is 0 dB.
TRIM = {"clap": 4, "hat": 6, "openhat": 5, "shaker": 5, "perc": 5, "snare": 2,
        "melody": 4, "bass": -2, "chords": 1}


# Measured so every chord/melody sound plays at a similar loudness at the same volume
# (recorded instruments peak high on the attack, sustained synths don't).
TONE_GAIN = {"pluck": 8.0, "glock": 5.5, "kalimba": 5.3, "piano": 3.1, "pad": 2.6, "lead": 2.2,
             "marimba": 0.0, "vibes": -0.4, "rhodes": -2.4, "sax": -2.5, "bell": -3.2,
             "flute": -3.8, "organ": -6.6}


def _bright_lp(b):
    return 1500 + b ** 2 * 15000


def _load_tag(path):
    sr, y = wavfile.read(path)
    y = y.astype(np.float32)
    if y.ndim == 1:
        y = np.stack([y, y], axis=1)
    if sr != SR:
        idx = np.arange(0, len(y), sr / SR)
        y = np.stack([np.interp(idx, np.arange(len(y)), y[:, c]) for c in range(2)], axis=1)
    return y.astype(np.float32)


def tag_times(song, tag_len, places):
    """Start times (seconds) for the producer tag. `places` is a list from TAG_PLACES
    (an old single 'position' string also works). Tags never overlap each other."""
    if isinstance(places, str):
        places = _LEGACY_PLACES.get(places, ["start"])
    end = song.total_bars * song.bar
    want = []
    if "start" in places:
        want.append(0.05)
    for sec in song.sections:
        t0 = sec["start"] * song.bar
        if "hooks" in places and sec["name"] == "hook" and sec["i"] > 0:
            want.append(t0 - tag_len + 0.25)  # the last word lands right on the drop
        if "verses" in places and sec["name"] == "verse":
            want.append(t0 + 0.05)
    if "every8" in places:
        t = 8 * song.bar
        while t < end - tag_len:
            want.append(t)
            t += 8 * song.bar
    if "end" in places and song.sections:
        last = song.sections[-1]
        t0 = last["start"] * song.bar if last["name"] == "outro" else end - min(8, last["bars"]) * song.bar
        want.append(t0 + 0.05)
    times = []
    for t in sorted(set(round(x, 3) for x in want)):
        if t < 0 or t + tag_len > end + 1.0:
            continue
        if times and t < times[-1] + tag_len + 0.3:
            continue
        times.append(t)
    return times


def tag_duck_curve(tag, duck):
    """Gain curve that dips the beat under one tag, starting a moment before it."""
    pre, tail = int(0.15 * SR), int(0.4 * SR)
    lvl = np.concatenate([np.zeros(pre, np.float32), np.abs(tag).max(axis=1), np.zeros(tail, np.float32)])
    env = fx.filt(lvl, "lowpass", 6)
    env = np.clip(env / (env.max() + 1e-9) * 3, 0, 1)
    return fx.db(-8 * duck * env).astype(np.float32), pre


def lay_tag(buf, tag, starts, duck):
    """Duck `buf` (n, 2) under each tag and add the tag, in place."""
    n = len(buf)
    g, pre = tag_duck_curve(tag, duck)
    for a in starts:
        lo = max(0, a - pre)
        hi = min(n, a - pre + len(g))
        if hi > lo:
            buf[lo:hi] *= g[lo - (a - pre): hi - (a - pre), None]
        e = min(n, a + len(tag))
        if e > a:
            buf[a:e] += tag[: e - a]


def write_tag_stem(path, n, tag, starts):
    """The tag's own stem: silence with the tag at each place, written piece by piece."""
    w = wavfile.Writer(path, SR, 2, n)
    step = 1 << 18
    for a in range(0, n, step):
        b = min(n, a + step)
        blk = np.zeros((b - a, 2), np.float32)
        for t in starts:
            lo, hi = max(a, t), min(b, t + len(tag))
            if hi > lo:
                blk[lo - a: hi - a] += tag[lo - t: hi - t]
        w.write(blk)
    w.close()


def preview_tag(beat_dir, tag_path, places, volume=-1.0, duck=0.5, out_name="tag_preview.wav"):
    """Lay a tag over an already-made beat (no re-render), so it can be heard in place.
    Uses the beat's saved settings to find the hooks and verses."""
    with open(os.path.join(beat_dir, "settings.json"), encoding="utf-8") as f:
        settings = sanitize(json.load(f))
    song = Song(settings)
    sr, beat = wavfile.read(os.path.join(beat_dir, "beat.wav"))
    beat = beat.astype(np.float32)
    if beat.ndim == 1:
        beat = np.stack([beat, beat], axis=1)
    tag = _load_tag(tag_path)
    peak = float(np.max(np.abs(beat))) or 1.0
    tag = tag * np.float32(peak * fx.db(volume) / (np.max(np.abs(tag)) + 1e-9))
    times = tag_times(song, len(tag) / SR, places)
    lay_tag(beat, tag, [int(t * SR) for t in times], duck)
    beat = dsp.blocks(beat, lambda seg: fx.limiter(seg, -1.0), int(0.25 * SR))
    out = os.path.join(beat_dir, out_name)
    w = wavfile.Writer(out, SR, 2, len(beat), pcm16=True)
    for a in range(0, len(beat), 1 << 18):
        w.write(beat[a:a + (1 << 18)])
    w.close()
    return {"wav": out, "times": [round(t, 2) for t in times], "count": len(times)}


def make_video(audio_path, out_path, title, subtitle):
    """Vertical 1080x1920 video with a moving waveform, ready to post."""
    if not media.has_ffmpeg():
        return None
    fonts = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf",
             "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
             "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"]
    font = next((f for f in fonts if os.path.exists(f)), None)
    folder = os.path.dirname(out_path)
    vf = ("[1:a]aformat=channel_layouts=mono,showwaves=s=1080x640:mode=cline:rate=30:scale=sqrt:colors=white,"
          "format=rgba,lutrgb=r=val:g=val*0.71:b=val*0.28[w];"
          "[0:v][w]overlay=0:640:shortest=1")
    if font:
        esc = lambda p: p.replace("\\", "/").replace(":", "\\:")
        for i, (txt, size, y, col) in enumerate(((title, 76, 380, "white"), (subtitle, 42, 1400, "0xb9b5c6"))):
            tf = os.path.join(folder, f"_text{i}.txt")
            with open(tf, "w", encoding="utf-8") as f:
                f.write(txt)
            vf += (f",drawtext=fontfile='{esc(font)}':textfile='{esc(tf)}':fontcolor={col}:"
                   f"fontsize={size}:x=(w-text_w)/2:y={y}")
    vf += "[v]"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x0f0e13:s=1080x1920:r=30",
           "-i", audio_path, "-filter_complex", vf, "-map", "[v]", "-map", "1:a", "-c:v", "libx264",
           "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
           "-shortest", "-movflags", "+faststart", out_path]
    p = subprocess.run(cmd, capture_output=True, text=True)
    for i in range(2):
        try:
            os.remove(os.path.join(folder, f"_text{i}.txt"))
        except OSError:
            pass
    return out_path if p.returncode == 0 and os.path.exists(out_path) else None


def render(settings, outdir, progress=None, tag_path=None):
    def say(msg):
        if progress:
            progress(msg)

    s = sanitize(settings)
    song = Song(s)
    N = song.N
    os.makedirs(os.path.join(outdir, "stems"), exist_ok=True)

    # long beats save 16-bit stems (half the size) when they can't clip; others stay 32-bit float
    small_stems = bool(s.get("length")) and not song.short
    mix = np.zeros((N, 2), np.float32)
    rev_send = np.zeros(N, np.float32)  # mono sends: reverb and delay make their own stereo
    del_send = np.zeros(N, np.float32)
    midi_tracks = {}
    stems = []

    kick_ev = drum_events(song, "kick")
    duck = fx.sidechain_curve(N, [t for t, _ in kick_ev], s["mix"]["sidechain"])

    def finish(name, mono, cfg, pan=0.0, width=0.0, sidechain=False):
        """Gain, pump, pan; then add to the mix and sends and save the stem, block by block
        so a 10-minute song never needs extra full-length stereo copies."""
        mono = np.asarray(mono, np.float32)
        mono *= np.float32(fx.db(cfg["volume"] + TRIM.get(name, 0)))
        if sidechain:
            mono *= duck
        side = None
        if width > 0:  # mono-safe stereo spread: a short delayed copy, highs only
            d = int(0.015 * SR)
            side = np.zeros_like(mono)
            side[d:] = mono[:-d]
            fx.filt(side, "highpass", 300, inplace=True)
            side *= np.float32(width * 0.5)
        ang = (np.clip(pan, -1, 1) + 1) * np.pi / 4
        cl, cr = np.float32(np.cos(ang)), np.float32(np.sin(ang))
        rv, dl = np.float32(cfg.get("reverb") or 0), np.float32(cfg.get("delay") or 0)
        path = os.path.join(outdir, "stems", f"{len(stems) + 1:02d}_{name}.wav")
        peak = float(np.max(np.abs(mono))) * max(cl, cr) + (float(np.max(np.abs(side))) if side is not None else 0)
        w = wavfile.Writer(path, SR, 2, N, pcm16=small_stems and peak < 0.99)
        step = 1 << 18
        for a in range(0, N, step):
            b = min(N, a + step)
            st = np.empty((b - a, 2), np.float32)
            np.multiply(mono[a:b], cl, out=st[:, 0])
            np.multiply(mono[a:b], cr, out=st[:, 1])
            if side is not None:
                st[:, 0] += side[a:b]
                st[:, 1] -= side[a:b]
            w.write(st)
            mix[a:b] += st
            if rv or dl:
                m = st.mean(axis=1)
                if rv:
                    rev_send[a:b] += m * rv
                if dl:
                    del_send[a:b] += m * dl
        w.close()
        stems.append(path)

    # ---- drums
    say("Programming drums")
    for name in DRUMS:
        cfg = s["drums"][name]
        ev = kick_ev if name == "kick" else drum_events(song, name)
        if not ev:
            continue
        takes = [DRUM_FN[name](cfg, k) for k in range(DRUM_VARIATIONS.get(name, 1))]
        rng = np.random.default_rng(len(name) * 101 + int(s.get("seed", 0)))
        buf = np.zeros(N, np.float32)
        last = -1
        for t, v in ev:
            # pick a different take than last time, the way samplers round-robin
            k = int(rng.integers(len(takes)))
            if len(takes) > 1 and k == last:
                k = (k + 1) % len(takes)
            last = k
            _place(buf, takes[k], t, v)
        if name not in ("kick",):
            fx.filt(buf, "highpass", 300 if name in ("hat", "openhat", "shaker") else 90, inplace=True)
        finish(name, buf, cfg, pan=cfg["pan"])
        midi_tracks[name] = (9, [(t, 0.1, GM_DRUMS[name], v) for t, v in ev])

    # ---- bass
    say("Laying down the bass")
    cfg = s["bass"]
    ev = bass_events(song)
    if ev:
        buf = np.zeros(N, np.float32)
        for t, midi, dur, v, gfrom in ev:
            y = synth.bass_note(cfg["sound"], round(theory.midi_to_hz(midi), 3), round(dur, 3),
                                cfg["decay"], round(gfrom, 3), round(cfg["glide"] * 0.12, 3))
            _place(buf, y, t, v)
        fx.filt(buf, "highpass", 28, inplace=True)
        fx.filt(buf, "lowpass", 5000, inplace=True)
        if s["mix"]["phone_bass"] > 0:
            peak = np.max(np.abs(buf)) or 1.0
            harm = fx.filt(fx.filt(np.tanh(buf / peak * 5), "highpass", 160), "lowpass", 1800)
            buf = buf + harm * peak * 0.35 * s["mix"]["phone_bass"]
        finish("bass", buf, cfg, sidechain=cfg.get("sidechain"))
        midi_tracks["bass"] = (1, [(t, d, n, v) for t, n, d, v, _ in ev])

    # ---- chords
    say("Playing the chords")
    cfg = s["chords"]
    ev = chord_events(song)
    if ev:
        buf = np.zeros(N, np.float32)
        for t, n, dur, v in ev:
            y = synth.tone_note(cfg["sound"], round(theory.midi_to_hz(n), 3), round(dur, 3),
                                round(cfg["brightness"], 2))
            _place(buf, y, t, v * 0.45 * fx.db(TONE_GAIN.get(cfg["sound"], 0)))
        fx.filt(buf, "highpass", 140, inplace=True)
        fx.filt(buf, "lowpass", _bright_lp(cfg["brightness"]), inplace=True)
        finish("chords", buf, cfg, width=cfg["stereo"], sidechain=cfg.get("sidechain"))
        midi_tracks["chords"] = (2, [(t, d, n, v) for t, n, d, v in ev])

    # ---- melody
    say("Writing a melody")
    cfg = s["melody"]
    ev = melody_events(song)
    if ev:
        buf = np.zeros(N, np.float32)
        for t, n, dur, v in ev:
            y = synth.tone_note(cfg["sound"], round(theory.midi_to_hz(n), 3), round(dur, 3),
                                round(cfg["brightness"], 2))
            _place(buf, y, t, v * fx.db(TONE_GAIN.get(cfg["sound"], 0)))
        fx.filt(buf, "highpass", 220, inplace=True)
        fx.filt(buf, "lowpass", _bright_lp(cfg["brightness"]), inplace=True)
        finish("melody", buf, cfg, width=0.3, sidechain=cfg.get("sidechain"))
        midi_tracks["melody"] = (3, [(t, d, n, v) for t, n, d, v in ev])

    # ---- transitions (risers, crashes, booms)
    cfg = s["fx"]
    if not cfg.get("mute") and (cfg.get("risers") or cfg.get("impacts")):
        buf = np.zeros(N, np.float32)
        for sec in song.sections:
            t0 = sec["start"] * song.bar
            if cfg.get("impacts") and sec["i"] > 0 and song.active("fx", sec):
                _place(buf, synth.crash(), t0, 0.8)
                if sec["name"] == "hook":
                    _place(buf, synth.boom(), t0, 0.9)
            if cfg.get("risers") and song.next_name(sec) == "hook" and song.active("fx", sec):
                d = min(2, sec["bars"]) * song.bar
                _place(buf, synth.riser(round(d, 3)), t0 + sec["bars"] * song.bar - d, 0.9)
        cfg = dict(cfg, reverb=0.4)
        finish("fx", buf, cfg)

    # ---- texture
    cfg = s["texture"]
    if cfg["sound"] == "vinyl" and not cfg.get("mute"):
        mask = np.zeros(N, np.float32)
        for sec in song.sections:
            if song.active("texture", sec):
                a = int(sec["start"] * song.bar * SR)
                b = int((sec["start"] + sec["bars"]) * song.bar * SR)
                mask[a:b] = 1
        mask = fx.filt(mask, "lowpass", 5)
        finish("texture", synth.vinyl(N) * mask, cfg)

    # ---- effect returns
    say("Mixing")
    # the instruments are done: free cached notes and the pump curve before the big steps
    synth.tone_note.cache_clear()
    synth.bass_note.cache_clear()
    duck = None
    mx = s["mix"]

    def add_return(name, wet_l, wet_r, gain):
        path = os.path.join(outdir, "stems", f"{len(stems) + 1:02d}_{name}.wav")
        g = np.float32(gain)
        peak = max(float(np.max(np.abs(wet_l))), float(np.max(np.abs(wet_r)))) * gain
        w = wavfile.Writer(path, SR, 2, N, pcm16=small_stems and peak < 0.99)
        for a in range(0, N, 1 << 18):
            b = min(N, a + (1 << 18))
            st = np.stack([wet_l[a:b], wet_r[a:b]], axis=1) * g
            w.write(st)
            mix[a:b] += st
        w.close()
        stems.append(path)

    if mx["reverb"] > 0 and np.any(rev_send):
        wl, wr = fx.reverb_mono(rev_send, mx["reverb_size"])
        rev_send = None
        add_return("reverb_return", wl, wr, mx["reverb"] * 0.8)
        wl = wr = None
    rev_send = None
    if mx["delay"] > 0 and np.any(del_send):
        wet = fx.delay(del_send, s["bpm"])
        del_send = None
        add_return("delay_return", wet[:, 0], wet[:, 1], mx["delay"] * 0.6)
        wet = None
    del_send = None

    # ---- producer tag (the beat ducks a little underneath it)
    tag_info = None
    if tag_path and os.path.exists(tag_path) and not s["tag"]["mute"] and s["tag"]["places"]:
        tag = _load_tag(tag_path)
        peak = np.max(np.abs(mix)) or 1.0
        tag = tag * np.float32(peak * fx.db(s["tag"]["volume"]) / (np.max(np.abs(tag)) + 1e-9))
        times = tag_times(song, len(tag) / SR, s["tag"]["places"])
        starts = [int(t * SR) for t in times]
        lay_tag(mix, tag, starts, s["tag"]["duck"])
        path = os.path.join(outdir, "stems", f"{len(stems) + 1:02d}_producer_tag.wav")
        write_tag_stem(path, N, tag, starts)
        stems.append(path)
        tag_info = len(times)

    # ---- master bus
    say("Mastering")
    peak = np.max(np.abs(mix)) or 1.0
    mix *= np.float32(fx.db(-6) / peak)
    # the whole mix-bus chain runs block by block, in place: the mix becomes the master bus
    bus = dsp.blocks(mix, lambda seg: fx.master_chain(seg, mx["warmth"], mx["air"], mx["width"]),
                     int(1.5 * SR), inplace=True)
    mix = None
    last = song.sections[-1]
    if last["name"] == "outro":
        a = int(last["start"] * song.bar * SR)
        b = int(song.total_bars * song.bar * SR)
        bus[a:b] *= (np.linspace(1, 0, b - a, dtype=np.float32) ** 1.5)[:, None]
        bus[b:] = 0
    if song.short:
        # loop-ready: cut exactly on the bar line and wrap the reverb tail back to the start
        L = int(round(song.total_bars * song.bar * SR))
        head, tail = bus[:L].copy(), bus[L:]
        head[: len(tail)] += tail[: L]
        bus = head
    final, loud = fx.master(bus, mx["loudness"], -1.0)
    bus = None

    if not song.short:  # trim silence at the end
        env = np.max(np.abs(final), axis=1)
        loud_idx = np.nonzero(env > fx.db(-60))[0]
        end = min(N, (loud_idx[-1] if len(loud_idx) else N) + int(0.5 * SR))
        final = final[:end]

    # ---- export
    say("Exporting")
    # 16-bit WAV with TPDF dither, written block by block
    wav_path = os.path.join(outdir, "beat.wav")
    w = wavfile.Writer(wav_path, SR, final.shape[1], len(final), pcm16=True)
    r1, r2 = np.random.default_rng(0), np.random.default_rng(1)
    for a in range(0, len(final), 1 << 18):
        blk = final[a:a + (1 << 18)] * np.float32(32767)
        blk += r1.random(blk.shape, dtype=np.float32)
        blk -= r2.random(blk.shape, dtype=np.float32)
        w.write(np.clip(np.round(blk), -32768, 32767).astype(np.int16))
    w.close()
    mp3_path = media.to_mp3(wav_path, os.path.join(outdir, "beat.mp3"))
    midi_path = os.path.join(outdir, "beat.mid")
    write_midi(midi_path, s["bpm"], midi_tracks)
    zip_path = os.path.join(outdir, "stems.zip")
    # audio barely compresses, so store it; then drop the loose copies to save phone storage
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
        for p in stems:
            z.write(p, os.path.basename(p))
    shutil.rmtree(os.path.join(outdir, "stems"), ignore_errors=True)
    with open(os.path.join(outdir, "settings.json"), "w") as f:
        json.dump(s, f, indent=2)
    video_path = None
    if s["export_video"] and media.has_ffmpeg():
        say("Making the video")
        title = s["title"] or f"{GENRES[s['genre']]['label']} beat"
        sub = f"{round(s['bpm'])} BPM · {s['key']} {s['scale']}" + (f" · prod. {s['producer']}" if s["producer"] else "")
        video_path = make_video(wav_path, os.path.join(outdir, "beat.mp4"), title, sub)

    return {
        "video": video_path, "tags_placed": tag_info, "arrangement": song.arrangement,
        "duration": round(len(final) / SR, 1),
        "lufs": round(loud, 1),
        "peak_db": round(float(20 * np.log10(np.max(np.abs(final)) + 1e-9)), 2),
        "wav": wav_path, "mp3": mp3_path if mp3_path and os.path.exists(mp3_path) else None,
        "midi": midi_path, "stems": zip_path, "settings": s,
    }
