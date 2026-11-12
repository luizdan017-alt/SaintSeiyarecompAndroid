/* Ponto de entrada do motor no Android (SDL_main). Prepara o que o main() original espera:
 *  - guarda o log em <files>/sstheh.log (o app mostra na tela inicial)
 *  - le a ISO direto do descritor recebido do Android ("fd:N", sem copiar)
 *  - extrai da ISO o executavel do jogo (pequeno) para <files>/disc/ na primeira vez
 * e entrega ao main() original (renomeado ss_main) a linha de comando "--iso fd:N <executavel>". */
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include <android/log.h>

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

int SDL_main(int argc, char **argv) {
    (void)argc; (void)argv;
    const char *files = getenv("SS_FILES"), *iso = getenv("SS_ISO");
    if (!files) { ALOG("SS_FILES nao definido"); return 1; }
    char path[1200];
    snprintf(path, sizeof path, "%s/sstheh.log", files);
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC | O_APPEND, 0644);
    if (fd >= 0) { dup2(fd, 1); dup2(fd, 2); }
    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);
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
