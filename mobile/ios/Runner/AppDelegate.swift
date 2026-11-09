import AVFoundation
import Flutter
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate {
  private let media = MediaTools()
  private let queue = DispatchQueue(label: "beatmaker.media")

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    GeneratedPluginRegistrant.register(with: self)
    if let registrar = self.registrar(forPlugin: "BeatMakerMedia") {
      let channel = FlutterMethodChannel(name: "beatmaker/media", binaryMessenger: registrar.messenger())
      channel.setMethodCallHandler { [weak self] call, result in
        guard let self = self else { return }
        let args = call.arguments as? [String: Any] ?? [:]
        self.queue.async {
          do {
            let out: Any?
            switch call.method {
            case "decodeToWav":
              out = try self.media.decodeToWav(args["input"] as! String, args["output"] as! String)
            case "encodeAac":
              out = try self.media.encodeAac(args["input"] as! String, args["output"] as! String)
            case "ttsVoices":
              out = self.media.ttsVoices()
            case "ttsToFile":
              out = try self.media.ttsToFile(args["text"] as! String, args["voice"] as? String ?? "", args["output"] as! String)
            case "saveToLibrary", "makeVideo":
              out = nil  // iOS: the app uses the share sheet; on-device video export is planned
            default:
              DispatchQueue.main.async { result(FlutterMethodNotImplemented) }
              return
            }
            DispatchQueue.main.async { result(out) }
          } catch {
            DispatchQueue.main.async { result(FlutterError(code: "MEDIA", message: error.localizedDescription, details: nil)) }
          }
        }
      }
    }
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }
}

enum MediaError: LocalizedError {
  case message(String)
  var errorDescription: String? {
    if case .message(let m) = self { return m }
    return nil
  }
}

/// Native media work on iOS: decode anything to WAV, AAC export and text-to-speech.
class MediaTools {
  private var synth: AVSpeechSynthesizer?

  func decodeToWav(_ input: String, _ output: String) throws -> String {
    let asset = AVURLAsset(url: URL(fileURLWithPath: input))
    guard let track = asset.tracks(withMediaType: .audio).first else { throw MediaError.message("No audio found in that file.") }
    let reader = try AVAssetReader(asset: asset)
    let settings: [String: Any] = [
      AVFormatIDKey: kAudioFormatLinearPCM, AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false,
      AVLinearPCMIsBigEndianKey: false, AVLinearPCMIsNonInterleaved: false,
      AVSampleRateKey: 44100, AVNumberOfChannelsKey: 2,
    ]
    let out = AVAssetReaderTrackOutput(track: track, outputSettings: settings)
    reader.add(out)
    reader.timeRange = CMTimeRange(start: .zero, duration: CMTime(seconds: min(asset.duration.seconds, 300), preferredTimescale: 600))
    guard reader.startReading() else { throw MediaError.message("Couldn't read that file.") }
    var pcm = Data()
    while let sb = out.copyNextSampleBuffer() {
      if let bb = CMSampleBufferGetDataBuffer(sb) {
        let len = CMBlockBufferGetDataLength(bb)
        var chunk = Data(count: len)
        chunk.withUnsafeMutableBytes { ptr in
          _ = CMBlockBufferCopyDataBytes(bb, atOffset: 0, dataLength: len, destination: ptr.baseAddress!)
        }
        pcm.append(chunk)
      }
    }
    var file = MediaTools.wavHeader(sampleRate: 44100, channels: 2, dataLength: pcm.count)
    file.append(pcm)
    try file.write(to: URL(fileURLWithPath: output))
    return output
  }

  func encodeAac(_ input: String, _ output: String) throws -> String {
    let src = try AVAudioFile(forReading: URL(fileURLWithPath: input))
    let format = src.processingFormat
    guard let buf = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(src.length)) else {
      throw MediaError.message("Out of memory")
    }
    try src.read(into: buf)
    let settings: [String: Any] = [
      AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: format.sampleRate,
      AVNumberOfChannelsKey: min(2, Int(format.channelCount)), AVEncoderBitRateKey: 192_000,
    ]
    try? FileManager.default.removeItem(atPath: output)
    let dst = try AVAudioFile(forWriting: URL(fileURLWithPath: output), settings: settings,
                              commonFormat: format.commonFormat, interleaved: format.isInterleaved)
    try dst.write(from: buf)
    return output
  }

  func ttsVoices() -> [[String: String]] {
    return AVSpeechSynthesisVoice.speechVoices()
      .filter { $0.language.hasPrefix("en") }
      .map { ["id": $0.identifier, "label": "\($0.name) (\($0.language))"] }
  }

  func ttsToFile(_ text: String, _ voice: String, _ output: String) throws -> String {
    let utterance = AVSpeechUtterance(string: text)
    if !voice.isEmpty, let v = AVSpeechSynthesisVoice(identifier: voice) { utterance.voice = v }
    utterance.rate = AVSpeechUtteranceDefaultSpeechRate * 0.95
    let synth = AVSpeechSynthesizer()
    self.synth = synth
    let done = DispatchSemaphore(value: 0)
    var file: AVAudioFile?
    var failure: Error?
    try? FileManager.default.removeItem(atPath: output)
    synth.write(utterance) { buffer in
      guard let pcm = buffer as? AVAudioPCMBuffer else { return }
      if pcm.frameLength == 0 {
        done.signal()
        return
      }
      do {
        if file == nil {
          file = try AVAudioFile(forWriting: URL(fileURLWithPath: output), settings: pcm.format.settings,
                                 commonFormat: pcm.format.commonFormat, interleaved: pcm.format.isInterleaved)
        }
        try file?.write(from: pcm)
      } catch {
        failure = error
        done.signal()
      }
    }
    if done.wait(timeout: .now() + 30) == .timedOut { throw MediaError.message("The voice took too long") }
    if let f = failure { throw f }
    file = nil  // closes the file
    self.synth = nil
    return output
  }

  static func wavHeader(sampleRate: Int, channels: Int, dataLength: Int) -> Data {
    var d = Data()
    func u32(_ v: UInt32) { var x = v.littleEndian; d.append(Data(bytes: &x, count: 4)) }
    func u16(_ v: UInt16) { var x = v.littleEndian; d.append(Data(bytes: &x, count: 2)) }
    d.append("RIFF".data(using: .ascii)!); u32(UInt32(36 + dataLength)); d.append("WAVE".data(using: .ascii)!)
    d.append("fmt ".data(using: .ascii)!); u32(16); u16(1); u16(UInt16(channels))
    u32(UInt32(sampleRate)); u32(UInt32(sampleRate * channels * 2)); u16(UInt16(channels * 2)); u16(16)
    d.append("data".data(using: .ascii)!); u32(UInt32(dataLength))
    return d
  }
}
