"""Run Henge graphs through the Comfy API v2 with the official Comfy SDK (pip install comfy-sdk).

Targets:
- proxy: the bridge starts `comfy-api-proxy` in front of a ComfyUI (local or remote) and talks API v2 to it;
- url:   an API v2 deployment that already runs (another proxy, a team server);
- cloud: Comfy Cloud with an API key (its node set must include Henge's custom nodes).

Same interface as RunPodBackend: run(graph, on_status, cancelled) -> ComfyUI-style outputs, download(item, dest),
online(), object_info(), cancel(job_id). Staged inputs (henge/<job>/...) are uploaded as SDK assets whose file_path
keeps that relative path, so nodes that take paths inside JSON text still find them. Henge nodes publish their ui
reports as `.henge-ui.json` file outputs (comfy_nodes/henge/report.py); they are merged back here."""
import copy
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests
from comfy_client import LIST_INPUTS, referenced_files

CLOUD_URL = 'https://cloud.comfy.org'
_ENV_LOCK = threading.Lock()
KIND = {'image': 'images', 'video': 'videos', 'audio': 'audio', 'latent': 'latents'}


class ComfySdkBackend:
    queue_message = 'Waiting in the Comfy API queue'

    def __init__(self, staging, state, *, target='proxy', comfy_url='http://127.0.0.1:8189', url='', api_key='', proxy_port=8199):
        self.staging, self.state = Path(staging), Path(state)
        self.target, self.comfy_url, self.api_key = target, comfy_url.rstrip('/'), api_key or ''
        self.base = (f'http://127.0.0.1:{proxy_port}' if target == 'proxy' else CLOUD_URL if target == 'cloud' else url).rstrip('/')
        self.proxy_port, self.proxy = proxy_port, None
        self.handles, self.offline_reason, self._sdk = {}, '', None
        if target == 'proxy':
            self.start_proxy()

    # --- the managed comfy-api-proxy -------------------------------------------------------------------------
    def start_proxy(self):
        if self.proxy and self.proxy.poll() is None:
            return
        log = open(self.state / 'comfy-api-proxy.log', 'ab')
        # Uploads carry guide videos, hence the large limit; state in the data folder survives bridge restarts.
        self.proxy = subprocess.Popen([sys.executable, '-m', 'comfy_api_proxy.cli', 'run', '--comfyui', self.comfy_url, '--host', '127.0.0.1',
                                       '--port', str(self.proxy_port), '--max-upload-mb', '2048', '--state-dir', str(self.state / 'comfy-api-proxy')],
                                      stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        for _ in range(40):
            if self.online():
                return
            time.sleep(.25)

    def sdk(self):
        """One client for this backend's lifetime: outputs are downloaded after run() returns."""
        if self._sdk is None:
            self._sdk = self.client()
        return self._sdk

    def close(self):
        if self._sdk is not None:
            self._sdk.close()
            self._sdk = None
        if self.proxy and self.proxy.poll() is None:
            self.proxy.terminate()
            try:
                self.proxy.wait(5)
            except subprocess.TimeoutExpired:
                self.proxy.kill()

    # --- status --------------------------------------------------------------------------------------------
    def client(self):
        """A Comfy SDK client for this target. The SDK reads its base URL from COMFY_BASE_URL, which the bridge also
        uses for its own ComfyUI, so it is set just for the construction."""
        from comfy_sdk import Comfy
        with _ENV_LOCK:
            saved = os.environ.get('COMFY_BASE_URL')
            try:
                if self.target == 'cloud':
                    os.environ.pop('COMFY_BASE_URL', None)
                else:
                    os.environ['COMFY_BASE_URL'] = self.base
                return Comfy(api_key=self.api_key or None, timeout=120, client_info='henge')
            finally:
                if saved is None:
                    os.environ.pop('COMFY_BASE_URL', None)
                else:
                    os.environ['COMFY_BASE_URL'] = saved

    def online(self):
        try:
            if self.target == 'cloud':
                with self.client() as c:
                    next(iter(c.list_jobs(limit=1)), None)  # lazy iterator: pull one page
            else:
                r = requests.get(self.base + '/api/v2/health', headers={'Authorization': 'Bearer ' + self.api_key} if self.api_key else {}, timeout=5)
                if not r.ok:
                    raise RuntimeError(f'HTTP {r.status_code}: {r.text[:200]}')
            self.offline_reason = ''
            return True
        except Exception as e:
            self.offline_reason = f'Comfy API at {self.base}: {str(e)[:200]}'
            return False

    def object_info(self):
        """Node and model lists for /health. Behind the managed proxy the ComfyUI itself answers; a remote deployment
        does not expose them through API v2, so {} (unknown: assume the full node set)."""
        if self.target != 'proxy':
            return {}
        try:
            return requests.get(self.comfy_url + '/object_info', timeout=10).json()
        except Exception:
            return {}

    # --- running a graph -----------------------------------------------------------------------------------
    def upload_graph_inputs(self, graph):
        return graph  # inputs travel with the request as assets

    def run(self, graph, on_status, cancelled):
        c = self.sdk()
        graph = copy.deepcopy(graph)
        assets = {}
        for rel in referenced_files(graph, self.staging):
            asset = c.assets.from_file(self.staging / rel)
            # Keep the staged path: the proxy places the input at input/<file_path>, so paths inside JSON text
            # (LIST_INPUTS) resolve as they do on a local ComfyUI. (SDK 0.5 sets file_path to the basename.)
            asset._file_path = 'input/' + rel
            assets[rel] = asset
        for node in graph.values():
            for key, value in node['inputs'].items():
                if (node['class_type'], key) not in LIST_INPUTS and isinstance(value, str) and value in assets:
                    node['inputs'][key] = assets[value]
        for asset in assets.values():
            asset.commit()
        job = c.submit(c.workflows.from_json(graph))
        on_status(job.id, None)
        stop = threading.Event()

        def watch():
            while not stop.wait(2):
                if cancelled():
                    try:
                        job.cancel()
                    except Exception:
                        pass
                    return
        threading.Thread(target=watch, daemon=True).start()
        try:
            self.follow(job, graph, on_status)
            job.wait()
        finally:
            stop.set()
        if cancelled():
            raise InterruptedError('Cancelled')
        if job.status != 'succeeded':
            raise RuntimeError(f'Comfy API job {job.status}: {json.dumps(job.error, default=str)[:1500]}')
        return self.outputs(job)

    def follow(self, job, graph, on_status):
        """Live events -> the same progress dicts RunPod's worker sends (value/max/class_type, queued, message)."""
        from comfy_sdk import Progress, StatusChange
        try:
            for event in job.events():
                if isinstance(event, StatusChange) and event.status in ('queued', 'pending'):
                    on_status(job.id, {'message': self.queue_message + (f' (position {event.queue_position})' if event.queue_position else '')})
                elif isinstance(event, Progress) and event.step is not None and event.steps:
                    node = graph.get(str(event.current_node), {})
                    on_status(job.id, {'value': event.step, 'max': event.steps, 'class_type': node.get('class_type')})
        except Exception:
            pass  # events are best effort; job.wait() is authoritative

    def outputs(self, job):
        """ComfyUI-style {node: {images|videos|...: [{filename, subfolder, type}], text|henge_*: [...]}}."""
        out = {}
        for o in job.outputs:
            entry = {'filename': o.name, 'subfolder': '', 'type': 'output'}
            if o.type == 'file' and o.name.endswith('.henge-ui.json'):
                report = json.loads(o.to_bytes())
                for key, values in report.items():
                    if key not in ('videos', 'gifs', 'images', 'files'):
                        out.setdefault(o.node_id, {}).setdefault(key, []).extend(values)
                continue
            self.handles[(o.node_id, o.name)] = o
            out.setdefault(o.node_id, {}).setdefault(KIND.get(o.type, o.type + 's'), []).append({**entry, 'node': o.node_id})
        return out

    def download(self, item, dest):
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        handle = self.handles.get((item.get('node'), item['filename']))
        if handle is None:
            raise RuntimeError(f"Comfy API reply has no {item['filename']}")
        tmp = dest.with_name(dest.name + '.part')
        handle.to_file(tmp)
        tmp.replace(dest)
        return dest

    def cancel(self, job_id):
        try:
            self.sdk().jobs.get(job_id).cancel()
        except Exception:
            pass
