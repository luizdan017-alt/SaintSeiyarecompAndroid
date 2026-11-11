package com.luizdan.sstheh

import org.libsdl.app.SDLActivity

/** A atividade do jogo: a do SDL3, que carrega libSDL3.so e libmain.so e chama SDL_main. */
class GameActivity : SDLActivity() {
    override fun getLibraries(): Array<String> = arrayOf("SDL3", "main")
}
