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

# 4) iop.c: o aviso "queue full" saia a cada chamada perdida (milhares por segundo) e enchia o log
patch("port/iop/iop.c",
      '        rt_log("iop", "IOP->EE queue full: call %X fn %X lost", sid, fn);\n',
      '        static unsigned lost_n;   /* Android: so as primeiras e depois 1 a cada 2000 */\n'
      '        if (lost_n++ < 5 || lost_n % 2000 == 0) rt_log("iop", "IOP->EE queue full: call %X fn %X lost (%u)", sid, fn, lost_n);\n')

# 5) platform.c: threads pesados so nos nucleos rapidos (android_entry.c)
patch("port/runtime/platform.c",
      "    pthread_setname_np(t, name);\n#endif\n",
      "    pthread_setname_np(t, name);\n#ifdef __ANDROID__\n"
      "    { extern void android_pin_thread(pthread_t, const char *); android_pin_thread(t, name); }\n#endif\n#endif\n")

# 6) cdvd.c: avisar leituras lentas da ISO (diagnostico das travadas)
patch("port/hle/cdvd.c",
      '#include <string.h>\n\n#include "r5900.h"',
      '#include <string.h>\n#include <time.h>\n\n#include "r5900.h"')
patch("port/hle/cdvd.c",
      "    if (!iso) return -1;\n    pthread_mutex_lock(&iso_lock);\n    int ok;\n",
      "    if (!iso) return -1;\n    struct timespec t0_, t1_;\n    clock_gettime(CLOCK_MONOTONIC, &t0_);\n"
      "    pthread_mutex_lock(&iso_lock);\n    int ok;\n")
patch("port/hle/cdvd.c",
      "    pthread_mutex_unlock(&iso_lock);\n    return ok ? 0 : -1;\n}",
      "    pthread_mutex_unlock(&iso_lock);\n    clock_gettime(CLOCK_MONOTONIC, &t1_);\n"
      "    long ms_ = (t1_.tv_sec - t0_.tv_sec) * 1000 + (t1_.tv_nsec - t0_.tv_nsec) / 1000000;\n"
      '    if (ms_ >= 100) rt_log("cdvd", "leitura lenta: %u setores em %u levou %ld ms", count, lsn, ms_);\n'
      "    return ok ? 0 : -1;\n}")

# 7) velocidade do thread do jogo (o limite de fps do port): ver android/ANDROID_CHANGES.md
# 7a) RAM do jogo como vetor estatico (endereco constante, sem recarregar o ponteiro a cada acesso)
patch("port/runtime/r5900.h",
      "extern u8 *rt_ram;              /* 32 MB */\n",
      "#ifdef __ANDROID__\n"
      "extern u8 rt_ram_buf[0x02000000] __attribute__((aligned(64)));   /* 32 MB, estatico */\n"
      "#define rt_ram rt_ram_buf\n"
      "#else\n"
      "extern u8 *rt_ram;              /* 32 MB */\n"
      "#endif\n")
patch("port/runtime/memory.c",
      "u8 *rt_ram;\n",
      "#ifdef __ANDROID__\n"
      "u8 rt_ram_buf[0x02000000] __attribute__((aligned(64)));\n"
      "#else\n"
      "u8 *rt_ram;\n"
      "#endif\n")
patch("port/runtime/memory.c",
      "    rt_ram = platform_aligned_alloc(64, 0x02000000);\n",
      "#ifndef __ANDROID__\n"
      "    rt_ram = platform_aligned_alloc(64, 0x02000000);\n"
      "#endif\n")
# 7b) caminho rapido de rt_ptr: RAM em KUSEG (0..32 MB) e o caso de quase todo acesso
patch("port/runtime/r5900.h",
      "    u32 seg = a >> 28;\n    if (seg == 0 ||",
      "    if (__builtin_expect(a < 0x02000000u, 1)) return rt_ram + a;   /* caso comum */\n"
      "    u32 seg = a >> 28;\n    if (seg == 0 ||")
# 7c) ENTER (so serve ao --trace) vira nada: tirava um load e um desvio de cada funcao
patch("port/runtime/r5900.h",
      "#define ENTER(a) do { if (__builtin_expect(rt_trace_on, 0)) rt_enter(c, a); } while (0)\n",
      "#ifdef __ANDROID__\n"
      "#define ENTER(a) do { } while (0)   /* --trace nao existe no Android */\n"
      "#else\n"
      "#define ENTER(a) do { if (__builtin_expect(rt_trace_on, 0)) rt_enter(c, a); } while (0)\n"
      "#endif\n")
# 7d) chamadas indiretas (jalr/jr): tabela direta em vez de busca binaria em ~16 mil funcoes
patch("port/runtime/cpu.c",
      "void rt_call(Ctx *c, u32 addr) {\n    const FuncEntry *f = rt_find(addr);\n",
      "/* tabela direta endereco -> funcao (o codigo fica em 0x100000..0x500000, alinhado a 4 bytes) */\n"
      "static GuestFn fn_map[0x100000];\n"
      "static const FuncEntry *fn_map_for;\n"
      "static void build_fn_map(void) {\n"
      "    memset(fn_map, 0, sizeof fn_map);\n"
      "    for (int i = 0; i < rt_functab_count; i++) {\n"
      "        u32 a = rt_functab[i].addr;\n"
      "        if (a >= 0x00100000u && a < 0x00500000u && !(a & 3)) fn_map[(a - 0x00100000u) >> 2] = rt_functab[i].fn;\n"
      "    }\n"
      "    fn_map_for = rt_functab;\n"
      "}\n\n"
      "void rt_call(Ctx *c, u32 addr) {\n"
      "    u32 mi = (addr - 0x00100000u) >> 2;\n"
      "    if (__builtin_expect(mi < 0x100000u && !(addr & 3), 1)) {\n"
      "        GuestFn g = fn_map[mi];\n"
      "        if (__builtin_expect(g != NULL, 1)) { g(c); return; }\n"
      "        if (fn_map_for != rt_functab) { build_fn_map(); g = fn_map[mi]; if (g) { g(c); return; } }\n"
      "    }\n"
      "    const FuncEntry *f = rt_find(addr);\n")

# 8) display.c: o profiler (SSTHEH_PROF) imprime o relatorio tambem ao fechar a partida pelo botao SAIR
patch("port/gs/display.c",
      "            if (e.type == SDL_EVENT_QUIT) { SDL_Quit(); _exit(0); }\n"
      "            gamepad_event(&e);\n"
      "            if (e.type == SDL_EVENT_KEY_DOWN && e.key.scancode == SDL_SCANCODE_F1 && !e.key.repeat) win_size_next(win);\n"
      "            if (e.type == SDL_EVENT_KEY_DOWN && e.key.scancode == SDL_SCANCODE_F2",
      "            if (e.type == SDL_EVENT_QUIT) { { void prof_report(void); prof_report(); } SDL_Quit(); _exit(0); }\n"
      "            gamepad_event(&e);\n"
      "            if (e.type == SDL_EVENT_KEY_DOWN && e.key.scancode == SDL_SCANCODE_F1 && !e.key.repeat) win_size_next(win);\n"
      "            if (e.type == SDL_EVENT_KEY_DOWN && e.key.scancode == SDL_SCANCODE_F2")

# 9) prof.c: prof_reset (o botao PROF do jogo recomeca a contagem); display.c: "game" -> "resto" (e o que sobra, nao so o thread do jogo)
patch("port/runtime/prof.c",
      'void prof_report(void) {\n    if (!getenv("SSTHEH_PROF")) return;',
      'void prof_reset(void) { nsamples = 0; }\n\nvoid prof_report(void) {\n    if (!getenv("SSTHEH_PROF")) return;')
patch("port/gs/display.c",
      'GS %3.0f%%  VU1 %3.0f%%  game %3.0f%%',
      'GS %3.0f%%  VU1 %3.0f%%  resto %3.0f%%')
