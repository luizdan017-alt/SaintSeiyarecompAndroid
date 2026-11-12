# Alteracoes do port Android

Arquivos novos em `android/` (app, CMake, patch_port.py). O codigo do jogo em `port/` so recebe os
ajustes de `android/patch_port.py`, aplicados pelo workflow `.github/workflows/android.yml`:

| Arquivo | Ajuste | Motivo |
|---|---|---|
| port/runtime/platform.c | `platform_sleep_until` usa o caminho do macOS no Android | `clock_nanosleep` so existe a partir da API 30 |
| port/hle/cdvd.c | `cdvd_open` aceita `fd:N` | ler a ISO direto do arquivo escolhido (Android), sem copiar 4 GB |
| port/gs/display.c | botoes do controle na tela somados ao controle 1; `touch_hud_poll` alterna o painel | controles touch (TouchOverlay.kt) |

Para ver tudo o que mudou em relacao ao projeto original: `git diff master..android -- port`.
