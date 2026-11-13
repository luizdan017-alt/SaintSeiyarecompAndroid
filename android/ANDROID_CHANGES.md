# Alteracoes do port Android

Arquivos novos em `android/` (app, CMake, patch_port.py). O codigo do jogo em `port/` so recebe os
ajustes de `android/patch_port.py`, aplicados pelo workflow `.github/workflows/android.yml`:

| Arquivo | Ajuste | Motivo |
|---|---|---|
| port/runtime/platform.c | `platform_sleep_until` usa o caminho do macOS no Android | `clock_nanosleep` so existe a partir da API 30 |
| port/hle/cdvd.c | `cdvd_open` aceita `fd:N` | ler a ISO direto do arquivo escolhido (Android), sem copiar 4 GB |
| port/gs/display.c | botoes do controle na tela somados ao controle 1; `touch_hud_poll` alterna o painel | controles touch (TouchOverlay.kt) |
| port/iop/iop.c | aviso "queue full" limitado | inundava o log (milhares de linhas) |
| port/runtime/platform.c | threads pesados ficam nos nucleos rapidos | o thread do jogo e o limite de velocidade |
| port/hle/cdvd.c | aviso de leitura lenta da ISO (>= 100 ms) | achar as travadas |

Para ver tudo o que mudou em relacao ao projeto original: `git diff master..android -- port`.

## Desempenho (variaveis de ambiente, definidas em GameActivity.kt)
`SSTHEH_SCALE` (resolucao interna, padrao 1), `SSTHEH_VSYNC=1`, `SSTHEH_INTERP=0`, `SSTHEH_PERF_LOG=1`.
O padrao do projeto escolhia escala 3 neste aparelho (alvos de 3072x3072) e nao limitava os fps.

Compilacao: codigo EU em -O2 (JP em -O1), sem stack protector/FORTIFY, simbolos escondidos (chamadas diretas),
`-mtune=cortex-a73` quando o compilador aceita.
