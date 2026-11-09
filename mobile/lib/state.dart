import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
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
  double renderPct = 0; // 0..1 while a beat is being made
  DateTime? renderStarted;
  String? _renderJob;
  Timer? _ticker;
  bool cancelling = false;

  // app-wide helpers for the UI
  final messenger = GlobalKey<ScaffoldMessengerState>();
  final resultKey = GlobalKey(); // the "Your beat" card, to scroll to it when ready
  int tab = 0; // the bottom-bar tab, so other screens can switch it
  bool showTips = false;

  // my beats (library)
  List<J> beats = [];
  bool beatsLoading = false;

  int settingsGen = 0; // bumps when settings are replaced wholesale, so text boxes refresh
  // undo for big changes to the settings
  final List<(String, String)> _undo = []; // (what changed, settings before)

  // inspiration
  List<Ref> refs = [];
  J use = {for (final k in useLabels.keys) k: true};
  List<String> inspireNotes = [];

  // tags
  J tag = {'text': '', 'voice': '', 'style': 'clean', 'pitch': 0.0, 'swell': true, 'impact': false, 'riser': false};
  J? draftTag; // the latest preview, not saved yet
  List<J> savedTags = []; // the tag library
  String? ownVoicePath;
  List<Voice> voices = [];
  List<J> ideas = [];
  bool tagBusy = false;
  String tagStatus = '';
  // hearing a tag on the current beat
  bool tagPreviewBusy = false;
  String tagPreviewStatus = '';
  String? tagPreviewWav;

  static const tagPlaces = {
    'start': 'At the start',
    'hooks': 'Right before each drop',
    'verses': 'Start of each verse',
    'every8': 'Every 8 bars',
    'end': 'In the outro',
  };

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
        try {
          final j = jsonDecode(savedTag) as Map<String, dynamic>;
          tag.addAll((j['tag'] as Map).cast<String, dynamic>());
          draftTag = (j['draft'] as Map?)?.cast<String, dynamic>();
          if (draftTag != null && !File('${draftTag!['wav']}').existsSync()) draftTag = null;
          final own = j['own'] as String?;
          if (own != null && File(own).existsSync()) ownVoicePath = own;
        } catch (_) {} // an old or damaged save: start the tag tab fresh
      }
      final savedResult = _prefs!.getString('result');
      if (savedResult != null) {
        try {
          final r = (jsonDecode(savedResult) as Map).cast<String, dynamic>();
          if (File('${r['wav']}').existsSync()) result = r;
        } catch (_) {}
      }
      if (s['format'] == 'full') presetLoudness = (sub('mix')['loudness'] as num?)?.toDouble() ?? -14.0;
      showTips = _prefs!.getBool('tips_done') != true;
      await loadVoices();
      await loadTags();
      unawaited(loadBeats());
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
    _prefs?.setString('tag', jsonEncode({'tag': tag, 'draft': draftTag, 'own': ownVoicePath}));
    notifyListeners();
  }

  J sub(String k) => (s[k] as Map).cast<String, dynamic>();

  // ---------------------------------------------------------------- small UI helpers
  void toast(String text, {String? action, VoidCallback? onAction}) {
    final m = messenger.currentState;
    if (m == null) return;
    m.hideCurrentSnackBar();
    m.showSnackBar(SnackBar(
      content: Text(text),
      behavior: SnackBarBehavior.floating,
      action: action == null ? null : SnackBarAction(label: action, onPressed: onAction ?? () {}),
    ));
  }

  void goTab(int i) {
    tab = i;
    notifyListeners();
  }

  void dismissTips() {
    showTips = false;
    _prefs?.setBool('tips_done', true);
    notifyListeners();
  }

  // ---------------------------------------------------------------- undo
  bool get canUndo => _undo.isNotEmpty;
  String get undoLabel => _undo.isEmpty ? '' : _undo.last.$1;

  /// Remember the settings before a big change, and offer to undo it.
  void _remember(String what) {
    _undo.add((what, jsonEncode(s)));
    settingsGen++;
    if (_undo.length > 20) _undo.removeAt(0);
  }

  void _offerUndo(String done) => toast(done, action: 'Undo', onAction: undo);

  Future<void> undo() async {
    if (_undo.isEmpty) return;
    final (what, before) = _undo.removeLast();
    settingsGen++;
    try {
      s = (await engine.post('/api/sanitize', jsonDecode(before)) as Map).cast<String, dynamic>();
    } catch (_) {
      s = (jsonDecode(before) as Map).cast<String, dynamic>();
    }
    changed();
    toast('Undid: $what');
  }

  // ---------------------------------------------------------------- settings actions
  Future<void> loadGenre(String g, {bool reset = false}) async {
    final label = '${((options['genres'] as Map?) ?? {})[g] ?? g}';
    _remember(reset ? 'Reset style' : 'Switch to $label');
    final keepTag = s['tag'];
    final producer = s['producer'];
    final format = s['format'];
    final length = s['length'];
    final title = s['title'];
    s = (await engine.get('/api/preset/$g') as Map).cast<String, dynamic>();
    if (title != null) s['title'] = title;
    if (keepTag != null) s['tag'] = keepTag;
    s['producer'] = producer ?? '';
    if (length != null) s['length'] = length;
    presetLoudness = (sub('mix')['loudness'] as num?)?.toDouble() ?? -14.0;
    if (format != null && format != 'full') setFormat('$format', notify: false);
    changed();
    _offerUndo(reset ? 'Style reset to its starting point' : 'Switched to $label');
  }

  double presetLoudness = -14.0; // the style's own loudness, restored when leaving TikTok format

  void setFormat(String f, {bool notify = true}) {
    s['format'] = f;
    final tt = f != 'full';
    final mix = sub('mix');
    mix['loudness'] = tt ? -10.0 : presetLoudness;
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
    _remember('Surprise me');
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
    _offerUndo('Shuffled key, chords, sounds and melody');
  }

  Future<void> importSettings(String path) async {
    final j = jsonDecode(await File(path).readAsString());
    _remember('Load settings');
    s = (await engine.post('/api/sanitize', j) as Map).cast<String, dynamic>();
    changed();
    _offerUndo('Settings loaded');
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
    cancelling = false;
    status = 'Starting…';
    renderPct = 0;
    renderStarted = DateTime.now();
    videoPath = null;
    _ticker?.cancel();
    _ticker = Timer.periodic(const Duration(seconds: 1), (_) => notifyListeners()); // elapsed time
    notifyListeners();
    try {
      final r = await engine.runJob('/api/render', {'settings': s},
          onProgress: (m) {
            status = m;
            notifyListeners();
          },
          onPct: (p) => renderPct = p,
          onStarted: (id) => _renderJob = id);
      s = (r['settings'] as Map).cast<String, dynamic>();
      result = {...r, ...beatSummary(s)};
      _prefs?.setString('settings', jsonEncode(s));
      _prefs?.setString('result', jsonEncode({...result!, 'settings': null}));
      tagPreviewWav = null; // a new beat: an old preview no longer matches
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
      final secs = DateTime.now().difference(renderStarted!).inSeconds;
      status = 'Done in ${elapsedText(secs)}. Change anything and make it again.';
      HapticFeedback.mediumImpact();
      toast('Your beat is ready');
      WidgetsBinding.instance.addPostFrameCallback((_) {
        final c = resultKey.currentContext;
        if (c != null) Scrollable.ensureVisible(c, duration: const Duration(milliseconds: 450), curve: Curves.easeOut);
      });
      unawaited(loadBeats());
    } on JobCancelled {
      status = 'Stopped. Your settings are still here.';
    } catch (e) {
      status = 'Something went wrong: $e';
    }
    _ticker?.cancel();
    _renderJob = null;
    busy = false;
    cancelling = false;
    notifyListeners();
  }

  Future<void> cancelRender() async {
    final id = _renderJob;
    if (id == null || cancelling) return;
    cancelling = true;
    status = 'Stopping…';
    notifyListeners();
    await engine.cancelJob(id);
  }

  int get renderSeconds => renderStarted == null ? 0 : DateTime.now().difference(renderStarted!).inSeconds;

  static String elapsedText(int secs) => secs < 60 ? '${secs}s' : '${secs ~/ 60}m ${(secs % 60).toString().padLeft(2, '0')}s';

  // ---------------------------------------------------------------- my beats
  Future<void> loadBeats() async {
    beatsLoading = true;
    notifyListeners();
    try {
      final j = await engine.get('/api/beats/list') as Map;
      beats = (j['beats'] as List).map((e) => (e as Map).cast<String, dynamic>()).toList();
      // a result saved by an older version doesn't say what the beat was: fill it in
      final r = result;
      if (r != null && r['genre'] == null) {
        for (final b in beats) {
          if (b['id'] == beatId(r)) {
            result = {...r, for (final k in ['id', 'name', 'genre', 'bpm', 'key', 'scale']) k: b[k]};
            _prefs?.setString('result', jsonEncode({...result!, 'settings': null}));
          }
        }
      }
    } catch (_) {}
    beatsLoading = false;
    notifyListeners();
  }

  Future<void> renameBeat(J b, String name) async {
    try {
      final r = await engine.post('/api/beats/update', {'id': b['id'], 'name': name}) as Map;
      if (result?['id'] == b['id']) s['title'] = name;
      _replaceBeat(r.cast<String, dynamic>());
    } catch (e) {
      toast("Couldn't rename: $e");
    }
  }

  Future<void> starBeat(J b, bool starred) async {
    try {
      final r = await engine.post('/api/beats/update', {'id': b['id'], 'starred': starred}) as Map;
      _replaceBeat(r.cast<String, dynamic>());
      toast(starred ? 'Starred: this beat is kept for good' : 'Unstarred');
    } catch (e) {
      toast("Couldn't update: $e");
    }
  }

  Future<void> deleteBeat(J b) async {
    try {
      await engine.post('/api/beats/delete', {'id': b['id']});
    } catch (_) {}
    beats.removeWhere((x) => x['id'] == b['id']);
    if (result?['id'] == b['id'] || result?['folder'] == b['folder']) {
      result = null;
      _prefs?.remove('result');
    }
    notifyListeners();
  }

  String? stemsBusy; // id of the beat whose stems are being made

  /// What a beat is (kept with the result so its card describes the beat, not the
  /// settings you're editing now).
  static J beatSummary(J settings) => {
        'name': '${settings['title'] ?? ''}'.trim(),
        'genre': settings['genre'], 'bpm': settings['bpm'], 'key': settings['key'], 'scale': settings['scale'],
      };

  static String beatId(J b) => '${b['id'] ?? '${b['folder']}'.split(Platform.pathSeparator).last}';

  /// Stems are made on demand (they're big). Returns the stems.zip path, or null.
  Future<String?> ensureStems(J b) async {
    final have = b['stems'] as String?;
    if (have != null && File(have).existsSync()) return have;
    if (stemsBusy != null) {
      toast('Already making stems. One moment…');
      return null;
    }
    final id = beatId(b);
    stemsBusy = id;
    notifyListeners();
    toast('Making the stems (each instrument on its own track)…');
    try {
      final r = await engine.runJob('/api/beats/stems', {'id': id});
      final path = r['stems'] as String?;
      if (result != null && beatId(result!) == id) result = {...result!, 'stems': path};
      _replaceBeat(r);
      return path;
    } catch (e) {
      toast("Couldn't make the stems: $e");
      return null;
    } finally {
      stemsBusy = null;
      notifyListeners();
    }
  }

  void _replaceBeat(J b) {
    final i = beats.indexWhere((x) => x['id'] == b['id']);
    if (i >= 0) beats[i] = b;
    notifyListeners();
  }

  /// Bring a beat back: its settings go into Create (undoable) and it becomes the current beat.
  Future<void> openBeat(J b) async {
    try {
      final j = jsonDecode(await File('${b['folder']}${Platform.pathSeparator}settings.json').readAsString());
      _remember('Open "${b['name']}"');
      s = (await engine.post('/api/sanitize', j) as Map).cast<String, dynamic>();
      s['title'] = b['name'];
      result = {...b, 'settings': null};
      _prefs?.setString('result', jsonEncode(result));
      videoPath = b['video'] as String?;
      tagPreviewWav = null;
      status = '';
      changed();
      goTab(0);
      _offerUndo('Opened "${b['name']}". Change anything and make it again');
    } catch (e) {
      toast("Couldn't open that beat: $e");
    }
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
      _remember('Inspiration');
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
    if (ownVoicePath != null && !File(ownVoicePath!).existsSync()) {
      ownVoicePath = null;
      tagStatus = 'Your recording is gone. Record or upload it again.';
      tagChanged();
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
        body['voice_label'] = v.label;
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
      draftTag = r;
      tagStatus = 'Here\'s your preview. Save it to use it on your beats, or change something and try again.';
      tagChanged();
    } catch (e) {
      tagStatus = "Couldn't make the tag: $e";
    }
    tagBusy = false;
    notifyListeners();
  }

  // ---------------------------------------------------------------- tag library
  Future<void> loadTags() async {
    try {
      final j = await engine.get('/api/tags/list') as Map;
      savedTags = (j['tags'] as List).map((e) => (e as Map).cast<String, dynamic>()).toList();
    } catch (_) {
      savedTags = [];
    }
    // the tag picked for beats was deleted or lost: stop using it
    final cfg = sub('tag');
    if (cfg['id'] != null && !savedTags.any((t) => t['id'] == cfg['id'])) {
      cfg['id'] = null;
      _prefs?.setString('settings', jsonEncode(s));
    }
  }

  Future<void> refreshTags() async {
    await loadTags();
    notifyListeners();
  }

  J? get activeTag {
    final id = sub('tag')['id'];
    for (final t in savedTags) {
      if (t['id'] == id) return t;
    }
    return null;
  }

  bool get tagOnBeats => activeTag != null && sub('tag')['mute'] != true;

  Future<void> saveDraft(String name) async {
    final d = draftTag;
    if (d == null) return;
    try {
      final saved = (await engine.post('/api/tags/save', {'id': d['id'], 'name': name}) as Map).cast<String, dynamic>();
      draftTag = null;
      await loadTags();
      useTag('${saved['id']}', notify: false);
      tagStatus = 'Saved "${saved['name']}". It\'s now on your beats. Choose where below.';
    } catch (e) {
      tagStatus = "Couldn't save the tag: $e";
    }
    tagChanged();
  }

  Future<void> discardDraft() async {
    final d = draftTag;
    draftTag = null;
    tagStatus = '';
    tagChanged();
    if (d != null) {
      try {
        await engine.post('/api/tags/delete', {'id': d['id']});
      } catch (_) {}
    }
  }

  Future<void> renameTag(String id, String name) async {
    try {
      await engine.post('/api/tags/rename', {'id': id, 'name': name});
      await loadTags();
    } catch (e) {
      tagStatus = "Couldn't rename the tag: $e";
    }
    notifyListeners();
  }

  Future<void> deleteTag(String id) async {
    try {
      await engine.post('/api/tags/delete', {'id': id});
    } catch (_) {}
    if (sub('tag')['id'] == id) tagPreviewWav = null;
    await loadTags();
    changed();
  }

  /// Pick which saved tag goes on beats (null = none).
  void useTag(String? id, {bool notify = true}) {
    final cfg = sub('tag');
    cfg['id'] = id;
    cfg['mute'] = false;
    final places = cfg['places'];
    if (places is! List || places.isEmpty) cfg['places'] = ['start'];
    tagPreviewWav = null;
    if (notify) {
      changed();
    } else {
      _prefs?.setString('settings', jsonEncode(s));
    }
  }

  void setTagOnBeats(bool on) {
    sub('tag')['mute'] = !on;
    tagPreviewWav = null;
    changed();
  }

  void toggleTagPlace(String place, bool on) {
    final cfg = sub('tag');
    final places = List<String>.from((cfg['places'] as List?)?.map((e) => '$e') ?? const []);
    if (on && !places.contains(place)) places.add(place);
    if (!on) places.remove(place);
    cfg['places'] = [for (final p in tagPlaces.keys) if (places.contains(p)) p];
    tagPreviewWav = null;
    changed();
  }

  void tagMixChanged() {
    tagPreviewWav = null;
    changed();
  }

  /// Hear the chosen tag on the current beat without re-making the beat.
  Future<void> previewTagOnBeat() async {
    final t = activeTag;
    final r = result;
    if (tagPreviewBusy || t == null) return;
    if (r == null || !File('${r['wav']}').existsSync()) {
      tagPreviewStatus = 'Make a beat on the Create tab first, then hear your tag on it here.';
      notifyListeners();
      return;
    }
    final cfg = sub('tag');
    if ((cfg['places'] as List?)?.isEmpty ?? true) {
      tagPreviewStatus = 'Pick at least one place for the tag.';
      notifyListeners();
      return;
    }
    tagPreviewBusy = true;
    tagPreviewStatus = 'Laying the tag over your beat…';
    notifyListeners();
    try {
      final p = await engine.runJob('/api/tags/preview', {
        'folder': r['folder'], 'id': t['id'], 'places': cfg['places'],
        'volume': cfg['volume'], 'duck': cfg['duck'],
      });
      tagPreviewWav = '${p['wav']}';
      final n = p['count'] as int? ?? 0;
      tagPreviewStatus = 'Your tag plays $n time${n == 1 ? '' : 's'} in this preview. '
          'Happy? Press "Add to this beat" to make it for real.';
    } catch (e) {
      tagPreviewStatus = "Couldn't make the preview: $e";
    }
    tagPreviewBusy = false;
    notifyListeners();
  }

  /// Re-make the current beat with the tag in it (same settings, so the same beat).
  Future<void> addTagToBeat() async {
    if (!tagOnBeats) setTagOnBeats(true);
    tagPreviewStatus = 'Making your beat with the tag…';
    notifyListeners();
    await make();
    final n = result?['tags_placed'] as int? ?? 0;
    tagPreviewStatus = n > 0
        ? 'Done: your tag is in the beat ($n time${n == 1 ? '' : 's'}). Share it from the Create tab.'
        : status;
    notifyListeners();
  }
}
