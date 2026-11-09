"""Tiny standard MIDI file writer (no dependencies)."""
import struct

TPB = 480
GM_DRUMS = {"kick": 36, "snare": 38, "clap": 39, "hat": 42, "openhat": 46,
            "shaker": 70, "perc": 37}


def _vlq(n):
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(out))


def _track(events, name):
    """events: list of (tick, bytes)."""
    data = b"\x00\xff\x03" + _vlq(len(name)) + name.encode()
    last = 0
    for tick, msg in sorted(events, key=lambda e: (e[0], e[1][0] & 0xF0 != 0x80)):
        data += _vlq(tick - last) + msg
        last = tick
    data += b"\x00\xff\x2f\x00"
    return b"MTrk" + struct.pack(">I", len(data)) + data


def write_midi(path, bpm, tracks):
    """tracks: {name: (channel, [(start_sec, dur_sec, note, vel01), ...])}"""
    spb = 60.0 / bpm
    tempo = int(spb * 1_000_000)
    meta = [(0, b"\xff\x51\x03" + tempo.to_bytes(3, "big"))]
    chunks = [_track(meta, "tempo")]
    for name, (ch, notes) in tracks.items():
        if not notes:
            continue
        ev = []
        for start, dur, note, vel in notes:
            t0 = int(round(start / spb * TPB))
            t1 = max(t0 + 1, int(round((start + dur) / spb * TPB)))
            v = max(1, min(127, int(vel * 110)))
            ev.append((t0, bytes([0x90 | ch, note, v])))
            ev.append((t1, bytes([0x80 | ch, note, 0])))
        chunks.append(_track(ev, name))
    header = b"MThd" + struct.pack(">IHHH", 6, 1, len(chunks), TPB)
    with open(path, "wb") as f:
        f.write(header + b"".join(chunks))
