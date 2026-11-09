import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../state.dart';
import '../widgets.dart';

class InspireScreen extends StatefulWidget {
  final AppState st;
  final VoidCallback onMade;
  const InspireScreen(this.st, {super.key, required this.onMade});

  @override
  State<InspireScreen> createState() => _InspireScreenState();
}

class _InspireScreenState extends State<InspireScreen> {
  final _link = TextEditingController();

  Future<void> _pick() async {
    final files = await FilePicker.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['mp3', 'wav', 'm4a', 'aac', 'flac', 'ogg', 'opus', 'mp4', 'mov', 'webm', '3gp'],
    );
    if (files.isEmpty) return;
    for (final f in files) {
      if (f.path != null) await widget.st.addSongFile(f.path!, f.name);
    }
  }

  @override
  void dispose() {
    _link.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final st = widget.st;
    final ready = st.refs.where((r) => r.id != null).length;
    return ListView(padding: const EdgeInsets.all(14), children: [
      SectionCard(title: 'Start from songs you love', collapsible: false, children: [
        const Note('Add songs or videos (TikToks, Reels, screen recordings). BeatMaker listens for their tempo, key, '
            'drum groove, chord movement, swing and tone, then blends them into a new beat. '
            'Their audio and melodies are never copied.'),
        const SizedBox(height: 8),
        OutlinedButton.icon(
          onPressed: _pick,
          icon: const Icon(Icons.library_music_outlined),
          label: const Padding(padding: EdgeInsets.symmetric(vertical: 14), child: Text('Add songs or videos')),
        ),
        if (st.engine.linksEnabled) ...[
          const SizedBox(height: 10),
          Row(children: [
            Expanded(
              child: TextField(
                controller: _link,
                decoration: const InputDecoration(
                    hintText: 'Paste a link (TikTok, YouTube, Instagram, Spotify…)', border: OutlineInputBorder(), isDense: true),
                onSubmitted: (_) => _addLink(),
              ),
            ),
            const SizedBox(width: 8),
            FilledButton(onPressed: _addLink, child: const Text('Add')),
          ]),
        ],
        const SizedBox(height: 6),
        ...st.refs.map((r) => _RefTile(st, r, showWeight: ready > 1)),
        const SizedBox(height: 10),
        const Text('Take from them:', style: TextStyle(color: kDim, fontSize: 13)),
        const SizedBox(height: 6),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: AppState.useLabels.entries
              .map((e) => FilterChip(
                    label: Text(e.value),
                    selected: st.use[e.key] == true,
                    onSelected: (v) {
                      st.use[e.key] = v;
                      st.refsChanged();
                    },
                  ))
              .toList(),
        ),
        if (ready > 0)
          BigButton('Make a beat inspired by these', busy: st.busy, onPressed: () async {
            if (await st.applyInspiration()) {
              widget.onMade();
              await st.make();
            }
          }),
        ...st.inspireNotes.map((n) => Note('• $n')),
      ]),
    ]);
  }

  void _addLink() {
    final url = _link.text.trim();
    if (url.isEmpty) return;
    _link.clear();
    widget.st.addSongLink(url);
  }
}

class _RefTile extends StatelessWidget {
  final AppState st;
  final Ref r;
  final bool showWeight;
  const _RefTile(this.st, this.r, {required this.showWeight});

  @override
  Widget build(BuildContext context) {
    final w = <String, dynamic>{'w': r.weight};
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 8),
      decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: kLine))),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          if (r.busy)
            const Padding(
                padding: EdgeInsets.only(right: 10), child: SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))),
          Expanded(
            child: Text(r.busy ? 'Listening to ${r.name}…' : r.name,
                maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w600)),
          ),
          IconButton(icon: const Icon(Icons.close, size: 20), onPressed: () => st.removeRef(r)),
        ]),
        if (r.error != null) Note(r.error!, color: kAccent2),
        if (r.id != null)
          Note(r.summary + (r.progression != null ? ' · chords ${r.progression!.join('-')}' : '')),
        if (r.id != null && showWeight)
          SliderRow('Influence', w, 'w', 0, 1, fmt: pct, onChanged: () {
            r.weight = (w['w'] as num).toDouble();
            st.refsChanged();
          }),
      ]),
    );
  }
}
