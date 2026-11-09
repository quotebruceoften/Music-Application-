"""Genre starting points. Every value here can be changed by the user.

Pattern grids have 16 steps (one bar of 16th notes):
  x = hit   o = soft hit   . = rest
Bass patterns also allow:  5 = play the fifth   ^ = play an octave up
"""
import copy

DRUMS = ["kick", "snare", "clap", "hat", "openhat", "shaker", "perc"]
INSTRUMENTS = ["bass", "chords", "melody"]
EXTRAS = ["fx", "texture"]
TRACKS = DRUMS + INSTRUMENTS + EXTRAS

SECTION_TYPES = ["intro", "verse", "hook", "break", "outro"]

OPTIONS = {
    "kick_sounds": ["punchy", "808kick", "soft"],
    "snare_sounds": ["tight", "fat"],
    "perc_sounds": ["rim", "conga", "wood", "cowbell"],
    "bass_sounds": ["logdrum", "808", "sub", "pluck"],
    "chord_sounds": ["rhodes", "piano", "pad", "organ", "pluck"],
    "melody_sounds": ["bell", "pluck", "flute", "lead", "marimba", "rhodes", "piano"],
    "texture_sounds": ["none", "vinyl"],
}


def _drum(pattern, volume=-6.0, sound=None, tune=0.0, decay=1.0, pan=0.0, reverb=0.05, **kw):
    d = {"pattern": pattern, "volume": volume, "tune": tune, "decay": decay,
         "pan": pan, "reverb": reverb, "mute": False}
    if sound:
        d["sound"] = sound
    d.update(kw)
    return d


def _sections(drums_in_verse):
    all_drums = list(DRUMS)
    return {
        "intro": ["chords", "hat", "shaker", "texture", "fx"],
        "verse": drums_in_verse + ["bass", "chords", "texture", "fx"],
        "hook": all_drums + ["bass", "chords", "melody", "texture", "fx"],
        "break": ["chords", "melody", "shaker", "texture", "fx"],
        "outro": ["chords", "hat", "shaker", "perc", "texture", "fx"],
    }


BASE_MIX = {"reverb": 0.5, "reverb_size": 2.0, "delay": 0.5, "sidechain": 0.5,
            "warmth": 0.25, "width": 1.15, "loudness": -14.0, "air": 0.5}

GENRES = {
    "amapiano": {
        "label": "Amapiano",
        "bpm": 113, "key": "F", "scale": "minor", "swing": 0.3, "energy": 0.6,
        "humanize": 0.5, "seed": 7,
        "progression": [1, 4, 6, 5], "chord_bars": 1,
        "arrangement": [["intro", 4], ["verse", 8], ["hook", 8], ["break", 4],
                        ["verse", 8], ["hook", 8], ["outro", 4]],
        "drums": {
            "kick": _drum("x...x...x...x...", -5, "soft"),
            "snare": _drum("................", -10, "tight", mute=True),
            "clap": _drum("....x.......x...", -7, reverb=0.25, fills=True),
            "hat": _drum("..x...x...x...x.", -13, pan=0.2),
            "openhat": _drum("................", -14),
            "shaker": _drum("oxoxoxoxoxoxoxox", -15, pan=-0.25),
            "perc": _drum("...x..x....x..x.", -12, "rim", pan=0.3, reverb=0.2),
        },
        "bass": {"sound": "logdrum", "pattern": "x..x..x...x..x..", "volume": -3.0,
                 "octave": 2, "decay": 1.0, "glide": 0.0, "mute": False, "sidechain": True},
        "chords": {"sound": "rhodes", "pattern": "x.....x...x.....", "voicing": "9th",
                   "octave": 4, "brightness": 0.6, "volume": -9.0, "stereo": 0.6,
                   "reverb": 0.3, "delay": 0.0, "mute": False, "sidechain": True},
        "melody": {"sound": "flute", "density": 0.4, "octave": 5, "volume": -12.0,
                   "brightness": 0.6, "reverb": 0.35, "delay": 0.25, "mute": False,
                   "sidechain": True, "seed": 3},
        "fx": {"risers": True, "impacts": True, "volume": -14.0, "mute": False},
        "texture": {"sound": "none", "volume": -26.0, "mute": False},
        "mix": dict(BASE_MIX, sidechain=0.45, warmth=0.3),
        "sections": _sections(["kick", "clap", "hat", "shaker", "perc"]),
    },
    "trap": {
        "label": "Trap",
        "bpm": 140, "key": "C#", "scale": "minor", "swing": 0.0, "energy": 0.7,
        "humanize": 0.3, "seed": 21,
        "progression": [1, 6, 3, 7], "chord_bars": 1,
        "arrangement": [["intro", 4], ["hook", 8], ["verse", 8], ["hook", 8],
                        ["verse", 8], ["hook", 8], ["outro", 4]],
        "drums": {
            "kick": _drum("x......x..x.....", -6, "punchy"),
            "snare": _drum("........x.......", -6, "fat", reverb=0.15, fills=True),
            "clap": _drum("........x.......", -9, reverb=0.2),
            "hat": _drum("x.x.x.x.x.x.x.x.", -12, pan=0.15, rolls=True),
            "openhat": _drum("......x.......x.", -16, pan=-0.2),
            "shaker": _drum("................", -18, mute=True),
            "perc": _drum("...........x....", -14, "rim", pan=0.35, reverb=0.25),
        },
        "bass": {"sound": "808", "pattern": "x......x..x.....", "volume": -4.0,
                 "octave": 1, "decay": 1.2, "glide": 0.4, "mute": False, "sidechain": False},
        "chords": {"sound": "pad", "pattern": "x.......x.......", "voicing": "triad",
                   "octave": 4, "brightness": 0.4, "volume": -13.0, "stereo": 0.8,
                   "reverb": 0.4, "delay": 0.0, "mute": False, "sidechain": False},
        "melody": {"sound": "bell", "density": 0.45, "octave": 5, "volume": -11.0,
                   "brightness": 0.6, "reverb": 0.35, "delay": 0.3, "mute": False,
                   "sidechain": False, "seed": 5},
        "fx": {"risers": True, "impacts": True, "volume": -13.0, "mute": False},
        "texture": {"sound": "none", "volume": -26.0, "mute": False},
        "mix": dict(BASE_MIX, sidechain=0.2, warmth=0.35, loudness=-12.0),
        "sections": _sections(["kick", "snare", "clap", "hat", "openhat", "perc"]),
    },
    "afrohouse": {
        "label": "Afro House",
        "bpm": 122, "key": "A", "scale": "minor", "swing": 0.15, "energy": 0.65,
        "humanize": 0.5, "seed": 12,
        "progression": [1, 7, 6, 7], "chord_bars": 1,
        "arrangement": [["intro", 8], ["verse", 8], ["hook", 8], ["break", 8],
                        ["hook", 8], ["outro", 8]],
        "drums": {
            "kick": _drum("x...x...x...x...", -5, "punchy", decay=0.9),
            "snare": _drum("................", -12, "tight", mute=True),
            "clap": _drum("....x.......x...", -8, reverb=0.2, fills=True),
            "hat": _drum("..x...x...x...x.", -11, pan=0.15),
            "openhat": _drum("..x...x...x...x.", -18, pan=-0.15),
            "shaker": _drum("oxooxoxooxoxooxo", -15, pan=-0.3),
            "perc": _drum("x..x..x...x..x..", -10, "conga", pan=0.35, reverb=0.15),
        },
        "bass": {"sound": "sub", "pattern": "..x...x...x..x..", "volume": -4.0,
                 "octave": 2, "decay": 1.0, "glide": 0.0, "mute": False, "sidechain": True},
        "chords": {"sound": "pad", "pattern": "x...............", "voicing": "7th",
                   "octave": 4, "brightness": 0.5, "volume": -12.0, "stereo": 0.8,
                   "reverb": 0.35, "delay": 0.0, "mute": False, "sidechain": True},
        "melody": {"sound": "marimba", "density": 0.5, "octave": 5, "volume": -11.0,
                   "brightness": 0.6, "reverb": 0.3, "delay": 0.3, "mute": False,
                   "sidechain": True, "seed": 9},
        "fx": {"risers": True, "impacts": True, "volume": -14.0, "mute": False},
        "texture": {"sound": "none", "volume": -26.0, "mute": False},
        "mix": dict(BASE_MIX, sidechain=0.55),
        "sections": _sections(["kick", "clap", "hat", "shaker", "perc"]),
    },
    "lofi": {
        "label": "Lo-fi",
        "bpm": 84, "key": "D", "scale": "major", "swing": 0.55, "energy": 0.4,
        "humanize": 0.7, "seed": 4,
        "progression": [2, 5, 1, 6], "chord_bars": 1,
        "arrangement": [["intro", 4], ["verse", 8], ["hook", 8], ["verse", 8],
                        ["hook", 8], ["outro", 4]],
        "drums": {
            "kick": _drum("x.......x.x.....", -6, "soft", decay=1.2),
            "snare": _drum("....x.......x...", -8, "tight", decay=1.3, reverb=0.2),
            "clap": _drum("................", -14, mute=True),
            "hat": _drum("x.x.x.x.x.x.x.x.", -14, decay=1.2, pan=0.2),
            "openhat": _drum("................", -18),
            "shaker": _drum("................", -18),
            "perc": _drum("...........x....", -16, "rim", pan=0.3, reverb=0.3),
        },
        "bass": {"sound": "sub", "pattern": "x.....x...x.....", "volume": -5.0,
                 "octave": 2, "decay": 1.0, "glide": 0.0, "mute": False, "sidechain": False},
        "chords": {"sound": "piano", "pattern": "x.......x.......", "voicing": "7th",
                   "octave": 4, "brightness": 0.45, "volume": -8.0, "stereo": 0.5,
                   "reverb": 0.35, "delay": 0.0, "mute": False, "sidechain": False},
        "melody": {"sound": "rhodes", "density": 0.3, "octave": 5, "volume": -13.0,
                   "brightness": 0.5, "reverb": 0.4, "delay": 0.3, "mute": False,
                   "sidechain": False, "seed": 2},
        "fx": {"risers": False, "impacts": False, "volume": -16.0, "mute": False},
        "texture": {"sound": "vinyl", "volume": -24.0, "mute": False},
        "mix": dict(BASE_MIX, sidechain=0.15, warmth=0.6, width=1.0, loudness=-15.0),
        "sections": _sections(["kick", "snare", "hat", "perc"]),
    },
}


def get_preset(genre):
    g = GENRES.get(genre, GENRES["amapiano"])
    p = copy.deepcopy(g)
    p["genre"] = genre if genre in GENRES else "amapiano"
    return p
