import 'dart:io';

import 'package:flutter/material.dart';

import '../engine.dart' show J;
import '../media.dart';
import '../player.dart';
import '../state.dart';
import '../widgets.dart';

/// Every beat you've made: play, name, star (keep for good), share, open again, delete.
class BeatsScreen extends StatefulWidget {
  final AppState st;
  const BeatsScreen(this.st, {super.key});

  @override
  State<BeatsScreen> createState() => _BeatsScreenState();
}

class _BeatsScreenState extends State<BeatsScreen> {
  bool _starredOnly = false;
  String? _playing;
  String _query = '';

  AppState get st => widget.st;

  static String _ago(num? created) {
    if (created == null) return '';
    final d = DateTime.now().difference(DateTime.fromMillisecondsSinceEpoch((created * 1000).round()));
    if (d.inMinutes < 1) return 'just now';
    if (d.inHours < 1) return '${d.inMinutes} min ago';
    if (d.inDays < 1) return '${d.inHours} h ago';
    if (d.inDays < 7) return '${d.inDays} d ago';
    final t = DateTime.fromMillisecondsSinceEpoch((created * 1000).round());
    return '${t.day}/${t.month}/${t.year}';
  }

  static String _len(num? secs) {
    if (secs == null) return '';
    final s = secs.round();
    return '${s ~/ 60}:${(s % 60).toString().padLeft(2, '0')}';
  }

  static String _size(num bytes) {
    if (bytes > 1e9) return '${(bytes / 1e9).toStringAsFixed(1)} GB';
    return '${(bytes / 1e6).round()} MB';
  }

  Future<String?> _ask(String title, String initial) {
    final c = TextEditingController(text: initial);
    return showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(title),
        content: TextField(
          controller: c,
          autofocus: true,
          maxLength: 60,
          decoration: const InputDecoration(labelText: 'Name'),
          onSubmitted: (v) => Navigator.pop(ctx, v),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, c.text), child: const Text('Save')),
        ],
      ),
    );
  }

  Future<void> _delete(J b) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Delete "${b['name']}"?'),
        content: const Text('The beat, its stems and MIDI are removed from the app. Files you already shared or saved stay.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(
              style: FilledButton.styleFrom(backgroundColor: kAccent2),
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Delete')),
        ],
      ),
    );
    if (ok == true) {
      if (_playing == b['id']) _playing = null;
      await st.deleteBeat(b);
      st.toast('Deleted "${b['name']}"');
    }
  }

  Future<void> _shareAudio(J b) async {
    String? path = (b['mp3'] ?? b['m4a']) as String?;
    if (path == null || !File(path).existsSync()) {
      final m4a = '${b['folder']}${Platform.pathSeparator}beat.m4a';
      path = await Media.encodeAac('${b['wav']}', m4a) ?? '${b['wav']}';
    }
    await shareFiles([path], text: '${b['name']} · made with BeatMaker');
  }

  Future<void> _saveWav(J b) async {
    final name = '${fileStamp({'title': b['name'], 'genre': b['genre'], 'bpm': b['bpm'], 'key': b['key']})}.wav';
    final where = await Media.saveToLibrary('${b['wav']}', name, 'audio/wav');
    if (where == null) {
      await shareFiles(['${b['wav']}']);
    } else {
      st.toast('Saved to $where');
    }
  }

  void _shareFile(String? path, String text) {
    if (path == null || !File(path).existsSync()) {
      st.toast('That file is missing for this beat.');
      return;
    }
    shareFiles([path], text: text);
  }

  @override
  Widget build(BuildContext context) {
    final all = st.beats;
    final q = _query.trim().toLowerCase();
    final shown = all
        .where((b) => !_starredOnly || b['starred'] == true)
        .where((b) => q.isEmpty || '${b['name']} ${b['genre_label']} ${b['key']}'.toLowerCase().contains(q))
        .toList();
    final total = all.fold<num>(0, (a, b) => a + ((b['size'] as num?) ?? 0));
    final starred = all.where((b) => b['starred'] == true).length;
    final currentId = st.result == null ? null : AppState.beatId(st.result!);

    return RefreshIndicator(
      onRefresh: st.loadBeats,
      child: ListView(padding: kPagePadding, physics: const AlwaysScrollableScrollPhysics(), children: [
        SectionCard(title: 'My beats', collapsible: false, children: [
          Text(
              all.isEmpty
                  ? 'Every beat you make is kept here.'
                  : '${all.length} beat${all.length == 1 ? '' : 's'} · $starred starred · ${_size(total)}',
              style: const TextStyle(color: kDim, fontSize: 12)),
          if (all.isNotEmpty) ...[
            const SizedBox(height: 10),
            TextField(
              decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.search), hintText: 'Search by name, style or key', isDense: true,
                  border: OutlineInputBorder()),
              onChanged: (v) => setState(() => _query = v),
            ),
            const SizedBox(height: 8),
            Wrap(spacing: 8, children: [
              ChoiceChip(label: const Text('All'), selected: !_starredOnly, onSelected: (_) => setState(() => _starredOnly = false)),
              ChoiceChip(
                  avatar: const Icon(Icons.star, size: 16),
                  label: const Text('Starred'),
                  selected: _starredOnly,
                  onSelected: (_) => setState(() => _starredOnly = true)),
            ]),
            const Note('The app keeps your newest 20 beats (up to 3 GB) and removes older ones. '
                'Starred beats are never removed.'),
          ],
        ]),
        if (st.beatsLoading && all.isEmpty) const Center(child: Padding(padding: EdgeInsets.all(24), child: CircularProgressIndicator())),
        if (!st.beatsLoading && all.isEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 30),
            child: Column(children: [
              const Icon(Icons.library_music_outlined, size: 48, color: kDim),
              const SizedBox(height: 10),
              const Text('No beats yet', style: TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 12),
              FilledButton.icon(onPressed: () => st.goTab(0), icon: const Icon(Icons.graphic_eq), label: const Text('Make a beat')),
            ]),
          ),
        if (all.isNotEmpty && shown.isEmpty)
          const Padding(padding: EdgeInsets.all(20), child: Center(child: Text('Nothing matches.', style: TextStyle(color: kDim)))),
        for (final b in shown) _tile(b, b['id'] == currentId),
      ]),
    );
  }

  Widget _tile(J b, bool current) {
    final playing = _playing == b['id'];
    final info = [
      '${b['genre_label'] ?? ''}',
      if (b['bpm'] != null) '${(b['bpm'] as num).round()} BPM',
      if (b['key'] != null) '${b['key']} ${b['scale'] ?? ''}',
      _len(b['duration'] as num?),
      if ((b['format'] ?? 'full') != 'full') 'TikTok',
      if (((b['tags_placed'] as num?) ?? 0) > 0) 'tagged',
    ].where((x) => x.trim().isNotEmpty).join(' · ');
    return Card(
      color: kCard,
      margin: const EdgeInsets.only(bottom: 10),
      shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14), side: BorderSide(color: current ? kAccent : kLine)),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(4, 4, 4, 8),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Row(children: [
            IconButton(
              tooltip: playing ? 'Hide player' : 'Play',
              icon: Icon(playing ? Icons.expand_less : Icons.play_circle_fill, color: kAccent, size: 34),
              onPressed: () => setState(() => _playing = playing ? null : '${b['id']}'),
            ),
            Expanded(
              child: InkWell(
                onTap: () => setState(() => _playing = playing ? null : '${b['id']}'),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(children: [
                    Flexible(
                      child: Text('${b['name']}',
                          maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w700)),
                    ),
                    if (current)
                      Container(
                        margin: const EdgeInsets.only(left: 6),
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                        decoration: BoxDecoration(color: kAccent.withValues(alpha: 0.18), borderRadius: BorderRadius.circular(6)),
                        child: const Text('current', style: TextStyle(color: kAccent, fontSize: 11)),
                      ),
                  ]),
                  const SizedBox(height: 2),
                  Text(info, style: const TextStyle(color: kDim, fontSize: 12)),
                  Text(_ago(b['created'] as num?), style: const TextStyle(color: kDim, fontSize: 11)),
                ]),
              ),
            ),
            IconButton(
              tooltip: b['starred'] == true ? 'Unstar' : 'Star (keep for good)',
              icon: Icon(b['starred'] == true ? Icons.star : Icons.star_border,
                  color: b['starred'] == true ? kAccent : kDim),
              onPressed: () => st.starBeat(b, b['starred'] != true),
            ),
            PopupMenuButton<String>(
              onSelected: (a) async {
                switch (a) {
                  case 'open':
                    await st.openBeat(b);
                  case 'rename':
                    final n = await _ask('Rename beat', '${b['name']}');
                    if (n != null && n.trim().isNotEmpty) await st.renameBeat(b, n.trim());
                  case 'share':
                    await _shareAudio(b);
                  case 'save':
                    await _saveWav(b);
                  case 'video':
                    _shareFile(b['video'] as String?, 'Use this sound!');
                  case 'stems':
                    final p = await st.ensureStems(b);
                    if (p != null) _shareFile(p, 'Stems · ${b['name']}');
                  case 'midi':
                    _shareFile(b['midi'] as String?, 'MIDI · ${b['name']}');
                  case 'delete':
                    await _delete(b);
                }
              },
              itemBuilder: (_) => [
                const PopupMenuItem(value: 'open', child: ListTile(leading: Icon(Icons.edit_note), title: Text('Open in Create'), dense: true)),
                const PopupMenuItem(value: 'rename', child: ListTile(leading: Icon(Icons.drive_file_rename_outline), title: Text('Rename'), dense: true)),
                const PopupMenuItem(value: 'share', child: ListTile(leading: Icon(Icons.share), title: Text('Share audio'), dense: true)),
                const PopupMenuItem(value: 'save', child: ListTile(leading: Icon(Icons.download), title: Text('Save WAV'), dense: true)),
                if (b['video'] != null)
                  const PopupMenuItem(value: 'video', child: ListTile(leading: Icon(Icons.movie_outlined), title: Text('Share video'), dense: true)),
                PopupMenuItem(
                    value: 'stems',
                    enabled: st.stemsBusy == null,
                    child: ListTile(
                        leading: const Icon(Icons.layers_outlined),
                        title: Text(b['stems'] == null ? 'Make & share stems' : 'Stems'),
                        dense: true)),
                const PopupMenuItem(value: 'midi', child: ListTile(leading: Icon(Icons.piano), title: Text('MIDI'), dense: true)),
                const PopupMenuItem(value: 'delete', child: ListTile(leading: Icon(Icons.delete_outline, color: kAccent2), title: Text('Delete'), dense: true)),
              ],
            ),
          ]),
          if (playing && File('${b['wav']}').existsSync())
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 10),
              child: PlayerBar(key: ValueKey('beat=${b['wav']}'), path: '${b['wav']}', autoplay: true),
            ),
        ]),
      ),
    );
  }
}
