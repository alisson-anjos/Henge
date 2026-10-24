# syntax=docker/dockerfile:1
ARG PYTORCH_IMAGE=pytorch/pytorch:2.12.0-cuda13.0-cudnn9-runtime
FROM node:22-bookworm-slim AS web
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM ${PYTORCH_IMAGE} AS runtime
ARG COMFY_REF=1a82e6d01f395b43275c77acd289af1eb7090bb9
ARG BFS_REF=f4b6f63be1a76ccc4992112568fad38bcaa4120c
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 NODE_ENV=production \
    COMFY_ROOT=/opt/ComfyUI COMFY_BASE_URL=http://127.0.0.1:8189 \
    KAGEMANE_BACKEND_URL=http://127.0.0.1:8766 KAGEMANE_DATA_DIR=/state/jobs \
    KAGEMANE_MODELS_DIR=/opt/ComfyUI/models KAGEMANE_MODEL_PROFILES=character \
    KAGEMANE_MODEL_MANIFEST=/app/config/model-repos.example.json \
    HF_HOME=/state/huggingface
RUN apt-get update && apt-get install -y --no-install-recommends git ffmpeg ca-certificates libgl1 libglib2.0-0 fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /opt/ComfyUI && git -C /opt/ComfyUI checkout "$COMFY_REF" \
 && git clone https://github.com/alisson-anjos/ComfyUI-BFSNodes.git /opt/ComfyUI/custom_nodes/bfsnodes \
 && git -C /opt/ComfyUI/custom_nodes/bfsnodes checkout "$BFS_REF"
COPY --from=web /usr/local/bin/node /usr/local/bin/node
COPY --from=web /app /app
RUN python -m pip install --no-cache-dir -r /opt/ComfyUI/requirements.txt -r /opt/ComfyUI/custom_nodes/bfsnodes/requirements.txt -r /app/backend/requirements.txt \
 && ln -s /app/backend/comfy_nodes/kagemane /opt/ComfyUI/custom_nodes/kagemane
WORKDIR /app
EXPOSE 8188
HEALTHCHECK --interval=30s --timeout=10s --start-period=60m --retries=3 CMD python -c "import requests; r=requests.get('http://127.0.0.1:8188/api/backend/health',timeout=8); r.raise_for_status(); assert r.json()['online']"
ENTRYPOINT ["python", "/app/docker/entrypoint.py"]
