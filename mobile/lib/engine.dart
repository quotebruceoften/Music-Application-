import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:serious_python/serious_python.dart';

typedef J = Map<String, dynamic>;

class EngineException implements Exception {
  final String message;
  final String? code;
  EngineException(this.message, {this.code});
  @override
  String toString() => message;
}

/// Thrown when a job was stopped on purpose.
class JobCancelled implements Exception {
  @override
  String toString() => 'Stopped';
}

/// Talks to the Python beat engine running inside the app (embedded via serious_python).
class Engine {
  static const int port = 8765;

  /// Store builds can turn song links off: flutter build apk --dart-define=ALLOW_LINKS=false
  static const bool allowLinks = bool.fromEnvironment('ALLOW_LINKS', defaultValue: true);

  final String base = 'http://127.0.0.1:$port';
  late String dataDir;
  bool hasFfmpeg = false;
  bool linksEnabled = true;
  String version = '';

  Future<void> start({void Function(String)? onStatus}) async {
    final support = await getApplicationSupportDirectory();
    dataDir = '${support.path}${Platform.pathSeparator}beatmaker';
    await Directory('$dataDir${Platform.pathSeparator}tmp').create(recursive: true);

    // A dev server may already be running (python server.py) — use it if so.
    if (await _ping()) return;

    onStatus?.call('Starting the beat engine…');
    // Python can only be started once per app process; "Try again" just waits again.
    if (!_launched) {
      _launched = true;
      _runError = null;
      SeriousPython.run(
        'app/app.zip',
        environmentVariables: {
          'BEATMAKER_PORT': '$port',
          'BEATMAKER_DATA': dataDir,
          'BEATMAKER_ALLOW_LINKS': allowLinks ? '1' : '0',
          if (Platform.isAndroid || Platform.isIOS) 'BEATMAKER_NO_FFMPEG': '1',
          if (Platform.isAndroid || Platform.isIOS) 'BEATMAKER_MAX_ANALYSIS_S': '90',
        },
      ).then((r) {
        // run() only returns once Python has stopped; the server should run forever.
        _runError = (r == null || r.trim().isEmpty) ? 'The engine stopped unexpectedly.' : r.trim();
      }, onError: (Object e) {
        _runError = '$e';
      });
    }
    // The first launch unpacks Python and NumPy, which can take a little while.
    for (var i = 0; i < 480; i++) {
      if (await _ping()) return;
      if (_runError != null) break;
      if (i == 20) onStatus?.call('Unpacking the engine (first launch only)…');
      await Future.delayed(const Duration(milliseconds: 250));
    }
    final log = await _readLog();
    final details = [if (_runError != null) _runError!, if (log.isNotEmpty) log].join('\n\n');
    throw EngineException(details.isEmpty
        ? 'The beat engine did not start. Please restart the app.'
        : 'The beat engine did not start.\n\n${_tail(details, 1500)}');
  }

  static bool _launched = false;
  static String? _runError;

  /// Python writes startup errors here (see mobile/python/main.py).
  Future<String> _readLog() async {
    try {
      final f = File('$dataDir${Platform.pathSeparator}engine.log');
      if (await f.exists()) return (await f.readAsString()).trim();
    } catch (_) {}
    return '';
  }

  static String _tail(String s, int n) => s.length <= n ? s : '…${s.substring(s.length - n)}';

  Future<bool> _ping() async {
    try {
      final r = await http.get(Uri.parse('$base/api/ping')).timeout(const Duration(seconds: 1));
      if (r.statusCode != 200) return false;
      final j = jsonDecode(r.body) as J;
      hasFfmpeg = j['ffmpeg'] == true;
      linksEnabled = j['links'] == true && allowLinks;
      version = '${j['version'] ?? ''}';
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<dynamic> get(String path) async {
    final r = await http.get(Uri.parse('$base$path')).timeout(const Duration(seconds: 30));
    return _decode(r);
  }

  Future<dynamic> post(String path, Object body) async {
    final r = await http
        .post(Uri.parse('$base$path'), headers: {'Content-Type': 'application/json'}, body: jsonEncode(body))
        .timeout(const Duration(seconds: 60));
    return _decode(r);
  }

  dynamic _decode(http.Response r) {
    final body = r.body.isEmpty ? {} : jsonDecode(utf8.decode(r.bodyBytes));
    if (r.statusCode >= 400) {
      throw EngineException(body is Map && body['error'] != null ? '${body['error']}' : 'Engine error ${r.statusCode}');
    }
    return body;
  }

  /// Start a background job and wait for it, reporting progress messages (and, for
  /// beats, how far along it is from 0 to 1). [onStarted] gets the job id for cancelling.
  Future<J> runJob(String path, Object body,
      {void Function(String)? onProgress, void Function(double)? onPct, void Function(String)? onStarted}) async {
    final job = await post(path, body) as J;
    final id = '${job['id']}';
    onStarted?.call(id);
    String last = '';
    var misses = 0;
    while (true) {
      await Future.delayed(const Duration(milliseconds: 400));
      J j;
      try {
        j = await get('/api/job/$id') as J;
        misses = 0;
      } catch (e) {
        // a busy phone can miss a poll; give up only if the engine stays silent
        if (++misses > 25) throw EngineException('Lost contact with the beat engine. Please try again.');
        continue;
      }
      final msg = '${j['message'] ?? ''}';
      if (msg != last) {
        last = msg;
        onProgress?.call(msg);
      }
      onPct?.call((j['pct'] as num?)?.toDouble() ?? 0);
      if (j['status'] == 'done') return (j['result'] as Map).cast<String, dynamic>();
      if (j['status'] == 'cancelled') throw JobCancelled();
      if (j['status'] == 'error') {
        throw EngineException('${j['error'] ?? 'Something went wrong'}', code: j['code'] as String?);
      }
    }
  }

  Future<void> cancelJob(String id) async {
    try {
      await post('/api/job/cancel', {'id': id});
    } catch (_) {}
  }

  String tmpPath(String ext) =>
      '$dataDir${Platform.pathSeparator}tmp${Platform.pathSeparator}${DateTime.now().microsecondsSinceEpoch}.$ext';
}
