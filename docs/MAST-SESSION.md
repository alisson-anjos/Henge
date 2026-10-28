# Retomar teste MAST no Henge

Registro: 2026-10-27, Europe/Lisbon. Conferir os estados atuais antes de agir;
os valores abaixo são uma fotografia da sessão.

## Objetivo

Comparar a atenção regional experimental inspirada em LAMA/MAST no H3.
Não é uma implementação completa de MAST. Contexto técnico e protocolo:
`docs/regional-attention-experiment.md`.

Repositório: `/home/alissonerdx/Henge`.
Branch atual: `experimental/mast-region-attention`.
Teste controlado: trecho de 1,5 s, duas pessoas e duas referências, sem cortes,
rótulos desligados; manter seed, prompt e referências iguais.
ON: strength 0.5, reference_budget 0.35, layers `10,25,40`.

## Estado confirmado ao salvar

- OFF: `e0e0f7003be54db7b09420ea5b657f3b`, projeto `MAST A/B OFF`.
  Estado `cancelled`, mensagem `Cancelled by user`. Não retomar automaticamente.
  Ele havia sido recolocado na fila após o crash; depois apareceu cancelado.
- ON: `080d7667283e46e79f038bef12cbfece`, projeto `MAST A/B ON`.
  Estado `running`, etapa `h3_segment_000`, mensagem `Reading guide and references`.
- Ainda não foi feita comparação visual dos resultados nesta retomada.

## Ambiente e restrições

- UI local: http://127.0.0.1:8188 ; bridge: http://127.0.0.1:8766 .
- Apenas UI e bridge locais; geração no RunPod Serverless.
- Endpoint salvo: `gh0jclxp3q4i3j` (provider `runpod`).
- Não iniciar ComfyUI local para este teste.
- Não executar comandos Docker locais, inclusive consultas; builds somente no GitHub Actions.
- Build experimental do commit `ea36b9e` passou no GitHub Actions
  (run `40595837805`). A imagem efetivamente usada pelo worker não foi
  reconfirmada nesta retomada.

## Arquivos e retomada

- IDs A/B: `.runtime/mast-ab-jobs.json`.
- Registros persistentes: `.runtime/data/jobs/<id>/job.json`.
- Logs: `.runtime/logs/bridge.log` e `.runtime/logs/ui.log`.
- Configuração da conexão: `.runtime/data/connection.json`; contém credenciais,
  não imprimir nem copiar seu conteúdo integral.
- Inicializar somente UI e bridge, se as portas estiverem livres:

  ```bash
  cd /home/alissonerdx/Henge
  PYTHON=/home/alissonerdx/envs/comfyui/bin/python bash scripts/local_stack.sh start
  ```

  Manter os processos em uma sessão persistente e confirmar HTTP 200 na UI.
  A retomada desta sessão precisou manter o shell aberto para os processos
  sobreviverem ao encerramento do comando pela ferramenta.

- Consultar `GET http://127.0.0.1:8766/jobs` para estados atuais.
- Ao iniciar, o bridge marca jobs `running` como falhos e processa os jobs
  que já estavam na fila. Verificar o RunPod antes de repetir um job interrompido,
  para evitar trabalho duplicado. Não repetir o OFF cancelado sem nova instrução.
- Próximo passo: conferir conclusão do ON, imagem/capacidade de atenção regional
  no worker e resultados disponíveis; só então definir a comparação restante.

## Contexto do crash

O usuário relata queda de todo o WSL ao gerar MiniMax H3 com TARA no ComfyUI local.
Há desligamento não limpo e aviso anterior em
`dxgvmb_send_wait_sync_object_gpu` / `dxgkrnl`, sem OOM registrado na sessão
anterior. A causa não foi confirmada. A primeira atenção Kitchen terminou em
0,407 s antes da queda. Foi sugerido testar `flash partitions (no compile)` no
lugar de `comfy kitchen (experimental)`; essa alteração não foi feita pelo agente.
Esse diagnóstico é separado do teste MAST remoto.

## Reteste após diagnóstico do worker (2026-10-27)

- A repetição do ON falhou no worker `9s9qqzzohegmrn`. Logs confirmam
  8/8 passos seguidos de `Fatal Python error: Segmentation fault`,
  `comfy_aimdo/malloc_graph.py:74 __del__` via `cleanup_malloc_graph` /
  `cleanup_prefetch_queues`; processo ComfyUI terminou com exit -11.
  Não há evidência nesses registros de OOM.
- Logs preservados em `.runtime/logs/mast-failed-worker.jsonl`.
- Usuário autorizou repetir com DynamicVRAM desligado. Template `ouo6ep22pd`
  atualizado para `HENGE_COMFY_ARGS=--fast-disk --disable-dynamic-vram`,
  mantendo imagem `ghcr.io/alisson-anjos/henge:sha-ea36b9e`.
- Endpoint drenado até zero workers e restaurado para workersMax=2.
  Primeira tentativa após restauração recebeu 409 ENDPOINT_PAUSED por
  propagação da configuração; retentar após aguardar. Conferir estado atual.
- OFF continua cancelado; apenas ON é alvo deste reteste.

- Reteste ON com `--disable-dynamic-vram` concluído: status completed, 8/8,
  run_seconds=256.3. `result.mp4` e `comparison.mp4` disponíveis no job ON.
  Comparação visual A/B ainda pendente; OFF permanece cancelado.

- Usuário autorizou gerar OFF para comparação. Retry enviado para
  `e0e0f7003be54db7b09420ea5b657f3b`; request e assets iguais ao ON,
  options diferem somente em regional_attention.enabled=false.
  DynamicVRAM permanece desligado. Conferir conclusão antes de comparar.

- OFF concluído com sucesso após autorização: run_seconds=166.7;
  result.mp4 e comparison.mp4 disponíveis no job e0e0f7003be54db7b09420ea5b657f3b.

## Direção atual: teste local BFS + TARA (salvo a pedido do usuário)

A implementação local foi instalada, com workflow pronto para o usuário testar.
Registro completo de retomada:
`/home/alissonerdx/tools/ComfyUI-BFSNodes-main/docs/MAST-SESSION.md`.
Cópia também no plugin instalado `custom_nodes/bfsnodes/docs/MAST-SESSION.md`.

Workflow: `/mnt/d/Downloads/tara-mast-local.comfy.json`
(`D:\Downloads\tara-mast-local.comfy.json`) e user/default/workflows do ComfyUI.
Novo node BFSH3MAST depois do TARA; SAM por clique sem cores no guia; ON/OFF
independente. 43 testes CPU passaram, 1 skipped; sem geração GPU local pelo agente.
Reiniciar ComfyUI com --disable-dynamic-vram, selecionar pessoas com setup_only=true,
depois desligar setup_only e gerar. Primeiro teste VHS=39 frames, strength=.5,
budget=.35, layers=10,25,40. Original preservado.
Pedido original do workflow usa Picture1 personagem/Picture2 cenário; para duas
identidades, alterar pedido e referências e selecionar cada pessoa.
Não iniciar geração nem repetir testes remotos automaticamente na retomada.

## 2026-10-28: IDAG Attention local

Usuário solicitou implementação de IDAG no BFS. Adaptação LG-CA/ID-SA para
H3/TARA concluída, 55 testes CPU passaram / 1 skipped, sem geração GPU local.
Registro mais recente: `/home/alissonerdx/tools/ComfyUI-BFSNodes-main/docs/IDAG-SESSION.md`.
Workflow: `D:\Downloads\tara-idag-local.comfy.json`. Não é IDAG-Edit completo:
sem inversão/reconstrução/null-text/IA-STDG por gradientes. MAST preservado.

- Memória atualizada novamente a pedido do usuário (risco de crash): ler
  `/home/alissonerdx/tools/ComfyUI-BFSNodes-main/docs/IDAG-SESSION.md`.
  Inclui associação Picture→clique→SAM→IDAG e estado do teste local pendente.
