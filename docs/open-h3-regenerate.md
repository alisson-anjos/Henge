# Open-H3 Regenerate no Sharpness

O modo **Open-H3 Refiner + LMS · padrão**, primeira opção e seleção inicial do dropdown de upscale do Sharpness, executa primeiro a nitidez LMS do Henge e depois uma segunda passagem generativa. Pode alterar detalhes: compare sempre com o vídeo original.

A segunda passagem usa a mesma base Ref2VA já instalada, carregada em uma cadeia independente de LoRAs, DMAD 4-step, o refiner rank 16 do Kijai e nosso LMS v1.0 r64 em strength 1.0. Esse arquivo contém **somente o refiner**, sem LMS e sem LightX2V Turbo. O LMS é carregado separadamente nas duas passagens, uma vez por cadeia de modelo. Na segunda passagem, `MiniMaxH3AddGuide` ancora o vídeo original do shot na resolução final, começando no frame 0.

O grafo adapta `minimax_h3_2stage_testing.json`: upscaler latente nativo, descrição textual mais Add Guide do vídeo original na segunda passagem e sampler `er_sde`. Selecionar esse método na interface preenche a primeira passagem com **DMAD 4-step, 4 passos e CFG 1**. Esses controles continuam editáveis após a seleção. O refiner tem passos independentes: o padrão usa dois passos (`0.7, 0.494118, 0`); três passos são experimentais (`0.909375, 0.857143, 0.666667, 0`), a partir do schedule alternativo não conectado no workflow. O DMAD público usado aqui é avg rank 39, diferente do arquivo rank 83 local daquele workflow. A base Ref2VA também difere da FL2VA do workflow fornecido. Essa combinação é experimental e não é uma reprodução idêntica da inferência CUDA da NVIDIA.

## Instalação no worker

O Dockerfile agora fixa o ComfyUI em `35060f0156181ae78a86b10f098f67ce8e83697f`, que inclui `MiniMaxH3LatentUpscaleWithModel`. Atualizar apenas o frontend não instala esse node no worker. Reconstrua e publique a imagem do worker e atualize o endpoint para essa imagem.

### Pod normal / instalação local

Adicione `regenerate` aos perfis existentes em `HENGE_MODEL_PROFILES` (por exemplo,
`character,sharpness,regenerate`) e reinicie o pod com a imagem atualizada. O perfil é opcional;
reaproveita a base Ref2VA comum e não baixa nem exige FL2VA. Para instalação manual:

```bash
python scripts/download_models.py --models-dir /opt/ComfyUI/models --profiles sharpness,regenerate
```

### RunPod Serverless

**Workers Serverless não executam o downloader.** Acrescentar o perfil apenas nas variáveis do
worker não instala os pesos. Use um pod temporário para completar o volume ligado ao endpoint:

```bash
VOLUME_ID=<volume-existente> DATACENTER=<datacenter-do-volume> \
  PROFILES=regenerate scripts/runpod_volume.sh
```

Depois, atualize a imagem do template do worker e recicle os workers antigos quando não houver
jobs ativos. Preserve o mesmo volume. O volume aparece em `/workspace/henge/models` no pod de
download e em `/runpod-volume/henge/models` no worker; ambos são o mesmo armazenamento persistente.

O bridge guarda o inventário retornado pelo worker. Após a atualização, execute pelo Henge um
job curto com outro método disponível e recarregue a página. Isso atualiza o cache sem precisar
reinstalar o bridge. `/health` e **Test connection** não acordam o worker para buscar um novo inventário.
Uma chamada direta de `inventory` no RunPod não atualiza automaticamente o cache do bridge.

Veja o [procedimento completo Serverless](SERVERLESS.md#enable-refiner--lms-on-an-existing-endpoint).

### Dependências que habilitam o dropdown

| Tipo | Arquivo em `models/` |
| --- | --- |
| Base já usada pelo Henge | `diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors` |
| DMAD | `loras/henge/minimax_h3_DMAD_4step_full_lora_avg_rank_39_bf16.safetensors` |
| Refiner | `loras/henge/minimax_h3_open_regenerate_2k_refiner_rank_16_bf16.safetensors` |
| LMS | `loras/henge/minimax_h3_lms_v1.0_r64.safetensors` |
| Upscaler nativo | `latent_upscale_models/minimax_h3_latent_upscaler_3d_conv_v1_bf16.safetensors` |

Os nodes verificados são `MiniMaxH3LatentUpscaleWithModel`, `LatentUpscaleModelLoader`,
`ManualSigmas`, `BasicGuider` e `MiniMaxH3AddGuide`. O upscaler LMS anterior não substitui o
upscaler nativo listado acima. Um worker antigo pode ter os pesos e continuar sem os nodes necessários.
O diagnóstico está em `regenerate.missing_nodes` e `regenerate.missing_models` na resposta do
bridge `/health` (pela UI: `/api/backend/health`).

## Uso e limites

Ao entrar em Nitidez, resoluções de 480p/720p passam para **1080p**, compatível com o método padrão. Também é possível escolher **2K**. O dropdown e o campo **Prompt do refiner (opcional)** ficam no painel principal de criação, fora de Avançado. Configurações salvas com método explícito continuam sendo respeitadas. A primeira passagem roda com lado curto de 768 pixels; a segunda recebe as dimensões finais explicitamente, preservando a orientação do vídeo. 4K não está habilitado para este método.

Informe uma descrição fiel da cena ou deixe vazio para o VLM configurado descrever os frames. Essa descrição é separada da instrução técnica LMS e pode ser revisada no plano do job. Não depende do Molmo local. Em clipes com vários shots, a descrição automática cobre o intervalo inteiro; valide especialmente os cortes e cenas diferentes.

Os testes automatizados verificam montagem do grafo, schedules, áudio, resolução e bloqueio de dependências ausentes. Ainda é necessário testar qualidade, tempo e VRAM no worker atualizado; não há estimativa de capacidade nem resultado visual validado deste modo.

Fontes: [workflow/modelos Kijai](https://huggingface.co/Kijai/MiniMax-H3-experimental), [node nativo ComfyUI](https://github.com/Comfy-Org/ComfyUI/commit/35060f0156181ae78a86b10f098f67ce8e83697f), [modelo NVIDIA](https://huggingface.co/Efficient-Large-Model/Open-H3-Regenerate-2K).
