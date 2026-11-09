"""Entry point run by the app's embedded Python (serious_python).

The build copies `beatengine/` and `server.py` next to this file.
The app passes BEATMAKER_DATA (its private storage folder) and BEATMAKER_PORT.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("BEATMAKER_NO_FFMPEG", "1")      # the phone decodes/encodes natively
os.environ.setdefault("BEATMAKER_MAX_ANALYSIS_S", "90")  # keep song analysis quick on phones

import server  # noqa: E402

server.serve()
