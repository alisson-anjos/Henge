# Guia visual de uso do Henge

[English version](../VISUAL-GUIDE.md)

No estúdio, clique em **Dicas** no topo. O guia é estático, acompanha o Henge em `public/guides/` e é servido pela
sua própria instância em `/guides/pt-BR/index.html` (local, pod ou Render); não exige um serviço externo.

Inclui capturas reais da interface, dicas de referências e prompts, marcações por cor,
TARA, seed, shots/vistas de costas, máscaras, revisão do plano, comparação de resultados,
Head Swap, Nitidez, Molmo2 e assistente. As imagens podem ser ampliadas; o exemplo de
prompt pode ser copiado. O botão de impressão permite salvar o guia como PDF.

## Múltiplos personagens

Prompts são extremamente importantes. Descreva atributos que distinguem as referências
e mantenha cada identidade ligada à pessoa marcada, independentemente da posição na tela.
Uma vista de costas continua de costas; uma pessoa ausente não deve ser criada no shot.

![Personagens, cores e importância do prompt](../../public/guides/images/13-prompt-multiple.png)

## Modelo e seed

Para marcações por cor, recomendamos Motion Transfer TARA com método TARA e prompt explícito.
Character Swap também pode funcionar; o resultado depende da associação e da descrição das referências.
Mantenha a seed para comparar uma mudança de cada vez, ou use Sortear nova seed.

![Configurações de TARA e seed](../../public/guides/images/03-tara-seed.png)

## Validar a troca

Use a comparação com guia e referências. Confira identidade, pose, pessoas não marcadas,
acessórios e continuidade. Os testes ilustrados não garantem comportamento em outros shots.

![Comparação com referências, guia e resultado](../../public/guides/images/09-comparison.png)

## Atualizar as capturas

O roteiro `scripts/docs/capture-guide.cjs` usa Playwright e jobs já existentes.
Ele abre um contexto de navegador isolado, bloqueia escritas na API e não inicia
renderizações, inferências do Molmo ou solicitações ao assistente. Um exemplo de prompt
é digitado apenas no rascunho desse contexto, sem envio. A comparação de vídeos pode
ser preparada localmente pelo backend, sem inferência de IA.

Use um navegador com H.264, como Chrome for Testing, para evitar capturas de players vazios.
O script verifica esse suporte antes de capturar.

```bash
PLAYWRIGHT_MODULE=/caminho/node_modules/playwright \
CHROMIUM_EXECUTABLE=/caminho/chrome \
node scripts/docs/capture-guide.cjs
```

Por padrão, o roteiro procura os testes Maverick locais. Em outro ambiente, informe
`HENGE_GUIDE_JOB` (TARA), `HENGE_CHARACTER_JOB` (Character Swap), `HENGE_MARKS_JOB`
(prévia de cores) e `HENGE_FULL_JOB` (plano aguardando aprovação com vários shots).
Também é possível mudar `HENGE_GUIDE_URL`.

O registro de execução está em `public/guides/images/capture-manifest.json`.
Não capture configurações com credenciais nem publique exemplos privados sem revisar as imagens.

## Verificação

O roteiro `scripts/docs/check-guide.cjs` confere o link Dicas no estúdio, os 24 assets,
os links internos, a ampliação, a cópia do prompt e o layout mobile. Use as mesmas
variáveis de navegador do roteiro de captura.

Para atualizar a instância hospedada, veja [Atualizar no Render](../RENDER.md) (em inglês).
