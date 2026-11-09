import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../state.dart';
import '../widgets.dart';

const _labels = {
  'kick': 'Kick', 'snare': 'Snare', 'clap': 'Clap', 'hat': 'Hi-hat', 'openhat': 'Open hat', 'shaker': 'Shaker',
  'perc': 'Perc', 'bass': 'Bass', 'chords': 'Chords', 'melody': 'Melody', 'fx': 'Risers/FX', 'texture': 'Vinyl',
};

class StudioScreen extends StatelessWidget {
  final AppState st;
  const StudioScreen(this.st, {super.key});

  @override
  Widget build(BuildContext context) {
    final sounds = (st.options['sounds'] as Map).cast<String, dynamic>();
    List<dynamic> snd(String k) => sounds[k] as List<dynamic>;
    final ch = st.changed;
    final bass = st.sub('bass'), chords = st.sub('chords'), melody = st.sub('melody'), mix = st.sub('mix');

    return ListView(padding: const EdgeInsets.all(14), children: [
      // ------------------------------------------------ drums
      SectionCard(title: 'Drums', subtitle: 'Tap squares to change the rhythm', initiallyExpanded: true, children: [
        const Note('Tap: empty → hit → soft hit. Tap the name for sound settings.'),
        ...(st.options['drums'] as List).map((d) => _DrumLane(st, '$d')),
      ]),

      // ------------------------------------------------ bass
      SectionCard(title: 'Bass', children: [
        const Note('Tap: empty → hit → soft → 5 (fifth) → ^ (octave up). The bass follows your chords.'),
        StepGrid(bass, 'pattern', const ['.', 'x', 'o', '5', '^'], onChanged: ch),
        SelectRow('Sound', bass, 'sound', SelectRow.of(snd('bass_sounds')), onChanged: ch),
        SliderRow('Volume', bass, 'volume', -30, 6, step: 1, fmt: dB, onChanged: ch),
        SliderRow('Octave', bass, 'octave', 0, 3, step: 1, fmt: (v) => '${v.round()}', onChanged: ch),
        SliderRow('Length', bass, 'decay', 0.25, 3, fmt: (v) => '${v.toStringAsFixed(2)}×', onChanged: ch),
        SliderRow('Glide (808)', bass, 'glide', 0, 1, fmt: pct, onChanged: ch),
        SwitchRow('Duck under the kick', bass, 'sidechain', onChanged: ch),
        SwitchRow('Mute', bass, 'mute', onChanged: ch),
      ]),

      // ------------------------------------------------ chords
      SectionCard(title: 'Chords', children: [
        _Progression(st),
        SelectRow('Each chord lasts', st.s, 'chord_bars', const {'0.5': 'Half a bar', '1': '1 bar', '2': '2 bars'},
            parse: (v) => double.parse(v), onChanged: ch),
        const Padding(padding: EdgeInsets.only(top: 12, bottom: 4), child: Text('Rhythm', style: TextStyle(fontSize: 13))),
        StepGrid(chords, 'pattern', const ['.', 'x', 'o'], onChanged: ch),
        SelectRow('Sound', chords, 'sound', SelectRow.of(snd('chord_sounds')), onChanged: ch),
        SelectRow('Richness', chords, 'voicing', SelectRow.of(st.options['voicings'] as List), onChanged: ch),
        SliderRow('Volume', chords, 'volume', -30, 6, step: 1, fmt: dB, onChanged: ch),
        SliderRow('Octave', chords, 'octave', 2, 6, step: 1, fmt: (v) => '${v.round()}', onChanged: ch),
        SliderRow('Brightness', chords, 'brightness', 0, 1, fmt: pct, onChanged: ch),
        SliderRow('Stereo width', chords, 'stereo', 0, 1, fmt: pct, onChanged: ch),
        SliderRow('Reverb', chords, 'reverb', 0, 1, fmt: pct, onChanged: ch),
        SliderRow('Echo', chords, 'delay', 0, 1, fmt: pct, onChanged: ch),
        SwitchRow('Duck under the kick', chords, 'sidechain', onChanged: ch),
        SwitchRow('Mute', chords, 'mute', onChanged: ch),
      ]),

      // ------------------------------------------------ melody
      SectionCard(title: 'Melody', children: [
        SelectRow('Sound', melody, 'sound', SelectRow.of(snd('melody_sounds')), onChanged: ch),
        SliderRow('Busy-ness', melody, 'density', 0.05, 1, fmt: pct, onChanged: ch),
        SliderRow('Octave', melody, 'octave', 3, 7, step: 1, fmt: (v) => '${v.round()}', onChanged: ch),
        SliderRow('Volume', melody, 'volume', -30, 6, step: 1, fmt: dB, onChanged: ch),
        SliderRow('Brightness', melody, 'brightness', 0, 1, fmt: pct, onChanged: ch),
        SliderRow('Reverb', melody, 'reverb', 0, 1, fmt: pct, onChanged: ch),
        SliderRow('Echo', melody, 'delay', 0, 1, fmt: pct, onChanged: ch),
        Row(children: [
          Expanded(child: Note('Melody idea #${numOf(melody['seed']).round()}')),
          TextButton.icon(onPressed: st.newMelody, icon: const Icon(Icons.casino_outlined), label: const Text('New idea')),
        ]),
        SwitchRow('Duck under the kick', melody, 'sidechain', onChanged: ch),
        SwitchRow('Mute', melody, 'mute', onChanged: ch),
      ]),

      // ------------------------------------------------ structure
      SectionCard(title: 'Song structure', subtitle: 'Full-song format only', children: [_Structure(st)]),

      // ------------------------------------------------ mix
      SectionCard(title: 'Mix & master', children: [
        SliderRow('Reverb amount', mix, 'reverb', 0, 1, fmt: pct, onChanged: ch),
        SliderRow('Room size', mix, 'reverb_size', 0.5, 5, fmt: (v) => '${v.toStringAsFixed(1)} s', onChanged: ch),
        SliderRow('Echo amount', mix, 'delay', 0, 1, fmt: pct, onChanged: ch),
        SliderRow('Pump (sidechain)', mix, 'sidechain', 0, 1, fmt: pct, onChanged: ch),
        SliderRow('Warmth', mix, 'warmth', 0, 1, fmt: pct, onChanged: ch),
        SliderRow('Air (sparkle)', mix, 'air', 0, 1, fmt: pct, onChanged: ch),
        SliderRow('Stereo width', mix, 'width', 0, 2, fmt: pct, onChanged: ch),
        SliderRow('Phone-speaker bass', mix, 'phone_bass', 0, 1, fmt: pct, onChanged: ch),
        SliderRow('Loudness target', mix, 'loudness', -20, -7, step: 0.5, fmt: (v) => '${v.toStringAsFixed(1)} LUFS', onChanged: ch),
        SelectRow('Vinyl crackle', st.sub('texture'), 'sound', SelectRow.of(snd('texture_sounds')), onChanged: ch),
        SwitchRow('Risers before hooks', st.sub('fx'), 'risers', onChanged: ch),
        SwitchRow('Crashes on new parts', st.sub('fx'), 'impacts', onChanged: ch),
      ]),

      // ------------------------------------------------ save/load
      SectionCard(title: 'Save & load', children: [
        const Note('Save your sound as a file to load later or share with a friend.'),
        Wrap(spacing: 8, children: [
          OutlinedButton.icon(
            icon: const Icon(Icons.save_alt),
            label: const Text('Save settings'),
            onPressed: () async => shareFiles([await st.exportSettings()]),
          ),
          OutlinedButton.icon(
            icon: const Icon(Icons.file_open_outlined),
            label: const Text('Load settings'),
            onPressed: () async {
              final f = await FilePicker.pickFile(type: FileType.custom, allowedExtensions: ['json']);
              final p = f?.path;
              if (p != null) await st.importSettings(p);
            },
          ),
        ]),
        Note('Engine ${st.engine.version}'),
      ]),
    ]);
  }
}

class _DrumLane extends StatelessWidget {
  final AppState st;
  final String name;
  const _DrumLane(this.st, this.name);

  void _settings(BuildContext context) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: kCard,
      builder: (ctx) => StatefulBuilder(builder: (ctx, setSheet) {
        final c = (st.sub('drums')[name] as Map).cast<String, dynamic>();
        void ch() {
          st.changed();
          setSheet(() {});
        }

        final sounds = (st.options['sounds'] as Map).cast<String, dynamic>();
        final soundKey = {'kick': 'kick_sounds', 'snare': 'snare_sounds', 'perc': 'perc_sounds'}[name];
        return Padding(
          padding: EdgeInsets.fromLTRB(16, 16, 16, 16 + MediaQuery.of(ctx).viewInsets.bottom),
          child: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              Text(_labels[name] ?? name, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
              if (soundKey != null) SelectRow('Sound', c, 'sound', SelectRow.of(sounds[soundKey] as List), onChanged: ch),
              SliderRow('Volume', c, 'volume', -30, 6, step: 1, fmt: dB, onChanged: ch),
              SliderRow('Tune', c, 'tune', -12, 12, step: 1, fmt: semis, onChanged: ch),
              SliderRow('Length', c, 'decay', 0.25, 3, fmt: (v) => '${v.toStringAsFixed(2)}×', onChanged: ch),
              SliderRow('Pan (left / right)', c, 'pan', -1, 1, fmt: (v) => v.toStringAsFixed(2), onChanged: ch),
              SliderRow('Reverb', c, 'reverb', 0, 1, fmt: pct, onChanged: ch),
              if (c.containsKey('fills')) SwitchRow('Fills at the end of parts', c, 'fills', onChanged: ch),
              if (c.containsKey('rolls')) SwitchRow('Trap hat rolls', c, 'rolls', onChanged: ch),
            ]),
          ),
        );
      }),
    );
  }

  @override
  Widget build(BuildContext context) {
    final c = (st.sub('drums')[name] as Map).cast<String, dynamic>();
    final muted = c['mute'] == true;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(children: [
        SizedBox(
          width: 70,
          child: InkWell(
            onTap: () => _settings(context),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(_labels[name] ?? name, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
              GestureDetector(
                onTap: () {
                  c['mute'] = !muted;
                  st.changed();
                },
                child: Text(muted ? 'muted' : 'mute', style: TextStyle(fontSize: 11, color: muted ? kAccent2 : kDim)),
              ),
            ]),
          ),
        ),
        Expanded(child: StepGrid(c, 'pattern', const ['.', 'x', 'o'], onChanged: st.changed, dimmed: muted)),
      ]),
    );
  }
}

class _Progression extends StatefulWidget {
  final AppState st;
  const _Progression(this.st);
  @override
  State<_Progression> createState() => _ProgressionState();
}

class _ProgressionState extends State<_Progression> {
  late final TextEditingController _c = TextEditingController(text: _text());
  String _text() => (widget.st.s['progression'] as List).map((e) => '${(e as num).round()}').join(' ');

  @override
  void didUpdateWidget(_Progression old) {
    super.didUpdateWidget(old);
    final t = _text();
    if (_c.text.trim() != t && !FocusScope.of(context).hasFocus) _c.text = t;
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  void _set(String t) {
    final p = t.split(RegExp(r'[\s,\-]+')).map(int.tryParse).whereType<int>().where((n) => n >= 1 && n <= 7).take(8).toList();
    if (p.isEmpty) return;
    widget.st.s['progression'] = p;
    widget.st.changed();
  }

  @override
  Widget build(BuildContext context) {
    final progs = (widget.st.options['progressions'] as Map).cast<String, dynamic>();
    final cur = _text();
    final match = progs.entries.where((e) => (e.value as List).join(' ') == cur).map((e) => e.key).firstOrNull;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Padding(
        padding: const EdgeInsets.only(top: 8),
        child: DropdownButtonFormField<String>(
          key: ValueKey('prog=$match'),
          initialValue: match,
          isExpanded: true,
          hint: const Text('Choose a progression…'),
          decoration: const InputDecoration(labelText: 'Progression', border: OutlineInputBorder(), isDense: true),
          items: progs.keys.map((k) => DropdownMenuItem(value: k, child: Text(k))).toList(),
          onChanged: (k) {
            if (k == null) return;
            final t = (progs[k] as List).join(' ');
            _c.text = t;
            _set(t);
          },
        ),
      ),
      Padding(
        padding: const EdgeInsets.only(top: 10),
        child: TextField(
          controller: _c,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(
              labelText: 'Or type your own (numbers 1–7)', border: OutlineInputBorder(), isDense: true),
          onSubmitted: _set,
          onChanged: _set,
        ),
      ),
    ]);
  }
}

class _Structure extends StatelessWidget {
  final AppState st;
  const _Structure(this.st);

  @override
  Widget build(BuildContext context) {
    final arr = st.s['arrangement'] as List;
    final types = (st.options['section_types'] as List).cast<String>();
    final tracks = (st.options['tracks'] as List).cast<String>();
    final secs = (st.s['sections'] as Map).cast<String, dynamic>();
    void move(int i, int d) {
      final j = i + d;
      if (j < 0 || j >= arr.length) return;
      final t = arr[i];
      arr[i] = arr[j];
      arr[j] = t;
      st.changed();
    }

    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      ...List.generate(arr.length, (i) {
        final item = arr[i] as List;
        return Padding(
          padding: const EdgeInsets.symmetric(vertical: 4),
          child: Row(children: [
            Expanded(
              flex: 3,
              child: DropdownButton<String>(
                value: types.contains(item[0]) ? '${item[0]}' : types.first,
                isExpanded: true,
                items: types.map((t) => DropdownMenuItem(value: t, child: Text(t))).toList(),
                onChanged: (v) {
                  item[0] = v;
                  st.changed();
                },
              ),
            ),
            IconButton(
                icon: const Icon(Icons.remove),
                onPressed: () {
                  item[1] = ((item[1] as num).toInt() - 1).clamp(1, 32);
                  st.changed();
                }),
            Text('${(item[1] as num).toInt()} bars'),
            IconButton(
                icon: const Icon(Icons.add),
                onPressed: () {
                  item[1] = ((item[1] as num).toInt() + 1).clamp(1, 32);
                  st.changed();
                }),
            IconButton(icon: const Icon(Icons.arrow_upward, size: 18), onPressed: () => move(i, -1)),
            IconButton(
                icon: const Icon(Icons.close, size: 18),
                onPressed: () {
                  if (arr.length > 1) arr.removeAt(i);
                  st.changed();
                }),
          ]),
        );
      }),
      Align(
        alignment: Alignment.centerLeft,
        child: TextButton.icon(
            onPressed: () {
              arr.add(['verse', 8]);
              st.changed();
            },
            icon: const Icon(Icons.add),
            label: const Text('Add part')),
      ),
      const Note('What plays in each kind of part:'),
      SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: DataTable(
          columnSpacing: 14,
          headingRowHeight: 32,
          dataRowMinHeight: 32,
          dataRowMaxHeight: 36,
          columns: [const DataColumn(label: Text('')), ...types.map((t) => DataColumn(label: Text(t)))],
          rows: tracks
              .map((tr) => DataRow(cells: [
                    DataCell(Text(_labels[tr] ?? tr)),
                    ...types.map((sec) {
                      final list = ((secs[sec] as List?) ?? []).map((e) => '$e').toList();
                      return DataCell(Checkbox(
                        value: list.contains(tr),
                        onChanged: (v) {
                          if (v == true) {
                            list.add(tr);
                          } else {
                            list.remove(tr);
                          }
                          secs[sec] = list.toSet().toList();
                          st.changed();
                        },
                      ));
                    }),
                  ]))
              .toList(),
        ),
      ),
    ]);
  }
}

