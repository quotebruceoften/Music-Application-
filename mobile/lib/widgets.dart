
import 'package:flutter/material.dart';
import 'package:share_plus/share_plus.dart';

import 'engine.dart';

// ---------------------------------------------------------------- design system
// Deep space background, frosted-glass surfaces, and a cyan → violet → magenta signature.
const kAccent = Color(0xFF2EE6FF); // cyan: highlights, values, focus
const kAccent2 = Color(0xFFFF4D8D); // hot pink: warnings, stop, delete
const kSoft = Color(0xFF8B5CF6); // violet
const kMagenta = Color(0xFFE649D8);
const kCard = Color(0xB3111120); // translucent glass
const kBg = Color(0xFF05050B);
const kLine = Color(0xFF26263F);
const kDim = Color(0xFF8E8FAA);
const kText = Color(0xFFEDEDF7);
const kFont = 'SpaceGrotesk';

/// Page padding: room at the bottom so the last card scrolls clear of the floating bar.
const kPagePadding = EdgeInsets.fromLTRB(14, 6, 14, 112);

const kGrad = LinearGradient(colors: [kAccent, kSoft, kMagenta]);
const kGradSoft = LinearGradient(
    begin: Alignment.topLeft, end: Alignment.bottomRight, colors: [Color(0x332EE6FF), Color(0x228B5CF6), Color(0x11E649D8)]);

/// Text painted with the signature gradient.
class GradientText extends StatelessWidget {
  final String text;
  final TextStyle style;
  final Gradient gradient;
  const GradientText(this.text, {super.key, required this.style, this.gradient = kGrad});
  @override
  Widget build(BuildContext context) => ShaderMask(
        blendMode: BlendMode.srcIn,
        shaderCallback: (r) => gradient.createShader(Rect.fromLTWH(0, 0, r.width, r.height)),
        child: Text(text, style: style),
      );
}

/// The app's backdrop: soft colour glows and a faint grid over deep black.
class AuroraBackground extends StatelessWidget {
  final Widget child;
  const AuroraBackground({super.key, required this.child});
  @override
  Widget build(BuildContext context) => Stack(children: [
        const Positioned.fill(child: RepaintBoundary(child: CustomPaint(painter: _AuroraPainter()))),
        child,
      ]);
}

class _AuroraPainter extends CustomPainter {
  const _AuroraPainter();
  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(Offset.zero & size, Paint()..color = kBg);
    void glow(Offset c, double r, Color color) {
      canvas.drawCircle(
          c,
          r,
          Paint()
            ..shader = RadialGradient(colors: [color, color.withValues(alpha: 0)])
                .createShader(Rect.fromCircle(center: c, radius: r)));
    }

    final w = size.width, h = size.height;
    glow(Offset(w * 0.05, h * 0.02), w * 0.95, const Color(0x388B5CF6));
    glow(Offset(w * 1.0, h * 0.45), w * 0.85, const Color(0x222EE6FF));
    glow(Offset(w * 0.2, h * 1.0), w * 0.9, const Color(0x1FE649D8));
    // faint grid, fading towards the bottom
    final grid = Paint()..strokeWidth = 1;
    const step = 36.0;
    for (double y = 0; y < h; y += step) {
      grid.color = Color.fromRGBO(140, 150, 255, 0.045 * (1 - y / h));
      canvas.drawLine(Offset(0, y), Offset(w, y), grid);
    }
    for (double x = 0; x < w; x += step) {
      grid.shader = LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [const Color.fromRGBO(140, 150, 255, 0.045), const Color.fromRGBO(140, 150, 255, 0)])
          .createShader(Rect.fromLTWH(x, 0, 1, h));
      canvas.drawLine(Offset(x, 0), Offset(x, h), grid);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter old) => false;
}

/// A slim gradient progress bar with a soft glow; null value = indeterminate shimmer.
class GlowProgress extends StatefulWidget {
  final double? value;
  final double height;
  const GlowProgress({super.key, this.value, this.height = 8});
  @override
  State<GlowProgress> createState() => _GlowProgressState();
}

class _GlowProgressState extends State<GlowProgress> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1400))..repeat();
  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => LayoutBuilder(builder: (context, box) {
        return AnimatedBuilder(
          animation: _c,
          builder: (context, _) {
            final v = widget.value;
            final w = box.maxWidth;
            final fill = v == null ? w * 0.3 : (w * v.clamp(0.0, 1.0));
            final left = v == null ? (w + fill) * _c.value - fill : 0.0;
            return Container(
              height: widget.height,
              decoration: BoxDecoration(color: const Color(0xFF181830), borderRadius: BorderRadius.circular(99)),
              clipBehavior: Clip.antiAlias,
              child: Stack(children: [
                AnimatedPositioned(
                  duration: const Duration(milliseconds: 380),
                  curve: Curves.easeOut,
                  left: left,
                  top: 0,
                  bottom: 0,
                  width: fill,
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: kGrad,
                      borderRadius: BorderRadius.circular(99),
                      boxShadow: const [BoxShadow(color: Color(0x888B5CF6), blurRadius: 12)],
                    ),
                    // a light sweeping across the bar so it feels alive
                    child: v == null
                        ? null
                        : FractionallySizedBox(
                            alignment: Alignment(-1 + 2 * _c.value, 0),
                            widthFactor: 0.25,
                            child: const DecoratedBox(
                                decoration: BoxDecoration(
                                    gradient: LinearGradient(
                                        colors: [Color(0x00FFFFFF), Color(0x55FFFFFF), Color(0x00FFFFFF)]))),
                          ),
                  ),
                ),
              ]),
            );
          },
        );
      });
}

/// Slider track painted with the signature gradient.
class GradientTrackShape extends RoundedRectSliderTrackShape {
  const GradientTrackShape();
  @override
  void paint(PaintingContext context, Offset offset,
      {required RenderBox parentBox,
      required SliderThemeData sliderTheme,
      required Animation<double> enableAnimation,
      required TextDirection textDirection,
      required Offset thumbCenter,
      Offset? secondaryOffset,
      bool isDiscrete = false,
      bool isEnabled = false,
      double additionalActiveTrackHeight = 2}) {
    final rect = getPreferredRect(parentBox: parentBox, offset: offset, sliderTheme: sliderTheme, isEnabled: isEnabled, isDiscrete: isDiscrete);
    final r = Radius.circular(rect.height / 2);
    context.canvas.drawRRect(RRect.fromRectAndRadius(rect, r), Paint()..color = const Color(0xFF1D1D36));
    final active = Rect.fromLTRB(rect.left, rect.top - 0.5, thumbCenter.dx, rect.bottom + 0.5);
    if (active.width > 0) {
      context.canvas.drawRRect(RRect.fromRectAndRadius(active, r),
          Paint()..shader = kGrad.createShader(Rect.fromLTWH(rect.left, rect.top, rect.width, rect.height)));
    }
  }
}

/// A bright slider thumb with a coloured halo.
class GlowThumbShape extends SliderComponentShape {
  const GlowThumbShape();
  @override
  Size getPreferredSize(bool isEnabled, bool isDiscrete) => const Size(22, 22);
  @override
  void paint(PaintingContext context, Offset center,
      {required Animation<double> activationAnimation,
      required Animation<double> enableAnimation,
      required bool isDiscrete,
      required TextPainter labelPainter,
      required RenderBox parentBox,
      required SliderThemeData sliderTheme,
      required TextDirection textDirection,
      required double value,
      required double textScaleFactor,
      required Size sizeWithOverflow}) {
    final c = context.canvas;
    final grow = 1 + activationAnimation.value * 0.25;
    c.drawCircle(center, 14 * grow, Paint()..color = const Color(0x332EE6FF)..maskFilter = const MaskFilter.blur(BlurStyle.normal, 6));
    c.drawCircle(center, 8.5 * grow, Paint()..color = Colors.white);
    c.drawCircle(center, 8.5 * grow, Paint()..style = PaintingStyle.stroke..strokeWidth = 2..shader = kGrad.createShader(Rect.fromCircle(center: center, radius: 9)));
  }
}

double numOf(dynamic v, [double d = 0]) => v is num ? v.toDouble() : double.tryParse('$v') ?? d;
/// Open the system share sheet for files (one place, so a share_plus API change is one edit).
Future<void> shareFiles(List<String> paths, {String? text}) async {
  await SharePlus.instance.share(ShareParams(files: [for (final p in paths) XFile(p)], text: text));
}

/// A safe file name for a beat: its name if it has one, else style-tempo-key.
String fileStamp(Map<String, dynamic> s) {
  final title = '${s['title'] ?? ''}'.trim().replaceAll(RegExp(r'[^A-Za-z0-9 _-]'), '').replaceAll(RegExp(r'\s+'), '-');
  if (title.isNotEmpty) return title.length > 50 ? title.substring(0, 50) : title;
  return 'beat-${s['genre']}-${(s['bpm'] as num? ?? 0).round()}bpm-${'${s['key']}'.replaceAll('#', 's')}';
}

String pct(double v) => '${(v * 100).round()}%';
String dB(double v) => '${v > 0 ? '+' : ''}${v.round()} dB';
String semis(double v) => '${v > 0 ? '+' : ''}${v.round()} st';

/// A frosted-glass panel with a glowing gradient edge.
class SectionCard extends StatelessWidget {
  final String title;
  final String? subtitle;
  final List<Widget> children;
  final bool initiallyExpanded;
  final bool collapsible;
  const SectionCard(
      {super.key, required this.title, this.subtitle, required this.children, this.initiallyExpanded = false, this.collapsible = true});

  Widget _title({double size = 17}) => Row(children: [
        Container(
          width: 4,
          height: size + 2,
          margin: const EdgeInsets.only(right: 10),
          decoration: BoxDecoration(
            gradient: const LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [kAccent, kMagenta]),
            borderRadius: BorderRadius.circular(4),
            boxShadow: const [BoxShadow(color: Color(0x662EE6FF), blurRadius: 8)],
          ),
        ),
        Expanded(
          child: Text(title,
              style: TextStyle(fontWeight: FontWeight.w700, fontSize: size, letterSpacing: -0.2, color: kText)),
        ),
      ]);

  @override
  Widget build(BuildContext context) {
    final body = Padding(
      padding: const EdgeInsets.fromLTRB(18, 0, 18, 18),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children),
    );
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      // the 1px gradient edge
      padding: const EdgeInsets.all(1),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(22),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0x552EE6FF), Color(0x1A8B5CF6), Color(0x10FFFFFF), Color(0x33E649D8)],
        ),
        boxShadow: const [BoxShadow(color: Color(0x40000000), blurRadius: 24, offset: Offset(0, 10))],
      ),
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(21),
          gradient: const LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xE6121226), Color(0xE60B0B18)],
          ),
        ),
        clipBehavior: Clip.antiAlias,
        child: collapsible
            ? Theme(
                data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
                child: ExpansionTile(
                  initiallyExpanded: initiallyExpanded,
                  tilePadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 4),
                  iconColor: kAccent,
                  collapsedIconColor: kDim,
                  title: _title(size: 16),
                  subtitle: subtitle == null
                      ? null
                      : Padding(
                          padding: const EdgeInsets.only(left: 14, top: 2),
                          child: Text(subtitle!, style: const TextStyle(color: kDim, fontSize: 12)),
                        ),
                  children: [body],
                ),
              )
            : Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Padding(padding: const EdgeInsets.fromLTRB(18, 18, 18, 10), child: _title()),
                body,
              ]),
      ),
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
          Expanded(child: Text(label, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: kText))),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
            decoration: BoxDecoration(
              color: const Color(0x142EE6FF),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: const Color(0x332EE6FF)),
            ),
            child: Text(fmt(v),
                style: const TextStyle(
                    color: kAccent, fontSize: 12, fontWeight: FontWeight.w600, fontFeatures: [FontFeature.tabularFigures()])),
          ),
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
        initialValue: cur.isEmpty ? null : cur,
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

  Color? _color(String c) {
    switch (c) {
      case 'x':
        return kAccent;
      case 'o':
        return const Color(0x992EE6FF);
      case '5':
        return kSoft;
      case '^':
        return kMagenta;
      default:
        return null;
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
          final on = _color(c);
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
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 160),
                  margin: const EdgeInsets.all(1.8),
                  decoration: BoxDecoration(
                    color: on ?? (i % 4 == 0 ? const Color(0xFF1C1C36) : const Color(0xFF13132A)),
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: on == null ? (i % 4 == 0 ? const Color(0xFF2E2E55) : kLine) : Colors.transparent),
                    boxShadow: on == null ? null : [BoxShadow(color: on.withValues(alpha: 0.55), blurRadius: 10)],
                  ),
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

/// The main call to action: a glowing gradient pill.
class BigButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final bool busy;
  final IconData? icon;
  const BigButton(this.label, {super.key, this.onPressed, this.busy = false, this.icon = Icons.bolt});

  @override
  Widget build(BuildContext context) {
    final enabled = onPressed != null && !busy;
    return Padding(
      padding: const EdgeInsets.only(top: 16),
      child: AnimatedOpacity(
        duration: const Duration(milliseconds: 200),
        opacity: enabled ? 1 : 0.55,
        child: DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(18),
            boxShadow: enabled
                ? const [
                    BoxShadow(color: Color(0x668B5CF6), blurRadius: 26, offset: Offset(0, 8)),
                    BoxShadow(color: Color(0x332EE6FF), blurRadius: 14, offset: Offset(-6, 0)),
                  ]
                : null,
          ),
          child: Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: enabled ? onPressed : null,
              borderRadius: BorderRadius.circular(18),
              child: Ink(
                padding: const EdgeInsets.symmetric(vertical: 17),
                decoration: BoxDecoration(gradient: kGrad, borderRadius: BorderRadius.circular(18)),
                child: Center(
                  child: busy
                      ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white))
                      : Row(mainAxisSize: MainAxisSize.min, children: [
                          if (icon != null) ...[Icon(icon, color: Colors.white, size: 20), const SizedBox(width: 8)],
                          Text(label,
                              style: const TextStyle(
                                  color: Colors.white, fontSize: 17, fontWeight: FontWeight.w700, letterSpacing: 0.3)),
                        ]),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class Note extends StatelessWidget {
  final String text;
  final Color color;
  const Note(this.text, {super.key, this.color = kDim});
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Text(text, style: TextStyle(color: color, fontSize: 13, height: 1.35)),
      );
}
