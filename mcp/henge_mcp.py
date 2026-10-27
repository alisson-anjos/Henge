# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=1.2,<2", "requests>=2.31"]
# ///
"""Henge MCP server: drive a running Henge from your own AI client (Claude Code, Claude Desktop, Cursor, Codex...)
instead of the built-in studio assistant.

It talks only to Henge's HTTP API (the UI on :8188, which proxies the bridge), so it works with any backend the
bridge uses: your ComfyUI, the Comfy SDK or RunPod Serverless. Media are read from paths on the machine that runs
this server and uploaded; results are downloaded next to them (or to HENGE_MCP_OUT).

Run:  uv run mcp/henge_mcp.py            (stdio)
Env:  HENGE_URL      default http://127.0.0.1:8188
      HENGE_PASSWORD the studio login, if one is turned on (user "henge")
      HENGE_MCP_OUT  folder for downloaded results (default ./henge-results)
Needs ffmpeg/ffprobe on the PATH for find_people and the video length.
See docs/MCP.md.
"""
import base64, json, os, re, subprocess, tempfile, time, uuid
from pathlib import Path

import requests
from mcp.server.fastmcp import FastMCP, Image

URL = os.environ.get('HENGE_URL', 'http://127.0.0.1:8188').rstrip('/') + '/api/backend'
AUTH = ('henge', os.environ['HENGE_PASSWORD']) if os.environ.get('HENGE_PASSWORD') else None
OUT = Path(os.environ.get('HENGE_MCP_OUT', 'henge-results')).expanduser()
COLORS = ['red', 'blue', 'green', 'yellow', 'magenta', 'cyan', 'orange', 'purple']
mcp = FastMCP('henge', instructions="""Henge turns a guide video plus reference pictures into a new video on ComfyUI with MiniMax H3.
Modes: swap (Character Swap: people in the guide become the pictures), motion (Motion Transfer: the pictures perform the guide's motion),
headswap (exactly one face picture), sharpness (video only, restores detail and upscales).
Typical flow: status -> (find_people to pick who is replaced) -> create_job -> wait_for_job until 'plan' -> look at the plan -> approve_job
-> wait_for_job until 'done' -> download_result. Start at 480p (fastest, cheapest) unless the user asks otherwise.
Jobs run in the background: one wait_for_job call blocks at most `timeout` seconds; call it again while the job is still running.""")


def api(method, path, **kw):
    r = requests.request(method, URL + path, auth=AUTH, timeout=kw.pop('timeout', 120), **kw)
    if not r.ok:
        try: detail = r.json().get('detail')
        except ValueError: detail = r.text[:500]
        raise RuntimeError(f'Henge {method} {path}: HTTP {r.status_code}: {detail}')
    return r


def probe(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', str(path)], capture_output=True, text=True, check=True)
    info = json.loads(out.stdout); v = next(s for s in info['streams'] if s['codec_type'] == 'video')
    return {'duration': float(info['format']['duration']), 'width': v['width'], 'height': v['height']}


def summary(job):
    keys = ('id', 'reference', 'mode', 'project', 'status', 'stage', 'progress', 'message', 'error', 'quality', 'duration')
    out = {k: job[k] for k in keys if job.get(k) not in (None, '')}
    plan = job.get('plan') or {}
    if plan: out['plan'] = {k: plan[k] for k in ('summary', 'prompt', 'representation', 'warnings', 'use_fibo') if k in plan}
    return out


@mcp.tool()
def status() -> dict:
    """Whether Henge and its GPU backend are online, which backend is in use, and which models, turbos and upscalers are installed."""
    h = api('GET', '/health').json()
    keep = ('online', 'comfy_url', 'offline_reason', 'training_busy', 'tara_ready', 'fibo_ready')
    return {**{k: h.get(k) for k in keep}, 'models': {k: {'label': v.get('label'), 'task': v.get('task'), 'available': v.get('available', True)} for k, v in (h.get('models') or {}).items()},
            'turbos': {k: v.get('label') for k, v in (h.get('turbos') or {}).items() if v.get('available', True)}, 'upscalers': h.get('upscalers')}


@mcp.tool()
def list_jobs(limit: int = 10) -> list:
    """The latest jobs, newest first."""
    return [summary(j) for j in api('GET', '/jobs').json()[:max(1, min(50, limit))]]


@mcp.tool()
def find_people(video: str, time: float, kind: str = 'person') -> list:
    """Number every person (kind='person') or animal (kind='animal') in one frame of a local guide video, at `time` seconds.
    Returns the people (number, x, y, box; coordinates 0-1) and the frame with the numbers drawn. Pass the chosen ones to create_job as subjects."""
    with tempfile.TemporaryDirectory() as d:
        frame = Path(d) / 'frame.png'
        subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{time:.3f}', '-i', str(Path(video).expanduser()), '-frames:v', '1', '-y', str(frame)], check=True)
        found = api('POST', '/assistant/people', files={'frame': ('frame.png', frame.read_bytes(), 'image/png')}, data={'kind': kind}, timeout=900).json()
    overlay = base64.b64decode(found.pop('overlay').split(',', 1)[1])
    return [json.dumps({**found, 'time': time}), Image(data=overlay, format='jpeg')]


@mcp.tool()
def create_job(mode: str, video: str, prompt: str = '', pictures: list[str] | None = None, start: float = 0, end: float | None = None,
               quality: str = '480p', project: str = 'Henge', subjects: list[dict] | None = None, auto_approve: bool = False,
               keep_audio: bool = True, seconds_per_shot: float = 4.5, options: dict | None = None) -> dict:
    """Start a generation from local files.
    mode: 'swap' | 'motion' | 'headswap' | 'sharpness'. video: path of the guide video. pictures: paths, in order Picture 1, 2...
    (swap/motion 1-11, headswap exactly 1 face, sharpness none). prompt: the request, naming pictures as @Picture1, @Picture2
    (headswap and sharpness ignore it). start/end: the interval in seconds (default the whole video).
    quality: '480p' | '720p' | '1080p' ('1440p' | '2160p' only for sharpness).
    subjects (swap with several people): [{"picture_slots": [1], "x": 0.42, "y": 0.35, "time": 2.0, "label": "driver"}], x/y from find_people.
    auto_approve: render straight after planning instead of stopping at the plan for review.
    options: generation options, e.g. {"profile": "character", "conditioning_mode": "guide"|"tara", "turbo": "dmd8", "seed": 42, "upscale": "h3"|"nvidia"|"none"}.
    Returns the job; follow it with wait_for_job."""
    pictures = [Path(p).expanduser() for p in pictures or []]
    source = Path(video).expanduser(); meta = probe(source)
    end = meta['duration'] if end is None else min(end, meta['duration'])
    duration = end - start; frames = max(22, int((round(seconds_per_shot * 24) - 5) // 17) * 17 + 5)
    bindings = [{'id': str(uuid.uuid4()), 'label': s.get('label') or f'Subject {i + 1}', 'color': COLORS[i % len(COLORS)], 'picture_slots': s.get('picture_slots') or [i + 1],
                 'anchors': [{'x': s['x'], 'y': s['y'], 'time_seconds': s.get('time', start), 'frame_width': meta['width'], 'frame_height': meta['height']}]} for i, s in enumerate(subjects or [])]
    native = re.sub(r'@Picture\s*(\d+)', r'<Picture \1>', prompt)
    for i, b in enumerate(bindings):
        refs = ', '.join(f'<Picture {n}>' for n in b['picture_slots'])
        native += f"\n<Subject {i + 1}> uses the identity and appearance from {refs} and follows its selected performer in <Video 1>. Keep this assignment through position changes, occlusion and cuts."
    fixed = mode in ('headswap', 'sharpness')
    direction = {'schema_version': 2, 'project': project, 'mode': mode, 'quality': quality,
                 'processing': {'mode': 'context_window' if duration > 15 else 'single', 'max_shots': 0, 'requested_seconds_per_shot': seconds_per_shot, 'frames_per_shot': frames,
                                'timeline_fps': 24, 'frame_grid': '17n+5', 'trim_to_source_length': True, 'join': 'ordered', 'execution_status': 'comfy_backend', 'context_frames': 22, 'cut_mode': 'fit'},
                 'audio_conditioning': {'enabled': False, 'source': None}, 'output_audio': {'keep_source': keep_audio},
                 'prompt': '' if fixed else native.strip(), 'editor_prompt': '' if fixed else prompt,
                 'subject_guidance': {'representation': 'original', 'bindings': [] if mode == 'sharpness' else bindings, 'status': 'selection_only', 'marker_colors_are_output_appearance': False},
                 'video': {'name': source.name, 'source_signature': f'{source.name}:{source.stat().st_size}', 'conditioning': 'guide_latents', 'source_duration': meta['duration'],
                           'start_seconds': start, 'end_seconds': end, 'duration': duration},
                 'pictures': [{'slot': i + 1, 'token': f'<Picture {i + 1}>', 'name': p.name} for i, p in enumerate(pictures)], 'generation_status': 'not_submitted'}
    opts = {'auto_approve': auto_approve, 'enhance_prompt': True, **(options or {})}
    files = [('video', (source.name, source.open('rb'), 'video/mp4'))] + [(f'picture_{i + 1}', (p.name, p.open('rb'), 'application/octet-stream')) for i, p in enumerate(pictures)]
    try: job = api('POST', '/jobs', data={'direction': json.dumps(direction), 'options': json.dumps(opts)}, files=files, timeout=1800).json()
    finally:
        for _, (_, f, _) in files: f.close()
    return summary(job)


@mcp.tool()
def wait_for_job(job_id: str, until: str = 'done', timeout: int = 600) -> dict:
    """Wait until a job reaches its plan review (until='plan') or finishes (until='done'), at most `timeout` seconds (max 1800).
    Returns the job either way; call again if it is still running."""
    stop = time.time() + max(5, min(1800, timeout))
    while True:
        job = api('GET', f'/jobs/{job_id}').json()
        if job['status'] in ('completed', 'failed', 'cancelled') or (until == 'plan' and job['status'] == 'awaiting_approval') or time.time() > stop:
            return summary(job)
        time.sleep(5)


@mcp.tool()
def get_job(job_id: str) -> dict:
    """Status, stage, progress, plan and errors of one job."""
    return summary(api('GET', f'/jobs/{job_id}').json())


@mcp.tool()
def approve_job(job_id: str) -> dict:
    """Approve a plan waiting for review so the video renders."""
    api('POST', f'/jobs/{job_id}/approve'); return get_job(job_id)


@mcp.tool()
def cancel_job(job_id: str) -> str:
    """Cancel a queued or running job."""
    api('POST', f'/jobs/{job_id}/cancel'); return 'Cancelled.'


@mcp.tool()
def retry_job(job_id: str) -> dict:
    """Run a failed or cancelled job again."""
    api('POST', f'/jobs/{job_id}/retry'); return get_job(job_id)


@mcp.tool()
def download_result(job_id: str, which: str = 'result') -> str:
    """Download a finished job: 'result' (the video), 'comparison' (guide, references and result side by side) or 'bundle' (zip with
    everything, including the exact ComfyUI graphs it ran). Returns the local path."""
    job = api('GET', f'/jobs/{job_id}').json(); OUT.mkdir(parents=True, exist_ok=True)
    if which == 'bundle': path, name = f'/jobs/{job_id}/bundle.zip', f"{job['reference']}.zip"
    elif which == 'comparison': path, name = f'/jobs/{job_id}/comparison-with-refs', f"{job['reference']}_comparison.mp4"
    else: path, name = f'/jobs/{job_id}/files/result.mp4', f"{job['reference']}.mp4"
    r = api('GET', path, stream=True, timeout=1800); dest = OUT / name
    with dest.open('wb') as f:
        for chunk in r.iter_content(1 << 20): f.write(chunk)
    return str(dest.resolve())


if __name__ == '__main__':
    mcp.run()
