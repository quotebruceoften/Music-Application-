import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'engine.dart';
import 'media.dart';

/// One reference song used for inspiration.
class Ref {
  String? id;
  String name;
  String summary;
  double weight;
  String? error;
  List<dynamic>? progression;
  Ref({this.id, required this.name, this.summary = '', this.weight = 1, this.error, this.progression});
  bool get busy => id == null && error == null;
  J toJson() => {'id': id, 'name': name, 'summary': summary, 'weight': weight, 'progression': progression};
  static Ref fromJson(J j) => Ref(
      id: j['id'] as String?,
      name: '${j['name'] ?? 'song'}',
      summary: '${j['summary'] ?? ''}',
      weight: (j['weight'] as num?)?.toDouble() ?? 1,
      progression: j['progression'] as List<dynamic>?);
}

/// A voice for producer tags: the phone's own TTS, an engine voice (PC), or none.
class Voice {
  final String source; // 'native' | 'edge' | 'pyttsx3' | 'espeak'
  final String id;
  final String label;
  const Voice(this.source, this.id, this.label);
  String get key => '$source|$id';
}

class AppState extends ChangeNotifier {
  final Engine engine = Engine();
  SharedPreferences? _prefs;

  bool ready = false;
  String startupStatus = 'Starting…';
  String? startupError;

  J options = {};
  J s = {}; // the beat settings (same shape as the engine's)

  // render
  bool busy = false;
  String status = '';
  J? result;
  String? videoPath;

  // inspiration
  List<Ref> refs = [];
  J use = {for (final k in useLabels.keys) k: true};
  List<String> inspireNotes = [];

  // tags
  J tag = {'text': '', 'voice': '', 'style': 'clean', 'pitch': 0.0, 'swell': true, 'impact': false, 'riser': false};
  J? lastTag;
  String? ownVoicePath;
  List<Voice> voices = [];
  List<J> ideas = [];
  bool tagBusy = false;
  String tagStatus = '';

  static const useLabels = {
    'style': 'Style', 'tempo': 'Tempo', 'key': 'Key', 'groove': 'Drum groove',
    'chords': 'Chords', 'feel': 'Swing & energy', 'tone': 'Tone',
  };

  // ---------------------------------------------------------------- startup
  Future<void> init() async {
    try {
      _prefs = await SharedPreferences.getInstance();
      await engine.start(onStatus: (m) {
        startupStatus = m;
        notifyListeners();
      });
      options = (await engine.get('/api/options') as Map).cast<String, dynamic>();
      final saved = _prefs!.getString('settings');
      if (saved != null) {
        s = (await engine.post('/api/sanitize', jsonDecode(saved)) as Map).cast<String, dynamic>();
      } else {
        s = (await engine.get('/api/preset/amapiano') as Map).cast<String, dynamic>();
      }
      final savedRefs = _prefs!.getString('refs');
      if (savedRefs != null) {
        final j = jsonDecode(savedRefs) as Map<String, dynamic>;
        refs = (j['refs'] as List).map((e) => Ref.fromJson((e as Map).cast<String, dynamic>())).toList();
        use.addAll((j['use'] as Map).cast<String, dynamic>());
      }
      final savedTag = _prefs!.getString('tag');
      if (savedTag != null) {
        final j = jsonDecode(savedTag) as Map<String, dynamic>;
        tag.addAll((j['tag'] as Map).cast<String, dynamic>());
        lastTag = (j['last'] as Map?)?.cast<String, dynamic>();
        if (lastTag != null && !File('${lastTag!['wav']}').existsSync()) lastTag = null;
      }
      await loadVoices();
      ready = true;
    } catch (e) {
      startupError = '$e';
    }
    notifyListeners();
  }

  Future<void> loadVoices() async {
    final list = <Voice>[];
    for (final v in await Media.ttsVoices()) {
      list.add(Voice('native', v['id'] ?? '', v['label'] ?? v['id'] ?? 'Voice'));
    }
    try {
      final j = await engine.get('/api/tags/voices') as Map;
      for (final v in (j['voices'] as List)) {
        final m = v as Map;
        list.add(Voice('${m['engine']}', '${m['id']}', '${m['label']}'));
      }
    } catch (_) {}
    voices = list;
    if (voices.isNotEmpty && !voices.any((v) => v.key == tag['voice'])) tag['voice'] = voices.first.key;
  }

  // ---------------------------------------------------------------- persistence
  void changed() {
    _prefs?.setString('settings', jsonEncode(s));
    notifyListeners();
  }

  void _saveRefs() {
    _prefs?.setString('refs', jsonEncode({'refs': refs.where((r) => r.id != null).map((r) => r.toJson()).toList(), 'use': use}));
  }

  void refsChanged() {
    _saveRefs();
    notifyListeners();
  }

  void tagChanged() {
    _prefs?.setString('tag', jsonEncode({'tag': tag, 'last': lastTag}));
    notifyListeners();
  }

  J sub(String k) => (s[k] as Map).cast<String, dynamic>();

  // ---------------------------------------------------------------- settings actions
  Future<void> loadGenre(String g) async {
    final keepTag = s['tag'];
    final producer = s['producer'];
    final format = s['format'];
    s = (await engine.get('/api/preset/$g') as Map).cast<String, dynamic>();
    if (keepTag != null) s['tag'] = keepTag;
    s['producer'] = producer ?? '';
    if (format != null) setFormat('$format', notify: false);
    changed();
  }

  void setFormat(String f, {bool notify = true}) {
    s['format'] = f;
    final tt = f != 'full';
    final mix = sub('mix');
    mix['loudness'] = tt ? -10.0 : -14.0;
    mix['phone_bass'] = tt ? 0.6 : 0.0;
    if (tt) mix['width'] = min((mix['width'] as num).toDouble(), 1.0);
    s['export_video'] = tt;
    if (notify) changed();
  }

  void newMelody() {
    sub('melody')['seed'] = Random().nextInt(100000);
    changed();
  }

  void surprise() {
    final r = Random();
    T pick<T>(List<T> l) => l[r.nextInt(l.length)];
    s['key'] = pick((options['notes'] as List).cast<String>());
    s['progression'] = pick((options['progressions'] as Map).values.toList());
    sub('melody')['seed'] = r.nextInt(100000);
    s['bpm'] = ((s['bpm'] as num) + r.nextInt(11) - 5).toDouble();
    s['energy'] = ((s['energy'] as num) + r.nextDouble() * 0.3 - 0.15).clamp(0.2, 1.0);
    sub('chords')['sound'] = pick(((options['sounds'] as Map)['chord_sounds'] as List).cast<String>());
    sub('melody')['sound'] = pick(((options['sounds'] as Map)['melody_sounds'] as List).cast<String>());
    changed();
  }

  Future<void> importSettings(String path) async {
    final j = jsonDecode(await File(path).readAsString());
    s = (await engine.post('/api/sanitize', j) as Map).cast<String, dynamic>();
    changed();
  }

  Future<String> exportSettings() async {
    final p = engine.tmpPath('json').replaceAll(RegExp(r'\d+\.json$'), 'beat-${s['genre']}-${s['key']}.json');
    await File(p).writeAsString(const JsonEncoder.withIndent('  ').convert(s));
    return p;
  }

  // ---------------------------------------------------------------- make the beat
  Future<void> make() async {
    if (busy) return;
    busy = true;
    status = 'Starting…';
    videoPath = null;
    notifyListeners();
    try {
      final r = await engine.runJob('/api/render', {'settings': s}, onProgress: (m) {
        status = m;
        notifyListeners();
      });
      result = r;
      s = (r['settings'] as Map).cast<String, dynamic>();
      _prefs?.setString('settings', jsonEncode(s));
      videoPath = r['video'] as String?;
      if (r['needs_video'] == true) {
        status = 'Making the video…';
        notifyListeners();
        try {
          videoPath = await Media.makeVideo('${r['wav']}', '${r['folder']}${Platform.pathSeparator}beat.mp4',
              videoTitle(), videoSubtitle());
        } catch (_) {
          videoPath = null; // shown as a note; the audio is still ready
        }
      }
      status = 'Done! Change anything and make it again.';
    } catch (e) {
      status = 'Something went wrong: $e';
    }
    busy = false;
    notifyListeners();
  }

  String videoTitle() {
    final t = '${s['title'] ?? ''}'.trim();
    if (t.isNotEmpty) return t;
    final label = ((options['genres'] as Map?) ?? {})[s['genre']] ?? 'New';
    return '$label beat';
  }

  String videoSubtitle() {
    final p = '${s['producer'] ?? ''}'.trim();
    return '${(s['bpm'] as num).round()} BPM · ${s['key']} ${s['scale']}${p.isNotEmpty ? ' · prod. $p' : ''}';
  }

  /// A small file for sharing: MP3 (PC with ffmpeg) or AAC/M4A (phones), else the WAV.
  Future<String> shareableAudio() async {
    final r = result!;
    if (r['mp3'] != null) return '${r['mp3']}';
    final m4a = '${r['folder']}${Platform.pathSeparator}beat.m4a';
    if (File(m4a).existsSync()) return m4a;
    return await Media.encodeAac('${r['wav']}', m4a) ?? '${r['wav']}';
  }

  // ---------------------------------------------------------------- inspiration
  /// Analyse a file; if the engine can't read it, convert it to WAV natively first.
  Future<J> _analyze(String path, String name) async {
    try {
      return await engine.runJob('/api/inspire/analyze', {'path': path, 'name': name});
    } on EngineException catch (e) {
      if (e.code != 'needs_decoding') rethrow;
      final wav = await Media.decodeToWav(path, engine.tmpPath('wav'));
      if (wav == null) throw EngineException("This device can't read that file. Try an MP3, M4A or MP4.");
      return await engine.runJob('/api/inspire/analyze', {'path': wav, 'name': name});
    }
  }

  void _fillRef(Ref ref, J j) {
    ref.id = j['id'] as String?;
    ref.name = '${j['name'] ?? ref.name}';
    ref.summary = '${j['summary'] ?? ''}';
    ref.progression = (j['analysis'] as Map?)?['progression'] as List<dynamic>?;
  }

  Future<void> addSongFile(String path, String name) async {
    final ref = Ref(name: name.replaceAll(RegExp(r'\.[A-Za-z0-9]+$'), ''));
    refs.add(ref);
    notifyListeners();
    try {
      _fillRef(ref, await _analyze(path, ref.name));
    } catch (e) {
      ref.error = '$e';
    }
    refsChanged();
  }

  Future<void> addSongLink(String url) async {
    final ref = Ref(name: url.replaceFirst(RegExp(r'^https?://(www\.)?'), ''));
    refs.add(ref);
    notifyListeners();
    try {
      final f = await engine.runJob('/api/inspire/fetch', {'url': url});
      ref.name = '${f['name']}';
      notifyListeners();
      _fillRef(ref, await _analyze('${f['path']}', ref.name));
    } catch (e) {
      ref.error = '$e';
    }
    refsChanged();
  }

  void removeRef(Ref r) {
    refs.remove(r);
    refsChanged();
  }

  Future<bool> applyInspiration() async {
    final ready = refs.where((r) => r.id != null).map((r) => {'id': r.id, 'weight': r.weight}).toList();
    if (ready.isEmpty) return false;
    try {
      final j = await engine.post('/api/inspire/apply', {'refs': ready, 'use': use, 'settings': s}) as Map;
      s = (j['settings'] as Map).cast<String, dynamic>();
      inspireNotes = (j['notes'] as List).map((e) => '$e').toList();
      changed();
      return true;
    } catch (e) {
      inspireNotes = ['$e'];
      notifyListeners();
      return false;
    }
  }

  // ---------------------------------------------------------------- producer tags
  Future<void> suggestIdeas() async {
    final name = Uri.encodeComponent('${s['producer'] ?? ''}'.trim().isEmpty ? 'Producer' : '${s['producer']}');
    final list = await engine.get('/api/tags/suggest?name=$name&genre=${s['genre']}&seed=${Random().nextInt(999999)}');
    ideas = (list as List).map((e) => (e as Map).cast<String, dynamic>()).toList();
    notifyListeners();
  }

  Future<void> makeTag() async {
    if (tagBusy) return;
    final text = '${tag['text']}'.trim();
    if (ownVoicePath == null && text.isEmpty) {
      tagStatus = 'Type your tag words (or tap an idea) first.';
      notifyListeners();
      return;
    }
    tagBusy = true;
    tagStatus = 'Recording the voice…';
    notifyListeners();
    try {
      final body = <String, dynamic>{
        'style': tag['style'], 'pitch': tag['pitch'], 'swell': tag['swell'], 'impact': tag['impact'],
        'riser': tag['riser'], 'bpm': s['bpm'], 'text': text,
      };
      String? voiceFile = ownVoicePath;
      if (voiceFile == null) {
        final v = voices.firstWhere((v) => v.key == tag['voice'],
            orElse: () => throw EngineException('No voice available. Record or upload your own voice.'));
        if (v.source == 'native') {
          voiceFile = await Media.ttsToFile(text, v.id, engine.tmpPath('wav'));
          if (voiceFile == null) throw EngineException("The phone's voice didn't respond. Try another voice.");
        } else {
          body['engine'] = v.source;
          body['voice'] = v.id;
        }
      }
      J r;
      try {
        r = await engine.runJob('/api/tags/make', {...body, 'voice_file': voiceFile}, onProgress: (m) {
          tagStatus = m;
          notifyListeners();
        });
      } on EngineException catch (e) {
        if (e.code != 'needs_decoding' || voiceFile == null) rethrow;
        final wav = await Media.decodeToWav(voiceFile, engine.tmpPath('wav'));
        if (wav == null) rethrow;
        r = await engine.runJob('/api/tags/make', {...body, 'voice_file': wav});
      }
      lastTag = r;
      sub('tag')['id'] = r['id'];
      changed();
      tagStatus = "Done: a ${r['duration']}s tag. It's on your beats now. Make a beat to hear it in place.";
      tagChanged();
    } catch (e) {
      tagStatus = "Couldn't make the tag: $e";
    }
    tagBusy = false;
    notifyListeners();
  }
}
