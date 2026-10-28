"""Molmo2 on the generation backend (serverless worker, pod or remote ComfyUI): the same tasks the bridge runs locally
(find people from photos, questions about the video, split points), for machines without a GPU of their own.

The checkpoint lives in models/molmo (on serverless: the network volume), downloaded from Hugging Face the first time.
It runs in an isolated Python (HENGE_MOLMO_PYTHON, the image's /opt/molmo venv) so its transformers version never
touches ComfyUI's, and ComfyUI's models are unloaded first so the two never share the GPU.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile

import folder_paths
import comfy.model_management as mm

from .report import ui_report

REPO = os.environ.get('HENGE_MOLMO_REPO', 'tollea1234/Molmo2-8B-FP8')
WORKER = Path(__file__).resolve().parents[2]/'molmo_pointing_worker.py'


def model_dir():
    return Path(folder_paths.models_dir)/'molmo'/REPO.split('/')[-1]


def ensure_model():
    """The checkpoint folder, downloaded once (about 14 GB) when it is not there yet."""
    target = model_dir()
    if (target/'config.json').is_file() and any(target.glob('*.safetensors')):
        return target
    from huggingface_hub import snapshot_download
    print(f'[Henge Molmo2] downloading {REPO} to {target} (first use)', flush=True)
    snapshot_download(REPO, local_dir=str(target), max_workers=4)
    return target


def input_path(name):
    root = Path(folder_paths.get_input_directory()).resolve(); path = (root/name).resolve()
    if root not in path.parents:
        raise ValueError('Molmo2 inputs must be inside the ComfyUI input folder')
    return path


class HengeMolmo:
    """task: {"mode": "point" | "match" | "ask", "video"?, "query"?, "start"?, "end"?, "fps"?, "refs"?: [...], "keys"?: [{shot,
    time, path}], "max_crops"?}; file names are relative to the input folder. Returns the worker's JSON."""
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'task': ('STRING', {'multiline': True, 'default': '{}'})}}
    RETURN_TYPES = ('STRING',); FUNCTION = 'run'; CATEGORY = 'Henge'; OUTPUT_NODE = True

    def run(self, task):
        spec = json.loads(task)
        python = os.environ.get('HENGE_MOLMO_PYTHON', '')
        if not python or not Path(python).is_file():
            raise ValueError('This backend has no Molmo2 environment (HENGE_MOLMO_PYTHON); update the Henge image')
        model = ensure_model()
        mm.unload_all_models(); mm.soft_empty_cache()
        with tempfile.TemporaryDirectory(prefix='henge-molmo-') as folder:
            out = Path(folder)/'result.json'
            args = [python, str(WORKER), '--model', str(model), '--mode', spec['mode'], '--output', str(out),
                    '--max-crops', str(int(spec.get('max_crops', 8)))]
            if spec.get('video'):
                args += ['--video', str(input_path(spec['video']))]
            for key in ('query', 'start', 'end', 'fps'):
                if spec.get(key) is not None:
                    args += ['--'+key, str(spec[key])]
            if spec.get('keys'):
                keys = Path(folder)/'keys.json'
                keys.write_text(json.dumps([{**k, 'path': str(input_path(k['path']))} for k in spec['keys']]))
                args += ['--keys', str(keys)]
            if spec.get('refs'):
                args += ['--refs', *[str(input_path(r)) for r in spec['refs']]]
            result = subprocess.run(args, capture_output=True, text=True, timeout=1800, cwd=str(WORKER.parent))
            if result.returncode:
                raise RuntimeError('Molmo2 failed: '+(result.stderr or result.stdout)[-2000:])
            text = out.read_text()
        return {'ui': ui_report({'henge_molmo': [text]}), 'result': (text,)}
