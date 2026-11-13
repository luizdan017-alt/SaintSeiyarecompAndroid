package com.luizdan.sstheh

import android.net.Uri
import android.os.Bundle
import android.os.ParcelFileDescriptor
import android.os.Process
import android.system.Os
import android.util.Log
import android.view.ViewGroup
import org.libsdl.app.SDLActivity

/** O jogo: carrega libSDL3.so e libsstheh.so (o motor) e chama SDL_main. Roda no processo ":game". */
class GameActivity : SDLActivity() {
    private var iso: ParcelFileDescriptor? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        try {
            val f = filesDir.absolutePath
            Os.setenv("SS_FILES", f, true)
            Os.setenv("HOME", f, true)
            Os.setenv("XDG_DATA_HOME", "$f/data", true)
            Os.setenv("SDL_ORIENTATIONS", "LandscapeLeft LandscapeRight", true)   // sempre deitado
            // desempenho: resolucao interna baixa (1 = a do PS2), 60 fps com vsync, sem quadros interpolados
            val sp = getSharedPreferences("sstheh", MODE_PRIVATE)
            Os.setenv("SSTHEH_SCALE", sp.getInt("render_scale", 1).toString(), true)
            Os.setenv("SSTHEH_VSYNC", "1", true)
            Os.setenv("SSTHEH_INTERP", "0", true)
            Os.setenv("SSTHEH_PERF_LOG", "1", true)   // uma linha de desempenho por segundo no log
            Os.setenv("SSTHEH_30FPS_SCENES", "1", true)   // menus e telas 2D a 30 fps, como no disco
            if (sp.getBoolean("hz50", true)) Os.setenv("SSTHEH_50HZ", "1", true)   // 50 Hz: o modo PAL original
            val s = intent.getStringExtra("iso")
            if (s != null) {
                // a ISO e lida direto do arquivo escolhido, sem copiar: o motor recebe so o numero do descritor
                iso = contentResolver.openFileDescriptor(Uri.parse(s), "r")
                Os.setenv("SS_ISO", "fd:${iso!!.fd}", true)
            }
        } catch (e: Exception) {
            Log.e("sstheh", "preparo falhou", e)
        }
        super.onCreate(savedInstanceState)
        addContentView(TouchOverlay(this), ViewGroup.LayoutParams(-1, -1))   // controle na tela
    }

    override fun getLibraries(): Array<String> = arrayOf("SDL3", "sstheh")

    override fun onDestroy() {
        super.onDestroy()
        Process.killProcess(Process.myPid())   // cada partida comeca com o processo limpo
    }
}
