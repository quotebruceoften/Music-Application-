import 'dart:async';
import 'dart:io';
import 'dart:isolate';
import 'dart:math' as math;
import 'dart:typed_data';

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
  List<double>? _peaks; // the track's waveform

  @override
  void initState() {
    super.initState();
    // keep the track loaded when it ends (the default releases it), so it rewinds and replays
    _p.setReleaseMode(ReleaseMode.stop);
    _subs.add(_p.onPositionChanged.listen((d) {
      if (mounted && _playing) setState(() => _pos = d); // ignore late ticks after it stops
    }));
    _subs.add(_p.onDurationChanged.listen((d) {
      if (mounted) setState(() => _dur = d);
    }));
    _subs.add(_p.onPlayerStateChanged.listen((s) {
      if (mounted) setState(() => _playing = s == PlayerState.playing);
    }));
    _subs.add(_p.onPlayerComplete.listen((_) {
      if (mounted) {
        setState(() {
          _playing = false;
          _pos = Duration.zero;
        });
      }
    }));
    _load();
  }

  Future<void> _load() async {
    final path = widget.path;
    wavPeaks(path).then((p) {
      if (mounted && widget.path == path) setState(() => _peaks = p);
    });
    try {
      await _p.setSource(DeviceFileSource(widget.path));
      final d = await _p.getDuration(); // show the length before playing
      if (mounted && d != null) setState(() => _dur = d);
      if (widget.autoplay) await _p.resume();
    } catch (_) {
      // a missing or unreadable file: leave the bar at 0:00 rather than crash
    }
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
    final frac = (_pos.inMilliseconds / max).clamp(0.0, 1.0);
    void seekTo(double f) {
      final d = Duration(milliseconds: (f.clamp(0.0, 1.0) * max).round());
      setState(() => _pos = d);
      _p.seek(d);
    }

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(children: [
        // glowing gradient play button
        GestureDetector(
          onTap: () => _playing ? _p.pause() : _p.resume(),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 220),
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: kGrad,
              boxShadow: [BoxShadow(color: const Color(0xFF8B5CF6).withValues(alpha: _playing ? 0.75 : 0.4), blurRadius: _playing ? 22 : 12)],
            ),
            child: Icon(_playing ? Icons.pause_rounded : Icons.play_arrow_rounded, color: Colors.white, size: 28),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _peaks != null && _peaks!.isNotEmpty
              ? LayoutBuilder(builder: (context, box) {
                  return GestureDetector(
                    behavior: HitTestBehavior.opaque,
                    onTapDown: (d) => seekTo(d.localPosition.dx / box.maxWidth),
                    onHorizontalDragUpdate: (d) => seekTo(d.localPosition.dx / box.maxWidth),
                    child: SizedBox(
                      height: 44,
                      child: CustomPaint(painter: _WavePainter(_peaks!, frac), size: Size(box.maxWidth, 44)),
                    ),
                  );
                })
              : Slider(value: frac * max, max: max, onChanged: (v) => seekTo(v / max)),
        ),
        const SizedBox(width: 10),
        Column(crossAxisAlignment: CrossAxisAlignment.end, mainAxisSize: MainAxisSize.min, children: [
          Text(_t(_pos),
              style: const TextStyle(color: kText, fontSize: 13, fontWeight: FontWeight.w600, fontFeatures: [FontFeature.tabularFigures()])),
          Text(_t(_dur), style: const TextStyle(color: kDim, fontSize: 11, fontFeatures: [FontFeature.tabularFigures()])),
        ]),
      ]),
    );
  }
}

/// Draws the track's waveform as rounded bars; the played part lights up in the gradient.
class _WavePainter extends CustomPainter {
  final List<double> peaks;
  final double progress;
  _WavePainter(this.peaks, this.progress);

  @override
  void paint(Canvas canvas, Size size) {
    final n = peaks.length;
    final slot = size.width / n;
    final barW = math.max(1.5, slot * 0.58);
    final mid = size.height / 2;
    final played = Paint()..shader = kGrad.createShader(Offset.zero & size);
    final rest = Paint()..color = const Color(0xFF2E2E52);
    final cut = size.width * progress;
    for (var i = 0; i < n; i++) {
      final x = i * slot + (slot - barW) / 2;
      final h = math.max(3.0, peaks[i] * size.height * 0.92);
      final r = RRect.fromRectAndRadius(Rect.fromLTWH(x, mid - h / 2, barW, h), Radius.circular(barW));
      canvas.drawRRect(r, x + barW / 2 <= cut ? played : rest);
    }
    // playhead
    if (progress > 0 && progress < 1) {
      canvas.drawRect(Rect.fromLTWH(cut - 1, 2, 2, size.height - 4), Paint()..color = Colors.white.withValues(alpha: 0.85));
    }
  }

  @override
  bool shouldRepaint(covariant _WavePainter old) => old.progress != progress || old.peaks != peaks;
}

/// Loudness outline of a WAV file in [n] slices (0..1), read in a background isolate.
/// Only small windows are read, so even a 10-minute file is quick. Not a WAV: empty list.
Future<List<double>> wavPeaks(String path, {int n = 72}) => Isolate.run(() {
      final f = File(path).openSync();
      try {
        final head = f.readSync(math.min(f.lengthSync(), 1 << 16));
        if (head.length < 44 || String.fromCharCodes(head.sublist(0, 4)) != 'RIFF') return <double>[];
        final bd = ByteData.sublistView(head);
        var pos = 12, fmt = 1, ch = 2, bits = 16, dataOff = -1, dataLen = 0;
        while (pos + 8 <= head.length) {
          final id = String.fromCharCodes(head.sublist(pos, pos + 4));
          final size = bd.getUint32(pos + 4, Endian.little);
          if (id == 'fmt ') {
            fmt = bd.getUint16(pos + 8, Endian.little);
            ch = bd.getUint16(pos + 10, Endian.little);
            bits = bd.getUint16(pos + 22, Endian.little);
            if (fmt == 0xFFFE && size >= 26) fmt = bd.getUint16(pos + 32, Endian.little);
          } else if (id == 'data') {
            dataOff = pos + 8;
            dataLen = (size == 0 || size == 0xFFFFFFFF) ? f.lengthSync() - dataOff : size;
            break;
          }
          pos += 8 + size + (size & 1);
        }
        if (dataOff < 0 || (bits != 16 && bits != 32 && bits != 24)) return <double>[];
        final bps = bits ~/ 8;
        final frame = bps * ch;
        final frames = dataLen ~/ frame;
        if (frames <= 0) return <double>[];
        const window = 2048; // frames read per slice
        final out = List<double>.filled(n, 0);
        for (var i = 0; i < n; i++) {
          final start = (frames * i / n).floor();
          final count = math.min(window, frames - start);
          if (count <= 0) continue;
          f.setPositionSync(dataOff + start * frame);
          final b = f.readSync(count * frame);
          final v = ByteData.sublistView(b);
          var peak = 0.0;
          for (var j = 0; j + bps <= b.length; j += bps * 3) {
            double x;
            if (bits == 16) {
              x = v.getInt16(j, Endian.little) / 32768;
            } else if (bits == 32 && fmt == 3) {
              x = v.getFloat32(j, Endian.little);
            } else if (bits == 32) {
              x = v.getInt32(j, Endian.little) / 2147483648;
            } else {
              final raw = b[j] | (b[j + 1] << 8) | (b[j + 2] << 16);
              x = (raw & 0x800000 != 0 ? raw - 0x1000000 : raw) / 8388608;
            }
            if (x.abs() > peak) peak = x.abs();
          }
          out[i] = peak;
        }
        final top = out.fold<double>(0, math.max);
        return top > 0 ? [for (final x in out) math.sqrt(x / top)] : out;
      } catch (_) {
        return <double>[];
      } finally {
        f.closeSync();
      }
    });
