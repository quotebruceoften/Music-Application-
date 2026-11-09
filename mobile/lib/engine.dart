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
    unawaited(SeriousPython.run(
      'app/app.zip',
      environmentVariables: {
        'BEATMAKER_PORT': '$port',
        'BEATMAKER_DATA': dataDir,
        'BEATMAKER_ALLOW_LINKS': allowLinks ? '1' : '0',
        if (Platform.isAndroid || Platform.isIOS) 'BEATMAKER_NO_FFMPEG': '1',
        if (Platform.isAndroid || Platform.isIOS) 'BEATMAKER_MAX_ANALYSIS_S': '90',
      },
    ));
    // The first launch unpacks Python and NumPy, which can take a little while.
    for (var i = 0; i < 360; i++) {
      if (await _ping()) return;
      if (i == 20) onStatus?.call('Unpacking the engine (first launch only)…');
      await Future.delayed(const Duration(milliseconds: 250));
    }
    throw EngineException('The beat engine did not start. Please restart the app.');
  }

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

  /// Start a background job and wait for it, reporting progress messages.
  Future<J> runJob(String path, Object body, {void Function(String)? onProgress}) async {
    final job = await post(path, body) as J;
    final id = job['id'];
    String last = '';
    while (true) {
      await Future.delayed(const Duration(milliseconds: 400));
      final j = await get('/api/job/$id') as J;
      final msg = '${j['message'] ?? ''}';
      if (msg != last) {
        last = msg;
        onProgress?.call(msg);
      }
      if (j['status'] == 'done') return (j['result'] as Map).cast<String, dynamic>();
      if (j['status'] == 'error') {
        throw EngineException('${j['error'] ?? 'Something went wrong'}', code: j['code'] as String?);
      }
    }
  }

  String tmpPath(String ext) =>
      '$dataDir${Platform.pathSeparator}tmp${Platform.pathSeparator}${DateTime.now().microsecondsSinceEpoch}.$ext';
}
