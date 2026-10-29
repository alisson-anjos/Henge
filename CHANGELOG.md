# Histórico de atualizações do Henge

Mudanças mais recentes primeiro. Datas no formato `AAAA-MM-DD`.
Este histórico começa com as atualizações de 28/10/2026; os commits anteriores continuam no histórico Git.

**Código publicado** significa disponível na `main`. Isso não significa que a imagem Docker terminou
ou que Render e RunPod já foram atualizados. Cada entrada registra esses estados separadamente.
Resultados de testes são descritos com seu alcance; testes CPU não substituem geração com os modelos reais.

## 2026-10-29

### Context windows — publicado e validado no Serverless

- Processamento temporal opcional para Character Swap, Motion Transfer, TARA, Head Swap e Sharpness.
- Janelas puras avaliam trechos sobrepostos em cada passo e combinam as previsões antes de atualizar o
  latent global. As avaliações ocorrem uma janela por vez; a acumulação das previsões fica em CPU.
- Estratégia adicional no Sharpness: segmentos normais com continuidade na primeira etapa, montagem
  sem crossfade e Open-H3 Refiner sobre o vídeo completo com context windows na segunda etapa.
- Janela/sobreposição configuráveis, inicialmente 107/22 frames. Opções experimentais, desligadas por padrão.
- Worker antigo mantém a opção indisponível; combinações sem suporte têm validação explícita.
- **Publicação:** código na `main`, commit `d1672fd`. Imagem Docker publicada; worker Serverless em
  `henge:sha-d1672fd` e UI/bridge do Render em `henge-ui:sha-d1672fd` (ComfyUI `35060f0`, BFS `6df4276`).
- **Testes:** testes de lógica, UI com Playwright e H3 reduzido em CPU passaram, incluindo o wrapper TARA
  em Flex. Geração real no RunPod Serverless, seed 42, todos concluídos sem erro:
  - Sharpness em duas etapas (LMS por segmentos → Open-H3 Refiner com janelas 73/22 sobre o vídeo
    completo): 124 frames, saída 1952×1088.
  - Refiner com janelas sobre um resultado existente de Character Swap: 124 frames, personagem, pose e
    fundo preservados. Também concluído pelo fluxo normal da UI no Render, com comparativo no histórico.
  - Motion Transfer e Motion Transfer TARA, normal × janelas 39/5 em 56 frames (duas janelas): mesma
    identidade e movimento; o TARA com janelas levou 107 s contra 227 s neste teste.
  - Nenhuma emenda entre janelas: o maior salto na zona de sobreposição ficou igual ao da versão sem
    janelas (0,9–1,4× a variação mediana entre frames), abaixo dos picos de movimento do próprio vídeo.
- **Limites:** um clipe por modo, curto (2,3–5,2 s); a comparação de tempo é de uma execução só e o pico de
  VRAM não foi medido. Falta um clipe longo com várias janelas e cortes de câmera.
- [Controles, funcionamento e limites](docs/temporal-windows.md).

### Junção dos shots e reinício do bridge

- Removido o carregamento dos dois shots inteiros em RGB e suas cópias em float na memória do bridge.
  Agora apenas a sobreposição é analisada em miniaturas; FFmpeg processa os frames completos por streaming.
- Mantidos o corte direto, a duração e a remoção única dos frames duplicados. Sem crossfade.
- Removido também o ajuste automático de cor: cada shot conserva suas próprias cores.
- As duas saídas temporárias são verificadas antes de substituir os arquivos dos shots.
- Recuperado um teste cujos dois shots terminaram no RunPod, mas cujo bridge reiniciou depois da geração;
  a montagem foi concluída sem repetir a inferência. Falta de RAM é uma suspeita sustentada pelo consumo
  encontrado na junção anterior; a causa do reinício não foi confirmada pelos logs do Render.
- **Publicação:** commits `1ec3192` e `8dbff80` na `main`. A correção exige atualizar a imagem da
  **UI/bridge no Render**; não exige alterar o worker GPU.
- **Testes:** 145 testes na versão estável, com 1 ignorado; cobertura FFmpeg real para duração, preservação
  das cores, falha de encode e sobreposição. Montagem dos shots recuperados e teste com shots mais longos concluídos.
- [Diagnóstico e atualização](docs/SERVERLESS.md#bridge-restarts-between-shots).

### Sharpness / Open-H3 e workflows Motion Transfer

- Ao selecionar Open-H3 Refiner + LMS, a primeira etapa recebe o preset DMAD, 4 passos e CFG 1;
  os passos do refiner continuam independentes.
- Corrigido o layout dos controles de Sharpness fora da seção Avançado.
- Refinamento tradicional por segmento limitado a 107 frames para conter o custo de memória em clipes longos.
- Publicados quatro workflows ComfyUI: nativo e Planner para Motion Transfer Guide Latents e para TARA.
  As referências podem ter papéis variados; não há exigência de uma imagem de pessoa e outra de fundo.
- Requisitos alinhados à versão pública do BFS. Documentado o kernel temporal modificado do Comfy Kitchen
  necessário para a implementação TARA correspondente.
- [Workflows](workflows/README.md) · [Motion Transfer](docs/motion-transfer.md) · [Open-H3](docs/open-h3-regenerate.md).

## 2026-10-28

### Open-H3 Refiner + LMS

- Adicionado o upscale com o refiner rank 16 do Kijai, upscaler latente nativo e LMS carregado separadamente.
- Mantida a base Ref2VA existente; não foi adicionada dependência de FL2VA.
- Add Guide usa o vídeo original para orientar a segunda passagem. Refiner + LMS tornou-se a seleção
  inicial do upscale Sharpness, com saída 1080p/2K.
- Prompt opcional do refiner exposto no painel principal. Sem descrição manual, o fluxo pode solicitar
  uma descrição automática da cena.
- Corrigida a criação do ambiente isolado Molmo no Docker e a resolução da dependência Click do RunPod.
- Documentados os downloads no volume Serverless e a atualização do inventário: atualizar a UI não
  instala nodes/pesos no worker; definir perfis no worker não preenche o volume automaticamente.

### Personagens, shots e interface

- Recomendado TARA com seu LoRA correspondente para marcações de cor. Character Swap pode funcionar
  com múltiplos personagens, mas depende especialmente da descrição e associação das referências no prompt.
- Melhorada a associação das identidades por shot quando personagens mudam de posição ou aparecem mais tarde.
- Expostos controles de seed para comparar gerações com ajustes reproduzíveis.
- Mantida a montagem sem crossfade após comparação visual favorável.
- Adicionados guia visual, dicas com capturas Playwright e instruções de atualização da UI no Render.
- [Guia visual](docs/GUIA-VISUAL.md) · [Atualização Render](docs/RENDER.md).

## Como manter este histórico

- Para cada mudança relevante, registrar data, comportamento alterado e motivo.
- Informar em qual componente entra: UI/bridge, worker, modelos, workflows ou documentação.
- Distinguir código na `main`, imagem publicada, deploy realizado e teste concluído.
- Atualizar a entrada quando um teste ou deploy pendente terminar, com resultado e limitações.
- Referenciar commits e documentação; nunca incluir credenciais, tokens ou dados privados de jobs.
