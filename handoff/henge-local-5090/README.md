# Pacote para o Codex local — Henge / RTX 5090

Abra `CODEX_TASK.md` e use o conteúdo como instrução para o Codex no seu computador. Os arquivos em `workflows/` são exemplos reais atuais, não incluem modelos, credenciais ou mídia. O exemplo API usa Guide Latents; o visual é o Character Swap v1.1 usado como base. A implementação TARA da UI é uma tarefa do handoff, não está pronta nesses exemplos.

Compacte esta pasta inteira. O código da aplicação deve ser obtido de https://github.com/alisson-anjos/Henge (`main`) e o BFS de https://github.com/alisson-anjos/ComfyUI-BFSNodes (`main`, 1.115.19 ou posterior).

Não use os caminhos `/data/...` dos exemplos sem adaptar à sua instalação. Não envie `.env.local`, chaves, vídeos privados ou pesos no ZIP.

## Novo exemplo TARA sem nó de benchmark

Abra `workflows/tara-native-10500-v2.comfy.json`. O guia de controles e dependências está em `workflows/TARA-README.md`. Há controles separados para resolução de saída, tamanho do vídeo de referência e quantidade de frames. O LoRA combinado precisa ser transferido separadamente.

## Versão com prompt e tamanho automáticos (mais recente)

Abra **`workflows/tara-native-auto-prompt.comfy.json`** depois de atualizar BFSNodes para **1.115.21+**. Referências são descritas individualmente com Generate Text; outro Generate Text analisa frames do guia, e o último escreve o prompt final no template H3. Canvas e quantidade de frames vêm do vídeo carregado. Veja `workflows/TARA-AUTO-PROMPT.md` para ligar1..9imagens e ajustar escalas. Não depende do plugin privado de benchmark.
