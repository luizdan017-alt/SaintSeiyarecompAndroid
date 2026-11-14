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

# 10) GS em dois threads (modo experimental, SSTHEH_GSSPLIT=1): gs.c recebe a fila; dmac.c manda o "quadro novo" pela fila
SPLIT_BLOCK = r'''/* ---- GS em dois threads (SSTHEH_GSSPLIT=1; modo experimental do Android) ----
 * O thread "gs" roda o VIF1 e os programas do VU1 e, em vez de interpretar os pacotes GIF na hora, copia cada
 * pacote para uma fila (anel). O thread "gsx" tira os pacotes da fila, na mesma ordem, e roda o estado do GS
 * e os desenhos. Assim o VU1 e o GS trabalham ao mesmo tempo, em dois nucleos. O EE nunca le o estado do GS
 * (CSR so devolve os vblanks), entao nada que o jogo ve muda. */
#include <sched.h>
void platform_thread_name(pthread_t t, const char *name);
void gsrec_flip(void);

#ifndef SPLIT_RING
#define SPLIT_RING (16u << 20)
#endif
#define SPLIT_MAX_FLIPS 2            /* quadros novos esperando o gsx: limita o atraso a ~2 quadros */

typedef struct { u32 kind, qwc, size, pad; } SplitHdr;   /* kind: 0 salto ao inicio do anel, 1 XGKICK, 2 VIF1 DIRECT, 3 DMA do GIF, 4 quadro novo */
static u8 *sp_ring;
static u64 sp_tail;                  /* so o produtor (thread gs) */
static u64 sp_head, sp_pub_tail;     /* head: o consumidor publica; pub_tail: o produtor publica */
static u32 sp_flips_in, sp_flips_done;
static int sp_sleeping;
static pthread_mutex_t sp_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t sp_cond = PTHREAD_COND_INITIALIZER;
static int sp_on = -1;

static void *split_consumer(void *arg) {
    (void)arg;
    u64 head = 0;
    for (;;) {
        u64 tail = __atomic_load_n(&sp_pub_tail, __ATOMIC_ACQUIRE);
        if (head == tail) {
            int spins = 0;
            while (head == (tail = __atomic_load_n(&sp_pub_tail, __ATOMIC_ACQUIRE)) && ++spins < 4000) { }
            if (head == tail) {
                pthread_mutex_lock(&sp_lock);
                __atomic_store_n(&sp_sleeping, 1, __ATOMIC_SEQ_CST);
                __atomic_thread_fence(__ATOMIC_SEQ_CST);
                if (head == __atomic_load_n(&sp_pub_tail, __ATOMIC_ACQUIRE)) pthread_cond_wait(&sp_cond, &sp_lock);
                __atomic_store_n(&sp_sleeping, 0, __ATOMIC_SEQ_CST);
                pthread_mutex_unlock(&sp_lock);
                continue;
            }
        }
        SplitHdr *h = (SplitHdr *)(sp_ring + (head & (SPLIT_RING - 1)));
        const u8 *p = (const u8 *)(h + 1);
        u32 size = h->size, kind = h->kind, qwc = h->qwc;
        if (kind == 1) {
            u64 t = perf_stamp();
            paths[0].tag_lo = 0;
            paths[0].loops = 0;
            gif(&paths[0], p, qwc, 1);
            if (t) perf.gs_ns += perf_since(t);
        } else if (kind == 2 || kind == 3) {
            u64 t = perf_stamp();
            gif(&paths[kind == 2 ? 1 : 2], p, qwc, 0);
            if (t) perf.gs_ns += perf_since(t);
        } else if (kind == 4) {
            gsrec_flip();
            gpu_seal_frame();
            __atomic_add_fetch(&sp_flips_done, 1, __ATOMIC_RELEASE);
        }
        head += size;
        __atomic_store_n(&sp_head, head, __ATOMIC_RELEASE);
    }
    return NULL;
}

static int split_on(void) {
    if (sp_on < 0) {
        const char *e = getenv("SSTHEH_GSSPLIT"), *t = getenv("SSTHEH_GSTHREAD"), *r = getenv("SSTHEH_GSREC");
        int want = e && atoi(e) && !(t && !atoi(t)) && !(r && *r);
        if (want) {
            sp_ring = aligned_alloc(64, SPLIT_RING);
            pthread_t th;
            if (!sp_ring || pthread_create(&th, NULL, split_consumer, NULL)) want = 0;
            else { platform_thread_name(th, "gsx"); pthread_detach(th); }
        }
        sp_on = want;
        if (want) fprintf(stderr, "GS em dois threads: gs (VIF1/VU1) + gsx (pacotes GIF e desenho)\n");
    }
    return sp_on;
}

static void sp_wake(void) {
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
    if (__atomic_load_n(&sp_sleeping, __ATOMIC_SEQ_CST)) {
        pthread_mutex_lock(&sp_lock);
        pthread_cond_signal(&sp_cond);
        pthread_mutex_unlock(&sp_lock);
    }
}

/* reserva um registro com `payload` bytes (multiplo de 16); espera o consumidor liberar espaco */
static SplitHdr *sp_reserve(u32 payload) {
    u32 need = (u32)sizeof(SplitHdr) + payload;
    for (;;) {
        u32 off = (u32)(sp_tail & (SPLIT_RING - 1));
        u32 pad = off + need > SPLIT_RING ? SPLIT_RING - off : 0;
        u64 head = __atomic_load_n(&sp_head, __ATOMIC_ACQUIRE);
        if (SPLIT_RING - (sp_tail - head) >= (u64)need + pad) {
            if (pad) {                       /* nao cabe ate o fim do anel: salto (publicado junto com o proximo registro) */
                SplitHdr *s = (SplitHdr *)(sp_ring + off);
                s->kind = 0; s->qwc = 0; s->size = pad; s->pad = 0;
                sp_tail += pad;
                off = 0;
            }
            return (SplitHdr *)(sp_ring + off);
        }
        sched_yield();
    }
}

static void sp_commit(SplitHdr *h, u32 kind, u32 qwc) {
    h->kind = kind; h->qwc = qwc; h->size = (u32)sizeof *h + qwc * 16; h->pad = 0;
    sp_tail += h->size;
    __atomic_store_n(&sp_pub_tail, sp_tail, __ATOMIC_RELEASE);
    sp_wake();
}

/* quantos quadwords tem o pacote do XGKICK que comeca no byte `a` da memoria do VU1 (ate o EOP, com volta ao inicio) */
static u32 path1_qwords(const u8 *vu_mem, u32 a) {
    u32 pos = a / 16, total = 0;
    for (int guard = 0; guard < 1024; guard++) {
        u64 lo;
        memcpy(&lo, vu_mem + (pos & 0x3FF) * 16, 8);
        u32 nloop = lo & 0x7FFF, eop = (u32)(lo >> 15) & 1, flg = (u32)(lo >> 58) & 3, nreg = (u32)(lo >> 60) & 15;
        if (!nreg) nreg = 16;
        u32 data = flg == 0 ? nloop * nreg : flg == 1 ? (nloop * nreg + 1) / 2 : nloop;
        total += 1 + data;
        pos += 1 + data;
        if (eop || total >= 0x400) break;
    }
    return total > 0x400 ? 0x400 : total;
}

static void sp_put_copy(u32 kind, const u8 *data, u32 qwc) {
    SplitHdr *h = sp_reserve(qwc * 16);
    memcpy(h + 1, data, (size_t)qwc * 16);
    sp_commit(h, kind, qwc);
}

void gif_path1(const u8 *vu_mem, u32 addr) {
    if (!split_on()) { real_path1(vu_mem, addr); return; }
    u32 a = (addr & 0x3FF) * 16;
    u32 qw = path1_qwords(vu_mem, a);
    SplitHdr *h = sp_reserve(qw * 16);
    u8 *d = (u8 *)(h + 1);
    u32 first = (0x4000 - a) / 16;
    if (first > qw) first = qw;
    memcpy(d, vu_mem + a, (size_t)first * 16);
    if (qw > first) memcpy(d + first * 16, vu_mem, (size_t)(qw - first) * 16);
    sp_commit(h, 1, qw);
}

void gif_path2(const u8 *data, u32 qwc) {
    if (!split_on()) { real_path2(data, qwc); return; }
    sp_put_copy(2, data, qwc);
}

void gif_dma(const u8 *data, u32 qwc) {
    if (!split_on()) { real_dma(data, qwc); return; }
    sp_put_copy(3, data, qwc);
}

/* dmac.c (thread gs): um quadro novo. Com os dois threads, vai na fila, depois dos pacotes anteriores. */
void gs_job_flip(void) {
    if (!split_on()) { gsrec_flip(); gpu_seal_frame(); return; }
    while (sp_flips_in - __atomic_load_n(&sp_flips_done, __ATOMIC_ACQUIRE) >= SPLIT_MAX_FLIPS) sched_yield();
    SplitHdr *h = sp_reserve(0);
    sp_flips_in++;
    sp_commit(h, 4, 0);
}

'''
patch("port/gs/gs.c",
      "void gif_path1(const u8 *vu_mem, u32 addr) {\n    static int told;",
      "static void real_path1(const u8 *vu_mem, u32 addr) {\n    static int told;")
patch("port/gs/gs.c",
      "void gif_path2(const u8 *data, u32 qwc) {\n    u64 t = perf_stamp();",
      "static void real_path2(const u8 *data, u32 qwc) {\n    u64 t = perf_stamp();")
patch("port/gs/gs.c",
      "void gif_dma(const u8 *data, u32 qwc) {\n    u64 t = perf_stamp();",
      "static void real_dma(const u8 *data, u32 qwc) {\n    u64 t = perf_stamp();")
DISPLAY_MARK = "/* ------------------------------------------------------------------------------- display */"
patch("port/gs/gs.c", DISPLAY_MARK, SPLIT_BLOCK + DISPLAY_MARK)
patch("port/gs/dmac.c",
      "void gsrec_flip(void);\n",
      "void gsrec_flip(void);\nvoid gs_job_flip(void);               /* gs.c: com SSTHEH_GSSPLIT vai pela fila do gsx */\n")
patch("port/gs/dmac.c",
      "            gsrec_flip();\n            gpu_seal_frame();\n            pthread_mutex_lock(&qlock);",
      "            gs_job_flip();\n            pthread_mutex_lock(&qlock);")

# 11) prof.c: o profiler da nome tambem as funcoes static, pela tabela de simbolos do arquivo da biblioteca
SYM_BLOCK = r'''#ifdef __ANDROID__
#include <elf.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
/* Nome de uma funcao nao exportada (static): le a tabela de simbolos (.symtab) do arquivo da biblioteca,
 * que o app agora instala sem tirar os simbolos. */
typedef struct { unsigned long addr, size; const char *name; } SymEnt;
static SymEnt *sym_tab;
static int sym_n, sym_tried;
static int sym_cmp(const void *a, const void *b) {
    unsigned long x = ((const SymEnt *)a)->addr, y = ((const SymEnt *)b)->addr;
    return x < y ? -1 : x > y;
}
static void sym_load(const char *path) {
    if (sym_tried) return;
    sym_tried = 1;
    int fd = open(path, O_RDONLY);
    if (fd < 0) return;
    struct stat st;
    if (fstat(fd, &st)) { close(fd); return; }
    unsigned char *m = mmap(NULL, (size_t)st.st_size, PROT_READ, MAP_PRIVATE, fd, 0);
    close(fd);
    if (m == MAP_FAILED) return;
    const Elf64_Ehdr *eh = (const Elf64_Ehdr *)m;
    if (memcmp(eh->e_ident, ELFMAG, SELFMAG) || eh->e_ident[EI_CLASS] != ELFCLASS64) return;
    const Elf64_Shdr *sh = (const Elf64_Shdr *)(m + eh->e_shoff);
    for (int i = 0; i < eh->e_shnum; i++) {
        if (sh[i].sh_type != SHT_SYMTAB) continue;
        const Elf64_Sym *sy = (const Elf64_Sym *)(m + sh[i].sh_offset);
        int n = (int)(sh[i].sh_size / sizeof *sy);
        const char *str = (const char *)(m + sh[sh[i].sh_link].sh_offset);
        sym_tab = malloc((size_t)n * sizeof *sym_tab);
        if (!sym_tab) return;
        for (int k = 0; k < n; k++)
            if (ELF64_ST_TYPE(sy[k].st_info) == STT_FUNC && sy[k].st_size)
                sym_tab[sym_n++] = (SymEnt){sy[k].st_value, sy[k].st_size, str + sy[k].st_name};
        qsort(sym_tab, (size_t)sym_n, sizeof *sym_tab, sym_cmp);
        return;
    }
}
static const char *sym_name(const char *path, unsigned long off) {
    sym_load(path);
    int lo = 0, hi = sym_n - 1, best = -1;
    while (lo <= hi) {
        int mid = (lo + hi) / 2;
        if (sym_tab[mid].addr <= off) { best = mid; lo = mid + 1; } else hi = mid - 1;
    }
    if (best >= 0 && off < sym_tab[best].addr + sym_tab[best].size) return sym_tab[best].name;
    return NULL;
}
#else
static const char *sym_name(const char *path, unsigned long off) { (void)path; (void)off; return NULL; }
#endif

'''
patch("port/runtime/prof.c",
      "typedef struct { const char *name; int count; } Row;\n",
      SYM_BLOCK + "typedef struct { const char *name; int count; } Row;\n")
patch("port/runtime/prof.c",
      "        if (dladdr(samples[i], &info) && info.dli_sname && strcmp(info.dli_sname, \"vu_prog\")) name = info.dli_sname;\n",
      "        int dl_ok = dladdr(samples[i], &info);\n"
      "        if (dl_ok && info.dli_sname && strcmp(info.dli_sname, \"vu_prog\")) name = info.dli_sname;\n")
patch("port/runtime/prof.c",
      "        else {\n            /* not exported (static): the offset in the executable, for addr2line; 64-byte buckets */\n",
      "        else if (dl_ok && info.dli_fname &&\n"
      "                 (name = sym_name(info.dli_fname, (unsigned long)((char *)samples[i] - (char *)info.dli_fbase))) != NULL) {\n"
      "            /* named from the library's symbol table */\n"
      "        } else {\n            /* not exported (static): the offset in the executable, for addr2line; 64-byte buckets */\n")
