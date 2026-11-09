"""Command line: python make_beat.py amapiano --bpm 115 --key G --out my_beat"""
import argparse
import json

from beatengine import GENRES, render

ap = argparse.ArgumentParser(description="Make a produced beat from a few choices.")
ap.add_argument("genre", nargs="?", default="amapiano", choices=list(GENRES))
ap.add_argument("--bpm", type=float)
ap.add_argument("--key")
ap.add_argument("--scale")
ap.add_argument("--energy", type=float)
ap.add_argument("--seed", type=int, help="change for a new melody")
ap.add_argument("--settings", help="JSON file saved from the app (overrides the rest)")
ap.add_argument("--out", default="renders/cli")
a = ap.parse_args()

s = {"genre": a.genre}
for k in ("bpm", "key", "scale", "energy"):
    if getattr(a, k) is not None:
        s[k] = getattr(a, k)
if a.seed is not None:
    s["melody"] = {"seed": a.seed}
if a.settings:
    s = json.load(open(a.settings))
r = render(s, a.out, progress=print)
print(f"Done: {r['duration']}s, {r['lufs']} LUFS, peak {r['peak_db']} dB -> {a.out}")
