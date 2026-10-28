# syntax=docker/dockerfile:1
ARG PYTORCH_IMAGE=pytorch/pytorch:2.14.0-cuda13.0-cudnn9-runtime
FROM node:22-bookworm-slim AS web
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# UI-only image (ghcr.io/<owner>/henge-ui): bridge + web UI without GPU, torch or ComfyUI. The bridge drives a
# remote ComfyUI (COMFY_BASE_URL) or a RunPod Serverless endpoint (HENGE_BACKEND=runpod).
FROM python:3.12-slim-bookworm AS ui
ENV PYTHONUNBUFFERED=1 NODE_ENV=production HENGE_ROLE=ui HENGE_BACKEND_URL=http://127.0.0.1:8766 HENGE_DATA_DIR=/state/jobs \
    PIP_ROOT_USER_ACTION=ignore
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
COPY --from=web /usr/local/bin/node /usr/local/bin/node
COPY --from=web /app /app
RUN python -m pip install --no-cache-dir -r /app/backend/requirements.txt
WORKDIR /app
EXPOSE 8188
VOLUME /state
ENTRYPOINT ["python", "/app/docker/entrypoint.py"]

# Full image (default target): one pod with ComfyUI + bridge + UI, or a serverless worker with HENGE_ROLE=worker.
FROM ${PYTORCH_IMAGE} AS runtime
ARG COMFY_REF=35060f0156181ae78a86b10f098f67ce8e83697f
ARG BFS_REF=6df4276ae9666e70a54be28c605338390010ce8a
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 NODE_ENV=production \
    COMFY_ROOT=/opt/ComfyUI COMFY_BASE_URL=http://127.0.0.1:8189 \
    HENGE_BACKEND_URL=http://127.0.0.1:8766 HENGE_DATA_DIR=/state/jobs \
    HENGE_MODELS_DIR=/opt/ComfyUI/models HENGE_MODEL_PROFILES=character,motion,headswap,sharpness,omniref,klein,sam2d,sam3d,audio \
    HENGE_MODEL_MANIFEST=/app/config/model-repos.example.json \
    HENGE_MOLMO_PYTHON=/opt/molmo/bin/python HENGE_MOLMO_REPO=tollea1234/Molmo2-8B-FP8 \
    HF_HOME=/state/huggingface HF_XET_HIGH_PERFORMANCE=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 PIP_ROOT_USER_ACTION=ignore
RUN apt-get update && apt-get install -y --no-install-recommends git ffmpeg ca-certificates openssh-server curl python3-venv libgl1 libglib2.0-0 fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /opt/ComfyUI && git -C /opt/ComfyUI checkout "$COMFY_REF" \
 && git clone https://github.com/alisson-anjos/ComfyUI-BFSNodes.git /opt/ComfyUI/custom_nodes/bfsnodes \
 && git -C /opt/ComfyUI/custom_nodes/bfsnodes checkout "$BFS_REF"
COPY --from=web /usr/local/bin/node /usr/local/bin/node
COPY --from=web /app /app
# Pin the base image's torch stack so custom-node requirements cannot swap the CUDA build.
RUN python -m pip freeze | grep -iE '^(torch|torchvision|torchaudio)==' > /tmp/torch-constraints.txt || true; cat /tmp/torch-constraints.txt \
 && python -m pip install --no-cache-dir -c /tmp/torch-constraints.txt -r /opt/ComfyUI/requirements.txt -r /opt/ComfyUI/custom_nodes/bfsnodes/requirements.txt -r /app/backend/requirements.txt runpod==1.12.0 nvidia-vfx 'click>=8,!=8.3.0,<8.4' \
 && python -m venv --system-site-packages /opt/molmo \
 && /opt/molmo/bin/pip install --no-cache-dir 'transformers==4.57.1' 'tokenizers==0.22.2' 'huggingface_hub==0.36.2' 'accelerate==1.5.2' 'safetensors==0.8.0' 'decord2==3.4.0' 'molmo-utils==0.0.1' 'compressed-tensors==0.20.0' \
 && ln -s /app/backend/comfy_nodes/henge /opt/ComfyUI/custom_nodes/henge \
 && python -c "import torch;print('torch',torch.__version__,'cuda',torch.version.cuda)" \
 && /opt/molmo/bin/python -c "import torch,transformers,molmo_utils,compressed_tensors;print('Molmo2 env',transformers.__version__,'torch',torch.__version__)"
# Optional TARA one-pass Kitchen kernel: source pinned here, the per-GPU binary is installed at boot.
RUN git clone --quiet https://github.com/alisson-anjos/comfy-kitchen.git /opt/comfy-kitchen-tara \
 && git -C /opt/comfy-kitchen-tara checkout --quiet 0413d43878606425a84aa400f1e5da50ed9dcdad
ENV HENGE_TARA_SOURCE=/opt/comfy-kitchen-tara
WORKDIR /app
# 8188 = web UI (RunPod HTTP port). 8189 = ComfyUI, only when HENGE_EXPOSE_COMFY=1. 22 = SSH with PUBLIC_KEY.
EXPOSE 8188 8189 22
HEALTHCHECK --interval=30s --timeout=10s --start-period=60m --retries=3 CMD python -c "import requests; r=requests.get('http://127.0.0.1:8188/api/backend/health',timeout=8); r.raise_for_status(); assert r.json()['online']"
ENTRYPOINT ["python", "/app/docker/entrypoint.py"]
