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
        if (tiktok) ...[
          Padding(
            padding: const EdgeInsets.only(top: 10),
            child: TextFormField(
              initialValue: '${s['title'] ?? ''}',
              decoration: const InputDecoration(labelText: 'Title on the video', hintText: 'e.g. Late night amapiano',
                  border: OutlineInputBorder(), isDense: true),
              onChanged: (v) {
                s['title'] = v;
                st.changed();
              },
            ),
          ),
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
              onPressed: () => st.loadGenre('${s['genre']}'), icon: const Icon(Icons.restart_alt), label: const Text('Reset style')),
        ]),
        BigButton('Make my beat', busy: st.busy, onPressed: st.make),
        if (st.status.isNotEmpty) Note(st.status, color: kAccent),
      ]),
      if (st.result != null && File('${st.result!['wav']}').existsSync()) _Result(st),
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
    final d = (r['duration'] as num).toDouble();
    final s = st.s;
    final stamp = '${s['genre']}-${(s['bpm'] as num).round()}bpm-${'${s['key']}'.replaceAll('#', 's')}';
    return SectionCard(title: 'Your beat', collapsible: false, children: [
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
          onPressed: () => _save(context, '${r['wav']}', 'beat-$stamp.wav', 'audio/wav'),
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
            onPressed: () => _save(context, st.videoPath!, 'beat-$stamp.mp4', 'video/mp4'),
          ),
        OutlinedButton.icon(
          icon: const Icon(Icons.layers_outlined),
          label: const Text('Stems'),
          onPressed: () => _share(context, '${r['stems']}', 'Stems'),
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
