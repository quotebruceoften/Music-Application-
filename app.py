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
# The web app shares the phone engine's server code: background jobs with progress and
# stop, the beats library (names, stars, cleanup) and stems on demand. Same data folder.
os.environ.setdefault("BEATMAKER_DATA", os.path.join(BASE, "renders"))
import server as core  # noqa: E402

for _d in (core.RENDERS, core.REFS, core.TAGS, core.TMP):
    os.makedirs(_d, exist_ok=True)
OLD_RENDERS = os.path.join(BASE, "renders", "web")  # beats made by older versions
REFS = core.REFS
TAGS = core.TAGS

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB uploads
lock = threading.Lock()

FILE_KEYS = ("wav", "mp3", "m4a", "midi", "stems", "video")


def _web(d):
    """Engine results hold file paths; the page needs links."""
    if not isinstance(d, dict):
        return d
    out = dict(d)
    bid = out.get("id") or os.path.basename(str(out.get("folder") or ""))
    for k in FILE_KEYS:
        p = out.get(k)
        out[k] = f"/beats/{bid}/{os.path.basename(p)}" if p else None
    out.pop("folder", None)
    return out


FONTS = os.path.join(BASE, "mobile", "assets", "fonts")


@app.get("/fonts/<name>")
def font(name):  # the app's bundled Space Grotesk, so the page looks the same offline
    return send_from_directory(FONTS, os.path.basename(name), max_age=86400)


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
    """Start making a beat in the background; poll /api/job/<id> for progress."""
    settings = request.get_json(force=True, silent=True) or {}
    job = core.start_job(core.do_render, settings)  # stems are made on demand, like the phone app
    return jsonify({"id": job["id"]})


@app.get("/api/job/<jid>")
def job_status(jid):
    job = core.jobs.get(jid)
    if not job:
        return jsonify({"error": "Unknown job"}), 404
    j = {k: v for k, v in job.items() if k != "cancel"}
    j["result"] = _web(job.get("result"))
    return jsonify(j)


@app.post("/api/job/cancel")
def job_cancel():
    job = core.jobs.get(str((request.get_json(force=True, silent=True) or {}).get("id")))
    if job and job["status"] in ("queued", "running"):
        job["cancel"] = True
        job["message"] = "Stopping…"
    return jsonify({"ok": True})


@app.get("/api/beats/list")
def beats_list():
    return jsonify({"beats": [_web(b) for b in core.list_beats()]})


@app.post("/api/beats/update")
def beats_update():
    b = request.get_json(force=True, silent=True) or {}
    folder = core._beat_folder(b.get("id"))
    if not folder:
        return jsonify({"error": "That beat is gone."}), 404
    meta = core._beat_meta(folder)
    if "name" in b:
        meta["name"] = str(b.get("name") or "").strip()[:60]
    if "starred" in b:
        meta["starred"] = bool(b.get("starred"))
    meta.setdefault("created", os.path.getmtime(folder))
    core._write_beat_meta(folder, meta)
    return jsonify(_web(core._beat_info(folder)))


@app.post("/api/beats/delete")
def beats_delete():
    folder = core._beat_folder((request.get_json(force=True, silent=True) or {}).get("id"))
    if folder:
        shutil.rmtree(folder, ignore_errors=True)
    return jsonify({"ok": True})


@app.post("/api/beats/stems")
def beats_stems():
    job = core.start_job(core.do_stems, (request.get_json(force=True, silent=True) or {}).get("id"))
    return jsonify({"id": job["id"]})


@app.get("/api/beats/<bid>/settings")
def beat_settings(bid):
    folder = core._beat_folder(bid)
    if not folder:
        abort(404)
    with open(os.path.join(folder, "settings.json"), encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.get("/beats/<bid>/<name>")
def beat_file(bid, name):
    folder = core._beat_folder(bid)
    name = os.path.basename(name)
    if not folder or not os.path.exists(os.path.join(folder, name)):
        abort(404)
    return send_from_directory(folder, name, as_attachment=not name.endswith((".mp3", ".mp4", ".wav", ".m4a")))


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
def files(job, name):  # links to beats made by older versions
    folder = os.path.join(OLD_RENDERS, os.path.basename(job))
    if not os.path.isdir(folder):
        abort(404)
    return send_from_directory(folder, os.path.basename(name), as_attachment=not name.endswith((".mp3", ".mp4")))


if __name__ == "__main__":
    # host 0.0.0.0 lets you open it from your phone on the same Wi-Fi
    app.run(host="0.0.0.0", port=5000, debug=False)
