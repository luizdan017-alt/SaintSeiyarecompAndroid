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
    struct stat st;
    if (stat(dest, &st) == 0 && (u32)st.st_size == size) return 0;      /* ja extraido */
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
    char *args[] = {"sstheh", "--iso", (char *)iso, exe, NULL};
    ALOG("iniciando o motor");
    return ss_main(4, args);
}
