package app.beatmaker.beatmaker

import android.content.ContentValues
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import android.media.AudioFormat
import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaExtractor
import android.media.MediaFormat
import android.media.MediaMuxer
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.MediaStore
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.speech.tts.Voice
import java.io.BufferedOutputStream
import java.io.File
import java.io.FileOutputStream
import java.io.OutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.Locale
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.math.ceil
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt

/** Native media work for the app: decoding, AAC export, TikTok video, saving, text-to-speech. */
class MediaTools(private val ctx: Context) {

    // ------------------------------------------------------------------ WAV helpers
    class Wav(val pcm: ShortArray, val sampleRate: Int, val channels: Int)

    private fun readWav(path: String): Wav {
        val b = File(path).readBytes()
        val bb = ByteBuffer.wrap(b).order(ByteOrder.LITTLE_ENDIAN)
        require(b.size > 12 && String(b, 0, 4, Charsets.US_ASCII) == "RIFF") { "Not a WAV file" }
        var pos = 12
        var fmt = 1
        var ch = 1
        var sr = 44100
        var bits = 16
        var dataOff = -1
        var dataLen = 0
        while (pos + 8 <= b.size) {
            val id = String(b, pos, 4, Charsets.US_ASCII)
            val size = bb.getInt(pos + 4)
            if (id == "fmt ") {
                fmt = bb.getShort(pos + 8).toInt() and 0xFFFF
                ch = bb.getShort(pos + 10).toInt()
                sr = bb.getInt(pos + 12)
                bits = bb.getShort(pos + 22).toInt()
                if (fmt == 0xFFFE && size >= 26) fmt = bb.getShort(pos + 32).toInt() and 0xFFFF
            } else if (id == "data") {
                dataOff = pos + 8
                dataLen = if (size <= 0 || dataOff + size > b.size) b.size - dataOff else size
                break
            }
            if (size < 0) break
            pos += 8 + size + (size and 1)
        }
        require(dataOff > 0) { "Broken WAV file" }
        val pcm: ShortArray = when {
            fmt == 3 && bits == 32 -> ShortArray(dataLen / 4) { i ->
                (bb.getFloat(dataOff + 4 * i).coerceIn(-1f, 1f) * 32767f).toInt().toShort()
            }
            bits == 16 -> ShortArray(dataLen / 2) { i -> bb.getShort(dataOff + 2 * i) }
            bits == 24 -> ShortArray(dataLen / 3) { i ->
                val o = dataOff + 3 * i
                ((b[o + 2].toInt() shl 8) or (b[o + 1].toInt() and 0xFF)).toShort()
            }
            bits == 32 -> ShortArray(dataLen / 4) { i -> (bb.getInt(dataOff + 4 * i) shr 16).toShort() }
            else -> throw IllegalArgumentException("Unsupported WAV ($bits-bit)")
        }
        return Wav(pcm, sr, max(1, ch))
    }

    private fun wavHeader(sr: Int, ch: Int, dataLen: Long): ByteArray {
        val h = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
        h.put("RIFF".toByteArray()); h.putInt((36 + dataLen).toInt()); h.put("WAVE".toByteArray())
        h.put("fmt ".toByteArray()); h.putInt(16); h.putShort(1.toShort()); h.putShort(ch.toShort())
        h.putInt(sr); h.putInt(sr * ch * 2); h.putShort((ch * 2).toShort()); h.putShort(16.toShort())
        h.put("data".toByteArray()); h.putInt(dataLen.toInt())
        return h.array()
    }

    // ------------------------------------------------------------------ decode anything -> WAV
    fun decodeToWav(input: String, output: String): String {
        val ex = MediaExtractor()
        ex.setDataSource(input)
        var track = -1
        var fmt: MediaFormat? = null
        for (i in 0 until ex.trackCount) {
            val f = ex.getTrackFormat(i)
            if ((f.getString(MediaFormat.KEY_MIME) ?: "").startsWith("audio/")) { track = i; fmt = f; break }
        }
        val inFmt = fmt ?: throw IllegalArgumentException("No audio found in that file.")
        ex.selectTrack(track)
        val codec = MediaCodec.createDecoderByType(inFmt.getString(MediaFormat.KEY_MIME)!!)
        codec.configure(inFmt, null, null, 0)
        codec.start()
        var sr = inFmt.getInteger(MediaFormat.KEY_SAMPLE_RATE)
        var ch = inFmt.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
        var isFloat = false
        val raw = File("$output.raw")
        var total = 0L
        val info = MediaCodec.BufferInfo()
        BufferedOutputStream(FileOutputStream(raw)).use { os ->
            var inDone = false
            var outDone = false
            while (!outDone) {
                if (!inDone) {
                    val ii = codec.dequeueInputBuffer(10_000)
                    if (ii >= 0) {
                        val buf = codec.getInputBuffer(ii)!!
                        val n = ex.readSampleData(buf, 0)
                        if (n < 0) {
                            codec.queueInputBuffer(ii, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                            inDone = true
                        } else {
                            codec.queueInputBuffer(ii, 0, n, ex.sampleTime, 0)
                            ex.advance()
                        }
                    }
                }
                val oi = codec.dequeueOutputBuffer(info, 10_000)
                if (oi == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                    val of = codec.outputFormat
                    sr = of.getInteger(MediaFormat.KEY_SAMPLE_RATE)
                    ch = of.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
                    if (Build.VERSION.SDK_INT >= 24 && of.containsKey(MediaFormat.KEY_PCM_ENCODING)) {
                        isFloat = of.getInteger(MediaFormat.KEY_PCM_ENCODING) == AudioFormat.ENCODING_PCM_FLOAT
                    }
                } else if (oi >= 0) {
                    val ob = codec.getOutputBuffer(oi)!!
                    ob.position(info.offset)
                    ob.limit(info.offset + info.size)
                    if (isFloat) {
                        val fb = ob.order(ByteOrder.LITTLE_ENDIAN).asFloatBuffer()
                        val out = ByteBuffer.allocate(fb.remaining() * 2).order(ByteOrder.LITTLE_ENDIAN)
                        while (fb.hasRemaining()) out.putShort((fb.get().coerceIn(-1f, 1f) * 32767f).toInt().toShort())
                        os.write(out.array()); total += out.capacity()
                    } else {
                        val bytes = ByteArray(info.size)
                        ob.get(bytes)
                        os.write(bytes); total += bytes.size
                    }
                    codec.releaseOutputBuffer(oi, false)
                    if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) outDone = true
                    if (total > 300L * sr * ch * 2) outDone = true // 5 minutes is plenty
                }
            }
        }
        codec.stop(); codec.release(); ex.release()
        FileOutputStream(output).use { out ->
            out.write(wavHeader(sr, ch, total))
            raw.inputStream().use { it.copyTo(out) }
        }
        raw.delete()
        return output
    }

    // ------------------------------------------------------------------ WAV -> AAC (.m4a)
    fun encodeAac(input: String, output: String): String {
        val wav = readWav(input)
        val ch = min(2, wav.channels)
        val fmt = MediaFormat.createAudioFormat(MediaFormat.MIMETYPE_AUDIO_AAC, wav.sampleRate, ch)
        fmt.setInteger(MediaFormat.KEY_AAC_PROFILE, MediaCodecInfo.CodecProfileLevel.AACObjectLC)
        fmt.setInteger(MediaFormat.KEY_BIT_RATE, 192_000)
        fmt.setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, 16_384)
        val enc = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_AUDIO_AAC)
        enc.configure(fmt, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
        enc.start()
        val mux = MediaMuxer(output, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)
        var track = -1
        val info = MediaCodec.BufferInfo()
        val frames = wav.pcm.size / wav.channels
        var frame = 0
        var inDone = false
        var outDone = false
        while (!outDone) {
            if (!inDone) {
                val ii = enc.dequeueInputBuffer(10_000)
                if (ii >= 0) {
                    val buf = enc.getInputBuffer(ii)!!.order(ByteOrder.LITTLE_ENDIAN)
                    buf.clear()
                    val n = min(frames - frame, buf.capacity() / (2 * ch))
                    if (n <= 0) {
                        enc.queueInputBuffer(ii, 0, 0, frame * 1_000_000L / wav.sampleRate, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                        inDone = true
                    } else {
                        for (f in frame until frame + n) for (c in 0 until ch) buf.putShort(wav.pcm[f * wav.channels + c])
                        enc.queueInputBuffer(ii, 0, n * 2 * ch, frame * 1_000_000L / wav.sampleRate, 0)
                        frame += n
                    }
                }
            }
            val oi = enc.dequeueOutputBuffer(info, 10_000)
            if (oi == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                track = mux.addTrack(enc.outputFormat)
                mux.start()
            } else if (oi >= 0) {
                val ob = enc.getOutputBuffer(oi)!!
                if (info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG != 0) info.size = 0
                if (info.size > 0 && track >= 0) {
                    ob.position(info.offset); ob.limit(info.offset + info.size)
                    mux.writeSampleData(track, ob, info)
                }
                enc.releaseOutputBuffer(oi, false)
                if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) outDone = true
            }
        }
        enc.stop(); enc.release()
        mux.stop(); mux.release()
        return output
    }

    // ------------------------------------------------------------------ TikTok video (720x1280)
    fun makeVideo(wavPath: String, output: String, title: String, subtitle: String): String {
        val fps = 30
        val w = 720
        val h = 1280
        val wav = readWav(wavPath)
        val frames = wav.pcm.size / wav.channels
        val nVideo = ceil(frames.toDouble() / wav.sampleRate * fps).toInt()
        // loudness per video frame, for the waveform
        val per = max(1, wav.sampleRate / fps)
        val amp = FloatArray(nVideo + 60)
        var peak = 1e-6f
        for (k in 0 until nVideo) {
            var acc = 0.0
            val a = k * per
            val e = min(frames, a + per)
            for (f in a until e) {
                var s = 0
                for (c in 0 until wav.channels) s += wav.pcm[f * wav.channels + c]
                val v = s.toDouble() / wav.channels / 32768.0
                acc += v * v
            }
            amp[k] = sqrt(acc / max(1, e - a)).toFloat()
            peak = max(peak, amp[k])
        }
        for (k in amp.indices) amp[k] = sqrt(amp[k] / peak)

        val audioTmp = "$output.audio.m4a"
        encodeAac(wavPath, audioTmp)
        val ex = MediaExtractor()
        ex.setDataSource(audioTmp)
        var aIdx = 0
        for (i in 0 until ex.trackCount) if ((ex.getTrackFormat(i).getString(MediaFormat.KEY_MIME) ?: "").startsWith("audio/")) aIdx = i
        ex.selectTrack(aIdx)
        val audioFormat = ex.getTrackFormat(aIdx)

        val vf = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, w, h)
        vf.setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface)
        vf.setInteger(MediaFormat.KEY_BIT_RATE, 4_000_000)
        vf.setInteger(MediaFormat.KEY_FRAME_RATE, fps)
        vf.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1)
        val enc = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_VIDEO_AVC)
        enc.configure(vf, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
        val surface = enc.createInputSurface()
        enc.start()
        val mux = MediaMuxer(output, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)
        var vTrack = -1
        var aTrack = -1
        var outFrames = 0L
        val info = MediaCodec.BufferInfo()

        fun drain(end: Boolean) {
            var idle = 0
            while (true) {
                val oi = enc.dequeueOutputBuffer(info, if (end) 10_000 else 0)
                if (oi == MediaCodec.INFO_TRY_AGAIN_LATER) {
                    if (!end || ++idle > 300) return
                } else if (oi == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                    vTrack = mux.addTrack(enc.outputFormat)
                    aTrack = mux.addTrack(audioFormat)
                    mux.start()
                } else if (oi >= 0) {
                    val ob = enc.getOutputBuffer(oi)!!
                    if (info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG != 0) info.size = 0
                    if (info.size > 0 && vTrack >= 0) {
                        ob.position(info.offset); ob.limit(info.offset + info.size)
                        // Canvas surfaces carry no timestamps, so time frames by their order.
                        info.presentationTimeUs = outFrames * 1_000_000L / fps
                        outFrames++
                        mux.writeSampleData(vTrack, ob, info)
                    }
                    enc.releaseOutputBuffer(oi, false)
                    if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) return
                }
            }
        }

        val bg = Color.rgb(15, 14, 19)
        val orange = Color.rgb(255, 181, 71)
        val dimOrange = Color.rgb(110, 80, 40)
        val titleP = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.WHITE; textSize = 54f; typeface = Typeface.DEFAULT_BOLD; textAlign = Paint.Align.CENTER
        }
        val subP = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.rgb(185, 181, 198); textSize = 30f; typeface = Typeface.DEFAULT_BOLD; textAlign = Paint.Align.CENTER
        }
        val barP = Paint(Paint.ANTI_ALIAS_FLAG)
        val bars = 72
        val barW = w.toFloat() / bars
        val rect = RectF()

        fun fit(p: Paint, text: String) {
            val base = p.textSize
            while (p.measureText(text) > w * 0.9f && p.textSize > 18f) p.textSize -= 2f
            if (text.isEmpty()) p.textSize = base
        }
        fit(titleP, title)
        fit(subP, subtitle)

        for (f in 0 until nVideo) {
            val c: Canvas = if (Build.VERSION.SDK_INT >= 23) surface.lockHardwareCanvas() else surface.lockCanvas(null)
            c.drawColor(bg)
            c.drawText(title, w / 2f, 260f, titleP)
            val cy = h / 2f
            for (i in 0 until bars) {
                val k = f + (i - bars / 2)
                val a = if (k in 0 until nVideo) amp[k] else 0f
                val bh = max(4f, a * 260f)
                barP.color = if (i <= bars / 2) orange else dimOrange
                rect.set(i * barW + 2f, cy - bh, (i + 1) * barW - 2f, cy + bh)
                c.drawRoundRect(rect, 4f, 4f, barP)
            }
            c.drawText(subtitle, w / 2f, 980f, subP)
            surface.unlockCanvasAndPost(c)
            drain(false)
        }
        enc.signalEndOfInputStream()
        drain(true)

        if (aTrack >= 0) {
            val buf = ByteBuffer.allocate(512 * 1024)
            val ai = MediaCodec.BufferInfo()
            while (true) {
                val n = ex.readSampleData(buf, 0)
                if (n < 0) break
                val flags = if (ex.sampleFlags and MediaExtractor.SAMPLE_FLAG_SYNC != 0) MediaCodec.BUFFER_FLAG_KEY_FRAME else 0
                ai.set(0, n, ex.sampleTime, flags)
                mux.writeSampleData(aTrack, buf, ai)
                ex.advance()
            }
        }
        ex.release()
        enc.stop(); enc.release(); surface.release()
        mux.stop(); mux.release()
        File(audioTmp).delete()
        return output
    }

    // ------------------------------------------------------------------ save into Music / Movies
    fun saveToLibrary(path: String, name: String, mime: String): String? {
        if (Build.VERSION.SDK_INT < 29) return null // older phones: the app falls back to the share sheet
        val video = mime.startsWith("video")
        val collection = if (video) MediaStore.Video.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
        else MediaStore.Audio.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
        val dir = (if (video) Environment.DIRECTORY_MOVIES else Environment.DIRECTORY_MUSIC) + "/BeatMaker"
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, name)
            put(MediaStore.MediaColumns.MIME_TYPE, if (mime == "audio/wav") "audio/x-wav" else mime)
            put(MediaStore.MediaColumns.RELATIVE_PATH, dir)
            put(MediaStore.MediaColumns.IS_PENDING, 1)
        }
        val resolver = ctx.contentResolver
        val uri = resolver.insert(collection, values) ?: return null
        resolver.openOutputStream(uri)?.use { out: OutputStream -> File(path).inputStream().use { it.copyTo(out) } }
        values.clear()
        values.put(MediaStore.MediaColumns.IS_PENDING, 0)
        resolver.update(uri, values, null, null)
        return dir
    }

    // ------------------------------------------------------------------ text-to-speech
    private var tts: TextToSpeech? = null

    private fun ensureTts(): TextToSpeech {
        tts?.let { return it }
        val latch = CountDownLatch(1)
        var ok = false
        val t = TextToSpeech(ctx) { status -> ok = status == TextToSpeech.SUCCESS; latch.countDown() }
        latch.await(10, TimeUnit.SECONDS)
        if (!ok) throw IllegalStateException("No text-to-speech engine on this phone.")
        tts = t
        return t
    }

    fun ttsVoices(): List<Map<String, String>> {
        val t = try { ensureTts() } catch (e: Exception) { return emptyList() }
        val list = (t.voices ?: emptySet<Voice>())
            .filter { it.locale.language == "en" && !it.features.contains(TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED) }
            .sortedWith(compareBy<Voice>({ it.isNetworkConnectionRequired }, { -it.quality }, { it.locale.country }, { it.name }))
            .take(30)
        val counts = HashMap<String, Int>()
        return list.map { v ->
            val country = v.locale.getDisplayCountry(Locale.ENGLISH).ifEmpty { "English" }
            val n = (counts[country] ?: 0) + 1
            counts[country] = n
            mapOf("id" to v.name, "label" to "$country voice $n" + if (v.isNetworkConnectionRequired) " (online)" else "")
        }
    }

    fun ttsToFile(text: String, voice: String, output: String): String {
        val t = ensureTts()
        if (voice.isNotEmpty()) t.voices?.firstOrNull { it.name == voice }?.let { t.voice = it }
        t.setSpeechRate(0.95f)
        val latch = CountDownLatch(1)
        var err: String? = null
        t.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) {}
            override fun onDone(utteranceId: String?) { latch.countDown() }
            @Suppress("OVERRIDE_DEPRECATION")
            override fun onError(utteranceId: String?) { err = "The voice failed"; latch.countDown() }
            override fun onError(utteranceId: String?, errorCode: Int) { err = "The voice failed ($errorCode)"; latch.countDown() }
        })
        val r = t.synthesizeToFile(text, Bundle(), File(output), "beatmaker-tag")
        if (r != TextToSpeech.SUCCESS) throw IllegalStateException("The voice couldn't start")
        if (!latch.await(30, TimeUnit.SECONDS)) throw IllegalStateException("The voice took too long")
        err?.let { throw IllegalStateException(it) }
        return output
    }

    fun shutdown() {
        tts?.shutdown()
        tts = null
    }
}
