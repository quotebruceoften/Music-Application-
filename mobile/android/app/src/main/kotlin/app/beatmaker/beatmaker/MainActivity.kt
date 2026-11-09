package app.beatmaker.beatmaker

import android.os.Handler
import android.os.Looper
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.util.concurrent.Executors

class MainActivity : FlutterActivity() {
    private val worker = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private lateinit var tools: MediaTools

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        tools = MediaTools(applicationContext)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "beatmaker/media").setMethodCallHandler { call, result ->
            worker.execute {
                try {
                    val out: Any? = when (call.method) {
                        "decodeToWav" -> tools.decodeToWav(call.argument<String>("input")!!, call.argument<String>("output")!!)
                        "encodeAac" -> tools.encodeAac(call.argument<String>("input")!!, call.argument<String>("output")!!)
                        "makeVideo" -> tools.makeVideo(
                            call.argument<String>("wav")!!, call.argument<String>("output")!!,
                            call.argument<String>("title") ?: "", call.argument<String>("subtitle") ?: ""
                        )
                        "saveToLibrary" -> tools.saveToLibrary(
                            call.argument<String>("path")!!, call.argument<String>("name")!!, call.argument<String>("mime")!!
                        )
                        "ttsVoices" -> tools.ttsVoices()
                        "ttsToFile" -> tools.ttsToFile(
                            call.argument<String>("text")!!, call.argument<String>("voice") ?: "", call.argument<String>("output")!!
                        )
                        else -> { main.post { result.notImplemented() }; return@execute }
                    }
                    main.post { result.success(out) }
                } catch (e: Throwable) {
                    main.post { result.error("MEDIA", e.message ?: e.javaClass.simpleName, null) }
                }
            }
        }
    }

    override fun onDestroy() {
        if (::tools.isInitialized) tools.shutdown()
        super.onDestroy()
    }
}
