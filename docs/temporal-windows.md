# Janelas temporais puras no Henge

Em **Configurações → Processamento temporal → Estratégia de processamento**, escolha:

- **Processamento padrão**: mantém o caminho anterior. É a seleção inicial.
- **Janelas temporais puras · experimental**: todas as avaliações de denoise usam janelas sobrepostas,
  cujas previsões são combinadas antes de o sampler atualizar o latent global. Não há aquecimento sequencial.

- **Segmentos → refiner completo com janelas · experimental**: no Sharpness com Open-H3 Refiner + LMS
  e saída 1080p/2K, a etapa 1 gera normalmente os segmentos (até 107 frames, mantendo contexto entre
  trechos). Depois de unir os segmentos sem crossfade, a etapa 2 refina **todo o intervalo** com janelas
  sobrepostas a cada passo. A etapa 1 não usa context windows nem executa um refiner por segmento.

A opção de janelas em todas as passagens está disponível para Character Swap, Motion Transfer (Guide Latents e TARA), Head Swap e Sharpness.
No Sharpness ela se aplica à primeira passagem e também ao refino H3/Open-H3, quando presente.
NVIDIA VSR continua operando nos frames depois da primeira passagem; não é um denoise adicional.

## Segmentos primeiro, refiner global depois

Esta estratégia mantém uma única avaliação global do sampler por nível de ruído na segunda etapa:
previsões locais são combinadas antes da atualização. Janela e sobreposição começam em 107/22 frames;
o refiner mantém os 2 passos padrão e `er_sde`. Não é o sampler híbrido que troca de estratégia no meio
**da mesma passagem**: são duas passagens completas, com modelos e schedules separados.

Para reutilizar a infraestrutura de segmentos e permitir Retry/Redo, os frames montados da primeira
passagem são re-encodados pelo VAE tiled. Não se concatenam arquivos de latents de geração: essa
recodificação pode introduzir perda. O upscaler latente nativo recebe o vídeo re-encodado, enquanto
Add Guide ancora o intervalo do **vídeo original** na resolução final. O áudio final continua seguindo
os controles de áudio do job; a segunda passagem não substitui a trilha por uma nova geração.

As janelas da segunda etapa podem atravessar cortes de câmera, inclusive os que dividiram a primeira
etapa. O guia completo mantém os cortes como controle, mas isso não garante transições perfeitas.
Compare essas regiões; reduza janela/sobreposição se houver mistura. A separação automática `fit→every`
descrita abaixo se refere apenas à opção de janelas em todas as passagens, não a esta estratégia.

O loader limita o intervalo completo a **3600 frames após padding** (aproximadamente 150 s a 24 fps).
Mesmo dentro desse limite, VAE, guia e latent global podem consumir muita RAM/VRAM. O limite de memória
da avaliação do modelo não elimina o custo de manter/encodar o vídeo completo.
Ao refazer um segmento, a etapa 2 é executada novamente sobre a montagem atualizada.

Na API, use `temporal_windows.enabled=true` e `scope="refiner_full"`. O valor `scope="all"` (ou sua
omissão) mantém janelas em todas as passagens. `enabled=false` mantém o caminho anterior, sem alterações.

## Três controles diferentes

| Controle | O que faz |
| --- | --- |
| Shots / detecção de cortes | Separa o vídeo em cenas ou trechos de trabalho |
| Frames de contexto entre trechos | Usa parte de um resultado já gerado para condicionar o próximo trecho |
| Janelas temporais puras | Compartilha previsões entre janelas durante cada passo de geração de um shot |

As janelas não concatenam vários vídeos prontos. Existe um latent global e um único sampler com seu
schedule, ruído e histórico. A cada avaliação do modelo, as janelas enxergam o mesmo nível de ruído.
As sobreposições recebem pesos positivos maiores no centro e são normalizadas depois de todas as previsões.
Isso não é crossfade de frames finais e não requer o sampler híbrido nem suas dependências.

Com detecção de cortes ativa, o modo puro transforma `fit` em `every`: cada corte detectado começa um
shot novo, impedindo a mistura de previsões entre essas cenas. Desligar a detecção mantém explicitamente
o intervalo contínuo escolhido. Cortes que o detector não reconhecer continuam dependendo de revisão manual.
Os frames de contexto entre shots continuam seguindo as regras existentes do Planner.

## Valores iniciais

- **Janela: 107 frames**, aproximadamente 4,46 s a 24 fps.
- **Sobreposição: 22 frames**, aproximadamente 0,92 s.
- Ambos respeitam a grade H3 `17n+5`, com a sobreposição menor que a janela.
- Acumulação das previsões em **CPU/FP32**, devolvendo ao sampler o tipo e dispositivo esperados.

Shots menores que a janela usam uma única janela. Para um primeiro teste, compare esse caso com o modo
padrão, mantendo a mesma seed e os demais ajustes. Depois teste um shot que precise de várias janelas.
Janelas menores reduzem os tokens por avaliação, mas aumentam o número de avaliações por passo.
A última janela é deslocada para terminar exatamente no fim do latent; nenhum frame ou coluna de áudio fica descoberto.

No refiner padrão, a proteção que divide trechos longos em blocos de até 107 frames continua ativa.
Ao selecionar janelas puras, esse limite extra é dispensado: o comprimento dos shots segue os controles
do usuário e os cortes; as avaliações do modelo ficam limitadas pela janela temporal.

## Condicionamento, referências e áudio

O node **HengeH3PureWindows** usa o protocolo de contexto do ComfyUI sem substituir o sampler:

- O Add Guide é recortado na grade temporal da janela e recebe índices locais.
- Referências de imagem mantêm seus papéis e sua ordem; não são convertidas em novos personagens.
- No TARA, o vídeo de referência e seu áudio associado acompanham o mesmo intervalo. O layout empacotado
  é reconstruído antes do wrapper de atenção TARA consultar as posições temporais.
- Frames de ancoragem individuais são mantidos somente nas janelas em que aparecem.
- Máscaras temporais de denoise de vídeo e áudio são recortadas junto dos respectivos streams.
- O sampler mantém seu ruído e histórico globais; não cria uma seed por janela nem reinicia um solver
  multistep em cada recorte. `er_sde` continua sendo o sampler do refiner; não foi trocado por Euler.

As referências de vídeo usadas como controle de movimento precisam ter o mesmo comprimento temporal do alvo.
Clips Add Guide parcialmente recortados precisam estar alinhados à grade causal; um caso incompatível gera
um erro explícito. O suporte inicial cobre os guias frame-0 e os anchors gerados pelos fluxos do Henge.

## Memória e limites

A redução é no tamanho das avaliações do DiT. Não é uma garantia de que qualquer duração/resolução cabe:
carregamento do vídeo, VAE, segmentação/tracking, latent global e exportação ainda consomem RAM/VRAM.
Em caso de falta de memória, reduza também duração por shot ou resolução. Não há promessa de identidade,
movimento ou qualidade iguais à atenção global com várias janelas.

Não combine esta opção com **Causal**, **atenção regional**, outro context handler ou ControlNet.
Esses caminhos precisam de integração própria e são rejeitados no caminho correspondente.
TARA/Kitchen continua dependendo da extensão temporal modificada: veja
[o guia de Motion Transfer](motion-transfer.md#comfy-kitchen-works-with-tara--use-the-modified-temporal-kernel).

## Atualizar UI e worker

São necessários o frontend/bridge novo e a imagem do worker que contenha `HengeH3PureWindows`.
Não há pesos extras nem novo perfil de download para janelas puras.

No RunPod, aguarde a publicação Docker, atualize o template e recicle os workers quando os jobs ativos
terminarem. O bridge habilita a opção quando o inventário reporta o node novo
(`temporal_windows_ready=true` em `/health`). O cache é atualizado pela resposta de um job do worker;
veja [atualização do endpoint](SERVERLESS.md#enable-refiner--lms-on-an-existing-endpoint).
A UI avisa quando o worker ainda é antigo, incluindo em configurações importadas.

API e exportação de ajustes usam:

```json
{
  "temporal_windows": {
    "enabled": true,
    "window_frames": 107,
    "overlap_frames": 22
  }
}
```

A configuração fica salva e aparece nos ajustes/comparações do job. Desligar a opção restaura o grafo
normal; não ativa o processamento híbrido como fallback.

## Referências de implementação e validação

Implementação independente no Henge, usando a API do
[ComfyUI ContextHandler](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy/context_windows.py).
[HybridWindows](https://github.com/Jalen-Brunson/ComfyUI-HybridWindows) foi estudado como referência H3
para áudio/vídeo, condicionamento por janela e a distinção entre fase sequencial e conjunta; esta opção
não usa sua fase de aquecimento, não instala esse pacote e não depende de MMH3Tools.

Testes CPU verificam cobertura AV, normalização das previsões, CFG, preservação de duração, anchors,
recorte de máscaras, controles incompatíveis, cancelamento e roteamento dos modelos nos modos do Henge.
Um H3 pequeno com pesos aleatórios também exercitou uma e várias janelas em CPU, incluindo o wrapper
TARA real em backend Flex, com saída finita e formatos AV preservados. Isso não valida os LoRAs de
produção nem os kernels Flash/Kitchen em GPU. É necessário comparar vídeos reais antes de promover o modo a padrão.

Para repetir o teste com o H3 reduzido em CPU (sem baixar pesos), no Python do ComfyUI:

```bash
python scripts/check_h3_pure_windows_cpu.py --comfy-root /path/to/ComfyUI --bfs-root /path/to/ComfyUI-BFSNodes
```
