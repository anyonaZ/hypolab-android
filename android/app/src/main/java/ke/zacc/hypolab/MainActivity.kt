package ke.zacc.hypolab

import android.annotation.SuppressLint
import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.WindowInsets
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import android.window.OnBackInvokedDispatcher
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

/**
 * HYPOLAB on the tablet (1.12.0, phase B): starts the Ideas web app in Python (hl_android.py) on 127.0.0.1
 * and shows it full screen. The page talks to Android only through the small bridge below (copy, paste, share).
 */
class MainActivity : Activity() {
    private lateinit var root: FrameLayout
    private var web: WebView? = null
    private var origin: String = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Color.rgb(5, 13, 10)
        window.navigationBarColor = Color.rgb(5, 13, 10)
        root = FrameLayout(this).apply { setBackgroundColor(Color.rgb(6, 16, 12)) }
        applyInsets(root)
        setContentView(root)
        showMessage("Starting HYPOLAB ...\n\nThe first start unpacks Python and takes up to a minute.")
        if (Build.VERSION.SDK_INT >= 33) {
            onBackInvokedDispatcher.registerOnBackInvokedCallback(OnBackInvokedDispatcher.PRIORITY_DEFAULT) { goBack() }
        }
        Thread {
            try {
                if (!Python.isStarted()) Python.start(AndroidPlatform(this))
                val mod = Python.getInstance().getModule("hl_android")
                val url = mod.callAttr("start", filesDir.absolutePath).toString()
                origin = mod.callAttr("origin").toString()
                runOnUiThread { openWeb(url) }
            } catch (e: Throwable) {
                runOnUiThread { showMessage("HYPOLAB could not start.\n\n$e\n\nLong-press to copy this text and send it to Claude.") }
            }
        }.start()
    }

    /** Android 15+ draws apps edge to edge: keep the page clear of the status bar, the gesture bar and the keyboard. */
    private fun applyInsets(v: View) {
        if (Build.VERSION.SDK_INT >= 30) {
            v.setOnApplyWindowInsetsListener { view, insets ->
                val b = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.ime() or WindowInsets.Type.displayCutout())
                view.setPadding(b.left, b.top, b.right, b.bottom)
                WindowInsets.CONSUMED
            }
        }
    }

    private fun showMessage(text: String) {
        root.removeAllViews()
        web = null
        val tv = TextView(this).apply {
            this.text = text; typeface = Typeface.MONOSPACE; textSize = 15f
            setTextColor(Color.rgb(61, 220, 151)); setPadding(48, 64, 48, 48); setTextIsSelectable(true)
        }
        root.addView(ScrollView(this).apply { addView(tv) })
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun openWeb(url: String) {
        root.removeAllViews()
        val w = WebView(this)
        w.setBackgroundColor(Color.rgb(6, 16, 12))
        with(w.settings) {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            allowContentAccess = false
            textZoom = 100
            setSupportMultipleWindows(false)
            builtInZoomControls = false
        }
        w.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val u = request.url
                if (u.scheme == "http" && u.host == "127.0.0.1") return false   // our own pages stay here
                openOutside(u)                                                  // papers, BRAIN, feeds: the browser
                return true
            }
        }
        w.addJavascriptInterface(Bridge(), "HypolabAndroid")
        root.addView(w, FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT))
        web = w
        w.loadUrl(url)
    }

    private fun openOutside(u: Uri) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, u).addCategory(Intent.CATEGORY_BROWSABLE))
        } catch (e: ActivityNotFoundException) {
            Toast.makeText(this, "No app can open $u", Toast.LENGTH_LONG).show()
        }
    }

    private fun goBack() {
        val w = web
        if (w != null && w.canGoBack()) w.goBack() else finish()
    }

    @Deprecated("Android 12 and older")
    override fun onBackPressed() {
        if (Build.VERSION.SDK_INT < 33) goBack() else super.onBackPressed()
    }

    /** What the page may ask Android to do. Nothing here can simulate, submit or read files. */
    inner class Bridge {
        private val clip get() = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager

        @JavascriptInterface
        fun copy(text: String) {
            runOnUiThread { clip.setPrimaryClip(ClipData.newPlainText("HYPOLAB", text)) }
        }

        @JavascriptInterface
        fun paste(): String {
            val c = clip.primaryClip ?: return ""
            if (c.itemCount == 0) return ""
            return c.getItemAt(0).coerceToText(this@MainActivity)?.toString() ?: ""
        }

        @JavascriptInterface
        fun share(text: String, title: String) {
            runOnUiThread {
                val send = Intent(Intent.ACTION_SEND).apply {
                    type = "text/plain"; putExtra(Intent.EXTRA_TEXT, text); putExtra(Intent.EXTRA_SUBJECT, title)
                }
                startActivity(Intent.createChooser(send, "Send to"))
            }
        }
    }
}
