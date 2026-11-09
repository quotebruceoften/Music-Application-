import 'package:flutter/services.dart';

/// Native media helpers (Android: Kotlin, iOS: Swift).
/// On PCs these return null and the engine uses ffmpeg instead.
class Media {
  static const _ch = MethodChannel('beatmaker/media');

  static Future<T?> _call<T>(String method, [Map<String, dynamic>? args]) async {
    try {
      return await _ch.invokeMethod<T>(method, args);
    } on MissingPluginException {
      return null; // not available on this platform
    }
  }

  /// Any audio or video file -> 16-bit WAV (keeps the original sample rate).
  static Future<String?> decodeToWav(String input, String output) async {
    try {
      return await _call<String>('decodeToWav', {'input': input, 'output': output});
    } on PlatformException catch (e) {
      throw Exception(e.message ?? "Couldn't read that file");
    }
  }

  /// WAV -> AAC in an .m4a file (small, shareable). Null if it fails.
  static Future<String?> encodeAac(String input, String output) async {
    try {
      return await _call<String>('encodeAac', {'input': input, 'output': output});
    } on PlatformException {
      return null;
    }
  }

  /// Vertical 1080x1920 MP4 with a moving waveform and text.
  static Future<String?> makeVideo(String wav, String output, String title, String subtitle) =>
      _call<String>('makeVideo', {'wav': wav, 'output': output, 'title': title, 'subtitle': subtitle});

  /// Copy a file into the phone's Music/Movies folder. Returns a readable location.
  static Future<String?> saveToLibrary(String path, String name, String mime) =>
      _call<String>('saveToLibrary', {'path': path, 'name': name, 'mime': mime});

  /// The phone's own text-to-speech voices.
  static Future<List<Map<String, String>>> ttsVoices() async {
    final r = await _call<List<dynamic>>('ttsVoices');
    if (r == null) return [];
    return r.map((e) => (e as Map).map((k, v) => MapEntry('$k', '$v'))).toList();
  }

  static Future<String?> ttsToFile(String text, String voice, String output) =>
      _call<String>('ttsToFile', {'text': text, 'voice': voice, 'output': output});
}
