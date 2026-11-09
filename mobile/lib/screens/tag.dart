import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:record/record.dart';
import 'package:share_plus/share_plus.dart';

import '../player.dart';
import '../state.dart';
import '../widgets.dart';

class TagScreen extends StatefulWidget {
  final AppState st;
  const TagScreen(this.st, {super.key});

  @override
  State<TagScreen> createState() => _TagScreenState();
}

class _TagScreenState extends State<TagScreen> {
  final AudioRecorder _rec = AudioRecorder();
  bool _recording = false;
  late final TextEditingController _text = TextEditingController(text: '${widget.st.tag['text']}');
  late final TextEditingController _name = TextEditingController(text: '${widget.st.s['producer'] ?? ''}');

  @override
  void dispose() {
    _rec.dispose();
    _text.dispose();
    _name.dispose();
    super.dispose();
  }

  Future<void> _toggleRecord() async {
    final st = widget.st;
    if (_recording) {
      final path = await _rec.stop();
      setState(() => _recording = false);
      if (path != null) {
        st.ownVoicePath = path;
        st.tagStatus = 'Got your voice. Choose a style and press "Make my tag".';
        st.tagChanged();
      }
      return;
    }
    if (!await _rec.hasPermission()) {
      st.tagStatus = 'BeatMaker needs microphone permission to record your tag.';
      st.tagChanged();
      return;
    }
    final path = st.engine.tmpPath('wav');
    await _rec.start(const RecordConfig(encoder: AudioEncoder.wav, sampleRate: 44100, numChannels: 1), path: path);
    setState(() => _recording = true);
  }

  Future<void> _upload() async {
    final res = await FilePicker.platform.pickFiles(
        type: FileType.custom, allowedExtensions: ['mp3', 'wav', 'm4a', 'aac', 'ogg', 'opus', 'mp4', 'mov', '3gp', 'webm']);
    final f = res?.files.single;
    if (f?.path == null) return;
    widget.st.ownVoicePath = f!.path;
    widget.st.tagChanged();
  }

  @override
  Widget build(BuildContext context) {
    final st = widget.st;
    final t = st.tag;
    final styles = ((st.options['tag_styles'] as Map?) ?? {}).cast<String, dynamic>();
    final tagCfg = st.sub('tag');
    return ListView(padding: const EdgeInsets.all(14), children: [
      SectionCard(title: 'Producer tag', collapsible: false, children: [
        const Note('Your signature at the start of every beat, like the big producers.'),
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
          decoration: const InputDecoration(labelText: 'Tag words', hintText: 'e.g. Ke Bruce!', border: OutlineInputBorder(), isDense: true),
          onChanged: (v) {
            t['text'] = v;
            st.tagChanged();
          },
        ),
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(onPressed: st.suggestIdeas, icon: const Icon(Icons.lightbulb_outline), label: const Text('Give me ideas')),
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
                        t['style'] = i['style'];
                        _text.text = '${i['text']}';
                        st.tagChanged();
                      },
                    ))
                .toList(),
          ),
        const SizedBox(height: 8),
        if (st.voices.isNotEmpty)
          SelectRow('Voice', t, 'voice', {for (final v in st.voices) v.key: v.label}, onChanged: st.tagChanged)
        else
          const Note('No built-in voice found on this device. Record or upload your own voice below.'),
        const Padding(
          padding: EdgeInsets.only(top: 12, bottom: 4),
          child: Text('…or use your own voice (best for a real signature):', style: TextStyle(color: kDim, fontSize: 13)),
        ),
        Wrap(spacing: 8, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
          FilledButton.icon(
            style: _recording ? FilledButton.styleFrom(backgroundColor: kAccent2) : null,
            onPressed: _toggleRecord,
            icon: Icon(_recording ? Icons.stop : Icons.mic),
            label: Text(_recording ? 'Stop' : 'Record'),
          ),
          OutlinedButton.icon(onPressed: _upload, icon: const Icon(Icons.upload_file), label: const Text('Upload voice')),
          if (st.ownVoicePath != null)
            InputChip(
              label: const Text('Using your voice'),
              onDeleted: () {
                st.ownVoicePath = null;
                st.tagChanged();
              },
            ),
        ]),
        SelectRow('Style', t, 'style', styles.map((k, v) => MapEntry(k, '$v'.split(':').first)), onChanged: st.tagChanged),
        if (styles[t['style']] != null) Note('${styles[t['style']]}'),
        SliderRow('Voice pitch', t, 'pitch', -7, 7, step: 1, fmt: semis, onChanged: st.tagChanged),
        SwitchRow('Reverse swell into the voice', t, 'swell', onChanged: st.tagChanged),
        SwitchRow('Impact (boom + crash)', t, 'impact', onChanged: st.tagChanged),
        SwitchRow('Riser before', t, 'riser', onChanged: st.tagChanged),
        BigButton('Make my tag', busy: st.tagBusy, onPressed: st.makeTag),
        if (st.tagStatus.isNotEmpty) Note(st.tagStatus, color: kAccent),
      ]),
      if (st.lastTag != null && File('${st.lastTag!['wav']}').existsSync())
        SectionCard(title: 'Your tag', collapsible: false, children: [
          PlayerBar(path: '${st.lastTag!['wav']}'),
          Row(children: [
            Expanded(
              child: SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Put this tag on my beats'),
                value: tagCfg['id'] == st.lastTag!['id'],
                onChanged: (v) {
                  tagCfg['id'] = v ? st.lastTag!['id'] : null;
                  st.changed();
                },
              ),
            ),
            IconButton(
              icon: const Icon(Icons.share),
              onPressed: () => Share.shareXFiles([XFile('${st.lastTag!['wav']}')], text: 'My producer tag'),
            ),
          ]),
          SelectRow('Where', tagCfg, 'position',
              const {'start': 'At the start', 'start+hooks': 'Start + before each hook', 'every8': 'Every 8 bars'},
              onChanged: st.changed),
          SliderRow('Tag volume', tagCfg, 'volume', -20, 6, step: 1, fmt: dB, onChanged: st.changed),
          SliderRow('Duck the beat under the tag', tagCfg, 'duck', 0, 1, fmt: pct, onChanged: st.changed),
        ]),
    ]);
  }
}
