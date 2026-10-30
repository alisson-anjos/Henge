# Hosting the UI on Render

Optional: run the Henge UI and bridge (`henge-ui` image) on [Render](https://render.com), with the GPU on RunPod
Serverless (option C in the README). Requirements and other hosts: [Hosting only the UI](HOSTING-UI.md).

Render needs code or an image that has already been published. A commit that only exists locally does not show up
in the remote service.

## Service using the `henge-ui` image

1. Release the reviewed `main`: `git tag v2026.10.30 && git push origin v2026.10.30` (any `v*` name), or run the
   **Docker image** workflow by hand in GitHub → Actions. Pushing commits alone does not build an image.
2. In GitHub → Actions, wait for the **Docker image** workflow to finish publishing the UI image.
   It publishes `ghcr.io/<owner>/henge-ui:latest`, the release tag and a `sha-<commit>` tag.
3. In Render, open the service and check **Settings → Image URL**.
4. To follow new versions, keep the image address with the `:latest` tag.
   A `:sha-...` tag or a digest pins one version; redeploying that reference does not fetch the image of newer code.
5. Use **Manual Deploy → Deploy latest reference**.
6. When the service is up, open the studio and check the **Tips** link.
   The guide is at `/guides/index.html` on the same instance (Portuguese: `/guides/pt-BR/index.html`).

Image-based services do not redeploy on their own just because the `latest` tag changed. You have to trigger the
deploy in Render (or set up automation with a deploy hook).

Redeploying restarts the bridge: wait until no job is running, or the running job is marked as failed and has to be
retried.

## Service connected directly to GitHub

1. Push the reviewed `main` to GitHub.
2. Check which branch is connected to the service.
3. Use **Manual Deploy → Deploy latest commit**, or wait for the configured auto-deploy.

The generation worker is a separate component: updating `henge-ui` does not update it.

Official references:

- [Deploying a Docker image on Render](https://render.com/docs/deploying-an-image)
- [Manual and automatic deploys](https://render.com/docs/deploys)

## Refiner visible but disabled

Updating `henge-ui` on Render updates the interface and the bridge; it does not update ComfyUI or install weights on
RunPod. Refiner + LMS needs the new worker image, the `regenerate` profile's weights on the volume and an updated
inventory in the bridge. On Serverless, use a temporary pod to top up the volume; setting the profile only on the
worker does not download anything.

Follow the [endpoint update steps](SERVERLESS.md#enable-refiner--lms-on-an-existing-endpoint).
Then run a short job with another method from Henge to refresh the cache, and reload the page.
