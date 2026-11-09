"""BeatMaker web app. Run:  python app.py   then open http://localhost:5000"""
import os
import json
import shutil
import tempfile
import threading
import time
import uuid

from flask import Flask, abort, jsonify, render_template, request, send_from_directory

from beatengine import GENRES, OPTIONS, render, sanitize
from beatengine import analyze as inspire
from beatengine import tags as tagger
from beatengine import theory
from beatengine.presets import DRUMS, SECTION_TYPES, TRACKS

BASE = os.path.dirname(os.path.abspath(__file__))
RENDERS = os.path.join(BASE, "renders", "web")
REFS = os.path.join(BASE, "renders", "refs")
TAGS = os.path.join(BASE, "renders", "tags")
KEEP = 20

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB uploads
lock = threading.Lock()


def _cleanup():
    if not os.path.isdir(RENDERS):
        return
    dirs = sorted((os.path.join(RENDERS, d) for d in os.listdir(RENDERS)), key=os.path.getmtime)
    for d in dirs[:-KEEP]:
        shutil.rmtree(d, ignore_errors=True)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/options")
def options():
    return jsonify({
        "genres": {k: v["label"] for k, v in GENRES.items()},
        "notes": theory.NOTE_NAMES,
        "scales": list(theory.SCALES),
        "progressions": theory.PROGRESSIONS,
        "voicings": theory.VOICINGS,
        "sounds": OPTIONS,
        "section_types": SECTION_TYPES,
        "tracks": TRACKS,
        "drums": DRUMS,
    })


@app.get("/api/preset/<genre>")
def preset(genre):
    return jsonify(sanitize({"genre": genre}))


@app.post("/api/sanitize")
def do_sanitize():
    return jsonify(sanitize(request.get_json(force=True, silent=True) or {}))


@app.post("/api/render")
def do_render():
    settings = request.get_json(force=True, silent=True) or {}
    job = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    out = os.path.join(RENDERS, job)
    tag_id = os.path.basename(str((settings.get("tag") or {}).get("id") or ""))
    tag_path = os.path.join(TAGS, tag_id, "tag.wav") if tag_id else None
    with lock:  # one render at a time keeps a small PC responsive
        result = render(settings, out, tag_path=tag_path)
    _cleanup()
    url = lambda p: f"/renders/{job}/{os.path.basename(p)}" if p else None
    return jsonify({
        "duration": result["duration"], "lufs": result["lufs"], "peak_db": result["peak_db"],
        "mp3": url(result["mp3"]), "wav": url(result["wav"]), "midi": url(result["midi"]),
        "stems": url(result["stems"]), "video": url(result.get("video")),
        "settings": result["settings"], "arrangement": result.get("arrangement"),
    })


# ---------------------------------------------------------------- producer tags
@app.get("/api/tags/voices")
def tag_voices():
    return jsonify({"voices": tagger.voices(), "styles": tagger.STYLES})


@app.get("/api/tags/suggest")
def tag_suggest():
    seed = request.args.get("seed", type=int)
    return jsonify(tagger.suggest(request.args.get("name", ""), request.args.get("genre", "amapiano"), 10, seed))


@app.post("/api/tags/make")
def tag_make():
    f = request.form
    tid = uuid.uuid4().hex[:10]
    out = os.path.join(TAGS, tid)
    upload = request.files.get("voice_file")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            voice_file = None
            if upload and upload.filename:
                voice_file = os.path.join(tmp, "voice" + (os.path.splitext(upload.filename)[1][:6] or ".webm"))
                upload.save(voice_file)
            yes = lambda k: f.get(k) in ("1", "true", "on")
            with lock:
                r = tagger.make_tag(out, style=f.get("style", "clean"), text=f.get("text"),
                                    engine=f.get("engine"), voice=f.get("voice"), voice_file=voice_file,
                                    pitch=float(f.get("pitch") or 0), swell=yes("swell"), impact=yes("impact"),
                                    riser=yes("riser"), bpm=float(f.get("bpm") or 120))
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(out, ignore_errors=True)
        return jsonify({"error": str(e)}), 400
    return jsonify({"id": tid, "duration": r["duration"],
                    "mp3": f"/tags/{tid}/tag.mp3" if r["mp3"] else None, "wav": f"/tags/{tid}/tag.wav"})


@app.get("/tags/<tid>/<name>")
def tag_file(tid, name):
    folder = os.path.join(TAGS, os.path.basename(tid))
    if not os.path.isdir(folder) or name not in ("tag.mp3", "tag.wav"):
        abort(404)
    return send_from_directory(folder, name, as_attachment=name.endswith(".wav"),
                               download_name="producer_tag.wav" if name.endswith(".wav") else None)


# ---------------------------------------------------------------- inspiration
def _save_ref(analysis):
    os.makedirs(REFS, exist_ok=True)
    rid = uuid.uuid4().hex[:10]
    with open(os.path.join(REFS, rid + ".json"), "w") as f:
        json.dump(analysis, f)
    return {"id": rid, "name": analysis["name"], "summary": inspire.summary(analysis),
            "analysis": {k: analysis[k] for k in ("bpm", "key", "scale", "genre", "swing", "energy",
                                                   "progression", "patterns", "duration")}}


def _load_ref(rid):
    path = os.path.join(REFS, os.path.basename(str(rid)) + ".json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _analyze_file(path, name):
    with lock:
        return _save_ref(inspire.analyze(path, name))


@app.post("/api/inspire/upload")
def inspire_upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "No file received."}), 400
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "upload" + os.path.splitext(f.filename)[1][:6])
        f.save(path)
        try:
            return jsonify(_analyze_file(path, os.path.splitext(os.path.basename(f.filename))[0]))
        except Exception as e:  # noqa: BLE001 - show the reason to the user
            return jsonify({"error": str(e)}), 400


@app.post("/api/inspire/link")
def inspire_link():
    url = (request.get_json(force=True, silent=True) or {}).get("url", "")
    with tempfile.TemporaryDirectory() as tmp:
        try:
            path, name = inspire.fetch_link(url, tmp)
            return jsonify(_analyze_file(path, name))
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": str(e)}), 400


@app.post("/api/inspire/apply")
def inspire_apply():
    body = request.get_json(force=True, silent=True) or {}
    refs = [(_load_ref(r.get("id")), r.get("weight", 1)) for r in body.get("refs", [])]
    refs = [(a, w) for a, w in refs if a]
    if not refs:
        return jsonify({"error": "Add at least one song first."}), 400
    base = sanitize(body.get("settings") or {})
    settings, notes = inspire.blend(refs, base, body.get("use"))
    return jsonify({"settings": sanitize(settings), "notes": notes})


@app.get("/renders/<job>/<name>")
def files(job, name):
    folder = os.path.join(RENDERS, os.path.basename(job))
    if not os.path.isdir(folder):
        abort(404)
    return send_from_directory(folder, os.path.basename(name), as_attachment=not name.endswith((".mp3", ".mp4")))


if __name__ == "__main__":
    # host 0.0.0.0 lets you open it from your phone on the same Wi-Fi
    app.run(host="0.0.0.0", port=5000, debug=False)
