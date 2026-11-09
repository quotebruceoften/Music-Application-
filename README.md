# BeatMaker

**Apps:** see [`mobile/README.md`](mobile/README.md) for the Android app (with iOS and PC builds ready).
The engine runs on the device, and GitHub Actions builds the APK for you.

Project layout:
- `beatengine/`: the producer engine (NumPy only, so it runs on phones)
- `server.py`: the engine's local API, used by the apps
- `mobile/`: Flutter app for Android, iOS, Windows, macOS and Linux
- `app.py` + `templates/`: the browser version (Flask) for PCs
- `make_beat.py`: command line
- `tool/`, `.github/workflows/`: build scripts


The user makes a few simple choices. Behind them, a producer engine programs the drums, picks
chords and voices them, writes a melody, arranges the song, mixes it and masters it.

## Run it
```
pip install flask numpy               # plus ffmpeg (reads uploaded songs, makes MP3 previews)
pip install yt-dlp                   # optional: links from TikTok, YouTube, Instagram, SoundCloud, Spotify…
pip install edge-tts                 # optional: natural neural voices for producer tags (needs internet)
python app.py
```
Open http://localhost:5000. To use it on your phone, open http://<your-PC-IP>:5000 while on the same Wi-Fi.

Command line: `python make_beat.py amapiano --bpm 115 --key G --seed 42 --out my_beat`

## Inspiration from real songs
Upload one or more songs, or paste links. For each one BeatMaker reads the tempo, key, drum groove
(kick, snare/clap, hats), chord progression, swing, energy and tone. It then blends them into your
beat using the influence sliders. You choose which traits to take: style, tempo, key, groove, chords,
swing & energy, tone. Only these musical traits are used; no audio or melody is copied.

- **Uploads:** anything ffmpeg can read (MP3, WAV, M4A, FLAC, OGG), up to 100 MB, first 3.5 minutes analysed
- **Direct links** to audio files work as they are
- **YouTube, SoundCloud and 1000+ other sites:** `pip install yt-dlp`. Respect each site's terms
  and only use songs you're allowed to download.
- **Spotify, Apple Music, Deezer, Tidal** lock their audio, so BeatMaker reads the song's name from
  the link and finds it through yt-dlp
- Analysis takes about 10 seconds per song

Tested on beats with known answers (4 styles, 7 songs): tempo 7/7, style 7/7, key 6/7,
chord progression 6/7, kick/snare grooves matched. Real mixes are messier, so treat results as a
strong starting point rather than a transcription.

## TikTok sounds
- **Format:** Full song, or a TikTok sound of 15, 30 or 60 seconds. Short formats are hook-first (the beat
  drops early, which is your video's transition moment), end on the bar line, and wrap the reverb tail
  back to the start so they loop seamlessly.
- **Phone-speaker bass:** adds harmonics so the bass is still heard on phone speakers. The loudness
  target switches to -10 LUFS automatically.
- **Vertical video:** a 1080×1920 MP4 with a moving waveform, your title and "prod. <name>", ready to upload.
- **Inspiration** also accepts video files (MP4, MOV) and TikTok, Reels or YouTube links (with yt-dlp).
  Clips as short as 6 seconds work.

## Producer tags
1. Type your producer name and tap **Give me ideas** for catchy phrases (general, genre-flavoured and
   name tricks like "Bruuuce!" or "B-R-U-C-E… Bruce!"), or write your own.
2. Pick a voice: neural voices via edge-tts (US, UK, South African, Nigerian, Australian), your computer's
   built-in voices (`pip install pyttsx3`), espeak, or **upload or record your own voice**. A real voice
   makes the most authentic tag.
3. Pick a style: Clean & punchy, Dark & deep, Echo out, Stutter & tape stop, Radio, Angelic. Optional extras:
   reverse swell, impact, riser, voice pitch.
4. The tag is processed like a studio vocal: EQ, compression, doubling, pitch layers, reverb and echo
   throws, then limiting. It's mixed into your beats (at the start, before each hook, or every 8 bars),
   and the beat ducks slightly underneath it.

Recording in the browser works when the app is opened as `localhost` on the same computer. On a phone,
record a voice note and upload it.

## What the user controls
- **Quick:** style (Amapiano, Trap, Afro House, Lo-fi), tempo, energy, swing, human feel, key, mood
- **Drums:** a 16-step grid for 7 drums, plus sound, volume, tune, length, pan, reverb, fills and hat rolls for each
- **Bass:** step grid (hit / soft / fifth / octave), log drum, 808, sub or pluck, glide, ducking under the kick
- **Chords:** ready-made or typed progressions, chord length, rhythm grid, sound, richness (triad / 7th / 9th), brightness, width
- **Melody:** sound, how busy it is, octave, echo, and a "melody idea #" (each number gives a new melody)
- **Song structure:** reorder, add or remove parts, and choose what plays in each kind of part
- **Mix & master:** reverb, room size, echo, pump, warmth, air, width, loudness target
- **Save/load:** settings as JSON files

## What the engine does in the background
- Swing, timing and velocity humanisation, and a slight strum on chords
- Chord voice leading (the smoothest inversion each time) and clash avoidance (drops flat 9ths)
- Melodies built in A-A'-A-B phrases: strong beats land on chord tones, and the last note resolves to the root
- Production moves: drums drop out before each hook, fills at the end of parts, risers, crashes and booms
- Mixing: gain staging, EQ, panning, sidechain pump, reverb and dotted-eighth ping-pong delay on send buses
- Master: glue compression, saturation, an air shelf, mono low end, and a lookahead limiter that hits the
  LUFS target (BS.1770) with a -1 dB ceiling
- Exports: mastered WAV and MP3, stems (32-bit float), MIDI, and the settings used

## Code map
- `beatengine/presets.py`: the genre starting points (add new genres here)
- `beatengine/synth.py`: drums, bass and synth keys, modelled from scratch (808-style drums, log drum,
  Rhodes, supersaw pad/lead, plucked string), with small hit-to-hit variations
- `beatengine/sampler.py` + `beatengine/samples/`: recorded piano, marimba, vibraphone, glockenspiel,
  kalimba, flute (recorder), tenor sax and hand percussion from the VCSL library (CC0, public domain).
  Rebuild them with `tool/build_samples.py`
- `beatengine/theory.py`: keys, scales, progressions, voicing
- `beatengine/engine.py`: arrangement, event building, mixing, export
- `beatengine/fx.py`: reverb, delay, compressor, limiter, loudness meter
- `beatengine/tags.py`: tag phrases, voices, phase-vocoder pitch shift, tag effect styles
- `beatengine/analyze.py`: song analysis (tempo, beat grid, drum/note separation, key, chords, swing) and blending

## Ideas for v2
- Let users load their own drum kits (`.wav`) alongside the built-in sounds
- Hum a melody into the mic and turn it into notes
- Live preview of a single loop while editing
- More genres (kwaito, gqom, drill, R&B)
