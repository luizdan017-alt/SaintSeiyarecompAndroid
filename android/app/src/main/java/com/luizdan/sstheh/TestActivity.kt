package com.luizdan.sstheh

import android.os.Process
import org.libsdl.app.SDLActivity

/** Teste dos graficos: a tela azul do esqueleto (libmain.so). */
class TestActivity : SDLActivity() {
    override fun getLibraries(): Array<String> = arrayOf("SDL3", "main")

    override fun onDestroy() {
        super.onDestroy()
        Process.killProcess(Process.myPid())
    }
}
