# TARA nativo — motion10500 + adapter V2

Abra `tara-native-10500-v2.comfy.json` no ComfyUI. `tara-native-10500-v2.api.json` é o equivalente para a API, não o arquivo visual.

Dependências: ComfyUI recente com MiniMax H3 nativo, VideoHelperSuite (`VHS_LoadVideo`) e ComfyUI-BFSNodes main >=1.115.19 para o patch TARA. Não usa H3BenchConditioning, KagemaneH3Conditioning ou Add Guide. Não precisa do plugin privado de benchmark. "Nativo" aqui significa conditioning H3 nativo; o loader de vídeo é VHS e o patch é BFS.

Copie `motion10500_plus_training_adapter_v2_exact.safetensors` para `ComfyUI/models/loras/`, escolha esse arquivo no único loader de LoRA e deixe força1. Já contém o10500 + V2, cada um em força1: não carregue V2 ou10500 novamente. Os pesos não estão incluídos no Git/pacote.

Fonte no servidor: `/data/reports/motion10500_adapter_v2/motion10500_plus_training_adapter_v2_exact.safetensors` (930422624 bytes). SHA256 `8c6facb0e2d63960926b6e8fb5abb010caf1c7ccd8ba2c9b03a98c2521135674`. Rank96,208módulos. Concatenação exata, sem Fro/SVD; cada fatia salva foi comparada bit a bit com os originais. Isso verifica o merge algébrico, não qualidade visual nem igualdade bit a bit da inferência GPU.

1. Selecione base H3 original, text encoder e VAE disponíveis na sua instalação. Os nomes do exemplo são os usados na bateria; FastH3 Omni não é substituto automático. Defaults: Euler28steps,CFG1,shift12/3.
2. Faça upload do guia no VHS e de duas referências nos LoadImage: Picture1=personagem, Picture2=cenário. Edite o prompt para o caso real. Não há mídia incluída. Para uma única referência, remova a conexão Picture2 e a instrução de cenário correspondente. Adicione mais slots no nó H3 se necessário respeitando o limite do nó instalado.
3. OUTPUT WIDTH/HEIGHT controlam somente a saída. Use múltiplos de32:512×288,288×512,416×736 etc. Comece pequeno na5090.
4. O ImageScale controla somente a resolução do guia como referência. Comece com as mesmas dimensões/aspecto da saída. Para saída512×288, pode testar384×224 ou256×160 (arredondamento para grade32 muda ligeiramente o aspecto). `crop=center` corta para o aspecto escolhido; use dimensões compatíveis com sua composição para evitar cortar ação importante. Não é necessário igualar resolução de referência e saída.
5. FRAMES é ligado ao frame_load_cap VHS e ao length H3. Use17n+5:73,90,107,124,141... O VHS força24fps;107frames≈4.46s. O guia precisa ter pelo menos o número escolhido DEPOIS do skip e reamostragem. Reduza FRAMES para um valor válido que caiba no vídeo se ele for curto; o exemplo não faz padding automático. `skip_first_frames` seleciona o início segundo a semântica da versão VHS instalada; confirme no preview. Não altere select_every_nth=1 para acelerar, pois muda o alinhamento temporal.
6. O nó TARA produz MODEL usado tanto no guider quanto scheduler. Video1 entra no positive nativo. Não adicione MiniMaxH3AddGuide ou âncora de primeiro frame. Para nativo SEM TARA, faça bypass apenas do nó de patch e conecte o MODEL anterior ao guider/scheduler; isso não vira Guide Latents.
7. Saída é vídeo silencioso24fps. Áudio não foi conectado para evitar dessintonia no corte. Preview inicial é teste local: este arquivo passou validação estrutural de links e foi construído contra schemas reais; ainda precisa abrir e renderizar no seu ComfyUI. Kernels/desempenho dependem do ambiente. Nenhum teste GPU novo foi disparado para não disputar o treinamento ativo.

Backend inicial: Flash partitions. Para testar Kitchen ou sparse, siga as instruções do BFS e selecione backend compatível de verdade; não instale dependências arbitrárias. Os controles não garantem identidade perfeita. Reduzir muito a referência pode perder movimento.
