package com.luizdan.sstheh

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.view.MotionEvent
import android.view.View
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min

/** Ponte para o motor (libsstheh.so): estado do controle e a tecla do painel de desempenho. */
object NativePad {
    @JvmStatic external fun set(buttons: Int, lx: Int, ly: Int)
    @JvmStatic external fun hud()
}

/** Controle na tela: direcional/analogico a esquerda, botoes a direita. Multitoque. */
class TouchOverlay(ctx: Context) : View(ctx) {
    // bits do controle do PS2 (iguais aos de port/iop/pad.h)
    private companion object {
        const val SELECT = 1 shl 0; const val START = 1 shl 3
        const val UP = 1 shl 4; const val RIGHT = 1 shl 5; const val DOWN = 1 shl 6; const val LEFT = 1 shl 7
        const val L2 = 1 shl 8; const val R2 = 1 shl 9; const val L1 = 1 shl 10; const val R1 = 1 shl 11
        const val TRIANGLE = 1 shl 12; const val CIRCLE = 1 shl 13; const val CROSS = 1 shl 14; const val SQUARE = 1 shl 15
    }

    private class Btn(val label: String, val bit: Int, val x: Float, val y: Float, val r: Float)

    private val prefs = ctx.getSharedPreferences("sstheh", Context.MODE_PRIVATE)
    private val userScale = prefs.getInt("touch_scale", 100) / 100f
    private val btnAlpha = prefs.getInt("touch_alpha", 55) * 255 / 100
    private var analog = prefs.getBoolean("touch_analog", false)

    private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }
    private val line = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 3f }
    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { textAlign = Paint.Align.CENTER }

    private var btns: List<Btn> = emptyList()
    private var hudBtn = Btn("HUD", 0, 0f, 0f, 0f)
    private var modeBtn = Btn("", 0, 0f, 0f, 0f)
    private var unit = 1f

    // direcional / analogico flutuante
    private var stickId = -1
    private var cx = 0f; private var cy = 0f      // centro (onde o dedo tocou)
    private var sx = 0f; private var sy = 0f      // posicao atual do dedo
    private var defX = 0f; private var defY = 0f  // posicao de repouso desenhada

    override fun onSizeChanged(w: Int, h: Int, ow: Int, oh: Int) {
        unit = resources.displayMetrics.density * userScale
        val u = unit
        val fw = w.toFloat(); val fh = h.toFloat()
        val ccx = fw - 120 * u; val ccy = fh - 105 * u; val off = 56 * u; val r = 30 * u
        btns = listOf(
            Btn("△", TRIANGLE, ccx, ccy - off, r), Btn("○", CIRCLE, ccx + off, ccy, r),
            Btn("✕", CROSS, ccx, ccy + off, r), Btn("□", SQUARE, ccx - off, ccy, r),
            Btn("R1", R1, fw - 60 * u, 48 * u, 28 * u), Btn("R2", R2, fw - 135 * u, 48 * u, 28 * u),
            Btn("L1", L1, 60 * u, 48 * u, 28 * u), Btn("L2", L2, 135 * u, 48 * u, 28 * u),
            Btn("SEL", SELECT, fw / 2 - 45 * u, fh - 28 * u, 20 * u), Btn("START", START, fw / 2 + 45 * u, fh - 28 * u, 24 * u)
        )
        hudBtn = Btn("HUD", 0, fw / 2 - 40 * u, 24 * u, 20 * u)
        modeBtn = Btn("", 0, fw / 2 + 40 * u, 24 * u, 20 * u)
        defX = 105 * u; defY = fh - 105 * u
    }

    private fun drawBtn(c: Canvas, b: Btn, label: String, down: Boolean) {
        fill.color = Color.WHITE; fill.alpha = if (down) min(255, btnAlpha + 80) else btnAlpha / 2
        c.drawCircle(b.x, b.y, b.r, fill)
        line.color = Color.WHITE; line.alpha = btnAlpha
        c.drawCircle(b.x, b.y, b.r, line)
        text.color = Color.WHITE; text.alpha = min(255, btnAlpha + 60)
        text.textSize = if (label.length > 2) b.r * 0.6f else b.r * 0.9f
        c.drawText(label, b.x, b.y + text.textSize / 3, text)
    }

    private var pressed = 0
    override fun onDraw(c: Canvas) {
        for (b in btns) drawBtn(c, b, b.label, (pressed and b.bit) != 0)
        drawBtn(c, hudBtn, "HUD", false)
        drawBtn(c, modeBtn, if (analog) "ANA" else "DPAD", false)
        // direcional
        val R = 55 * unit
        val bx = if (stickId >= 0) cx else defX
        val by = if (stickId >= 0) cy else defY
        fill.color = Color.WHITE; fill.alpha = btnAlpha / 3
        c.drawCircle(bx, by, R, fill)
        line.color = Color.WHITE; line.alpha = btnAlpha
        c.drawCircle(bx, by, R, line)
        fill.alpha = btnAlpha
        val kx = if (stickId >= 0) bx + clampVec(sx - cx, R) else bx
        val ky = if (stickId >= 0) by + clampVec(sy - cy, R) else by
        c.drawCircle(kx, ky, 24 * unit, fill)
    }

    private fun clampVec(v: Float, r: Float): Float = max(-r, min(r, v))

    private fun hit(b: Btn, x: Float, y: Float) = hypot(x - b.x, y - b.y) <= b.r * 1.2f

    override fun onTouchEvent(ev: MotionEvent): Boolean {
        val act = ev.actionMasked
        if (act == MotionEvent.ACTION_CANCEL) { stickId = -1; push(0); return true }
        val upIdx = if (act == MotionEvent.ACTION_UP || act == MotionEvent.ACTION_POINTER_UP) ev.actionIndex else -1
        val downIdx = if (act == MotionEvent.ACTION_DOWN || act == MotionEvent.ACTION_POINTER_DOWN) ev.actionIndex else -1
        var buttons = 0
        var stickAlive = false
        for (i in 0 until ev.pointerCount) {
            if (i == upIdx) continue
            val id = ev.getPointerId(i); val x = ev.getX(i); val y = ev.getY(i)
            if (i == downIdx) {
                if (hit(hudBtn, x, y)) { try { NativePad.hud() } catch (e: UnsatisfiedLinkError) { } ; continue }
                if (hit(modeBtn, x, y)) { analog = !analog; prefs.edit().putBoolean("touch_analog", analog).apply(); continue }
            }
            if (id == stickId) { sx = x; sy = y; stickAlive = true; continue }
            var hitBit = 0
            for (b in btns) if (hit(b, x, y)) { hitBit = b.bit; break }
            if (hitBit != 0) { buttons = buttons or hitBit; continue }
            if (stickId == -1 && i == downIdx && x < width * 0.42f && y > height * 0.3f) {
                stickId = id; cx = x; cy = y; sx = x; sy = y; stickAlive = true
            }
        }
        if (!stickAlive) stickId = -1
        push(buttons)
        return true
    }

    private fun push(buttons: Int) {
        var b = buttons
        var lx = 128; var ly = 128
        if (stickId >= 0) {
            val R = 55 * unit
            val dx = clampVec(sx - cx, R) / R; val dy = clampVec(sy - cy, R) / R
            if (analog) {
                lx = 128 + (dx * 127).toInt(); ly = 128 + (dy * 127).toInt()
            } else {
                if (dx > 0.38f) b = b or RIGHT
                if (dx < -0.38f) b = b or LEFT
                if (dy > 0.38f) b = b or DOWN
                if (dy < -0.38f) b = b or UP
            }
        }
        pressed = b
        try { NativePad.set(b, lx, ly) } catch (e: UnsatisfiedLinkError) { }
        invalidate()
    }
}
