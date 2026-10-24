# Build and run the Kawarimi image

This image starts the web UI, bridge and ComfyUI. **Models download on the first
start into a persistent volume**, not into the public image layers. The image
does not publish or contain the private 10500/4500 LoRAs or an HF token.

Requirements: Docker Engine/Desktop with Compose v2 and NVIDIA GPU support.
The default PyTorch CUDA 13.0 image needs a compatible host NVIDIA driver.
Linux with NVIDIA Container Toolkit is the intended first target; Windows needs
Docker Desktop's WSL2 GPU support. No full Docker/GPU build has been validated on
this pod because Docker is unavailable here. Native UI/backend checks are
separate from container validation.

## Commands

```sh
git clone https://github.com/alisson-anjos/Kawarimi.git
cd Kawarimi
cp config/model-repos.example.json config/model-repos.json
docker compose build
docker compose up -d
docker compose logs -f
```

Open **http://localhost:8188** after the model downloads and services finish
starting. The first start downloads large H3 weights; allow sufficient disk
space (tens of GB for the base profiles, more for optional models), RAM and VRAM.
Do not delete the model volumes between starts.

To build only, or use a custom tag:

```sh
docker build -t kawarimi:local .
```

On Windows PowerShell, use `Copy-Item config/model-repos.example.json
config/model-repos.json` instead of `cp`. The remaining Compose commands are the
same. The default profiles download public Character Swap and the shared H3,
prompt-writer and preview models. Motion LoRAs are not publicly supplied here.

## Configure model repositories

Edit `config/model-repos.json` before starting. Each entry has `repo_id`,
`repo_type`, `filename`, `revision`, `destination` and `profiles`. Destinations are
relative to ComfyUI's models directory. Use pinned commit revisions if you want
reproducible downloads. Existing files are reused; changing the manifest does
not silently replace installed weights. Remove/move the specific installed file
or use a new destination when deliberately changing versions.

Optional profiles are `fibo`, `sam2d`, `sam3d`, `audio`, `motion10500` and
`motion4500`. Set `KAWARIMI_MODEL_PROFILES` in an untracked `.env` beside Compose:

```dotenv
KAWARIMI_MODEL_PROFILES=character,fibo,sam2d,audio
```

For private motion models, configure their currently-null `repo_id` and
`filename` entries, set `repo_type=dataset` if needed, and add their profile.
Alternatively mount/copy your weights into their documented destinations. An
unconfigured selected private model fails with an explicit error rather than
downloading a different model under its name. The SAM3D MoGe entry is also local
until its exact distribution is configured. Some optional upstream assets may
require accepted licenses or access permission.

If needed, supply `HF_TOKEN` **at runtime** through an untracked environment file.
Do not put it in the Dockerfile, manifest, image or GitHub. The downloader also
supports `HF_TOKEN_FILE` for a mounted secret file in custom deployments. Read
each model's terms; downloading does not grant additional usage rights.

You can preview the selected downloads without fetching weights:

```sh
python scripts/download_models.py --manifest config/model-repos.json --profiles character,fibo --dry-run
```

## Persistence and shutdown

Compose preserves named volumes for weights, job history, inputs and outputs.
`docker compose down` stops services while retaining these volumes.
**`docker compose down -v` deletes them.** Back up volumes before moving machines;
private HF backups are separate from Docker's local persistence.

```sh
docker compose stop
docker compose start
docker compose logs -f --tail=100
```

The UI's Connection settings can test/save a ComfyUI API URL. The bundled API is
`http://127.0.0.1:8189` from inside the container. Connecting to a separate ComfyUI
server also requires shared/synchronized input/output files and its Kawarimi
custom nodes; changing the URL alone does not synchronize remote files.
