import 'dart:async';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:record/record.dart';

import '../engine.dart' show J;
import '../player.dart';
import '../state.dart';
import '../widgets.dart';

/// Producer tags: make one, preview it, save it to your library, then choose if and
/// where it goes in your beats (and hear it on your current beat before committing).
class TagScreen extends StatefulWidget {
  final AppState st;
  const TagScreen(this.st, {super.key});

  @override
  State<TagScreen> createState() => _TagScreenState();
}

class _TagScreenState extends State<TagScreen> {
  static const maxRecordSeconds = 12; // the engine uses up to 12 s of a recording

  final AudioRecorder _rec = AudioRecorder();
  bool _recording = false;
  int _recSeconds = 0;
  Timer? _recTimer;
  String? _playingId; // the library tag whose player is open
  late final TextEditingController _text = TextEditingController(text: '${widget.st.tag['text']}');
  late final TextEditingController _name = TextEditingController(text: '${widget.st.s['producer'] ?? ''}');

  AppState get st => widget.st;

  @override
  void dispose() {
    _recTimer?.cancel();
    _rec.dispose();
    _text.dispose();
    _name.dispose();
    super.dispose();
  }

  // ---------------------------------------------------------------- your own voice
  Future<void> _toggleRecord() async {
    if (_recording) return _stopRecording();
    try {
      if (!await _rec.hasPermission()) {
        st.tagStatus = 'BeatMaker needs microphone permission to record your tag. '
            'Allow it in your phone\'s settings, then try again.';
        st.tagChanged();
        return;
      }
      final path = st.engine.tmpPath('wav');
      await _rec.start(const RecordConfig(encoder: AudioEncoder.wav, sampleRate: 44100, numChannels: 1), path: path);
      setState(() {
        _recording = true;
        _recSeconds = 0;
      });
      _recTimer = Timer.periodic(const Duration(seconds: 1), (t) {
        if (!mounted) return;
        setState(() => _recSeconds++);
        if (_recSeconds >= maxRecordSeconds) _stopRecording();
      });
    } catch (e) {
      st.tagStatus = "Couldn't start recording: $e";
      st.tagChanged();
    }
  }

  Future<void> _stopRecording() async {
    _recTimer?.cancel();
    String? path;
    try {
      path = await _rec.stop();
    } catch (_) {}
    if (!mounted) return;
    setState(() => _recording = false);
    if (path != null && File(path).existsSync() && File(path).lengthSync() > 2000) {
      st.ownVoicePath = path;
      st.tagStatus = 'Got your voice. Listen back below, pick a style, then press "Make preview".';
    } else {
      st.tagStatus = "That recording was empty. Hold the phone close and try again.";
    }
    st.tagChanged();
  }

  Future<void> _upload() async {
    try {
      final f = await FilePicker.pickFile(
          type: FileType.custom, allowedExtensions: ['mp3', 'wav', 'm4a', 'aac', 'ogg', 'opus', 'mp4', 'mov', '3gp', 'webm']);
      if (f?.path == null) return;
      st.ownVoicePath = f!.path;
      st.tagStatus = 'Using "${f.name}". Pick a style, then press "Make preview".';
      st.tagChanged();
    } catch (e) {
      st.tagStatus = "Couldn't open that file: $e";
      st.tagChanged();
    }
  }

  // ---------------------------------------------------------------- dialogs
  Future<String?> _askName(String title, String initial, String action) {
    final c = TextEditingController(text: initial);
    return showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(title),
        content: TextField(
          controller: c,
          autofocus: true,
          maxLength: 40,
          decoration: const InputDecoration(labelText: 'Name', hintText: 'e.g. Main tag'),
          onSubmitted: (v) => Navigator.pop(ctx, v),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, c.text), child: Text(action)),
        ],
      ),
    );
  }

  Future<bool> _confirm(String title, String body, String action) async {
    final r = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(title),
        content: Text(body),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(
              style: FilledButton.styleFrom(backgroundColor: kAccent2),
              onPressed: () => Navigator.pop(ctx, true),
              child: Text(action)),
        ],
      ),
    );
    return r == true;
  }

  void _share(J t) {
    final path = '${t['mp3'] ?? t['wav']}';
    if (!File(path).existsSync()) return;
    shareFiles([path], text: 'My producer tag');
  }

  String _describe(J t) {
    final styles = ((st.options['tag_styles'] as Map?) ?? {}).cast<String, dynamic>();
    final style = '${styles[t['style']] ?? t['style'] ?? ''}'.split(':').first;
    final parts = <String>[
      if ('${t['text'] ?? ''}'.isNotEmpty) '"${t['text']}"',
      if (style.isNotEmpty) style,
      if (t['duration'] != null) '${t['duration']} s',
      if ('${t['voice'] ?? ''}'.isNotEmpty) '${t['voice']}',
    ];
    return parts.join(' · ');
  }

  // ---------------------------------------------------------------- build
  @override
  Widget build(BuildContext context) {
    return ListView(padding: const EdgeInsets.all(14), children: [
      _makeCard(),
      if (st.draftTag != null) _draftCard(),
      _libraryCard(),
      if (st.activeTag != null) _placementCard(),
    ]);
  }

  Widget _makeCard() {
    final t = st.tag;
    final styles = ((st.options['tag_styles'] as Map?) ?? {}).cast<String, dynamic>();
    final own = st.ownVoicePath;
    return SectionCard(title: 'Make a producer tag', collapsible: false, children: [
      const Note('Your signature in every beat, like the big producers. Make one, listen, '
          'and only save it if you like it.'),
      const SizedBox(height: 6),
      TextField(
        controller: _name,
        decoration: const InputDecoration(labelText: 'Producer name', border: OutlineInputBorder(), isDense: true),
        onChanged: (v) {
          st.s['producer'] = v;
          st.changed();
        },
      ),
      const SizedBox(height: 10),
      TextField(
        controller: _text,
        maxLength: 60,
        decoration: const InputDecoration(
            labelText: 'Tag words', hintText: 'e.g. Ke Bruce!', border: OutlineInputBorder(), isDense: true),
        onChanged: (v) {
          t['text'] = v;
          st.tagChanged();
        },
      ),
      Align(
        alignment: Alignment.centerLeft,
        child: TextButton.icon(
            onPressed: () async {
              try {
                await st.suggestIdeas();
              } catch (e) {
                st.tagStatus = "Couldn't get ideas: $e";
                st.tagChanged();
              }
            },
            icon: const Icon(Icons.lightbulb_outline),
            label: const Text('Give me ideas')),
      ),
      if (st.ideas.isNotEmpty)
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: st.ideas
              .map((i) => ActionChip(
                    label: Text('${i['text']}'),
                    onPressed: () {
                      t['text'] = i['text'];
                      if (styles.containsKey(i['style'])) t['style'] = i['style'];
                      _text.text = '${i['text']}';
                      st.tagChanged();
                    },
                  ))
              .toList(),
        ),
      const SizedBox(height: 8),
      if (own == null) ...[
        if (st.voices.isNotEmpty)
          SelectRow('Voice', t, 'voice', {for (final v in st.voices) v.key: v.label}, onChanged: st.tagChanged)
        else
          const Note('No built-in voice found on this device. Record or upload your own voice below.'),
      ],
      const Padding(
        padding: EdgeInsets.only(top: 12, bottom: 4),
        child: Text('…or use your own voice (best for a real signature):', style: TextStyle(color: kDim, fontSize: 13)),
      ),
      Wrap(spacing: 8, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
        FilledButton.icon(
          style: _recording ? FilledButton.styleFrom(backgroundColor: kAccent2) : null,
          onPressed: _toggleRecord,
          icon: Icon(_recording ? Icons.stop : Icons.mic),
          label: Text(_recording ? 'Stop  ${_recSeconds}s / ${maxRecordSeconds}s' : 'Record'),
        ),
        OutlinedButton.icon(
            onPressed: _recording ? null : _upload, icon: const Icon(Icons.upload_file), label: const Text('Upload voice')),
        if (own != null)
          InputChip(
            avatar: const Icon(Icons.record_voice_over, size: 18),
            label: const Text('Using your voice'),
            onDeleted: () {
              st.ownVoicePath = null;
              st.tagStatus = '';
              st.tagChanged();
            },
          ),
      ]),
      if (_recording)
        const Note('Say your tag clearly, then press Stop. Recording stops by itself after 12 seconds.', color: kAccent),
      if (own != null && !_recording && File(own).existsSync()) ...[
        const SizedBox(height: 6),
        const Text('Your recording (before effects):', style: TextStyle(color: kDim, fontSize: 12)),
        PlayerBar(key: ValueKey('own=$own'), path: own),
      ],
      const Divider(height: 28),
      SelectRow('Style', t, 'style', styles.map((k, v) => MapEntry(k, '$v'.split(':').first)), onChanged: st.tagChanged),
      if (styles[t['style']] != null) Note('${styles[t['style']]}'),
      SliderRow('Voice pitch', t, 'pitch', -7, 7, step: 1, fmt: semis, onChanged: st.tagChanged),
      SwitchRow('Reverse swell into the voice', t, 'swell', onChanged: st.tagChanged),
      SwitchRow('Impact (boom + crash)', t, 'impact', onChanged: st.tagChanged),
      SwitchRow('Riser before', t, 'riser', onChanged: st.tagChanged),
      BigButton(st.draftTag == null ? 'Make preview' : 'Make a new preview',
          busy: st.tagBusy, onPressed: _recording ? null : st.makeTag),
      if (st.tagStatus.isNotEmpty) Note(st.tagStatus, color: kAccent),
    ]);
  }

  Widget _draftCard() {
    final d = st.draftTag!;
    return SectionCard(title: 'Preview', collapsible: false, children: [
      Text(_describe(d), style: const TextStyle(color: kDim, fontSize: 12)),
      PlayerBar(key: ValueKey('draft=${d['wav']}'), path: '${d['wav']}', autoplay: true),
      const Note('Not saved yet. Save it to put it on your beats, or change the words, voice or style '
          'above and make a new preview.'),
      const SizedBox(height: 8),
      Wrap(spacing: 8, runSpacing: 8, children: [
        FilledButton.icon(
          onPressed: () async {
            final name = await _askName('Save this tag', '${d['text'] ?? ''}'.trim(), 'Save');
            if (name != null) await st.saveDraft(name);
          },
          icon: const Icon(Icons.bookmark_add),
          label: const Text('Save tag'),
        ),
        OutlinedButton.icon(onPressed: () => _share(d), icon: const Icon(Icons.share), label: const Text('Share')),
        TextButton.icon(onPressed: st.discardDraft, icon: const Icon(Icons.delete_outline), label: const Text('Discard')),
      ]),
    ]);
  }

  Widget _libraryCard() {
    final tags = st.savedTags;
    final activeId = st.activeTag?['id'] as String?;
    return SectionCard(title: 'My tags${tags.isEmpty ? '' : ' (${tags.length})'}', collapsible: false, children: [
      if (tags.isEmpty)
        const Note('Tags you save show up here. Pick one to put it on your beats.')
      else
        RadioGroup<String?>(
          groupValue: activeId,
          onChanged: (v) => st.useTag(v),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        const Note('Tap a tag to put it on your beats.'),
        const RadioListTile<String?>(
          contentPadding: EdgeInsets.zero,
          dense: true,
          value: null,
          title: Text('No tag on my beats'),
        ),
        for (final t in tags) ...[
          Row(children: [
            Expanded(
              child: RadioListTile<String?>(
                contentPadding: EdgeInsets.zero,
                dense: true,
                value: '${t['id']}',
                title: Text('${t['name']}', style: const TextStyle(fontWeight: FontWeight.w600)),
                subtitle: Text(_describe(t), maxLines: 2, overflow: TextOverflow.ellipsis),
              ),
            ),
            IconButton(
              tooltip: _playingId == t['id'] ? 'Hide player' : 'Play',
              icon: Icon(_playingId == t['id'] ? Icons.expand_less : Icons.play_circle_outline),
              onPressed: () => setState(() => _playingId = _playingId == t['id'] ? null : '${t['id']}'),
            ),
            PopupMenuButton<String>(
              onSelected: (a) async {
                if (a == 'rename') {
                  final name = await _askName('Rename tag', '${t['name']}', 'Rename');
                  if (name != null && name.trim().isNotEmpty) await st.renameTag('${t['id']}', name);
                } else if (a == 'share') {
                  _share(t);
                } else if (a == 'delete') {
                  if (await _confirm('Delete "${t['name']}"?', 'This removes the tag from the app. '
                      'Beats you already made keep it.', 'Delete')) {
                    if (_playingId == t['id']) _playingId = null;
                    await st.deleteTag('${t['id']}');
                  }
                }
              },
              itemBuilder: (_) => const [
                PopupMenuItem(value: 'rename', child: Text('Rename')),
                PopupMenuItem(value: 'share', child: Text('Share')),
                PopupMenuItem(value: 'delete', child: Text('Delete')),
              ],
            ),
          ]),
          if (_playingId == t['id'] && File('${t['wav']}').existsSync())
            PlayerBar(key: ValueKey('lib=${t['wav']}'), path: '${t['wav']}', autoplay: true),
        ],
          ]),
        ),
    ]);
  }

  Widget _placementCard() {
    final t = st.activeTag!;
    final cfg = st.sub('tag');
    final places = ((cfg['places'] as List?) ?? const []).map((e) => '$e').toSet();
    final on = st.tagOnBeats;
    final hasBeat = st.result != null && File('${st.result!['wav']}').existsSync();
    final preview = st.tagPreviewWav;
    return SectionCard(title: 'Put it in your beat', collapsible: false, children: [
      SwitchListTile(
        contentPadding: EdgeInsets.zero,
        title: Text('Add "${t['name']}" to my beats'),
        subtitle: Text(on ? 'It goes into every beat you make.' : 'Off: your beats are made without a tag.'),
        value: on,
        onChanged: st.setTagOnBeats,
      ),
      Opacity(
        opacity: on ? 1 : 0.45,
        child: IgnorePointer(
          ignoring: !on,
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            const Padding(
              padding: EdgeInsets.only(top: 4, bottom: 6),
              child: Text('Where in the song', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
            ),
            Wrap(spacing: 6, runSpacing: 6, children: [
              for (final e in AppState.tagPlaces.entries)
                FilterChip(
                  label: Text(e.value),
                  selected: places.contains(e.key),
                  onSelected: (v) => st.toggleTagPlace(e.key, v),
                ),
            ]),
            if (places.isEmpty) const Note('Pick at least one place, or switch the tag off.', color: kAccent2),
            const Note('Tags never overlap: if two places are too close, the tag plays once.'),
            SliderRow('Tag volume', cfg, 'volume', -20, 6, step: 1, fmt: dB, onChanged: st.tagMixChanged),
            SliderRow('Duck the beat under the tag', cfg, 'duck', 0, 1, fmt: pct, onChanged: st.tagMixChanged),
          ]),
        ),
      ),
      const Divider(height: 24),
      const Text('Hear it in your beat', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
      if (!hasBeat)
        const Note('Make a beat on the Create tab first. Then you can hear your tag on it here before adding it.')
      else ...[
        const SizedBox(height: 6),
        Wrap(spacing: 8, runSpacing: 8, children: [
          OutlinedButton.icon(
            onPressed: !on || places.isEmpty || st.tagPreviewBusy ? null : st.previewTagOnBeat,
            icon: st.tagPreviewBusy
                ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.headphones),
            label: const Text('Preview on my beat'),
          ),
          FilledButton.icon(
            onPressed: !on || places.isEmpty || st.busy ? null : st.addTagToBeat,
            icon: st.busy
                ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.check),
            label: const Text('Add to this beat'),
          ),
        ]),
        if (preview != null && File(preview).existsSync())
          PlayerBar(key: ValueKey('pv=$preview'), path: preview, autoplay: true),
        if (st.tagPreviewStatus.isNotEmpty) Note(st.tagPreviewStatus, color: kAccent),
        if (st.busy && st.status.isNotEmpty) Note(st.status),
      ],
    ]);
  }
}
