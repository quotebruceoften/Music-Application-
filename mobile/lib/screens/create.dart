import 'dart:io';

import 'package:flutter/material.dart';
import 'package:share_plus/share_plus.dart';

import '../media.dart';
import '../player.dart';
import '../state.dart';
import '../widgets.dart';

class CreateScreen extends StatelessWidget {
  final AppState st;
  const CreateScreen(this.st, {super.key});

  @override
  Widget build(BuildContext context) {
    final s = st.s;
    final genres = (st.options['genres'] as Map).cast<String, dynamic>();
    final tiktok = s['format'] != 'full';
    return ListView(padding: const EdgeInsets.all(14), children: [
      if (st.showTips) _Tips(st),
      SectionCard(title: 'Make a beat', collapsible: false, children: [
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: genres.entries
              .map((e) => ChoiceChip(
                    label: Text('${e.value}'),
                    selected: s['genre'] == e.key,
                    onSelected: (_) => st.loadGenre(e.key),
                  ))
              .toList(),
        ),
        const SizedBox(height: 6),
        SliderRow('Tempo', s, 'bpm', 60, 180, step: 1, fmt: (v) => '${v.round()} BPM', onChanged: st.changed),
        SliderRow('Energy', s, 'energy', 0, 1, fmt: pct, onChanged: st.changed),
        SliderRow('Swing / bounce', s, 'swing', 0, 1, fmt: pct, onChanged: st.changed),
        SliderRow('Human feel', s, 'humanize', 0, 1, fmt: pct, onChanged: st.changed),
        Row(children: [
          Expanded(child: SelectRow('Key', s, 'key', SelectRow.of(st.options['notes'] as List), onChanged: st.changed)),
          const SizedBox(width: 10),
          Expanded(child: SelectRow('Mood', s, 'scale', SelectRow.of(st.options['scales'] as List), onChanged: st.changed)),
        ]),
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: TextFormField(
            key: ValueKey('title=${st.settingsGen}'),
            initialValue: '${s['title'] ?? ''}',
            maxLength: 60,
            decoration: InputDecoration(
                labelText: tiktok ? 'Name (also shown on the video)' : 'Name your beat (optional)',
                hintText: 'e.g. Late night amapiano',
                border: const OutlineInputBorder(),
                isDense: true,
                counterText: ''),
            onChanged: (v) {
              s['title'] = v;
              st.changed();
            },
          ),
        ),
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: DropdownButtonFormField<String>(
            key: ValueKey('format=${s['format']}'),
            value: '${s['format']}',
            isExpanded: true,
            decoration: const InputDecoration(labelText: 'Format', border: OutlineInputBorder(), isDense: true),
            items: const [
              DropdownMenuItem(value: 'full', child: Text('Full song (~1.5–2 min)')),
              DropdownMenuItem(value: 'tiktok15', child: Text('TikTok sound · 15 s')),
              DropdownMenuItem(value: 'tiktok30', child: Text('TikTok sound · 30 s')),
              DropdownMenuItem(value: 'tiktok60', child: Text('TikTok sound · 60 s')),
            ],
            onChanged: (v) {
              if (v != null) st.setFormat(v);
            },
          ),
        ),
        if (!tiktok)
          Padding(
            padding: const EdgeInsets.only(top: 10),
            child: DropdownButtonFormField<String>(
              key: ValueKey('length=${s['length']}'),
              value: '${((s['length'] ?? 0) as num).round()}',
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Length', border: OutlineInputBorder(), isDense: true),
              items: [
                const DropdownMenuItem(value: '0', child: Text('Standard (~1.5–2 min)')),
                for (var m = 3; m <= 10; m++) DropdownMenuItem(value: '$m', child: Text('$m minutes')),
              ],
              onChanged: (v) {
                if (v == null) return;
                s['length'] = int.parse(v);
                st.changed();
              },
            ),
          ),
        if (!tiktok && ((s['length'] ?? 0) as num) > 0)
          const Note('The song repeats its verses and hooks with new melody ideas to fill the time. '
              'Long beats take a few minutes to make on a phone.'),
        if (tiktok) ...[
          SwitchRow('Also make a vertical video (MP4)', s, 'export_video', onChanged: st.changed),
          const Note('Hook-first, loops seamlessly, louder, with bass that comes through phone speakers.'),
        ],
        const SizedBox(height: 6),
        Wrap(spacing: 8, runSpacing: 8, children: [
          OutlinedButton.icon(onPressed: () {
            st.newMelody();
            st.make();
          }, icon: const Icon(Icons.casino_outlined), label: const Text('New melody')),
          OutlinedButton.icon(onPressed: () {
            st.surprise();
            st.make();
          }, icon: const Icon(Icons.auto_awesome), label: const Text('Surprise me')),
          OutlinedButton.icon(
              onPressed: () => st.loadGenre('${s['genre']}', reset: true),
              icon: const Icon(Icons.restart_alt),
              label: const Text('Reset style')),
        ]),
        if (!st.busy) BigButton('Make my beat', onPressed: st.make) else _Progress(st),
        if (!st.busy && st.status.isNotEmpty) Note(st.status, color: kAccent),
      ]),
      if (st.result != null && File('${st.result!['wav']}').existsSync()) KeyedSubtree(key: st.resultKey, child: _Result(st)),
    ]);
  }
}

/// Shown while a beat is being made: what's happening, how far along, time so far, and Stop.
class _Progress extends StatelessWidget {
  final AppState st;
  const _Progress(this.st);

  @override
  Widget build(BuildContext context) {
    final long = ((st.s['length'] ?? 0) as num) > 0;
    return Padding(
      padding: const EdgeInsets.only(top: 14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          Expanded(child: Text(st.status, style: const TextStyle(fontWeight: FontWeight.w600))),
          Text('${(st.renderPct * 100).round()}% · ${AppState.elapsedText(st.renderSeconds)}',
              style: const TextStyle(color: kDim, fontSize: 12)),
        ]),
        const SizedBox(height: 8),
        ClipRRect(
          borderRadius: BorderRadius.circular(6),
          child: LinearProgressIndicator(value: st.renderPct > 0 ? st.renderPct : null, minHeight: 8),
        ),
        const SizedBox(height: 6),
        Row(children: [
          Expanded(
            child: Text(
                long ? 'Long beats take a few minutes. You can use other tabs meanwhile.' : 'You can use other tabs meanwhile.',
                style: const TextStyle(color: kDim, fontSize: 12)),
          ),
          TextButton.icon(
            onPressed: st.cancelling ? null : st.cancelRender,
            icon: const Icon(Icons.stop_circle_outlined),
            label: Text(st.cancelling ? 'Stopping…' : 'Stop'),
          ),
        ]),
      ]),
    );
  }
}

/// A one-time quick start for new users.
class _Tips extends StatelessWidget {
  final AppState st;
  const _Tips(this.st);

  @override
  Widget build(BuildContext context) {
    Widget tip(IconData i, String t) => Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Icon(i, size: 18, color: kAccent),
            const SizedBox(width: 10),
            Expanded(child: Text(t, style: const TextStyle(fontSize: 13))),
          ]),
        );
    return SectionCard(title: 'Quick start', collapsible: false, children: [
      tip(Icons.touch_app_outlined, 'Pick a style and press "Make my beat". That\'s it: the producer engine does the rest.'),
      tip(Icons.casino_outlined, '"New melody" and "Surprise me" give fresh ideas. Changed your mind? Tap Undo at the top.'),
      tip(Icons.headphones, 'Inspire: add songs you love and the beat borrows their tempo, key and groove.'),
      tip(Icons.sell_outlined, 'Tag: make your producer tag and choose where it goes in your beats.'),
      tip(Icons.library_music_outlined, 'My beats keeps everything you make. Star the ones you want to keep for good.'),
      Align(alignment: Alignment.centerRight, child: FilledButton(onPressed: st.dismissTips, child: const Text('Got it'))),
    ]);
  }
}

class _Result extends StatelessWidget {
  final AppState st;
  const _Result(this.st);

  Future<void> _share(BuildContext context, String path, String text) async {
    await Share.shareXFiles([XFile(path)], text: text);
  }

  Future<void> _save(BuildContext context, String path, String name, String mime) async {
    final where = await Media.saveToLibrary(path, name, mime);
    if (!context.mounted) return;
    if (where == null) {
      await Share.shareXFiles([XFile(path)]); // no native "save" here: let the user pick a place
    } else {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Saved to $where')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final r = st.result!;
    final d = ((r['duration'] as num?) ?? 0).toDouble();
    // describe the beat itself (older saved results may not have these: fall back to the settings)
    final s = {...st.s, for (final k in ['genre', 'bpm', 'key', 'scale']) if (r[k] != null) k: r[k]};
    s['title'] = '${r['name'] ?? ''}'.isNotEmpty ? r['name'] : st.s['title'];
    final stamp = fileStamp(s);
    final name = '${s['title'] ?? ''}'.trim();
    return SectionCard(title: name.isEmpty ? 'Your beat' : 'Your beat · $name', collapsible: false, children: [
      PlayerBar(path: '${r['wav']}', autoplay: true),
      Note('${d ~/ 60}:${(d % 60).round().toString().padLeft(2, '0')} · ${r['lufs']} LUFS · '
          '${(s['bpm'] as num).round()} BPM in ${s['key']} ${s['scale']}'),
      Wrap(spacing: 8, runSpacing: 8, children: [
        FilledButton.icon(
          icon: const Icon(Icons.share),
          label: const Text('Share'),
          onPressed: () async => _share(context, await st.shareableAudio(), 'Made with BeatMaker'),
        ),
        OutlinedButton.icon(
          icon: const Icon(Icons.download),
          label: const Text('Save WAV'),
          onPressed: () => _save(context, '${r['wav']}', '$stamp.wav', 'audio/wav'),
        ),
        if (st.videoPath != null)
          FilledButton.icon(
            icon: const Icon(Icons.movie_outlined),
            label: const Text('Share video'),
            onPressed: () => _share(context, st.videoPath!, 'Use this sound!'),
          ),
        if (st.videoPath != null)
          OutlinedButton.icon(
            icon: const Icon(Icons.download),
            label: const Text('Save video'),
            onPressed: () => _save(context, st.videoPath!, '$stamp.mp4', 'video/mp4'),
          ),
        OutlinedButton.icon(
          icon: st.stemsBusy == AppState.beatId(r)
              ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.layers_outlined),
          label: Text(st.stemsBusy == AppState.beatId(r) ? 'Making stems…' : 'Stems'),
          onPressed: st.stemsBusy != null
              ? null
              : () async {
                  final p = await st.ensureStems(r);
                  if (p != null && context.mounted) await _share(context, p, 'Stems');
                },
        ),
        OutlinedButton.icon(
          icon: const Icon(Icons.piano),
          label: const Text('MIDI'),
          onPressed: () => _share(context, '${r['midi']}', 'MIDI'),
        ),
      ]),
      if (s['export_video'] == true && st.videoPath == null && !st.busy)
        const Note("The video couldn't be made on this device yet. Share the audio and add it in TikTok's editor."),
    ]);
  }
}
