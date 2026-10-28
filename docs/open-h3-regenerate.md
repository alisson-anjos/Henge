# Open-H3 Regenerate no Sharpness

O modo opcional **Open-H3 Regenerate 2K · refiner rank 16 (experimental)** executa primeiro a nitidez LMS do Henge e depois uma segunda passagem generativa. Pode alterar detalhes: compare sempre com o vídeo original.

A segunda passagem usa uma base FL2VA independente, DMAD 4-step, o refiner rank 16 do Kijai e nosso LMS v1.0 r64 em strength 1.0. Esse arquivo contém **somente o refiner**, sem LMS e sem LightX2V Turbo. O LMS é carregado separadamente nas duas passagens, uma vez por base. Na segunda passagem, `MiniMaxH3AddGuide` ancora o vídeo original do shot na resolução final, começando no frame 0.

O grafo adapta `minimax_h3_2stage_testing.json`: upscaler latente nativo, descrição textual mais Add Guide do vídeo original na segunda passagem e sampler `er_sde`. O padrão usa dois passos (`0.7, 0.494118, 0`); três passos são experimentais (`0.909375, 0.857143, 0.666667, 0`), a partir do schedule alternativo não conectado no workflow. O DMAD público usado aqui é avg rank 39, diferente do arquivo rank 83 local daquele workflow. Não é uma reprodução idêntica da inferência CUDA da NVIDIA.

## Instalação no worker

O Dockerfile agora fixa o ComfyUI em `35060f0156181ae78a86b10f098f67ce8e83697f`, que inclui `MiniMaxH3LatentUpscaleWithModel`. Atualizar apenas o frontend não instala esse node no worker. Reconstrua e publique a imagem do worker e atualize o endpoint para essa imagem.

Adicione `regenerate` aos perfis existentes em `HENGE_MODEL_PROFILES` (por exemplo, `character,sharpness,regenerate`). O perfil é opcional para não forçar o download de outra base em todas as instalações. Para instalação manual:

```bash
python scripts/download_models.py --models-dir /opt/ComfyUI/models --profiles sharpness,regenerate
```

O manifesto fornece a base FL2VA INT8, DMAD, o refiner rank 16, LMS e `minimax_h3_latent_upscaler_3d_conv_v1_bf16.safetensors`. O upscaler deve ficar em `models/latent_upscale_models`; o LMS upscaler anterior não o substitui.

O Henge exige os nodes nativos e os cinco pesos no inventário do worker. No Serverless, esse inventário é atualizado pelas respostas do worker; após trocar a imagem, execute um job de um modo já disponível para atualizar o cache do Henge. O worker também suporta a operação `inventory`, mas chamá-la diretamente no RunPod não atualiza o cache do bridge. A checagem de saúde do Henge usa o cache e não acorda um worker automaticamente.

## Uso e limites

Em Nitidez, escolha saída **1080p ou 2K** e selecione o novo método. A primeira passagem roda com lado curto de 768 pixels; a segunda recebe as dimensões finais explicitamente, preservando a orientação do vídeo. 4K não está habilitado para este método.

Informe uma descrição fiel da cena ou deixe vazio para o VLM configurado descrever os frames. Essa descrição é separada da instrução técnica LMS e pode ser revisada no plano do job. Não depende do Molmo local. Em clipes com vários shots, a descrição automática cobre o intervalo inteiro; valide especialmente os cortes e cenas diferentes.

Os testes automatizados verificam montagem do grafo, schedules, áudio, resolução e bloqueio de dependências ausentes. Ainda é necessário testar qualidade, tempo e VRAM no worker atualizado; não há estimativa de capacidade nem resultado visual validado deste modo.

Fontes: [workflow/modelos Kijai](https://huggingface.co/Kijai/MiniMax-H3-experimental), [node nativo ComfyUI](https://github.com/Comfy-Org/ComfyUI/commit/35060f0156181ae78a86b10f098f67ce8e83697f), [modelo NVIDIA](https://huggingface.co/Efficient-Large-Model/Open-H3-Regenerate-2K).
