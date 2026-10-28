# Build and run the Henge image

This image starts the web UI, bridge and ComfyUI. **Models download on the first
start into a persistent volume**, not into the public image layers. The image
does not contain model weights or an HF token; the Motion Transfer LoRAs download from the public
Alissonerdx/Minimax-H3-ComfyUI repository.

Requirements: Docker Engine/Desktop with Compose v2 and NVIDIA GPU support.
The default PyTorch CUDA 13.0 image needs a compatible host NVIDIA driver.
Linux with NVIDIA Container Toolkit is the intended first target; Windows needs
Docker Desktop's WSL2 GPU support. No full Docker/GPU build has been validated on
this pod because Docker is unavailable here. Native UI/backend checks are
separate from container validation.

## Commands

```sh
git clone https://github.com/alisson-anjos/Henge.git
cd Henge
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
docker build -t henge:local .
```

On Windows PowerShell, use `Copy-Item config/model-repos.example.json
config/model-repos.json` instead of `cp`. The remaining Compose commands are the
same. The default profiles download the public task LoRAs and the shared H3, prompt-writer and preview models.

## Configure model repositories

Edit `config/model-repos.json` before starting. Each entry has `id`, `url`,
`destination` and `profiles`. `url` is any direct HTTP(S) download link;
Hugging Face links (`/resolve/` or `/blob/`) use the faster Hub/Xet downloader
and `HF_TOKEN` for private repos. `repo_id`/`filename`/`repo_type`/`revision`
are still accepted instead of `url`. Destinations are relative to ComfyUI's
models directory. Put a commit hash in place of `main` in the URL for
reproducible downloads. Existing files are reused; changing the manifest does
not silently replace installed weights. Remove/move the specific installed file
or use a new destination when deliberately changing versions.

Optional profiles are `sam2d`, `sam3d`, `audio`, `motion` (Motion Transfer v1.0, TARA v1.0 and
Combined). Set `HENGE_MODEL_PROFILES` in an untracked `.env` beside Compose:

```dotenv
HENGE_MODEL_PROFILES=character,klein,sam2d,audio
```

For your own private models, override their URL (or configure `repo_id`, `filename` and `repo_type`), then add the
corresponding profile. Alternatively mount/copy weights into their documented destinations. The experimental `ffp`
profile is private; some optional upstream assets may require accepted licenses or access permission.

If needed, supply `HF_TOKEN` **at runtime** through an untracked environment file.
Do not put it in the Dockerfile, manifest, image or GitHub. The downloader also
supports `HF_TOKEN_FILE` for a mounted secret file in custom deployments. Read
each model's terms; downloading does not grant additional usage rights.

You can preview the selected downloads without fetching weights:

```sh
python scripts/download_models.py --manifest config/model-repos.json --profiles character,klein --dry-run
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

The UI's settings (gear in the top bar → Connection) can test and save a ComfyUI address. The bundled API is
`http://127.0.0.1:8189` from inside the container. A separate ComfyUI server works
too: the bridge sends each graph's input files through `/upload/image` and fetches
results through `/view`, so no shared folders are needed. That server still needs
the Henge (and, for TARA, BFSNodes) custom nodes and the models.
