# Atualizar a UI no Render

O Render precisa receber código ou imagem que já foi publicado. Um commit apenas local
não aparece no serviço remoto.

## Serviço usando a imagem `henge-ui`

1. Envie a `main` revisada para o GitHub: `git push origin main`.
2. Em GitHub → Actions, aguarde o workflow **Docker** concluir a publicação da imagem de UI.
   O workflow deste repositório publica `ghcr.io/<owner>/henge-ui:latest` na branch principal,
   além das tags de branch e SHA.
3. No Render, abra o serviço e confira **Settings → Image URL**.
4. Para acompanhar as novas versões, mantenha o endereço da imagem e use a tag `:latest`.
   Uma tag `:sha-...` ou um digest fixa uma versão; repetir o deploy dessa referência
   não busca automaticamente a imagem correspondente ao novo código.
5. Use **Manual Deploy → Deploy latest reference**.
6. Quando o serviço estiver disponível, abra o estúdio e confira o link **Dicas**.
   O guia fica em `/guides/index.html` na mesma instância.

Serviços baseados em imagem não fazem redeploy automático só porque o conteúdo da tag
`latest` mudou. É necessário disparar o deploy no Render (ou configurar automação por deploy hook).

## Serviço conectado diretamente ao GitHub

1. Envie a `main` revisada ao GitHub.
2. Confira qual branch está conectada ao serviço.
3. Use **Manual Deploy → Deploy latest commit**, ou aguarde o auto-deploy configurado.

## O que esta atualização inclui

O guia visual com capturas, avisos sobre prompts e TARA, o controle de seed e os ajustes do bridge
fazem parte da imagem de UI. O worker de geração é um componente separado.

Referências oficiais:
- [Deploy de imagem Docker no Render](https://render.com/docs/deploying-an-image)
- [Deploys manuais e automáticos](https://render.com/docs/deploys)

## Refiner visível, mas desabilitado

Atualizar `henge-ui` no Render atualiza a interface e o bridge; não atualiza o ComfyUI nem
instala pesos no RunPod. O Refiner + LMS exige a nova imagem do worker, os pesos do perfil
`regenerate` no volume e um inventário atualizado no bridge. Em Serverless, use um pod temporário
para completar o volume; definir o perfil apenas no worker não faz downloads.

Siga os [passos de atualização do endpoint](SERVERLESS.md#enable-refiner--lms-on-an-existing-endpoint).
Depois execute um job curto com outro método pelo Henge para atualizar o cache e recarregue a página.
