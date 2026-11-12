#!/usr/bin/env python3
"""Ajustes minimos do codigo do jogo para o Android (rodado pelo workflow, na raiz do repositorio).
Cada ajuste troca um trecho exato; se o trecho nao existir (e o ajuste ainda nao estiver feito), falha.
Documentado em android/ANDROID_CHANGES.md."""
import sys

def patch(path, old, new):
    s = open(path, encoding="utf-8").read()
    if new in s:
        print("ja aplicado:", path); return
    if s.count(old) != 1:
        sys.exit(f"ERRO: trecho nao encontrado (ou repetido) em {path}:\n{old}")
    open(path, "w", encoding="utf-8").write(s.replace(old, new))
    print("aplicado:", path)

# 1) platform.c: no Android (API 29) nao existe clock_nanosleep: usar o mesmo caminho do macOS
patch("port/runtime/platform.c",
      "#ifdef __APPLE__\n#include <errno.h>\n",
      "#include <errno.h>\n#ifdef __APPLE__\n")
patch("port/runtime/platform.c",
      "#elif defined(__APPLE__)\n    /* no absolute clock_nanosleep",
      "#elif defined(__APPLE__) || defined(__ANDROID__)\n    /* no absolute clock_nanosleep")

# 2) cdvd.c: a ISO pode vir como "fd:N" (descritor aberto pelo Android), lida sem copiar o arquivo
patch("port/hle/cdvd.c",
      'int cdvd_open(const char *path) {\n    iso = fopen(path, "rb");\n',
      'int cdvd_open(const char *path) {\n'
      '    if (!strncmp(path, "fd:", 3)) {   /* Android: descritor da ISO escolhida; dup para nao fechar o original */\n'
      '        extern int dup(int);\n'
      '        int d = dup(atoi(path + 3));\n'
      '        iso = d >= 0 ? fdopen(d, "rb") : NULL;\n'
      '    } else iso = fopen(path, "rb");\n')

# 3) display.c: botoes do controle na tela entram no controle 1; HUD pode ser alternado pela tela
patch("port/gs/display.c",
      "static void poll_pads(void) {\n    pad_buttons[0] = training_pad(keyboard() | gamepad_buttons(0) | scripted(kernel_vblank_count()));\n",
      "extern volatile u16 touch_pad_buttons;    /* Android: controle na tela (android_entry.c) */\n"
      "static void touch_hud_poll(void);\n"
      "static void poll_pads(void) {\n    touch_hud_poll();\n"
      "    pad_buttons[0] = training_pad(keyboard() | gamepad_buttons(0) | scripted(kernel_vblank_count()) | touch_pad_buttons);\n")
patch("port/gs/display.c",
      "static int panel_on = 1;\n",
      "static int panel_on = 1;\n"
      "extern volatile int touch_hud_toggle;\n"
      "static void touch_hud_poll(void) { if (touch_hud_toggle) { touch_hud_toggle = 0; panel_on = !panel_on; } }\n")
