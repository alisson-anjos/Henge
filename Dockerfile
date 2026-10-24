# syntax=docker/dockerfile:1
ARG PYTORCH_IMAGE=pytorch/pytorch:2.14.0-cuda13.0-cudnn9-runtime
FROM node:22-bookworm-slim AS web
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM ${PYTORCH_IMAGE} AS runtime
ARG COMFY_REF=d52a7a5ef60b36062f7c3c69bd774f4c98b56eb0
ARG BFS_REF=f4b6f63be1a76ccc4992112568fad38bcaa4120c
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 NODE_ENV=production \
    COMFY_ROOT=/opt/ComfyUI COMFY_BASE_URL=http://127.0.0.1:8189 \
    HENGE_BACKEND_URL=http://127.0.0.1:8766 HENGE_DATA_DIR=/state/jobs \
    HENGE_MODELS_DIR=/opt/ComfyUI/models HENGE_MODEL_PROFILES=character,motion10500,motion4500,headswap,sharpness \
    HENGE_MODEL_MANIFEST=/app/config/model-repos.example.json \
    HF_HOME=/state/huggingface HF_XET_HIGH_PERFORMANCE=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 PIP_ROOT_USER_ACTION=ignore
RUN apt-get update && apt-get install -y --no-install-recommends git ffmpeg ca-certificates openssh-server curl libgl1 libglib2.0-0 fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /opt/ComfyUI && git -C /opt/ComfyUI checkout "$COMFY_REF" \
 && git clone https://github.com/alisson-anjos/ComfyUI-BFSNodes.git /opt/ComfyUI/custom_nodes/bfsnodes \
 && git -C /opt/ComfyUI/custom_nodes/bfsnodes checkout "$BFS_REF"
COPY --from=web /usr/local/bin/node /usr/local/bin/node
COPY --from=web /app /app
# Pin the base image's torch stack so custom-node requirements cannot swap the CUDA build.
RUN python -m pip freeze | grep -iE '^(torch|torchvision|torchaudio)==' > /tmp/torch-constraints.txt || true; cat /tmp/torch-constraints.txt \
 && python -m pip install --no-cache-dir -c /tmp/torch-constraints.txt -r /opt/ComfyUI/requirements.txt -r /opt/ComfyUI/custom_nodes/bfsnodes/requirements.txt -r /app/backend/requirements.txt \
 && ln -s /app/backend/comfy_nodes/henge /opt/ComfyUI/custom_nodes/henge \
 && python -c "import torch;print('torch',torch.__version__,'cuda',torch.version.cuda)"
WORKDIR /app
# 8188 = web UI (RunPod HTTP port). 8189 = ComfyUI, only when HENGE_EXPOSE_COMFY=1. 22 = SSH with PUBLIC_KEY.
EXPOSE 8188 8189 22
HEALTHCHECK --interval=30s --timeout=10s --start-period=60m --retries=3 CMD python -c "import requests; r=requests.get('http://127.0.0.1:8188/api/backend/health',timeout=8); r.raise_for_status(); assert r.json()['online']"
ENTRYPOINT ["python", "/app/docker/entrypoint.py"]
