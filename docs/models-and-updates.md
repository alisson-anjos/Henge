# Install models and check updates

## Settings → Models

The model catalog follows this repository's public manifest on GitHub. It is cached for five minutes, so new
entries appear without reinstalling the UI. When GitHub is unavailable, Henge shows the bundled catalog and says
that it is offline. Models are only downloaded after an explicit **Install model** action.

- **Local ComfyUI:** configure `COMFY_ROOT` on the bridge. Downloads go to its `models` folder, without loading
  weights on the GPU. A ComfyUI running on another machine must install weights on that machine; setting a URL
  alone does not give the bridge filesystem access to it.
- **RunPod Serverless:** update the worker image once to a version supporting model installs, then use
  **Refresh worker inventory**. This explicitly wakes the existing endpoint and reports its capabilities. Select a
  model and click **Install model**. The worker downloads directly into the existing shared models volume.
  Neither the browser nor the Render host relays the weight. No temporary pod or S3 credentials are needed.
  GPU time is billed during the download and inventory refresh.

Normal generation and worker startup still do not automatically download models. The original fill-pod procedure
remains available for bulk setup. The new operation is a separate, explicit worker request, not part of a render.

The UI shows queued/download/verification states, transferred bytes and completion or failure. Cancel keeps a
partial download; retry resumes it when the source supports ranges. The final model name appears only after the
file is complete. Downloads sharing a models folder are serialized. Pika's explicit install also checks the pinned
SHA256 and installs its license/notice files. Existing non-empty installed files are reused.

Henge blocks installation during active generation and blocks new generation during installation. A bridge restart
can resume polling an existing Serverless request without submitting the download a second time. Interrupted local
installs are marked failed and can be retried from the retained partial file. Switching the backend is blocked during
an installation. The local UI must remain running for local downloads; closing just the browser does not stop them.

Only models in the public catalog can be installed; the API does not accept arbitrary URLs or filesystem destinations.
Gated models require accepted access and `HF_TOKEN` on the host doing the download (local bridge or worker).
Installing a weight does not install a new node or add a new workflow. Some future models may require a code update
before Henge can use them. Check the changelog for those requirements.

The installer refreshes the model inventory on completion, so installed turbo/model choices become available without
rendering a dummy generation. An old worker must be updated before its new install capability can be used.

## Footer version and changelog

The footer displays the running application commit and **What's new**, using the GitHub changelog. It checks
again every five minutes. If the running commit is behind upstream main, **New version available** links to the
update instructions. Unknown versions and failed/offline checks do not produce a false update notice. Relative
changelog links point to the corresponding GitHub revision.

Docker builds record `HENGE_BUILD_SHA` automatically in both UI and full images. Native Git installations report
`git rev-parse HEAD`; manual image builds can supply `--build-arg HENGE_BUILD_SHA=<full-commit-sha>`. When reported
by the worker, its image revision appears separately in What's new. Old images without build metadata may show an
unknown application/worker version until updated.

This is a code-update notification, not a claim that an image has finished publishing or that a deployment has
updated. Code, image publication, UI/bridge deployment and worker deployment are separate. No automatic restart
or code installation occurs. Wait until active jobs finish before deploying an update.

## Assistant and MCP

`get_models` reads the catalog, progress and availability. `install_model(model_id)` starts an explicitly requested
install. `get_updates` reads version and release notes. The external MCP server also exposes inventory refresh and
installation cancellation. These use the same backend guards as the Settings screen.
