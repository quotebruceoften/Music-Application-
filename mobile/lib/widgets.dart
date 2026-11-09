import 'dart:ui' show FontFeature;

import 'package:flutter/material.dart';

import 'engine.dart';

const kAccent = Color(0xFFFFB547);
const kAccent2 = Color(0xFFFF6B4A);
const kSoft = Color(0xFF6A5CFF);
const kCard = Color(0xFF1A1820);
const kBg = Color(0xFF0F0E13);
const kLine = Color(0xFF2C2934);
const kDim = Color(0xFF9A96A6);

double numOf(dynamic v, [double d = 0]) => v is num ? v.toDouble() : double.tryParse('$v') ?? d;
String pct(double v) => '${(v * 100).round()}%';
String dB(double v) => '${v > 0 ? '+' : ''}${v.round()} dB';
String semis(double v) => '${v > 0 ? '+' : ''}${v.round()} st';

class SectionCard extends StatelessWidget {
  final String title;
  final String? subtitle;
  final List<Widget> children;
  final bool initiallyExpanded;
  final bool collapsible;
  const SectionCard(
      {super.key, required this.title, this.subtitle, required this.children, this.initiallyExpanded = false, this.collapsible = true});

  @override
  Widget build(BuildContext context) {
    final body = Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children),
    );
    return Card(
      color: kCard,
      margin: const EdgeInsets.only(bottom: 12),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14), side: const BorderSide(color: kLine)),
      clipBehavior: Clip.antiAlias,
      child: collapsible
          ? Theme(
              data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
              child: ExpansionTile(
                initiallyExpanded: initiallyExpanded,
                title: Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
                subtitle: subtitle == null ? null : Text(subtitle!, style: const TextStyle(color: kDim, fontSize: 12)),
                children: [body],
              ),
            )
          : Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                child: Text(title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
              ),
              body,
            ]),
    );
  }
}

class SliderRow extends StatelessWidget {
  final String label;
  final J obj;
  final String k;
  final double min, max;
  final double? step;
  final String Function(double) fmt;
  final VoidCallback onChanged;
  const SliderRow(this.label, this.obj, this.k, this.min, this.max,
      {super.key, this.step, required this.fmt, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    final v = numOf(obj[k], min).clamp(min, max).toDouble();
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Padding(
        padding: const EdgeInsets.only(top: 6),
        child: Row(children: [
          Expanded(child: Text(label, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600))),
          Text(fmt(v), style: const TextStyle(color: kAccent, fontSize: 13, fontFeatures: [FontFeature.tabularFigures()])),
        ]),
      ),
      Slider(
        value: v,
        min: min,
        max: max,
        divisions: step == null ? null : ((max - min) / step!).round(),
        onChanged: (x) {
          obj[k] = step != null && step! >= 1 ? x.roundToDouble() : x;
          onChanged();
        },
      ),
    ]);
  }
}

class SelectRow extends StatelessWidget {
  final String label;
  final J obj;
  final String k;
  final Map<String, String> choices;
  final VoidCallback onChanged;
  final dynamic Function(String)? parse;
  const SelectRow(this.label, this.obj, this.k, this.choices, {super.key, required this.onChanged, this.parse});

  static Map<String, String> of(List<dynamic> l) => {for (final x in l) '$x': '$x'};

  @override
  Widget build(BuildContext context) {
    String cur = '${obj[k]}';
    if (cur.endsWith('.0') && !choices.containsKey(cur)) cur = cur.substring(0, cur.length - 2);
    if (!choices.containsKey(cur)) cur = choices.keys.isEmpty ? '' : choices.keys.first;
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: DropdownButtonFormField<String>(
        key: ValueKey('$k=$cur'),
        value: cur.isEmpty ? null : cur,
        isExpanded: true,
        decoration: InputDecoration(labelText: label, border: const OutlineInputBorder(), isDense: true),
        items: choices.entries.map((e) => DropdownMenuItem(value: e.key, child: Text(e.value, overflow: TextOverflow.ellipsis))).toList(),
        onChanged: (v) {
          if (v == null) return;
          obj[k] = parse != null ? parse!(v) : v;
          onChanged();
        },
      ),
    );
  }
}

class SwitchRow extends StatelessWidget {
  final String label;
  final J obj;
  final String k;
  final VoidCallback onChanged;
  const SwitchRow(this.label, this.obj, this.k, {super.key, required this.onChanged});

  @override
  Widget build(BuildContext context) => SwitchListTile(
        contentPadding: EdgeInsets.zero,
        dense: true,
        title: Text(label, style: const TextStyle(fontSize: 14)),
        value: obj[k] == true,
        onChanged: (v) {
          obj[k] = v;
          onChanged();
        },
      );
}

/// 16-step rhythm grid. Tap a square to cycle through [cycle].
class StepGrid extends StatelessWidget {
  final J obj;
  final String k;
  final List<String> cycle;
  final VoidCallback onChanged;
  final bool dimmed;
  const StepGrid(this.obj, this.k, this.cycle, {super.key, required this.onChanged, this.dimmed = false});

  Color _color(String c, int i) {
    switch (c) {
      case 'x':
        return kAccent;
      case 'o':
        return const Color(0xFFA87A33);
      case '5':
        return kSoft;
      case '^':
        return const Color(0xFF45C4A0);
      default:
        return i % 4 == 0 ? const Color(0xFF34303E) : const Color(0xFF2A2732);
    }
  }

  @override
  Widget build(BuildContext context) {
    final pat = ('${obj[k] ?? ''}'.padRight(16, '.')).substring(0, 16).split('');
    return Opacity(
      opacity: dimmed ? 0.35 : 1,
      child: Row(
        children: List.generate(16, (i) {
          final c = pat[i];
          return Expanded(
            child: GestureDetector(
              onTap: () {
                final idx = cycle.indexOf(c);
                pat[i] = cycle[(idx + 1) % cycle.length];
                obj[k] = pat.join();
                onChanged();
              },
              child: AspectRatio(
                aspectRatio: 1,
                child: Container(
                  margin: const EdgeInsets.all(1.5),
                  decoration: BoxDecoration(color: _color(c, i), borderRadius: BorderRadius.circular(4)),
                  alignment: Alignment.center,
                  child: (c == '5' || c == '^')
                      ? Text(c, style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w800, color: Colors.white))
                      : null,
                ),
              ),
            ),
          );
        }),
      ),
    );
  }
}

class BigButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final bool busy;
  const BigButton(this.label, {super.key, this.onPressed, this.busy = false});

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: 14),
        child: Opacity(
          opacity: onPressed == null || busy ? 0.6 : 1,
          child: InkWell(
            onTap: busy ? null : onPressed,
            borderRadius: BorderRadius.circular(12),
            child: Ink(
              padding: const EdgeInsets.symmetric(vertical: 16),
              decoration: BoxDecoration(
                gradient: const LinearGradient(colors: [kAccent, kAccent2]),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Center(
                child: busy
                    ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.5, color: Color(0xFF1A0D00)))
                    : Text(label, style: const TextStyle(color: Color(0xFF1A0D00), fontSize: 17, fontWeight: FontWeight.w800)),
              ),
            ),
          ),
        ),
      );
}

class Note extends StatelessWidget {
  final String text;
  final Color color;
  const Note(this.text, {super.key, this.color = kDim});
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Text(text, style: TextStyle(color: color, fontSize: 13)),
      );
}
