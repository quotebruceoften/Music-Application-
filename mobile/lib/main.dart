import 'package:flutter/material.dart';

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

class BeatMakerApp extends StatelessWidget {
  final AppState state;
  const BeatMakerApp({super.key, required this.state});

  @override
  Widget build(BuildContext context) {
    final scheme = ColorScheme.fromSeed(seedColor: kAccent, brightness: Brightness.dark, primary: kAccent, surface: kBg);
    return MaterialApp(
      title: 'BeatMaker',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: scheme,
        useMaterial3: true,
        scaffoldBackgroundColor: kBg,
        sliderTheme: const SliderThemeData(trackHeight: 3),
        chipTheme: const ChipThemeData(side: BorderSide(color: kLine)),
      ),
      home: ListenableBuilder(listenable: state, builder: (context, _) => Home(state)),
    );
  }
}

class Home extends StatefulWidget {
  final AppState st;
  const Home(this.st, {super.key});
  @override
  State<Home> createState() => _HomeState();
}

class _HomeState extends State<Home> {
  int _tab = 0;

  @override
  Widget build(BuildContext context) {
    final st = widget.st;
    if (!st.ready) {
      return Scaffold(
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              RichText(
                text: const TextSpan(style: TextStyle(fontSize: 34, fontWeight: FontWeight.w800), children: [
                  TextSpan(text: 'Beat', style: TextStyle(color: Colors.white)),
                  TextSpan(text: 'Maker', style: TextStyle(color: kAccent)),
                ]),
              ),
              const SizedBox(height: 24),
              if (st.startupError == null) ...[
                const CircularProgressIndicator(),
                const SizedBox(height: 16),
                Text(st.startupStatus, style: const TextStyle(color: kDim)),
              ] else ...[
                const Icon(Icons.error_outline, color: kAccent2, size: 40),
                const SizedBox(height: 12),
                ConstrainedBox(
                  constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.45),
                  child: SingleChildScrollView(
                    child: SelectableText(st.startupError!, textAlign: TextAlign.center),
                  ),
                ),
                const SizedBox(height: 12),
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

    final pages = [
      CreateScreen(st),
      InspireScreen(st, onMade: () => setState(() => _tab = 0)),
      TagScreen(st),
      StudioScreen(st),
    ];
    return Scaffold(
      appBar: AppBar(
        backgroundColor: kBg,
        title: RichText(
          text: const TextSpan(style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800), children: [
            TextSpan(text: 'Beat', style: TextStyle(color: Colors.white)),
            TextSpan(text: 'Maker', style: TextStyle(color: kAccent)),
          ]),
        ),
        actions: [
          if (st.busy)
            const Padding(
              padding: EdgeInsets.only(right: 16),
              child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
            ),
        ],
      ),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 860), // tablets and PCs
            child: IndexedStack(index: _tab, children: pages),
          ),
        ),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) => setState(() => _tab = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.graphic_eq), label: 'Create'),
          NavigationDestination(icon: Icon(Icons.headphones), label: 'Inspire'),
          NavigationDestination(icon: Icon(Icons.sell_outlined), label: 'Tag'),
          NavigationDestination(icon: Icon(Icons.tune), label: 'Studio'),
        ],
      ),
    );
  }
}
