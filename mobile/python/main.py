"""Entry point run by the app's embedded Python (serious_python).

The build copies `beatengine/` and `server.py` next to this file.
The app passes BEATMAKER_DATA (its private storage folder) and BEATMAKER_PORT.
If startup fails, the error is written to BEATMAKER_DATA/engine.log so the app can show it.
"""
import os
import sys
import traceback

# serious_python 6 runs this file without __file__; it puts the app folder first on sys.path
_me = globals().get("__file__")
HERE = os.path.dirname(os.path.abspath(_me)) if _me else (sys.path[0] or os.getcwd())
DATA = os.environ.get("BEATMAKER_DATA") or os.path.join(HERE, "renders")
LOG = os.path.join(DATA, "engine.log")


def log(msg):
    try:
        os.makedirs(DATA, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(msg.rstrip() + "\n")
    except Exception:  # noqa: BLE001
        pass


try:
    os.remove(LOG)  # keep only this launch's messages
except OSError:
    pass

try:
    sys.path.insert(0, HERE)
    os.environ.setdefault("BEATMAKER_NO_FFMPEG", "1")      # the phone decodes/encodes natively
    os.environ.setdefault("BEATMAKER_MAX_ANALYSIS_S", "90")  # keep song analysis quick on phones

    import server  # noqa: E402

    server.serve()
except BaseException as e:  # noqa: BLE001
    if not isinstance(e, (KeyboardInterrupt, SystemExit)):
        log(f"Python {sys.version.split()[0]}\n" + traceback.format_exc())
    raise
