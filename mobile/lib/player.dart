import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';

import 'widgets.dart';

/// Simple play/pause + seek bar for a local audio file.
class PlayerBar extends StatefulWidget {
  final String path;
  final bool autoplay;
  const PlayerBar({super.key, required this.path, this.autoplay = false});

  @override
  State<PlayerBar> createState() => _PlayerBarState();
}

class _PlayerBarState extends State<PlayerBar> {
  final AudioPlayer _p = AudioPlayer();
  Duration _pos = Duration.zero, _dur = Duration.zero;
  bool _playing = false;
  final List<StreamSubscription> _subs = [];

  @override
  void initState() {
    super.initState();
    _subs.add(_p.onPositionChanged.listen((d) => setState(() => _pos = d)));
    _subs.add(_p.onDurationChanged.listen((d) => setState(() => _dur = d)));
    _subs.add(_p.onPlayerStateChanged.listen((s) => setState(() => _playing = s == PlayerState.playing)));
    _subs.add(_p.onPlayerComplete.listen((_) => setState(() => _pos = Duration.zero)));
    _load();
  }

  Future<void> _load() async {
    await _p.setSource(DeviceFileSource(widget.path));
    if (widget.autoplay) await _p.resume();
  }

  @override
  void didUpdateWidget(PlayerBar old) {
    super.didUpdateWidget(old);
    if (old.path != widget.path) {
      _p.stop();
      _pos = Duration.zero;
      _load();
    }
  }

  @override
  void dispose() {
    for (final s in _subs) {
      s.cancel();
    }
    _p.dispose();
    super.dispose();
  }

  String _t(Duration d) => '${d.inMinutes}:${(d.inSeconds % 60).toString().padLeft(2, '0')}';

  @override
  Widget build(BuildContext context) {
    final max = _dur.inMilliseconds > 0 ? _dur.inMilliseconds.toDouble() : 1.0;
    return Row(children: [
      IconButton.filled(
        style: IconButton.styleFrom(backgroundColor: kAccent, foregroundColor: Colors.black),
        icon: Icon(_playing ? Icons.pause : Icons.play_arrow),
        onPressed: () => _playing ? _p.pause() : _p.resume(),
      ),
      Expanded(
        child: Slider(
          value: _pos.inMilliseconds.clamp(0, max.toInt()).toDouble(),
          max: max,
          onChanged: (v) => _p.seek(Duration(milliseconds: v.toInt())),
        ),
      ),
      Text('${_t(_pos)} / ${_t(_dur)}', style: const TextStyle(color: kDim, fontSize: 12)),
    ]);
  }
}
