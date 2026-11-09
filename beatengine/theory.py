"""Music theory helpers: keys, scales, chords and voice leading."""

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

SCALES = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "harmonic minor": [0, 2, 3, 5, 7, 8, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
}

# Ready-made progressions, written as scale degrees (1 = the key's home chord).
PROGRESSIONS = {
    "Dark & emotional (1-6-3-7)": [1, 6, 3, 7],
    "Deep groove (1-4-6-5)": [1, 4, 6, 5],
    "Jazzy (2-5-1-6)": [2, 5, 1, 6],
    "Pop anthem (1-5-6-4)": [1, 5, 6, 4],
    "Afro vamp (1-7-6-7)": [1, 7, 6, 7],
    "Two-chord vamp (1-4)": [1, 4],
    "Uplifting (6-4-1-5)": [6, 4, 1, 5],
    "Hypnotic (1-1-6-6)": [1, 1, 6, 6],
}

VOICINGS = ["triad", "7th", "9th"]


def key_pc(key):
    return NOTE_NAMES.index(key)


def degree_semitones(scale, deg0):
    """Semitones above the key for a 0-based scale degree (may exceed 6)."""
    octave, idx = divmod(deg0, 7)
    return SCALES[scale][idx] + 12 * octave


def scale_pcs(key, scale):
    k = key_pc(key)
    return {(k + s) % 12 for s in SCALES[scale]}


def chord_root_pc(key, scale, degree):
    return (key_pc(key) + degree_semitones(scale, degree - 1)) % 12


def chord_pcs(key, scale, degree, voicing="triad"):
    stack = [0, 2, 4]
    if voicing in ("7th", "9th"):
        stack.append(6)
    if voicing == "9th":
        stack.append(8)
    k = key_pc(key)
    pcs = [(k + degree_semitones(scale, degree - 1 + s)) % 12 for s in stack]
    if voicing == "9th" and (pcs[-1] - pcs[0]) % 12 == 1:
        pcs = pcs[:-1]  # a flat 9 clashes; producers drop it
    return pcs


def _inversions(pcs, center):
    """All inversions of a chord stacked upward, starting near `center`."""
    out = []
    n = len(pcs)
    for r in range(n):
        order = pcs[r:] + pcs[:r]
        base = order[0]
        # lowest note: the pc closest below/at center - 5
        low = center - 7
        first = low + ((base - low) % 12)
        notes = [first]
        for pc in order[1:]:
            nxt = notes[-1] + ((pc - notes[-1]) % 12 or 12)
            notes.append(nxt)
        out.append(notes)
    return out


def voice_progression(key, scale, progression, voicing, octave):
    """Voice every chord so it moves smoothly from the previous one."""
    center = 12 * (octave + 1) + 7  # around G of the chosen octave
    voiced = []
    prev = None
    for deg in progression:
        pcs = chord_pcs(key, scale, deg, voicing)
        cands = _inversions(pcs, center)
        if prev is None:
            best = min(cands, key=lambda c: abs(sum(c) / len(c) - center) + 0.4 * (c[-1] - c[0]))
        else:
            pm = sum(prev) / len(prev)
            best = min(
                cands,
                key=lambda c: abs(sum(c) / len(c) - pm) * 1.0
                + abs(sum(c) / len(c) - center) * 0.35
                + (c[-1] - c[0]) * 0.4,
            )
        voiced.append(best)
        prev = best
    return voiced


def midi_to_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)
