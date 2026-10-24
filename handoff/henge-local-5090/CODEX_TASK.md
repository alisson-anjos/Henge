# Codex local: entregar Henge UI + ComfyUI na RTX 5090

Você está recebendo uma tarefa de implementação, não apenas de planejamento. Inspecione a máquina, faça as alterações necessárias, rode a aplicação e valide geração real na RTX 5090. Progrida sem pedir confirmação para escolhas rotineiras. Não altere treinamentos, remova modelos, resete Git ou publique credenciais. Não prometa qualidade perfeita. Leia AGENTS.md de cada repositório antes de editar.

## Objetivo e decisões já autorizadas

Entregar um workflow funcional e revisável conectado ao Henge UI: guia em vídeo, N referências, prompt manual ou aprimorado, troca de personagens/objetos/cenário/estilo preservando performance, bindings por cor, processamento por shots, geração, progresso, cancelamento, histórico, download e comparação sincronizada.

O nome público é **Henge**. O repositório ainda se chama OpenJutsu. Preserve IDs legados, chaves localStorage, nomes de classes e variáveis HENGE_* para compatibilidade. **Guide Latents é o padrão.** Ofereça separadamente **TARA - Native Temporal Alignment (experimental)**. Não ative TARA silenciosamente e não faça fallback silencioso entre contratos.

## Fontes e ponto de partida

- UI/bridge: https://github.com/alisson-anjos/OpenJutsu, branch main. Commit de política/branding: 5fc6e9a; use main atual e inspecione diferenças locais antes de atualizar.
- BFS: https://github.com/alisson-anjos/ComfyUI-BFSNodes, branch main. Release TARA experimental: 1.115.19, commit 3c00387. Não precisa trocar para a branch experimental antiga.
- A instalação local conhecida do usuário é ~/tools/ComfyUI, com custom_nodes/bfsnodes (algumas instalações antigas usavam bfsnode). Descubra caminhos reais; evite duas cópias do mesmo plugin.
- Máquina de desenvolvimento remota usava /data/OpenJutsu e /data/henge-comfy-backend. Esses caminhos NÃO são requisitos locais.
- Hardware local: RTX 5090, 32 GB VRAM. Verifique driver, PyTorch/CUDA, ComfyUI e kernels efetivamente instalados antes de escolher backend. Não instale wheels incompatíveis nem faça git reset --hard.

Arquivos a estudar no repo UI:
- components/studio.tsx e components/generation-panel.tsx: edição, bindings, opções, execução/revisão.
- lib/prompt.ts e lib/h3-prompt-policy.json: tokens e política H3 compartilhada.
- app/api/prompt/route.ts: enhancement opcional; app/api/backend/[...path]/route.ts: proxy.
- backend/server.py: jobs persistentes, VLM, aprovação, FFmpeg, segmentação, execução.
- backend/workflows.py: construtores reais dos grafos.
- backend/comfy_nodes/henge/__init__.py: loaders, guia 2D/3D, conditioning e saída.
- scripts/start_backend.py, scripts/download_backend_models.py, .env.example, backend/extra_model_paths.yaml.
- docs/prompt-format.md, docs/roadmap.md, docs/competition.md.

No BFS: H3_NATIVE_TEMPORAL.md, minimax_h3_native_temporal.py, minimax_h3_clip_video.py, módulos temporal_* e sparse_compat, BFSShotH3Conditioning/Simple. Use interfaces reais, não reimplemente a atenção no frontend.

## Estado real e lacunas conhecidas

Já existe UI + FastAPI + grafos API; não comece outra aplicação. Testes CPU não comprovam geração GPU. O README registra limitações de validação. O construtor h3_graph atual usa HengeH3Conditioning, que chama Add Guide. Ainda precisa integrar o modo TARA de ponta a ponta.

Os perfis atuais em backend/workflows.py apontam motion_8000, character_v1_1 e mix50. Não alegue que já usam motion 10500 ou o novo TARA. Torne modelos/LoRAs/adapters configuráveis com inventário dos arquivos locais, sem valores fictícios nem download automático de dezenas de GB. Preserve perfis existentes.

O launcher atual contém caminhos /data, PYTHONPATH com separador Linux, whitelist apenas henge e versões fixadas de dependências. Adapte para o ambiente local; não rode cegamente, não substitua pacotes da instalação ComfyUI existente sem verificar compatibilidade. Ao usar BFS/TARA, sua whitelist precisa realmente carregar BFS. Permita conectar a um ComfyUI já em execução sem iniciar outro na mesma porta.

CRÍTICO: HengeH3Conditioning atualmente enumera uma lista de referências como ref_image_1, ref_image_2... Audite todo o trajeto UI → upload → job → FIBO → loader → encoder. Se o usuário envia slots 1 e 3, eles devem continuar Picture 1 e Picture 3; nunca compacte para 1 e 2. Verifique as regras do encoder H3 para slots esparsos e implemente uma representação explícita de slot/imagem ou rejeição clara caso realmente incompatível. Não corrija apenas o texto escondendo associação errada.

## Contratos dos dois modos

### Guide Latents — default

Vídeo/shot guia normalizado na mesma grade temporal da saída; latentes via MiniMaxH3AddGuide. Opção de enviar também frames RGB do guia ao text encoder/Qwen em clip_video_fps (2 fps inicial), SEM adicionar esse vídeo como referência latente nativa no positive. As imagens de referência continuam nativas. A presença textual de <Video 1> não pode mudar o contrato silenciosamente.

### TARA — experimental

Vídeo guia como referência NATIVA <Video 1>, com seus tokens/latentes de referência no positive. Aplicar BFSMiniMaxH3NativeTemporal no MODEL e usar o MODEL resultante no guider. **Não usar Add Guide para o vídeo nesse modo.** Sem first-frame/continuity Add Guide escondido. Não confundir Video 1 com Picture 1. Imagens permanecem referências nativas.

Defaults do patch: motion_video_index=1, strength=2.0, window_seconds=0.2, falloff_seconds=0.25, max_penalty=6.0. Grade temporal atual 24 fps; vídeo e saída precisam de duração/tempo alinhados. Exponha reference/downscale factor independente da resolução final. Comece 1.0; 0.75/0.5 são testes com compromisso de detalhe, não melhorias garantidas.

Use o patch BFS existente e descubra o schema dos nós em /object_info. O node solto só modifica MODEL: NÃO carrega LoRA, NÃO codifica vídeo e NÃO cria positive. A cadeia precisa fornecer os três corretamente. Não use o mesmo HengeH3Conditioning atual sem modificá-lo: ele sempre aplica Add Guide.

O MODEL patch deve ser request-local. Teste TARA ON → Guide → TARA OFF no mesmo processo sem vazamento de patch/cache. Defina a diferença entre desabilitar o patch e zerar apenas a força do viés: RoPE e bias são componentes distintos.

Backends: Flash partitions é fallback documentado; Comfy Kitchen e sol-attn possuem suporte experimental específico no BFS. Respeite Model Attention Backend/Model Sparse Attention, as combinações verificadas e conflitos reais. Não trate seleções diferentes como equivalentes, não remova patches indiscriminadamente. Registre backend efetivo, uso de one-pass ou fallback. Kernels baixados precisam de verificação; nunca baixe/executa binário arbitrário. GPU/OS/ABI podem impedir kernel opcional.

## Prompt e bindings

- Enhance ON: política H3 compartilhada, seis seções e trigger motion_transfer: (motion) ou body_swap: (swap).
- subject_definitions, summary, retention_analysis, detailed_description, overall_soundscape, non_diegetic_music, nessa ordem.
- Descrever cada referência separadamente antes de compor; papéis identity/outfit/environment/style/object; N imagens não significam N personagens. Duas vistas do mesmo cão são uma identidade.
- Sujeito e Picture são índices independentes. Preserve slots exatos. Guia é Video 1 apenas no contrato nativo correspondente.
- Cor identifica um sujeito persistente, não posição esquerda/direita em todos os frames. Preserve bindings em cruzamentos, oclusões e cortes. Traduza cor ↔ slot de referência explicitamente.
- Cenário pode ser substituído INTEIRO, inclusive piso/paredes/teto; preserve objetos e interações solicitadas (piano, bicicleta, cavalo, microfone). Não acrescente preservação do cenário/realismo quando contradiz a intenção.
- VLM de prompt vê frames amostrados, não áudio. N/A para som não estabelecido; não invente diálogo, cortes nem ações invisíveis.
- Enhance OFF: texto exato do usuário, inclusive espaços; nenhuma reescrita, trigger, binding ou anotação FIBO acrescentada silenciosamente. Routing visual pode continuar, mas deve ser revisável.
- Não restaurar estado velho sobre edições novas ao fazer polling/hidratação/escrita VLM. Respostas assíncronas precisam de versão da solicitação; marque output obsoleto corretamente e não apague vídeo, refs ou prompt atuais.

## Preparação opcional

Original/2D/3D são representações de guia, não métodos de conditioning. Mantenha escolhas separadas de Guide/TARA.
- 2D: SAM, cor fixa por binding e opacidade explícita; preview antes de gerar, detectar frames vazios.
- 3D: reproduzir pipeline SAM 3.1 + SAM 3D Body/MoGe existente quando dependências disponíveis. Não trocar 3D por máscara 2D sem informar. Human source para Body; animais precisam rota compatível ou indisponibilidade clara.
- Preservar fundo e props importantes fora da marcação; manter cores fixas entre frames, sujeitos e shots; validar boca/olhos e falhas de corpo visualmente.
- FIBO Edit opcional para preparação de anatomia/aparência humano↔animal. Não afirmar que uma imagem preparada resolve retargeting temporal completo. Execute apenas se selecionado no plano. Referências de cenário não viram identidade. Não imponha FIBO em toda geração.

## Integração e portabilidade

Faça seleção validada de modelo, LoRA, adapter, força, steps, seed, canvas, fps, modo, escala e backend atravessar UI → request → plano → grafo → histórico. Mostre prompt efetivo e modelo efetivo antes da execução. Assinatura de cache precisa incluir essas configurações, refs, intervalo, bindings e representação. Mudanças precisam invalidar só o necessário.

Portas são configuráveis; padrões do desenvolvimento: UI 3000, bridge 8766, Comfy isolado 8189. Instalação Comfy existente pode estar 8188. Não confunda esses serviços. Variáveis legadas: HENGE_BACKEND_URL, COMFY_BASE_URL, COMFY_ROOT, HENGE_DATA_DIR, HENGE_PYTHON. Credenciais VLM_CHAT_URL/VLM_MODEL/VLM_API_KEY só servidor. Confirme quais são lidas por cada processo; .env.local do Next não configura automaticamente Python.

O proxy atual expõe /api/backend/*; bridge tem /health, /jobs, /jobs/{id}, /approve, /cancel, /files/{name}, /workflow. Preserve os contratos e revisão humana do plano. Cancelar apenas o job da aplicação, sem interromper fila alheia. Validar limites de upload, caminhos e URLs. FFmpeg/ffprobe precisam estar disponíveis. Aplique intervalo ao áudio e vídeo juntos. Keep source audio e audio conditioning são controles independentes. Sem áudio solicitado, geração visual deve funcionar.

Context Window: grade H3 17n+5, padding e trim explícitos, shots na ordem certa. Contexto de continuidade do Guide não deve entrar no TARA sem suporte equivalente definido. Respeite cortes de câmera e remapeamento de tempo das marcas. Não prometa estabilidade de identidade por causa de sobreposição apenas.

## Workflow de exemplo e modelos

A pasta workflows deste pacote contém:
1. guide-current.api.json: export real do construtor atual da UI, para referência de API. Não é workflow visual arrastável e não é TARA. Caminhos/arquivos precisam existir localmente.
2. character-swap-v1.1.comfy.json: workflow visual nativo publicado, ponto de partida para abrir no ComfyUI. Inspecione tipos/links e versões antes de executar.

Gere como entregáveis NOVOS um workflow API e um workflow visual equivalentes para Guide, e outro par para TARA, ambos conectáveis à UI. Não entregue apenas JSON de exemplo sem testar os schemas e links. Um workflow API usa class_type/inputs; um visual usa nodes/links/widgets_values. /prompt recebe API, não o JSON visual inteiro.

Inventário conhecido do servidor (não bundled): base minimax_h3_ref2va_pruned_int8_convrot.safetensors; TE qwen3vl_32b_minimax_h3_int8_convrot.safetensors; VAE minimax_h3_video_vae_fp16.safetensors. Adapter V2 congelado e LoRA motion 10500 foram usados na bateria. Não assuma que o modelo FastH3 Omni 8-step é intercambiável com o H3 original ou que todo adapter serve para todo perfil. Use a combinação realmente instalada e documente scheduler/steps apropriados.

O LoRA 10500 original está no servidor em /data/reports/h3_rank_analysis_10500/source_step10500.safetensors. TARA antigo1000: /data/ai-toolkit-h3-lg/output/openjutsu_h3_native_temporal_v1/openjutsu_h3_native_temporal_v1_000001000.safetensors. São caminhos de origem para transferência manual, não URLs nem arquivos deste pacote. Os merges iniciais não ganharam consistentemente: não os escolha por default. O novo treinamento tara_h3_motion_r64_multiscale_v2 segue no servidor até5000; não o interrompa nem suponha que seu checkpoint já está local.

## Ordem de execução e critérios de aceite

1. Inventariar repo/Comfy/ambiente/modelos, preservar modificações do usuário, relatar lacunas concretas. Ler docs locais do Next antes de mudar frontend. Configurar loopback e integração ao Comfy existente.
2. Fazer Guide original gerar um clip curto pela UI na5090. Depois N refs, slots esparsos, enhancement on/off, plano revisado, resultado/download/comparação.
3. Integrar TARA opt-in com MODEL roteado e guia nativo; validar ausência de Add Guide, backend efetivo e desligamento sem resíduos. Guide permanece default em novos projetos.
4. Habilitar preparação2D/3D/FIBO por dependências e realizar previews e testes reais em cada rota habilitada. Indisponibilidade deve ser explícita, sem derrubar o modo original.
5. Testar intervalos, shot único, múltiplos shots/cortes, contexto, áudio, progresso, cancelamento, retry e histórico sem perda de inputs.
6. Testes CPU: python -m unittest discover -s backend/tests -q; node --experimental-strip-types --test test/prompt.test.ts; TypeScript e build. Acrescentar contratos relevantes a modos/slots/routing, não testes só de strings.
7. GPU: começar 107frames/24fps, 512x288 ou288x512, batch1. Depois resolução solicitada pelo usuário e clip mais longo. O desempenho no servidor96GB não prediz5090. Medir VRAM, tempo primeiro step e steps seguintes; não chamar compilação de travamento sem evidência. Evitar preparar todos os modelos simultaneamente.
8. Matriz visual mínima: 1personagem;2identidades distintas;3refs com cenário;mesma identidade em2vistas;humano→animal;objeto/interação;cruzamento/oclusão;cenário fechado→praia;mudança de estilo;2shots. Reusar seed/prompt/guia entre Guide/TARA. Inspecionar início/meio/fim e binding, motion, props, background. PSNR contra guia não mede sucesso de swap.
9. Guardar logs, request/plano/grafo efetivos, versões/modelos, tempos, vídeos lado a lado sincronizados e falhas observadas. Não declarar100% pelo job ter terminado.

Entregar: código integrado; quatro workflows (Guide/TARA × API/visual); .env.example local portável sem segredos; lista de modelos/dependências com origem e nomes reais; comandos de iniciar/parar; tutorial curto; evidências GPU e limitações; commits focados. Não publicar nem fazer push até autorização local. Ao terminar cada etapa, diga o que foi validado e o que ainda falta, e continue a próxima etapa autorizada.

## Atualização: workflow automático disponível

O pacote agora inclui `workflows/tara-native-auto-prompt.comfy.json` e `.api.json`, documentados em `workflows/TARA-AUTO-PROMPT.md`. BFSNodes main **1.115.21+** fornece os nós públicos `BFSH3PrepareNativeVideo`, `BFSH3DescribeReferences`, `BFSH3BuildNativePrompt` e `BFSH3NativeReferenceSetToVideo`. Use-os como ponto de partida para integrar a opção TARA na UI; não reimplemente o nó privado H3BenchConditioning. O fluxo usa Generate Text nativo (inclusive uma chamada isolada por imagem), inventário de1..9refs, template H3 editável e frame/canvas derivados do vídeo. O conjunto de imagens descrito é o mesmo usado no encoder H3.

O vídeo é ressampleado24fps no loader. Default de duração é todo o vídeo carregado; padding de último frame até17n+5 é removido da saída pelo ImageFromBatch. O exemplo não segmenta vídeos longos automaticamente e carregar o arquivo inteiro ainda consome RAM; o bridge/context-window deve tratar isso. Não remova esse trim ao integrar. Para testes, limite explicitamente o intervalo/VHS frame cap. Novos nós e links passaram testes CPU/estruturais; ainda é necessário validar carregamento visual, captions e geração real na5090. Guia padrão do aplicativo continua Add Guide; esse exemplo é a opção TARA experimental.
