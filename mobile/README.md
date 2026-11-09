# BeatMaker app (Android first, iOS and PC ready)

One Flutter app for Android, iOS, Windows, macOS and Linux. The beat engine (Python + NumPy) runs
**on the device** inside the app through [serious_python](https://pub.dev/packages/serious_python).
No server and no internet are needed, except for optional song links.

```
┌──────────────────────── the app ────────────────────────┐
│ Flutter UI (lib/)                                        │
│   Create · My beats · Inspire · Tag · Studio             │
│        │ http://127.0.0.1:8765 (inside the app only)     │
│        ▼                                                 │
│ Embedded Python: server.py + beatengine/ (NumPy only)    │
│        ▲                                                 │
│ Native media (android/…/MediaTools.kt, ios/AppDelegate)  │
│   decode any audio/video → WAV, AAC export, TikTok video,│
│   save to Music/Movies, phone voices for tags            │
└──────────────────────────────────────────────────────────┘
```

## What's in the app
- **Create:** pick a style, name the beat, choose a length (standard or 3–10 min), make it. A progress bar
  shows each stage, and you can stop a long render. Big changes (style, Surprise me, inspiration) can be undone.
- **My beats:** every beat you've made: play, rename, star (starred beats are never cleaned up), share,
  save, stems, MIDI, delete, or open it again in Create to tweak it. Stems are made when you ask for them
  (they're big), from the same settings, so they match the beat exactly.
- **Inspire:** borrow tempo, key, groove and chords from songs you love.
- **Tag:** make a producer tag, preview it, save it to your library, and choose if and where it goes.
- **Studio:** every detail: drum grids, bass, chords, melody, song structure, mix.

## Get the Android app (no Android Studio needed)
1. Create a GitHub repository and push this whole project (the folder that contains `beatengine/`,
   `server.py`, `mobile/` and `.github/`).
2. Open the repository on GitHub, then **Actions → Build BeatMaker apps**. Every push to `main` builds
   automatically, or press **Run workflow**.
3. When it's green (about 10–15 minutes), open the run and download **BeatMaker-Android**.
4. Unzip it and copy `app-arm64-v8a-release.apk` to your phone. That build fits almost every phone
   from the last 6+ years. Very old phones need `armeabi-v7a`.
5. Open the APK on the phone and allow "Install unknown apps" when asked.

The first launch takes a little longer while the engine unpacks.

## Build on your PC instead
Requirements: Flutter (stable), Android Studio (for the Android SDK), Python 3.10+, and `pip install pillow`.
```bash
export SERIOUS_PYTHON_SITE_PACKAGES="$PWD/mobile/build/site-packages"   # Python packages for the app
export SERIOUS_PYTHON_APP="$PWD/mobile/build/python-app"                # the engine, staged for the build
export SERIOUS_PYTHON_VERSION=3.12                                      # Python the app embeds
flutter create --project-name beatmaker --org app.beatmaker --platforms=android,ios,macos,windows,linux /tmp/template
python tool/merge_template.py /tmp/template mobile
cd mobile && python ../tool/patch_platforms.py && cd ..
python tool/apply_icons.py
cd mobile && flutter pub get && cd ..
bash tool/prepare_python.sh Android          # or iOS / Windows / macOS / Linux
cd mobile && flutter build apk --release --split-per-abi
```
Run these from the project root, in one terminal (the two `export` lines must stay set for the build).
On Windows, use Git Bash.

**Faster UI development:** start the engine yourself with `python server.py`, then `cd mobile && flutter run`.
The app notices the running engine and uses it.

## Other platforms
| Platform | Status | How |
|---|---|---|
| Android | ✅ main target | GitHub Actions (above) |
| iOS | 🟡 builds unsigned; video export not yet native | Actions → Run workflow → tick **iOS**. Installing on an iPhone needs an Apple Developer account (signing in Xcode) or a sideloading tool |
| Windows / macOS / Linux | 🟡 builds | Run workflow → tick the platform. For MP3 and video export on PC, install ffmpeg |

## Store releases
- **Google Play:** build with `--dart-define=ALLOW_LINKS=false` (the workflow has a switch for this).
  Downloading from YouTube or TikTok breaks Play policy, but uploads still work. You also need your own
  signing key and an app bundle (`flutter build appbundle`).
- **App Store:** the same applies to links. Apple also reviews apps with embedded Python case by case.

## Where things live
- `lib/`: Flutter UI and engine bridge (`engine.dart`), native bridge (`media.dart`), state (`state.dart`)
- `android/app/src/main/kotlin/app/beatmaker/beatmaker/`: Android native media and voices
- `ios/Runner/AppDelegate.swift`: iOS native media and voices
- `python/main.py`: what the embedded Python runs (the build copies `beatengine/` and `server.py` in)
- `assets/icon.png`: the app icon (resized for every platform by `tool/apply_icons.py`)

## If the first build fails
This code was written without an Android SDK available, so the first GitHub build is its first real
compile. If a step goes red, open it, copy the last ~30 lines of the log, and send them to me to fix.
