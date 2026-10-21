package ke.zacc.hypolab

import android.app.Activity
import android.app.ActivityManager
import android.content.ClipData
import android.content.ClipboardManager
import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.os.Debug
import android.os.SystemClock
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File

/** Phase A spike: one button runs spike.py and shows time and memory for each step. */
class MainActivity : Activity() {
    private lateinit var out: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val green = Color.rgb(0, 255, 156)
        out = TextView(this).apply {
            typeface = Typeface.MONOSPACE; textSize = 11f; setTextColor(green); setPadding(24, 24, 24, 24)
            setTextIsSelectable(true)
            text = "HYPOLAB feasibility spike (phase A)\nTap RUN SPIKE. It builds the practice market, so it takes a minute.\n"
        }
        val run = Button(this).apply { text = "RUN SPIKE"; minHeight = 144 }
        val copy = Button(this).apply { text = "COPY REPORT"; minHeight = 144 }
        val bar = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; addView(run); addView(copy) }
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setBackgroundColor(Color.BLACK)
            addView(bar); addView(ScrollView(this@MainActivity).apply { addView(out) })
        }
        setContentView(root)
        copy.setOnClickListener {
            (getSystemService(CLIPBOARD_SERVICE) as ClipboardManager)
                .setPrimaryClip(ClipData.newPlainText("HYPOLAB spike", out.text))
        }
        run.setOnClickListener { run.isEnabled = false; Thread { spike(); runOnUiThread { run.isEnabled = true } }.start() }
    }

    private fun say(s: String) = runOnUiThread { out.append(s + "\n") }

    private fun deviceLine(): String {
        val am = getSystemService(ACTIVITY_SERVICE) as ActivityManager
        val mi = ActivityManager.MemoryInfo().also { am.getMemoryInfo(it) }
        return "device ${android.os.Build.MANUFACTURER} ${android.os.Build.MODEL} Android ${android.os.Build.VERSION.RELEASE} " +
            "(API ${android.os.Build.VERSION.SDK_INT}) ABI ${android.os.Build.SUPPORTED_ABIS.joinToString()}\n" +
            "RAM total ${mi.totalMem / 1048576} MB, available ${mi.availMem / 1048576} MB, " +
            "app limit ${am.memoryClass} MB (large ${am.largeMemoryClass} MB), lowMemory=${mi.lowMemory}"
    }

    private fun pssMb(): Long = Debug.getPss() / 1024

    private fun spike() {
        say(deviceLine())
        val t0 = SystemClock.elapsedRealtime()
        try {
            if (!Python.isStarted()) Python.start(AndroidPlatform(this))
            say("Python start ${(SystemClock.elapsedRealtime() - t0) / 1000.0} s, PSS ${pssMb()} MB")
            val home = File(filesDir, "hypolab_home_spike").apply { mkdirs() }
            val mod = Python.getInstance().getModule("spike")
            val logger = java.util.function.Consumer<String> { say(it) }
            mod.callAttr("run", home.absolutePath, "rank(-ts_delta(close, 5))", logger)
            say("done in ${(SystemClock.elapsedRealtime() - t0) / 1000.0} s, PSS ${pssMb()} MB")
        } catch (e: Throwable) {
            say("FAILED: $e")
        }
        say(deviceLine())
    }
}
