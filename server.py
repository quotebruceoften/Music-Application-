"""BeatMaker engine server: the API the app talks to (Android, iOS and PC).

Uses only the Python standard library + NumPy, so it runs inside the app's embedded
Python. It listens on 127.0.0.1 only. Long jobs (rendering, analysing, making tags)
run in a background thread; the app polls /api/job/<id> for progress.

Environment:
  BEATMAKER_PORT          port to listen on (default 8765)
  BEATMAKER_DATA          folder for renders, songs and tags (default ./renders)
  BEATMAKER_ALLOW_LINKS   "0" disables song links (e.g. for store builds)
  BEATMAKER_NO_FFMPEG     "1" on phones: the app does decoding/encoding natively
"""
import json
import os
import shutil
import tempfile
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from beatengine import GENRES, OPTIONS, render, sanitize, theory
from beatengine import analyze as inspire
from beatengine import media
from beatengine import tags as tagger
from beatengine.engine import preview_tag
from beatengine.presets import DRUMS, SECTION_TYPES, TRACKS

VERSION = "1.4.0"
DATA = os.path.abspath(os.environ.get("BEATMAKER_DATA", os.path.join(os.path.dirname(__file__), "renders")))
RENDERS, REFS, TAGS, TMP = (os.path.join(DATA, d) for d in ("beats", "refs", "tags", "tmp"))
KEEP_RENDERS = 20
KEEP_BYTES = 3 * 1024 ** 3  # 3 GB of old beats at most

work_lock = threading.Lock()  # one heavy job at a time keeps phones responsive
jobs = {}
jobs_lock = threading.Lock()


# ---------------------------------------------------------------- jobs
class Cancelled(Exception):
    """Raised inside a job when the app asked to stop it."""


# Rough share of the work done when each render stage starts (for the progress bar)
STAGE_PCT = {"Programming drums": 0.03, "Laying down the bass": 0.18, "Playing the chords": 0.26,
             "Writing a melody": 0.34, "Mixing": 0.42, "Mastering": 0.58, "Exporting": 0.85,
             "Making the video": 0.93}


def start_job(fn, *args):
    jid = uuid.uuid4().hex[:12]
    job = {"id": jid, "status": "queued", "message": "Waiting…", "result": None, "error": None,
           "started": time.time(), "pct": 0.0, "cancel": False}
    with jobs_lock:
        jobs[jid] = job
        for old in [k for k, v in jobs.items() if time.time() - v["started"] > 3600]:
            jobs.pop(old, None)

    def progress(msg):
        if job["cancel"]:
            raise Cancelled()
        job["message"] = msg
        if msg in STAGE_PCT:
            job["pct"] = STAGE_PCT[msg]

    def run():
        with work_lock:
            if job["cancel"]:
                job["status"], job["message"] = "cancelled", "Stopped"
                return
            job["status"] = "running"
            try:
                job["result"] = fn(progress, *args)
                job["status"] = "done"
                job["message"] = "Done"
                job["pct"] = 1.0
            except Cancelled:
                job["status"], job["message"] = "cancelled", "Stopped"
            except media.NeedsDecoding as e:
                job["status"], job["error"], job["code"] = "error", str(e), "needs_decoding"
            except Exception as e:  # noqa: BLE001 - report every failure to the app
                traceback.print_exc()
                job["status"], job["error"] = "error", str(e) or e.__class__.__name__

    threading.Thread(target=run, daemon=True).start()
    return job


def _folder_size(d):
    return sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(d) for f in fs)


def _cleanup_renders():
    """Keep the newest renders: at most KEEP_RENDERS, and at most KEEP_BYTES in total
    (long beats with stems are big). The newest render is always kept."""
    if not os.path.isdir(RENDERS):
        return
    dirs = sorted((os.path.join(RENDERS, d) for d in os.listdir(RENDERS)), key=os.path.getmtime, reverse=True)
    total = 0
    kept = 0
    for i, d in enumerate(dirs):
        if _beat_meta(d).get("starred"):
            continue  # starred beats are the user's keepers: never removed automatically
        total += _folder_size(d)
        kept += 1
        if i > 0 and (kept > KEEP_RENDERS or total > KEEP_BYTES):
            shutil.rmtree(d, ignore_errors=True)


def do_stems(progress, bid):
    """Make the stems for a beat in the library by rendering it again from its settings
    (the engine is deterministic, so the stems add up to the same beat)."""
    folder = _beat_folder(bid)
    if not folder:
        raise ValueError("That beat is gone.")
    zip_path = os.path.join(folder, "stems.zip")
    if os.path.exists(zip_path):
        return _beat_info(folder)
    with open(os.path.join(folder, "settings.json"), encoding="utf-8") as f:
        settings = json.load(f)
    tmp = tempfile.mkdtemp(dir=TMP)
    try:
        settings["export_video"] = False
        tp = _tag_path(settings)
        render(settings, tmp, progress=progress, tag_path=tp if tp and os.path.exists(tp) else None, stems=True)
        os.replace(os.path.join(tmp, "stems.zip"), zip_path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return _beat_info(folder)


# ---------------------------------------------------------------- my beats (library)
def _beat_meta(folder):
    try:
        with open(os.path.join(folder, "meta.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _write_beat_meta(folder, meta):
    tmp = os.path.join(folder, "meta.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    os.replace(tmp, os.path.join(folder, "meta.json"))


def _beat_folder(bid):
    bid = os.path.basename(str(bid or ""))
    folder = os.path.join(RENDERS, bid)
    return folder if bid and os.path.exists(os.path.join(folder, "beat.wav")) else None


def _beat_info(folder):
    meta = _beat_meta(folder)
    try:
        with open(os.path.join(folder, "settings.json"), encoding="utf-8") as f:
            settings = json.load(f)
    except (OSError, ValueError):
        settings = {}
    f = lambda n: os.path.join(folder, n) if os.path.exists(os.path.join(folder, n)) else None  # noqa: E731
    label = GENRES.get(settings.get("genre"), {}).get("label", "Beat")
    return {
        "id": os.path.basename(folder),
        "name": meta.get("name") or settings.get("title") or f"{label} in {settings.get('key', '')} {settings.get('scale', '')}".strip(),
        "starred": bool(meta.get("starred")),
        "created": meta.get("created") or os.path.getmtime(folder),
        "duration": meta.get("duration"), "lufs": meta.get("lufs"), "tags_placed": meta.get("tags_placed", 0),
        "genre": settings.get("genre"), "genre_label": label, "bpm": settings.get("bpm"),
        "key": settings.get("key"), "scale": settings.get("scale"), "format": settings.get("format", "full"),
        "folder": folder, "wav": f("beat.wav"), "mp3": f("beat.mp3"), "m4a": f("beat.m4a"),
        "midi": f("beat.mid"), "stems": f("stems.zip"), "video": f("beat.mp4"),
        "size": _folder_size(folder),
    }


def list_beats():
    out = []
    if os.path.isdir(RENDERS):
        for d in os.listdir(RENDERS):
            folder = os.path.join(RENDERS, d)
            if os.path.exists(os.path.join(folder, "beat.wav")):
                out.append(_beat_info(folder))
    return sorted(out, key=lambda b: b["created"], reverse=True)


# ---------------------------------------------------------------- work functions
def _tag_path(settings):
    tag_id = os.path.basename(str((settings.get("tag") or {}).get("id") or ""))
    return os.path.join(TAGS, tag_id, "tag.wav") if tag_id else None


def do_render(progress, settings, with_stems=False):
    """Make a beat. Stems are skipped by default (they're big and slow to write);
    do_stems() makes them later from the saved settings, giving identical audio."""
    out = os.path.join(RENDERS, time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4])
    tag_path = _tag_path(settings)
    try:
        r = render(settings, out, progress=progress, tag_path=tag_path, stems=with_stems)
    except BaseException:
        shutil.rmtree(out, ignore_errors=True)  # stopped or failed: don't leave half a beat behind
        raise
    title = str((r["settings"].get("title") or "")).strip()
    _write_beat_meta(out, {"name": title, "starred": False, "created": time.time(), "duration": r["duration"],
                           "lufs": r["lufs"], "tags_placed": r.get("tags_placed") or 0})
    _cleanup_renders()
    return {"id": os.path.basename(out), "folder": out, "wav": r["wav"], "mp3": r["mp3"], "midi": r["midi"], "stems": r["stems"],
            "video": r.get("video"), "duration": r["duration"], "lufs": r["lufs"], "peak_db": r["peak_db"],
            "settings": r["settings"], "arrangement": r.get("arrangement"),
            "tags_placed": r.get("tags_placed") or 0, "needs_video": bool(
                r["settings"].get("export_video") and not r.get("video"))}


def _save_ref(a):
    os.makedirs(REFS, exist_ok=True)
    rid = uuid.uuid4().hex[:10]
    with open(os.path.join(REFS, rid + ".json"), "w") as f:
        json.dump(a, f)
    return {"id": rid, "name": a["name"], "summary": inspire.summary(a),
            "analysis": {k: a[k] for k in ("bpm", "key", "scale", "genre", "swing", "energy",
                                           "progression", "patterns", "duration")}}


def _load_ref(rid):
    p = os.path.join(REFS, os.path.basename(str(rid)) + ".json")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


def do_analyze(progress, path, name):
    progress("Listening…")
    return _save_ref(inspire.analyze(path, name))


def do_fetch(progress, url):
    progress("Downloading…")
    folder = tempfile.mkdtemp(dir=TMP)
    path, name = inspire.fetch_link(url, folder)
    return {"path": path, "name": name}


KEEP_DRAFTS = 6  # unsaved tag previews kept (saved tags are never cleaned up)


def _tag_meta_path(tid):
    return os.path.join(TAGS, os.path.basename(str(tid)), "meta.json")


def _read_tag(tid):
    """A tag's info, or None if it's missing or its audio is gone."""
    tid = os.path.basename(str(tid or ""))
    folder = os.path.join(TAGS, tid)
    wav = os.path.join(folder, "tag.wav")
    if not tid or not os.path.exists(wav):
        return None
    meta = {}
    try:
        with open(_tag_meta_path(tid), encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        meta = {"saved": True, "name": "Tag", "created": os.path.getmtime(wav)}  # tags from older versions
    meta.update({"id": tid, "wav": wav})
    mp3 = os.path.join(folder, "tag.mp3")
    meta["mp3"] = mp3 if os.path.exists(mp3) else None
    return meta


def _write_tag(meta):
    keep = {k: v for k, v in meta.items() if k not in ("wav", "mp3")}
    tmp = _tag_meta_path(meta["id"]) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(keep, f, indent=1)
    os.replace(tmp, _tag_meta_path(meta["id"]))  # atomic, so a crash can't corrupt it


def list_tags(saved=True):
    out = []
    if os.path.isdir(TAGS):
        for tid in os.listdir(TAGS):
            m = _read_tag(tid)
            if m and bool(m.get("saved")) == saved:
                out.append(m)
    return sorted(out, key=lambda m: m.get("created", 0), reverse=True)


def _cleanup_drafts():
    for m in list_tags(saved=False)[KEEP_DRAFTS:]:
        shutil.rmtree(os.path.join(TAGS, m["id"]), ignore_errors=True)
    if os.path.isdir(TAGS):  # folders left behind by a failed run
        for tid in os.listdir(TAGS):
            d = os.path.join(TAGS, tid)
            if os.path.isdir(d) and not os.path.exists(os.path.join(d, "tag.wav")) \
                    and time.time() - os.path.getmtime(d) > 3600:
                shutil.rmtree(d, ignore_errors=True)


def do_tag(progress, p):
    progress("Processing your voice…")
    text = str(p.get("text") or "").strip()[:80]
    voice_file = p.get("voice_file") or None
    if voice_file and not os.path.exists(voice_file):
        raise ValueError("Your recording couldn't be found. Record or upload it again.")
    if not voice_file and not text:
        raise ValueError("Type your tag words first.")
    tid = uuid.uuid4().hex[:10]
    out = os.path.join(TAGS, tid)
    style = p.get("style", "clean")
    try:
        r = tagger.make_tag(out, style=style, text=text, engine=p.get("engine"),
                            voice=p.get("voice"), voice_file=voice_file,
                            pitch=float(p.get("pitch") or 0), swell=bool(p.get("swell")),
                            impact=bool(p.get("impact")), riser=bool(p.get("riser")),
                            bpm=float(p.get("bpm") or 120))
    except Exception:
        shutil.rmtree(out, ignore_errors=True)
        raise
    meta = {"id": tid, "saved": False, "name": text or "My voice", "text": text,
            "style": style if style in tagger.STYLES else "clean",
            "voice": "Your voice" if voice_file else str(p.get("voice_label") or p.get("voice") or ""),
            "pitch": float(p.get("pitch") or 0), "swell": bool(p.get("swell")),
            "impact": bool(p.get("impact")), "riser": bool(p.get("riser")),
            "duration": r["duration"], "created": time.time()}
    _write_tag(meta)
    _cleanup_drafts()
    return _read_tag(tid)


def do_tag_preview(progress, p):
    progress("Laying the tag over your beat…")
    folder = os.path.abspath(str(p.get("folder") or ""))
    if not folder.startswith(os.path.abspath(RENDERS) + os.sep) or not os.path.exists(os.path.join(folder, "beat.wav")):
        raise ValueError("That beat is gone. Make a beat first, then preview the tag on it.")
    tag = _read_tag(p.get("id"))
    if not tag:
        raise ValueError("That tag can't be found. Make or pick another one.")
    places = p.get("places")
    if not isinstance(places, list) or not places:
        raise ValueError("Pick at least one place for the tag.")
    r = preview_tag(folder, tag["wav"], places, float(p.get("volume", -1)), float(p.get("duck", 0.5)))
    if not r["count"]:
        raise ValueError("None of those spots fit in this beat. Pick another place for the tag.")
    return r


# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "BeatMaker/" + VERSION

    def log_message(self, fmt, *args):  # keep the app's log quiet
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        parts = [p for p in u.path.split("/") if p]
        try:
            if u.path == "/api/ping":
                return self._send(200, {"ok": True, "version": VERSION, "ffmpeg": media.has_ffmpeg(),
                                        "links": os.environ.get("BEATMAKER_ALLOW_LINKS", "1") == "1",
                                        "data": DATA})
            if u.path == "/api/options":
                return self._send(200, {
                    "genres": {k: v["label"] for k, v in GENRES.items()}, "notes": theory.NOTE_NAMES,
                    "scales": list(theory.SCALES), "progressions": theory.PROGRESSIONS,
                    "voicings": theory.VOICINGS, "sounds": OPTIONS, "section_types": SECTION_TYPES,
                    "tracks": TRACKS, "drums": DRUMS, "tag_styles": tagger.STYLES})
            if len(parts) == 3 and parts[:2] == ["api", "preset"]:
                return self._send(200, sanitize({"genre": parts[2]}))
            if len(parts) == 3 and parts[:2] == ["api", "job"]:
                job = jobs.get(parts[2])
                if not job:
                    return self._send(404, {"error": "Unknown job"})
                return self._send(200, job)
            if u.path == "/api/beats/list":
                return self._send(200, {"beats": list_beats()})
            if u.path == "/api/tags/list":
                return self._send(200, {"tags": list_tags(saved=True)})
            if u.path == "/api/tags/voices":
                return self._send(200, {"voices": tagger.voices()})
            if u.path == "/api/tags/suggest":
                seed = int(q["seed"]) if q.get("seed", "").isdigit() else None
                return self._send(200, tagger.suggest(q.get("name", ""), q.get("genre", "amapiano"), 10, seed))
            return self._send(404, {"error": "Not found"})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._send(500, {"error": str(e)})

    def do_POST(self):
        b = self._body()
        try:
            if self.path == "/api/sanitize":
                return self._send(200, sanitize(b))
            if self.path == "/api/render":
                return self._send(200, start_job(do_render, b.get("settings") or b, bool(b.get("with_stems"))))
            if self.path == "/api/beats/stems":
                return self._send(200, start_job(do_stems, b.get("id")))
            if self.path == "/api/inspire/analyze":
                path = b.get("path", "")
                if not os.path.exists(path):
                    return self._send(400, {"error": "File not found"})
                return self._send(200, start_job(do_analyze, path, b.get("name") or "song"))
            if self.path == "/api/inspire/fetch":
                return self._send(200, start_job(do_fetch, b.get("url", "")))
            if self.path == "/api/inspire/apply":
                refs = [(_load_ref(r.get("id")), r.get("weight", 1)) for r in b.get("refs", [])]
                refs = [(a, w) for a, w in refs if a]
                if not refs:
                    return self._send(400, {"error": "Add at least one song first."})
                s, notes = inspire.blend(refs, sanitize(b.get("settings") or {}), b.get("use"))
                return self._send(200, {"settings": sanitize(s), "notes": notes})
            if self.path == "/api/tags/make":
                return self._send(200, start_job(do_tag, b))
            if self.path == "/api/job/cancel":
                job = jobs.get(str(b.get("id")))
                if job and job["status"] in ("queued", "running"):
                    job["cancel"] = True
                    job["message"] = "Stopping…"
                return self._send(200, {"ok": True})
            if self.path == "/api/beats/update":
                folder = _beat_folder(b.get("id"))
                if not folder:
                    return self._send(404, {"error": "That beat is gone."})
                meta = _beat_meta(folder)
                if "name" in b:
                    meta["name"] = str(b.get("name") or "").strip()[:60]
                if "starred" in b:
                    meta["starred"] = bool(b.get("starred"))
                meta.setdefault("created", os.path.getmtime(folder))
                _write_beat_meta(folder, meta)
                return self._send(200, _beat_info(folder))
            if self.path == "/api/beats/delete":
                folder = _beat_folder(b.get("id"))
                if folder:
                    shutil.rmtree(folder, ignore_errors=True)
                return self._send(200, {"ok": True})
            if self.path == "/api/tags/preview":
                return self._send(200, start_job(do_tag_preview, b))
            if self.path in ("/api/tags/save", "/api/tags/rename"):
                m = _read_tag(b.get("id"))
                if not m:
                    return self._send(404, {"error": "That tag can't be found."})
                name = str(b.get("name") or "").strip()[:40]
                m["name"] = name or m.get("name") or "My tag"
                m["saved"] = True
                _write_tag(m)
                return self._send(200, _read_tag(m["id"]))
            if self.path == "/api/tags/delete":
                tid = os.path.basename(str(b.get("id") or ""))
                if tid and os.path.isdir(os.path.join(TAGS, tid)):
                    shutil.rmtree(os.path.join(TAGS, tid), ignore_errors=True)
                return self._send(200, {"ok": True})
            return self._send(404, {"error": "Not found"})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._send(500, {"error": str(e)})


def serve(port=None, block=True):
    for d in (RENDERS, REFS, TAGS, TMP):
        os.makedirs(d, exist_ok=True)
    port = int(port or os.environ.get("BEATMAKER_PORT", 8765))
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    print(f"BeatMaker engine {VERSION} on http://127.0.0.1:{port} (data: {DATA})", flush=True)
    if block:
        httpd.serve_forever()
    else:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


if __name__ == "__main__":
    serve()
