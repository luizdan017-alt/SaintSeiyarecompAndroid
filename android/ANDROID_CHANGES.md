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
| port/runtime/r5900.h, memory.c | RAM do jogo como vetor estatico; `rt_ptr` com caminho rapido; `ENTER` vazio | menos instrucoes em cada acesso a memoria e em cada funcao |
| port/runtime/cpu.c | `rt_call` usa tabela direta | trocar a busca binaria (~14 passos) em cada chamada indireta |
| port/gs/display.c | relatorio do profiler tambem ao fechar a partida | medir o desempenho no celular |
| port/runtime/prof.c | `prof_reset` | o botao PROF recomeca a medicao no meio da partida |
| port/gs/display.c | rotulo "game" do painel vira "resto" | e o que sobra do total, nao so o thread do jogo |
| port/gs/gs.c, port/gs/dmac.c | `SSTHEH_GSSPLIT=1`: pacotes GIF vao por uma fila para o thread `gsx` | VU1 e GS em dois nucleos (experimental, desligado por padrao) |
| port/runtime/prof.c | nomes das funcoes `static` pela tabela de simbolos | profiler legivel |
| port/hle/cdvd.c | leitura adiantada de 2 MB quando a leitura e em sequencia | leituras de ~40 KB pelo FUSE chegavam a 1,4 s |
| port/gs/display.c | `android_render_frames()` (vigia) e a interpolacao nao mistura texturas diferentes | achar travadas da tela e evitar partes deformadas |

Para ver tudo o que mudou em relacao ao projeto original: `git diff master..android -- port`.

## Desempenho (variaveis de ambiente, definidas em GameActivity.kt)
`SSTHEH_SCALE` (resolucao interna, padrao 1), `SSTHEH_VSYNC=1`, `SSTHEH_INTERP=0`, `SSTHEH_PERF_LOG=1`.
O padrao do projeto escolhia escala 3 neste aparelho (alvos de 3072x3072) e nao limitava os fps.

Compilacao: codigo EU em -O2 (JP em -O1), sem stack protector/FORTIFY, simbolos escondidos (chamadas diretas),
`-mtune=cortex-a73` quando o compilador aceita.

## Jogo: opcoes do app (variaveis de ambiente)
`SSTHEH_50HZ` (padrao ligado), `SSTHEH_WIDESCREEN=0` (tela 4:3). `SSTHEH_30FPS_SCENES` nao e mais definido:
com ele o jogo espera o vblank em cada quadro das cenas e, abaixo de 50 fps, cai em degraus (25 fps).

`SSTHEH_UNLOCK_ALL=1` (opcao do app) e `SSTHEH_PROF=1` (opcao do app; relatorio no log ao sair).
Os simbolos ficam visiveis e o link usa `-Wl,-Bsymbolic` (em vez de `-fvisibility=hidden`) para o profiler dar nomes.

## Modo rapido (GS em 2 threads)
`SSTHEH_GSSPLIT=1`: o thread `gs` (VIF1 + VU1) copia cada pacote GIF para um anel de 16 MB e o thread `gsx` o
interpreta, na mesma ordem. O EE nao le o estado do GS (o CSR so devolve vblanks), entao o jogo nao ve diferenca.
No maximo 2 quadros novos esperam o `gsx`. Testado so numa bancada no PC (194 mil itens, ordem e conteudo iguais).

## Interpolacao de quadros
`SSTHEH_INTERP` volta ao padrao do projeto (ligada). Desligada (`SSTHEH_INTERP=0`, opcao do app) cada quadro do jogo
aparece como veio, e quando o jogo oscila entre 25 e 40 fps o tempo entre quadros fica irregular (tremida).

## Interruptores no jogo
Botoes INT (interpolacao) e 16:9 (widescreen) no topo da tela do jogo: `touch_hud_toggle` ganhou bits (1 HUD, 2 widescreen,
4 interpolacao, 8 vsync), tratados em `touch_hud_poll()` (port/gs/display.c). Serve para comparar uma falha visual na hora.

## Niveis de otimizacao (workflow)
`Run workflow` pede `ee_opt` e `vu_opt` (O2 ou O1). O1 e o nivel do projeto original; serve para ver se uma falha vem do -O2.

## Interpolacao: correspondencia de vertices
`interpolate()` (port/gs/display.c) agora so mistura um desenho se TODOS os vertices tem a mesma profundidade (<= 0,1) e as
mesmas coordenadas de textura (<= 2 texels, ou 0,03 em STQ) nos dois quadros. Com a interpolacao desligada as manchas pretas
nas colunas nao apareciam; com ela ligada apareciam.
