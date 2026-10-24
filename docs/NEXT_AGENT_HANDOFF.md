# Next agent handoff — Kagemane / H3, 2026-10-24

Continue from the existing implementation; do not restart this project from zero.

## User priorities and naming

- Repository renamed from OpenJutsu to https://github.com/alisson-anjos/Kagemane.
  The checkout on this pod is still `/data/OpenJutsu`. Legacy KAGEMANE_* names,
  ComfyUI node IDs and browser storage keys remain compatible. The current
  rendered brand still says Kagemage; the user explicitly renamed the repository.
- User wants a beginner-facing UI: settings in the LEFT SIDEBAR above Output,
  only Generate and Export beside the prompt, templates in Community.
- Export/import means sharing Kagemane settings, not a ComfyUI graph. Do not call
  the request “Direction” in those controls. Shared JSON excludes media; import
  restores settings and asks for media again.
- Character Swap uses v1.1 automatically. Motion offers Original 10500 and
  TARA-trained 4500. BOTH TASKS must allow Guide Latents or TARA. Default Guide.
- Anatomy preparation is automatic but optional. For a dog reference following
  a human guide, suggest an upright, human-compatible version preserving dog
  identity. Explain the recommendation before rendering and let the user choose
  Adapt reference / Use original image. Normal human-to-human swaps must NOT
  enable FIBO automatically merely for hair, outfit or makeup.
- Keep all new weights/data backups PRIVATE. Code goes to GitHub. Never commit
  credentials, local model manifests with private settings, or model files.

## Training and verified recovery

Training was STOPPED at step **4500** at the user's request. Do not resume it
without new authorization. Original fresh TARA goal was 5000 TOTAL, not +5000.
The pod may be deleted at any moment.

Private repository: `Alissonerdx/Kagemage-Backups` (dataset), prefix
`pod_20261024T000050Z`. Checkpoint + optimizer + config + save_pair for step4500
were remotely size/SHA verified. This is a private backup, not a public release.
Local receipt/state: `/data/reports/private_hf_backup_20261024/mirror_state.json`.
Stop/snapshot gate: `/data/reports/kagemage_e2e_20261024/checkpoint_gate.json`.
Local matched pair snapshot: `/data/reports/kagemage_e2e_20261024/resume_step_4500/`.

Other private backups contain 411 dataset media/manifests, original10500, V2,
code archives and prior workflows. Memory notes are not a backup. Verify remote
receipts if restoring on another pod. Never use the corrupted old SwapAnything
optimizer (overwritten by a historical slider naming bug).

## Services and code

- UI 8188, bridge 8766, isolated ComfyUI 8189.
- `backend/services.json` tracks current PIDs; verify live, do not trust old PIDs.
- Comfy root `/data/kagemane-comfy-backend`, custom nodes symlink to this repo's
  `backend/comfy_nodes/kagemane` and `/data/ComfyUI-BFSNodes`.
- Shared base models `/data/models/minimax-h3` and `/data/comfyui/models`.
- Local LoRAs under isolated Comfy `models/loras/kagemane`: motion_10500 and
  motion_tara_4500 are symlinks to the original10500 and verified4500 snapshot.
- Source/runtime edits require appropriate server reload; the user's active
  render must finish before restarting bridge/Comfy. Verify queue AND job state.
- `scripts/start_backend.py` is the historical pod launcher. For a new machine,
  prefer `docs/RUN_LOCAL.md` or Docker. Do not assume pod paths exist locally.

## What is implemented

Independent per-reference VLM inventory; guide-only analysis; text-only H3
composition. Separate routing cannot rewrite the generated prompt. Raw mode
preserves user text. User Picture slots remain fixed. Guard missing references.

Guide mode shows video to Qwen context without native guide reference latents,
then uses Add Guide. TARA mode uses native Video1 and patches MODEL; no AddGuide.
Both guider and scheduler receive the patched MODEL. Context uses prior native
image reference for TARA versus AddGuide history for Guide.

Settings UI can test/save a ComfyUI API URL via `/settings`, persisted in backend
data `settings.json`. Required Kagemane nodes are checked. Active jobs block
connection changes. API URL alone does not synchronize files: COMFY_ROOT/input/
output must be accessible to the bridge. Proxy whitelist must include new
routes; earlier omissions broke preparation and preview until fixed.

Finished preview supports a cached CPU-encoded guide/result/labelled-reference
MP4 and a download. Route `/jobs/{id}/comparison-with-refs` also supports older
completed jobs that retain original uploads. Per-job encoding lock avoids
blocking progress saves for unrelated jobs. Output width capped at1600.

Sampling preview: launcher now uses `--preview-method taesd`, shared `vae_approx`
path. Actual TAEH3 exists locally. Binary Comfy image events are decoded/validated
per job, written atomically and exposed as cache-busted image URLs. UI shows an
approximate FRAME evolving over sampling steps, not full video playback. Real
sampling-preview GPU validation is still pending. Never claim it is the final
VAE result or that every video frame is previewed.

Readable status labels replace queued_plan/etc. Community owns templates.
Sidebar/settings + prompt-footer actions use React portals; verify on both
mobile/desktop after layout changes.

## Docker / auto-download

Dockerfile + compose.yaml + docker/entrypoint.py + docker/README.md are provided.
The image bundles code/services, NOT private weights; selected models download
on first launch into persistent volumes. `config/model-repos.example.json`
contains configurable repo/file/revision/destination/profile entries. Copy to
ignored `config/model-repos.json`. Motion10500, motion4500 and MoGe entries have
null sources intentionally: configure private sources or mount local weights.
HF_TOKEN is runtime-only; HF_TOKEN_FILE is supported. No automatic uploads.
`python scripts/download_models.py --profiles character --dry-run` lists public
requirements without fetching them. Default profile is Character Swap. Optional
FIBO/SAM/audio profiles are documented. CUDA13/PyTorch2.12 image tag was verified
in the registry. Docker itself is unavailable here: full container build and GPU
startup have NOT been validated. Validate Compose/schema/build on a Docker host.

## Evidence / tests

Evidence root `/data/reports/kagemage_e2e_20261024/`.
- Native UI/backend short renders completed with Original10500 + Guide and
  TARA4500 + TARA. Two steps, 22frames24fps896x480: plumbing only, NOT quality proof.
  Jobs a1ea07d6096a40e4a0e7eed505b4b22a / c89f4ef0993e4245abf614736f736618.
- The user's longer test 4deb8037544249888d8251c63e90d8af reached completion before
  the idle restart enabling TAEH3. Verify its live stored state if relevant.
- Old human-human test 2ff9ddad75e14c438a9230354cf44e33 failed with the old bad
  FIBO graph. It is a historical failure, not a current successful rerun.
- FIBO native image inputs MUST be `images.image_1`, `images.image_2`, ... in API
  graphs (Autogrow), not `image_1`. Fixed and contract-tested.
- 36 Python CPU tests + TS + Next production builds passed before the final
  sidebar/import/settings additions; rerun after final edits. New Docker build
  and latest layout/import/browser tests may still need validation.
- Comparison-with-refs created on CPU and ffprobe verified22frames24fps1600x644.
- Existing evolution grids at `/data/reports/tara_sample_evolution_20261024/`.
  Training previews have a KNOWN reference-order mismatch versus training, fixed
  only in published source. Do not attribute all identity drift to weights until
  doing corrected controlled inference. Training runtime was immutable.

## Next work

1. Check GitHub main and working tree; all authorized changes should be pushed.
2. Reload only idle services with current code; confirm actual frontend port8188
   and external proxy access (local HTTP200 is not proof of external reachability).
3. Browser-test sidebar aboveOutput; Generate/Export footer; Community templates;
   settings import/export (including method/model); both methods in both tasks;
   connection form; readable statuses; reference comparison video/download.
4. Validate a real TAEH3 streaming preview through the proxy during sampling.
5. Test optional FIBO prep on/off through the actual UI; 2D/3D/audio/cut/continuity
   branches are not all GPU-validated. Do not claim all functionality passed.
6. Build/run Docker on a Docker+NVIDIA host and verify auto-download/persistence.
7. User may shut down this pod; prioritize private remote backup of new results
   and durable handoff. Code push is not a dataset/optimizer backup.
