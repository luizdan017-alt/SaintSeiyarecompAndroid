#define _GNU_SOURCE
/* Ponto de entrada do motor no Android (SDL_main). Prepara o que o main() original espera:
 *  - guarda o log em <files>/sstheh.log (o app mostra na tela inicial)
 *  - le a ISO direto do descritor recebido do Android ("fd:N", sem copiar)
 *  - extrai da ISO o executavel do jogo (pequeno) para <files>/disc/ na primeira vez
 * e entrega ao main() original (renomeado ss_main) a linha de comando "--iso fd:N <executavel>". */
#include <dirent.h>
#include <fcntl.h>
#include <pthread.h>
#include <sched.h>
#include <sys/resource.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include <android/log.h>
#include <jni.h>

typedef unsigned int u32;
typedef unsigned char u8;
int cdvd_open(const char *path);
int cdvd_find(const char *path, u32 *lsn, u32 *size);
int cdvd_read(u32 lsn, u32 count, u8 *out);
int ss_main(int argc, char **argv);

#define ALOG(...) __android_log_print(ANDROID_LOG_INFO, "sstheh", __VA_ARGS__)

/* nome do executavel que o disco inicia (SYSTEM.CNF: BOOT2 = cdrom0:\NOME;1) */
static const char *boot_exe_name(void) {
    static char name[32];
    u32 lsn, size;
    u8 buf[2048];
    if (!cdvd_find("\\SYSTEM.CNF;1", &lsn, &size) || cdvd_read(lsn, 1, buf)) return NULL;
    buf[size < sizeof buf ? size : sizeof buf - 1] = 0;
    const char *p = strstr((const char *)buf, "cdrom0:\\");
    if (!p) return NULL;
    p += 8;
    int n = 0;
    while (p[n] && p[n] != ';' && p[n] != '\r' && p[n] != '\n' && n < (int)sizeof name - 1) { name[n] = p[n]; n++; }
    name[n] = 0;
    return n ? name : NULL;
}

static int extract(const char *name, const char *dest) {
    char key[64];
    u32 lsn, size;
    snprintf(key, sizeof key, "\\%s;1", name);
    if (!cdvd_find(key, &lsn, &size)) { fprintf(stderr, "o disco nao tem %s\n", name); return -1; }
    FILE *f = fopen(dest, "wb");
    if (!f) { fprintf(stderr, "nao consegui criar %s\n", dest); return -1; }
    static u8 buf[2048 * 32];
    for (u32 done = 0; done < size;) {
        u32 left = (size - done + 2047) / 2048, n = left < 32 ? left : 32;
        if (cdvd_read(lsn + done / 2048, n, buf)) { fprintf(stderr, "leitura da ISO falhou\n"); fclose(f); remove(dest); return -1; }
        u32 bytes = n * 2048 < size - done ? n * 2048 : size - done;
        fwrite(buf, 1, bytes, f);
        done += bytes;
    }
    fclose(f);
    fprintf(stderr, "extraido %s (%u bytes)\n", name, size);
    return 0;
}



/* ---- nucleos rapidos: os threads pesados (jogo, GS, EE, IOP, tela) ficam so nos nucleos "grandes" ----
 * Celulares tem nucleos rapidos e lentos; o motor e limitado pelo thread do jogo, e num nucleo lento ele
 * anda bem menos. Os nucleos rapidos sao os de frequencia maxima maior que a dos mais lentos. */
static int big_n;
static cpu_set_t big_set;
static void init_big(void) {
    static int done;
    if (done) return;
    done = 1;
    long n = sysconf(_SC_NPROCESSORS_CONF), f[32], minf = 0, maxf = 0;
    if (n < 2 || n > 32) return;
    for (int i = 0; i < n; i++) {
        char p[96];
        snprintf(p, sizeof p, "/sys/devices/system/cpu/cpu%d/cpufreq/cpuinfo_max_freq", i);
        FILE *fp = fopen(p, "r");
        f[i] = 0;
        if (fp) { if (fscanf(fp, "%ld", &f[i]) != 1) f[i] = 0; fclose(fp); }
        if (f[i] <= 0) { fprintf(stderr, "afinidade: nao consegui ler a frequencia da CPU %d\n", i); return; }
        if (!minf || f[i] < minf) minf = f[i];
        if (f[i] > maxf) maxf = f[i];
    }
    if (maxf * 100 < minf * 105) { fprintf(stderr, "afinidade: todos os nucleos sao iguais\n"); return; }
    CPU_ZERO(&big_set);
    for (int i = 0; i < n; i++)
        if (f[i] * 100 > minf * 105) { CPU_SET(i, &big_set); big_n++; }
    fprintf(stderr, "afinidade: %d nucleos rapidos de %ld (frequencias %ld a %ld kHz)\n", big_n, n, minf, maxf);
}

/* chamada por platform_thread_name (port/runtime/platform.c) e pelo SDL_main */
void android_pin_thread(pthread_t t, const char *name) {
    init_big();
    if (!big_n) return;
    if (strcmp(name, "game") && strcmp(name, "gs") && strcmp(name, "gsx") && strncmp(name, "ee-", 3) && strncmp(name, "iop-", 4) && strcmp(name, "main")) return;
    pid_t tid = pthread_gettid_np(t);
    if (sched_setaffinity(tid, sizeof big_set, &big_set)) fprintf(stderr, "afinidade de %s falhou\n", name);
    if (!strcmp(name, "game") || !strcmp(name, "gs") || !strcmp(name, "gsx") || !strcmp(name, "main")) setpriority(PRIO_PROCESS, tid, -4);
}


/* ---- uso de CPU por thread (nome, %, nucleo, frequencia): /proc/self/task e cpufreq ----
 * O painel do jogo soma tudo em "CPU"; aqui da para ver qual thread esta no limite. */
typedef struct { int tid; unsigned long ticks; char name[20]; int cpu; double pct; } Th;
static Th th_prev[256], th_cur[256];
static int th_nprev;
static double th_prev_t;

static double mono_s(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec / 1e9;
}

static int read_threads(Th *out, int max) {
    DIR *d = opendir("/proc/self/task");
    if (!d) return 0;
    int n = 0;
    struct dirent *e;
    while ((e = readdir(d)) && n < max) {
        int tid = atoi(e->d_name);
        if (tid <= 0) continue;
        char p[64], buf[600];
        snprintf(p, sizeof p, "/proc/self/task/%d/stat", tid);
        FILE *f = fopen(p, "r");
        if (!f) continue;
        size_t k = fread(buf, 1, sizeof buf - 1, f);
        fclose(f);
        buf[k] = 0;
        char *lp = strchr(buf, '('), *rp = strrchr(buf, ')');
        if (!lp || !rp || rp < lp) continue;
        Th *t = &out[n];
        size_t nl = (size_t)(rp - lp - 1);
        if (nl > 15) nl = 15;
        memcpy(t->name, lp + 1, nl);
        t->name[nl] = 0;
        t->tid = tid;
        unsigned long ut = 0, st = 0;
        int cpu = -1, field = 3;
        char *s2 = rp + 2;
        while (*s2) {                       /* campos do /proc/PID/stat: 14 utime, 15 stime, 39 processador */
            char *sp = strchr(s2, ' ');
            if (sp) *sp = 0;
            if (field == 14) ut = strtoul(s2, NULL, 10);
            else if (field == 15) st = strtoul(s2, NULL, 10);
            else if (field == 39) { cpu = atoi(s2); break; }
            if (!sp) break;
            s2 = sp + 1;
            field++;
        }
        t->ticks = ut + st;
        t->cpu = cpu;
        t->pct = 0;
        n++;
    }
    closedir(d);
    return n;
}

static long cpu_khz(int c) {
    char p[96];
    snprintf(p, sizeof p, "/sys/devices/system/cpu/cpu%d/cpufreq/scaling_cur_freq", c);
    FILE *f = fopen(p, "r");
    if (!f) return -1;
    long v = -1;
    if (fscanf(f, "%ld", &v) != 1) v = -1;
    fclose(f);
    return v;
}

/* texto com as 6 threads que mais usaram CPU desde a chamada anterior + a frequencia dos nucleos */
void android_make_stats(char *out, size_t cap) {
    double now = mono_s(), dt = now - th_prev_t;
    int n = read_threads(th_cur, 256);
    long hz = sysconf(_SC_CLK_TCK);
    if (hz <= 0) hz = 100;
    for (int i = 0; i < n; i++)
        for (int j = 0; j < th_nprev; j++)
            if (th_prev[j].tid == th_cur[i].tid && dt > 0.05) {
                th_cur[i].pct = 100.0 * (double)(th_cur[i].ticks - th_prev[j].ticks) / (double)hz / dt;
                break;
            }
    for (int a = 0; a < n && a < 6; a++) {      /* as 6 maiores */
        int best = a;
        for (int b = a + 1; b < n; b++) if (th_cur[b].pct > th_cur[best].pct) best = b;
        Th t = th_cur[a]; th_cur[a] = th_cur[best]; th_cur[best] = t;
    }
    size_t o = 0;
    out[0] = 0;
    for (int i = 0; i < n && i < 6; i++) {
        long f = th_cur[i].cpu >= 0 ? cpu_khz(th_cur[i].cpu) : -1;
        char fr[16] = "";
        if (f > 0) snprintf(fr, sizeof fr, " %.1fGHz", f / 1e6);
        o += (size_t)snprintf(out + o, cap - o, "%-9.9s %3.0f%%  cpu%d%s\n", th_cur[i].name, th_cur[i].pct, th_cur[i].cpu, fr);
        if (o >= cap) return;
    }
    long nc = sysconf(_SC_NPROCESSORS_CONF);
    if (nc > 0 && nc <= 16 && o + 64 < cap) {
        o += (size_t)snprintf(out + o, cap - o, "clock:");
        for (int c = 0; c < nc; c++) {
            long f = cpu_khz(c);
            if (f > 0) o += (size_t)snprintf(out + o, cap - o, " %.1f", f / 1e6);
            else o += (size_t)snprintf(out + o, cap - o, " ?");
        }
        snprintf(out + o, cap - o, " GHz");
    }
    memcpy(th_prev, th_cur, (size_t)n * sizeof *th_cur);   /* (so as 6 primeiras ficam ordenadas; o resto vem desordenado) */
    th_nprev = n;
    th_prev_t = now;
}

/* ---- diagnostico do executavel extraido: tamanho, FNV-1a 64 (o que o jogo confere) e SHA-1 ---- */
static u32 rol(u32 v, int n) { return v << n | v >> (32 - n); }
static void sha1_block(u32 h[5], const u8 *p) {
    u32 w[80];
    for (int i = 0; i < 16; i++) w[i] = (u32)p[4*i] << 24 | p[4*i+1] << 16 | p[4*i+2] << 8 | p[4*i+3];
    for (int i = 16; i < 80; i++) w[i] = rol(w[i-3] ^ w[i-8] ^ w[i-14] ^ w[i-16], 1);
    u32 a = h[0], b = h[1], c = h[2], d = h[3], e = h[4];
    for (int i = 0; i < 80; i++) {
        u32 f, k;
        if (i < 20) { f = (b & c) | (~b & d); k = 0x5A827999; }
        else if (i < 40) { f = b ^ c ^ d; k = 0x6ED9EBA1; }
        else if (i < 60) { f = (b & c) | (b & d) | (c & d); k = 0x8F1BBCDC; }
        else { f = b ^ c ^ d; k = 0xCA62C1D6; }
        u32 t = rol(a, 5) + f + e + k + w[i];
        e = d; d = c; c = rol(b, 30); b = a; a = t;
    }
    h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e;
}
static void describe(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) return;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    u8 *b = malloc(n > 0 ? (size_t)n : 1);
    if (!b || fread(b, 1, (size_t)n, f) != (size_t)n) { fclose(f); free(b); return; }
    fclose(f);
    unsigned long long fnv = 0xCBF29CE484222325ull;
    for (long i = 0; i < n; i++) fnv = (fnv ^ b[i]) * 0x100000001B3ull;
    u32 h[5] = {0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0};
    long full = n / 64 * 64;
    for (long i = 0; i < full; i += 64) sha1_block(h, b + i);
    u8 last[128] = {0};
    long rest = n - full;
    memcpy(last, b + full, (size_t)rest);
    last[rest] = 0x80;
    int tot = rest < 56 ? 64 : 128;
    unsigned long long bits = (unsigned long long)n * 8;
    for (int i = 0; i < 8; i++) last[tot - 1 - i] = (u8)(bits >> (8 * i));
    for (int i = 0; i < tot; i += 64) sha1_block(h, last + i);
    fprintf(stderr, "executavel extraido: tamanho=%ld fnv=%016llX sha1=%08x%08x%08x%08x%08x\n", n, fnv, h[0], h[1], h[2], h[3], h[4]);
    fprintf(stderr, "primeiros bytes: %02X %02X %02X %02X (um ELF comeca com 7F 45 4C 46)\n", b[0], b[1], b[2], b[3]);
    fprintf(stderr, "esperado (EU SLES-54162): fnv=61BAC351F3463E34 sha1=7ba6b0a1c05a94f28452840fcb73c204e46e79e6\n");
    fprintf(stderr, "esperado (JP SLPS-25744): fnv=1855DF702BBE6B8D\n");
    free(b);
}

__attribute__((visibility("default"))) int SDL_main(int argc, char **argv) {
    (void)argc; (void)argv;
    const char *files = getenv("SS_FILES"), *iso = getenv("SS_ISO");
    if (!files) { ALOG("SS_FILES nao definido"); return 1; }
    char path[1200];
    snprintf(path, sizeof path, "%s/sstheh.log", files);
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC | O_APPEND, 0644);
    if (fd >= 0) { dup2(fd, 1); dup2(fd, 2); }
    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);
    android_pin_thread(pthread_self(), "main");
    if (chdir(files)) fprintf(stderr, "chdir(%s) falhou\n", files);
    mkdir("data", 0755);
    mkdir("disc", 0755);
    fprintf(stderr, "sstheh android: files=%s iso=%s\n", files, iso ? iso : "(nenhuma)");
    if (!iso) { fprintf(stderr, "nenhuma ISO recebida\n"); return 1; }
    if (cdvd_open(iso)) { fprintf(stderr, "nao consegui abrir a ISO (%s)\n", iso); return 1; }
    const char *boot = boot_exe_name();
    if (!boot) { fprintf(stderr, "a ISO nao tem SYSTEM.CNF: nao e um disco de PS2?\n"); return 1; }
    fprintf(stderr, "executavel do disco: %s\n", boot);
    char exe[1200];
    snprintf(exe, sizeof exe, "%s/disc/%s", files, boot);
    if (extract(boot, exe)) return 1;
    describe(exe);
    char *args[] = {"sstheh", "--iso", (char *)iso, exe, NULL};
    ALOG("iniciando o motor");
    return ss_main(4, args);
}

/* ---- controle na tela (TouchOverlay.kt -> NativePad): botoes do PS2 e analogico esquerdo ---- */
volatile unsigned short touch_pad_buttons;     /* lido por poll_pads() em port/gs/display.c */
volatile int touch_hud_toggle;                 /* pedido de mostrar/esconder o painel de desempenho */
extern volatile unsigned char pad_sticks[2][4];/* port/iop/pad.c: RX RY LX LY, 128 = centro */

JNIEXPORT void JNICALL Java_com_luizdan_sstheh_NativePad_set(JNIEnv *env, jclass cls, jint buttons, jint lx, jint ly) {
    (void)env; (void)cls;
    touch_pad_buttons = (unsigned short)buttons;
    pad_sticks[0][2] = (unsigned char)(lx < 0 ? 0 : lx > 255 ? 255 : lx);
    pad_sticks[0][3] = (unsigned char)(ly < 0 ? 0 : ly > 255 ? 255 : ly);
}

JNIEXPORT void JNICALL Java_com_luizdan_sstheh_NativePad_hud(JNIEnv *env, jclass cls) {
    (void)env; (void)cls;
    touch_hud_toggle = 1;
}

static unsigned stats_calls;

JNIEXPORT jstring JNICALL Java_com_luizdan_sstheh_NativePad_stats(JNIEnv *env, jclass cls) {
    (void)cls;
    char buf[700];
    android_make_stats(buf, sizeof buf);
    if (++stats_calls % 4 == 0) {            /* uma linha no log a cada ~4 s */
        char one[700];
        size_t o = 0;
        for (const char *p = buf; *p && o + 4 < sizeof one; p++) { one[o++] = *p == '\n' ? '|' : *p; }
        one[o] = 0;
        fprintf(stderr, "[threads] %s\n", one);
    }
    return (*env)->NewStringUTF(env, buf);
}

/* profiler (SSTHEH_PROF): 0 = recomeca a contagem; 1 = imprime o relatorio no log (numa thread, sem travar a tela) */
void prof_reset(void);
void prof_report(void);
static void *prof_thread(void *a) { (void)a; prof_report(); return NULL; }

JNIEXPORT void JNICALL Java_com_luizdan_sstheh_NativePad_prof(JNIEnv *env, jclass cls, jint op) {
    (void)env; (void)cls;
    if (op == 0) { prof_reset(); return; }
    pthread_t t;
    if (pthread_create(&t, NULL, prof_thread, NULL) == 0) pthread_detach(t);
}
