package com.luizdan.sstheh

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.graphics.Typeface
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.SeekBar
import android.widget.TextView
import android.widget.Toast
import java.io.File

/** Tela inicial: escolher a ISO, jogar, testar os graficos e ver o log da ultima partida. */
class LauncherActivity : Activity() {
    private lateinit var status: TextView
    private lateinit var logView: TextView

    private fun prefs() = getSharedPreferences("sstheh", MODE_PRIVATE)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val pad = (16 * resources.displayMetrics.density).toInt()
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad * 2, pad, pad)
        }
        status = TextView(this).apply { textSize = 16f }
        val pick = Button(this).apply { text = "Escolher a ISO"; setOnClickListener { pickIso() } }
        val play = Button(this).apply { text = "Jogar"; setOnClickListener { play() } }
        val test = Button(this).apply {
            text = "Testar gráficos (tela azul)"
            setOnClickListener { startActivity(Intent(this@LauncherActivity, TestActivity::class.java)) }
        }
        logView = TextView(this).apply {
            textSize = 11f
            typeface = Typeface.MONOSPACE
            setTextIsSelectable(true)
        }
        val scroll = ScrollView(this).apply { addView(logView) }
        root.addView(status)
        root.addView(pick)
        root.addView(play)
        root.addView(test)
        val res = Button(this)
        fun refresh() { res.text = "Resolução interna: ${prefs().getInt("render_scale", 1)}x (1 = mais rápido)" }
        res.setOnClickListener {
            prefs().edit().putInt("render_scale", prefs().getInt("render_scale", 1) % 3 + 1).apply()
            refresh()
        }
        refresh()
        root.addView(res)
        val hz = Button(this)
        fun refreshHz() { hz.text = "Taxa do jogo: " + (if (prefs().getBoolean("hz50", true)) "50 Hz (original, mais leve)" else "60 Hz") }
        hz.setOnClickListener {
            prefs().edit().putBoolean("hz50", !prefs().getBoolean("hz50", true)).apply()
            refreshHz()
        }
        refreshHz()
        root.addView(hz)
        val wide = Button(this)
        fun refreshWide() { wide.text = "Tela: " + (if (prefs().getBoolean("wide", true)) "16:9 (ampla)" else "4:3 (original)") }
        wide.setOnClickListener {
            prefs().edit().putBoolean("wide", !prefs().getBoolean("wide", true)).apply()
            refreshWide()
        }
        refreshWide()
        root.addView(wide)
        fun toggle(label: String, key: String, def: Boolean): Button {
            val b = Button(this)
            fun refreshT() { b.text = label + ": " + (if (prefs().getBoolean(key, def)) "LIGADO" else "desligado") }
            b.setOnClickListener { prefs().edit().putBoolean(key, !prefs().getBoolean(key, def)).apply(); refreshT() }
            refreshT()
            return b
        }
        root.addView(toggle("Desbloquear tudo (personagens, modos...)", "unlock", false))
        root.addView(toggle("Medir desempenho (profiler)", "prof", false))
        val copy = Button(this).apply {
            text = "Copiar o log"
            setOnClickListener {
                val log = File(filesDir, "sstheh.log")
                val txt = if (log.exists()) log.readText().takeLast(30000) else "(sem log)"
                (getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager)
                    .setPrimaryClip(ClipData.newPlainText("sstheh.log", txt))
                Toast.makeText(this@LauncherActivity, "Log copiado.", Toast.LENGTH_SHORT).show()
            }
        }
        root.addView(copy)
        root.addView(slider("Tamanho dos botões", "touch_scale", 60, 150, 100))
        root.addView(slider("Opacidade dos botões", "touch_alpha", 10, 100, 55))
        root.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(root)
    }

    override fun onResume() {
        super.onResume()
        val s = prefs().getString("iso", null)
        status.text = if (s == null) "Nenhuma ISO escolhida." else "ISO: " + displayName(Uri.parse(s))
        val log = File(filesDir, "sstheh.log")
        logView.text = if (log.exists()) "Log da última partida:\n" + log.readText().takeLast(8000)
                       else "Ainda não há log."
    }

    /** Barra de ajuste guardada nas preferencias (lida pelo controle na tela ao iniciar a partida). */
    private fun slider(label: String, key: String, min: Int, max: Int, def: Int): LinearLayout {
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val t = TextView(this)
        val bar = SeekBar(this).apply { this.max = max - min; progress = prefs().getInt(key, def) - min }
        fun show(v: Int) { t.text = "$label: $v%" }
        show(bar.progress + min)
        bar.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(sb: SeekBar, p: Int, fromUser: Boolean) {
                show(p + min); prefs().edit().putInt(key, p + min).apply()
            }
            override fun onStartTrackingTouch(sb: SeekBar) {}
            override fun onStopTrackingTouch(sb: SeekBar) {}
        })
        box.addView(t); box.addView(bar)
        return box
    }

    private fun displayName(uri: Uri): String = try {
        contentResolver.query(uri, null, null, null, null)?.use { c ->
            val i = c.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (c.moveToFirst() && i >= 0) c.getString(i) else uri.toString()
        } ?: uri.toString()
    } catch (e: Exception) { uri.toString() }

    private fun pickIso() {
        val i = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "*/*"
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
        }
        startActivityForResult(i, 1)
    }

    @Deprecated("simples e sem dependencias")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        val uri = data?.data
        if (requestCode == 1 && resultCode == RESULT_OK && uri != null) {
            try { contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION) }
            catch (e: Exception) { /* sem permissao persistente: vale so ate fechar o app */ }
            prefs().edit().putString("iso", uri.toString()).apply()
        }
    }

    private fun play() {
        val s = prefs().getString("iso", null)
        if (s == null) {
            Toast.makeText(this, "Escolha a ISO primeiro.", Toast.LENGTH_SHORT).show()
            return
        }
        startActivity(Intent(this, GameActivity::class.java).putExtra("iso", s))
    }
}
