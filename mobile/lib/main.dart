import 'dart:math' as math;
import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';

import 'screens/beats.dart';
import 'screens/create.dart';
import 'screens/inspire.dart';
import 'screens/studio.dart';
import 'screens/tag.dart';
import 'state.dart';
import 'widgets.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(BeatMakerApp(state: AppState()..init()));
}

ThemeData buildTheme() {
  const scheme = ColorScheme.dark(
    primary: kAccent,
    onPrimary: Color(0xFF00141A),
    secondary: kSoft,
    onSecondary: Colors.white,
    tertiary: kMagenta,
    error: kAccent2,
    surface: Color(0xFF0D0D1A),
    onSurface: kText,
    surfaceContainerHighest: Color(0xFF1A1A30),
    outline: kLine,
  );
  final base = ThemeData(useMaterial3: true, brightness: Brightness.dark, colorScheme: scheme, fontFamily: kFont);
  final rounded = RoundedRectangleBorder(borderRadius: BorderRadius.circular(14));
  return base.copyWith(
    scaffoldBackgroundColor: Colors.transparent,
    canvasColor: const Color(0xFF0D0D1A),
    dividerColor: kLine,
    dividerTheme: const DividerThemeData(color: kLine, thickness: 1),
    textTheme: base.textTheme.apply(bodyColor: kText, displayColor: kText),
    appBarTheme: const AppBarTheme(
      backgroundColor: Colors.transparent,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 0,
      foregroundColor: kText,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: const Color(0x0DFFFFFF),
      isDense: true,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      labelStyle: const TextStyle(color: kDim),
      floatingLabelStyle: const TextStyle(color: kAccent),
      hintStyle: const TextStyle(color: Color(0xFF5E5F7A)),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: kLine)),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: kLine)),
      focusedBorder:
          OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: kAccent, width: 1.4)),
    ),
    sliderTheme: const SliderThemeData(
      trackHeight: 5,
      trackShape: GradientTrackShape(),
      thumbShape: GlowThumbShape(),
      overlayColor: Color(0x1A2EE6FF),
      activeTickMarkColor: Colors.transparent,
      inactiveTickMarkColor: Colors.transparent,
    ),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? Colors.white : kDim),
      trackColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? kSoft : const Color(0xFF1D1D36)),
      trackOutlineColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? kSoft : kLine),
    ),
    radioTheme: RadioThemeData(fillColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? kAccent : kDim)),
    checkboxTheme: CheckboxThemeData(fillColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? kAccent : null)),
    chipTheme: ChipThemeData(
      backgroundColor: const Color(0x0AFFFFFF),
      selectedColor: const Color(0x338B5CF6),
      side: const BorderSide(color: kLine),
      shape: const StadiumBorder(),
      labelStyle: const TextStyle(fontFamily: kFont, fontWeight: FontWeight.w600, fontSize: 13),
      checkmarkColor: kAccent,
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: kAccent,
        foregroundColor: const Color(0xFF00141A),
        shape: const StadiumBorder(),
        textStyle: const TextStyle(fontFamily: kFont, fontWeight: FontWeight.w700),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: kText,
        side: const BorderSide(color: Color(0xFF34345A)),
        backgroundColor: const Color(0x08FFFFFF),
        shape: const StadiumBorder(),
        textStyle: const TextStyle(fontFamily: kFont, fontWeight: FontWeight.w600),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 11),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
          foregroundColor: kAccent, textStyle: const TextStyle(fontFamily: kFont, fontWeight: FontWeight.w600)),
    ),
    iconButtonTheme: IconButtonThemeData(style: IconButton.styleFrom(foregroundColor: kText)),
    progressIndicatorTheme: const ProgressIndicatorThemeData(color: kAccent, linearTrackColor: Color(0xFF181830)),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: const Color(0xF2151528),
      contentTextStyle: const TextStyle(fontFamily: kFont, color: kText, fontWeight: FontWeight.w500),
      actionTextColor: kAccent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: const BorderSide(color: Color(0x552EE6FF))),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: const Color(0xFF10101F),
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24), side: const BorderSide(color: kLine)),
      titleTextStyle: const TextStyle(fontFamily: kFont, fontSize: 20, fontWeight: FontWeight.w700, color: kText),
    ),
    popupMenuTheme: PopupMenuThemeData(
      color: const Color(0xFF12122A),
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: const BorderSide(color: kLine)),
    ),
    listTileTheme: ListTileThemeData(shape: rounded, iconColor: kDim),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: Colors.transparent,
      surfaceTintColor: Colors.transparent,
      indicatorColor: const Color(0x338B5CF6),
      indicatorShape: const StadiumBorder(),
      height: 66,
      labelTextStyle: WidgetStateProperty.resolveWith((s) => TextStyle(
            fontFamily: kFont,
            fontSize: 11.5,
            fontWeight: s.contains(WidgetState.selected) ? FontWeight.w700 : FontWeight.w500,
            color: s.contains(WidgetState.selected) ? kText : kDim,
          )),
      iconTheme: WidgetStateProperty.resolveWith(
          (s) => IconThemeData(color: s.contains(WidgetState.selected) ? kAccent : kDim, size: 23)),
    ),
  );
}

class BeatMakerApp extends StatelessWidget {
  final AppState state;
  const BeatMakerApp({super.key, required this.state});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'BeatMaker',
      scaffoldMessengerKey: state.messenger,
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      builder: (context, child) => AuroraBackground(child: child ?? const SizedBox()),
      home: ListenableBuilder(listenable: state, builder: (context, _) => Home(state)),
    );
  }
}

/// The BeatMaker wordmark: "Beat" in white, "Maker" in the signature gradient.
class Wordmark extends StatelessWidget {
  final double size;
  const Wordmark({super.key, this.size = 22});
  @override
  Widget build(BuildContext context) => Row(mainAxisSize: MainAxisSize.min, children: [
        Text('Beat', style: TextStyle(fontSize: size, fontWeight: FontWeight.w700, color: Colors.white, letterSpacing: -0.5)),
        GradientText('Maker', style: TextStyle(fontSize: size, fontWeight: FontWeight.w700, letterSpacing: -0.5)),
      ]);
}

/// First-launch screen: pulsing rings around the logo while the engine starts.
class _Startup extends StatefulWidget {
  final AppState st;
  const _Startup(this.st);
  @override
  State<_Startup> createState() => _StartupState();
}

class _StartupState extends State<_Startup> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(seconds: 3))..repeat();
  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final st = widget.st;
    return Scaffold(
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            SizedBox(
              width: 170,
              height: 170,
              child: AnimatedBuilder(
                animation: _c,
                builder: (context, _) => CustomPaint(
                  painter: _RingsPainter(_c.value, error: st.startupError != null),
                  child: Center(
                    child: Container(
                      width: 74,
                      height: 74,
                      decoration: const BoxDecoration(
                        shape: BoxShape.circle,
                        gradient: kGrad,
                        boxShadow: [BoxShadow(color: Color(0x888B5CF6), blurRadius: 30)],
                      ),
                      child: Icon(st.startupError == null ? Icons.graphic_eq : Icons.priority_high, color: Colors.white, size: 38),
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 18),
            const Wordmark(size: 34),
            const SizedBox(height: 18),
            if (st.startupError == null) ...[
              const SizedBox(width: 180, child: GlowProgress(height: 4)),
              const SizedBox(height: 14),
              Text(st.startupStatus, style: const TextStyle(color: kDim, letterSpacing: 0.3)),
            ] else ...[
              ConstrainedBox(
                constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.4),
                child: SingleChildScrollView(child: SelectableText(st.startupError!, textAlign: TextAlign.center)),
              ),
              const SizedBox(height: 14),
              FilledButton(
                  onPressed: () {
                    st.startupError = null;
                    st.init();
                  },
                  child: const Text('Try again')),
            ],
          ]),
        ),
      ),
    );
  }
}

class _RingsPainter extends CustomPainter {
  final double t;
  final bool error;
  _RingsPainter(this.t, {this.error = false});
  @override
  void paint(Canvas canvas, Size size) {
    final c = size.center(Offset.zero);
    for (var i = 0; i < 3; i++) {
      final p = (t + i / 3) % 1.0;
      final r = 40 + p * 45;
      final color = error ? kAccent2 : Color.lerp(kAccent, kMagenta, p)!;
      canvas.drawCircle(
          c,
          r,
          Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = 2
            ..color = color.withValues(alpha: (1 - p) * 0.7));
    }
    // a rotating arc for a bit of motion
    final rect = Rect.fromCircle(center: c, radius: 52);
    canvas.drawArc(
        rect,
        t * 2 * math.pi,
        1.4,
        false,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 3
          ..strokeCap = StrokeCap.round
          ..shader = SweepGradient(colors: const [Color(0x002EE6FF), kAccent], transform: GradientRotation(t * 2 * math.pi))
              .createShader(rect));
  }

  @override
  bool shouldRepaint(covariant _RingsPainter old) => old.t != t || old.error != error;
}

class Home extends StatefulWidget {
  final AppState st;
  const Home(this.st, {super.key});
  @override
  State<Home> createState() => _HomeState();
}

class _HomeState extends State<Home> {
  @override
  Widget build(BuildContext context) {
    final st = widget.st;
    if (!st.ready) return _Startup(st);

    final pages = [
      CreateScreen(st),
      BeatsScreen(st),
      InspireScreen(st, onMade: () => st.goTab(0)),
      TagScreen(st),
      StudioScreen(st),
    ];
    final tab = st.tab.clamp(0, pages.length - 1);
    return Scaffold(
      extendBody: true, // content scrolls under the floating bar
      appBar: AppBar(
        titleSpacing: 18,
        title: const Wordmark(),
        actions: [
          if (st.canUndo && (tab == 0 || tab == 4))
            IconButton(
              tooltip: 'Undo: ${st.undoLabel}',
              icon: const Icon(Icons.undo_rounded),
              onPressed: st.undo,
            ),
          if (st.busy)
            const Padding(
              padding: EdgeInsets.only(right: 18),
              child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
            ),
        ],
      ),
      body: SafeArea(
        bottom: false,
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 860), // tablets and PCs
            child: IndexedStack(index: tab, children: pages),
          ),
        ),
      ),
      bottomNavigationBar: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(12, 0, 12, 10),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(26),
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18),
              child: Container(
                decoration: BoxDecoration(
                  color: const Color(0xC70C0C1A),
                  borderRadius: BorderRadius.circular(26),
                  border: Border.all(color: const Color(0x332EE6FF)),
                ),
                child: NavigationBar(
                  selectedIndex: tab,
                  labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
                  onDestinationSelected: (i) {
                    if (i == 1) st.loadBeats(); // refresh the library when opening it
                    if (i == 3) st.refreshTags();
                    st.goTab(i);
                  },
                  destinations: const [
                    NavigationDestination(icon: Icon(Icons.graphic_eq), label: 'Create'),
                    NavigationDestination(icon: Icon(Icons.library_music_outlined), selectedIcon: Icon(Icons.library_music), label: 'My beats'),
                    NavigationDestination(icon: Icon(Icons.headphones_outlined), selectedIcon: Icon(Icons.headphones), label: 'Inspire'),
                    NavigationDestination(icon: Icon(Icons.sell_outlined), selectedIcon: Icon(Icons.sell), label: 'Tag'),
                    NavigationDestination(icon: Icon(Icons.tune), label: 'Studio'),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
