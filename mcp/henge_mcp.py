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
Use status to inspect current capabilities and get_settings for backend configuration. Original guide is the default, including vehicles/objects. Mask is opt-in and requires subject anchors. Temporal windows are optional, disabled by default and require temporal_windows_ready. Use view_frame for visual inspection; call Molmo tools only if pointing_status reports configured. Never require Molmo for an ordinary edit.
For multiple replacements, always recommend Motion Transfer TARA: its LoRA was trained for multiple people, objects and vehicles. Use mode='motion' with options profile='motion_tara' AND conditioning_mode='tara'; do not substitute the Guide Latents motion LoRA. Character Swap is an alternative only when every replaced subject is a person. If the user has not explicitly chosen the mode, ask them to choose in your client and wait before create_job; do not infer approval from the default mode.
Optional turbo pika6 uses the Ref2VA base, 6 steps, CFG 1 and sampler_name='auto' (LCM). Six steps use the published Comfy manual sigmas; custom steps use the normal model scheduler. Stage-2 Open-H3 settings stay independent.
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
    if plan: out['plan'] = {k: plan[k] for k in ('summary', 'prompt', 'representation', 'warnings', 'adapt_reference') if k in plan}
    return out


@mcp.tool()
def status() -> dict:
    """Whether Henge and its GPU backend are online, which backend is in use, and which models, turbos and upscalers are installed."""
    h = api('GET', '/health').json()
    keep = ('online', 'comfy_url', 'offline_reason', 'training_busy', 'tara_ready', 'temporal_windows_ready', 'editor_ready', 'samplers', 'bases', 'regenerate', 'guides')
    return {**{k: h.get(k) for k in keep}, 'models': {k: {'label': v.get('label'), 'task': v.get('task'), 'available': v.get('available', True)} for k, v in (h.get('models') or {}).items()},
            'turbos': h.get('turbos'), 'upscalers': h.get('upscalers'), 'video_analysis': pointing_status()}


SETTINGS_ROUTES = {'connection': '/connection', 'assistant': '/assistant/config', 'molmo': '/molmo/settings'}


@mcp.tool()
def get_settings(section: str = 'all') -> dict:
    """Read current backend connection, assistant and Molmo settings; 'all' returns all sections.
    Stored credentials stay redacted. Browser draft/generation settings are separate; pass generation options to create_job.
    """
    if section == 'all': return {key: api('GET', path).json() for key, path in SETTINGS_ROUTES.items()}
    if section not in SETTINGS_ROUTES: raise ValueError('Choose connection, assistant, molmo or all')
    return api('GET', SETTINGS_ROUTES[section]).json()


@mcp.tool()
def set_settings(section: str, settings: dict) -> dict:
    """Patch connection, assistant or molmo backend settings after reading get_settings, when requested by the user.
    Existing API validation and active-job connection locks apply. Blank credentials preserve stored keys.
    Does not edit the web browser draft or start a generation.
    """
    if section not in SETTINGS_ROUTES: raise ValueError('Choose connection, assistant or molmo')
    return api('POST', SETTINGS_ROUTES[section], json=settings).json()


@mcp.tool()
def view_frame(video: str, time: float = 0) -> list:
    """Inspect a local guide frame without Molmo or a GPU. Use start/middle/end frames to understand vehicles,
    objects and motion. Coordinates for subject anchors are normalized x/y from 0 to 1.
    """
    source = Path(video).expanduser()
    if time < 0 or time >= probe(source)['duration']: raise ValueError('Choose a time inside the video')
    with tempfile.TemporaryDirectory() as folder:
        frame = Path(folder) / 'frame.jpg'
        subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(time), '-i', str(source), '-frames:v', '1', '-vf', 'scale=960:960:force_original_aspect_ratio=decrease', '-y', str(frame)], check=True)
        return [json.dumps({'time': time}), Image(data=frame.read_bytes(), format='jpeg')]


@mcp.tool()
def get_models() -> dict:
    """Live catalog, installation progress and model availability for local ComfyUI or Serverless. No download starts."""
    return api('GET','/models').json()


@mcp.tool()
def install_model(model_id: str) -> dict:
    """Install a catalogued model only when requested by the user. Serverless GPU time is billed during download.
    Uses the configured local models folder or existing worker/volume; blocked during generations. Poll get_models.
    """
    return api('POST','/models/install',json={'model_id':model_id}).json()


@mcp.tool()
def cancel_model_installation() -> dict:
    """Cancel a download when requested; keeps partial data for retry. Does not cancel a generation."""
    return api('POST','/models/cancel',json={}).json()


@mcp.tool()
def refresh_worker_inventory() -> dict:
    """Explicitly wake the configured worker to refresh capabilities and models. GPU time is billed. Poll get_models."""
    return api('POST','/models/refresh',json={}).json()


@mcp.tool()
def get_updates() -> dict:
    """Running version, upstream changelog and update notice; never installs code or restarts services."""
    return api('GET','/updates').json()


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
def pointing_status() -> dict:
    """Whether the optional local MolmoPoint model/runner is configured on the Henge bridge."""
    return api('GET','/assistant/pointing').json()


@mcp.tool()
def point_video(video: str, query: str, start: float, end: float) -> list:
    """Use local MolmoPoint to propose points for described targets in one video shot, at most 30 seconds.
    Returns normalized x/y, absolute times and previews. This does not segment, bind Pictures or generate.
    Inspect results, group the right person's points and pass them as subjects[].anchors to create_job.
    Object IDs are scoped to this request; repeat and inspect after each camera cut.
    Requires HENGE_MOLMO_PYTHON and HENGE_MOLMO_MODEL on the Henge bridge machine.
    """
    source=Path(video).expanduser()
    with source.open('rb') as stream:
        result=api('POST','/assistant/point-video',files={'video':(source.name,stream,'video/mp4')},
            data={'query':query,'start':str(start),'end':str(end)},timeout=1000).json()
    previews=result.pop('previews',[])
    return [json.dumps(result), *[Image(data=base64.b64decode(p.split(',',1)[1]),format='jpeg') for p in previews]]


@mcp.tool()
def suggest_cuts(video: str, max_seconds: float = 5, start: float = 0, end: float | None = None) -> str:
    """Let local Molmo2 choose where a video splits into shots of at most max_seconds: natural breaks (end of a
    sentence, a pause between actions) plus camera cuts. Returns points (seconds from start) and the shots; pass the
    points as split_points to create_job. Requires Molmo2 on the Henge bridge machine.
    """
    source = Path(video).expanduser()
    end = probe(source)['duration'] if end is None else end
    with source.open('rb') as stream:
        result = api('POST', '/assistant/suggest-cuts', files={'video': (source.name, stream, 'video/mp4')},
                     data={'start': str(start), 'end': str(end), 'max_seconds': str(max_seconds)}, timeout=1000).json()
    return json.dumps(result)


@mcp.tool()
def ask_video(video: str, question: str, start: float = 0, end: float | None = None) -> str:
    """Ask local Molmo2 about a video: it watches the whole interval with timestamps. Use it for captions, timelines,
    how many people and where, who does or says what and when, camera moves and cuts. Timestamps in the answer are
    seconds from start. Requires HENGE_MOLMO_PYTHON and HENGE_MOLMO_MODEL on the Henge bridge machine.
    """
    source = Path(video).expanduser()
    end = probe(source)['duration'] if end is None else end
    with source.open('rb') as stream:
        result = api('POST', '/assistant/ask-video', files={'video': (source.name, stream, 'video/mp4')},
                     data={'question': question, 'start': str(start), 'end': str(end)}, timeout=1000).json()
    return result.get('answer', json.dumps(result))


@mcp.tool()
def match_people(video: str, photos: list[str], start: float = 0, end: float | None = None) -> list:
    """Find the people shown in photos (one photo per person, at most 6) in every shot of a video, with local Molmo2.
    Camera cuts are detected; a person gets one anchor per shot where they are found in two of its three keyframes
    and a reverse check agrees. Returns people[i].anchors ready for create_job subjects (add picture_slots), shots
    and one preview per shot. Inspect the previews. Does not segment or generate; SAM tracks from the anchors.
    Requires HENGE_MOLMO_PYTHON and HENGE_MOLMO_MODEL on the Henge bridge machine.
    """
    source = Path(video).expanduser()
    end = probe(source)['duration'] if end is None else end
    streams = [source.open('rb'), *[Path(p).expanduser().open('rb') for p in photos]]
    try:
        files = [('video', (source.name, streams[0], 'video/mp4'))] + [('people', (Path(p).name, s, 'application/octet-stream')) for p, s in zip(photos, streams[1:])]
        result = api('POST', '/assistant/match-people', files=files, data={'start': str(start), 'end': str(end)}, timeout=1800).json()
    finally:
        for s in streams: s.close()
    previews = result.pop('previews', [])
    return [json.dumps(result), *[Image(data=base64.b64decode(p.split(',', 1)[1]), format='jpeg') for p in previews]]


@mcp.tool()
def create_job(mode: str, video: str, prompt: str = '', pictures: list[str] | None = None, start: float = 0, end: float | None = None,
               quality: str = '480p', project: str = 'Henge', subjects: list[dict] | None = None, auto_approve: bool = False,
               keep_audio: bool = True, generate_audio: bool = False, background: str | None = None, seconds_per_shot: float = 4.5, options: dict | None = None, split_points: list[float] | None = None, guide_representation: str = 'original', mark_opacity: float = 1, processing: dict | None = None, audio_conditioning: bool = False, first_frame_slot: int | None = None) -> dict:
    """Start a generation from local files.
    mode: 'swap' | 'motion' | 'headswap' | 'sharpness'. video: path of the guide video. pictures: paths, in order Picture 1, 2...
    (swap/motion 1-11, headswap exactly 1 face, sharpness none). prompt: the request, naming pictures as @Picture1, @Picture2
    (headswap and sharpness ignore it). start/end: the interval in seconds (default the whole video).
    quality: '480p' | '720p' | '1080p' ('1440p' | '2160p' only for sharpness).
    subjects (swap with several people): [{"picture_slots": [1], "x": 0.42, "y": 0.35, "time": 2.0, "label": "driver"}], x/y from find_people.
    Each subject can instead supply anchors: [{"x": 0.42, "y": 0.35, "time_seconds": 2.0}, ...] for multiple marks/cuts.
    auto_approve: render straight after planning instead of stopping at the plan for review.
    split_points: seconds (from start) where shots must end, e.g. from suggest_cuts.
    background: optional path of a picture that replaces what is behind the people, moving with the guide's camera
    (moving plate, built before planning; swap and motion).
    generate_audio: keep the soundtrack H3 generates per shot (joined at the cuts) instead of the guide's sound; write spoken
    lines in the prompt as <d>[language] text</d>. Needs the H3 audio VAE on the backend (profile audio).
    guide_representation: original (default), 2d, 3d or mask; mask requires subjects with anchors.
    mark_opacity: color-guide opacity 0.1-1. processing: backend processing fields (cut_mode, context_frames, mode, etc.).
    audio_conditioning: use guide audio as conditioning. first_frame_slot: optional reference slot used as first frame.
    options: all backend generation options, including temporal_windows, regional_attention, mask and refiner settings, e.g. {"profile": "character", "conditioning_mode": "guide"|"tara", "turbo": "dmd8", "seed": 42, "upscale_method": "h3"|"regenerate"|"nvidia"|"none"}.
    Returns the job; follow it with wait_for_job."""
    if guide_representation not in ('original', '2d', '3d', 'mask'): raise ValueError('Unknown guide representation')
    if guide_representation == 'mask' and not subjects: raise ValueError('Mask requires subject anchors; use original for an ordinary edit')
    pictures = [Path(p).expanduser() for p in pictures or []]
    source = Path(video).expanduser(); meta = probe(source)
    end = meta['duration'] if end is None else min(end, meta['duration'])
    duration = end - start; frames = max(22, int((round(seconds_per_shot * 24) - 5) // 17) * 17 + 5)
    bindings = [{'id': str(uuid.uuid4()), 'label': s.get('label') or f'Subject {i + 1}', 'color': COLORS[i % len(COLORS)], 'picture_slots': s.get('picture_slots') or [i + 1],
                 'anchors': [{'x': a['x'], 'y': a['y'], 'time_seconds': a.get('time_seconds', a.get('time', start)), 'frame_width': meta['width'], 'frame_height': meta['height']} for a in (s.get('anchors') or [s])]} for i, s in enumerate(subjects or [])]
    native = re.sub(r'@Picture\s*(\d+)', r'<Picture \1>', prompt)
    for i, b in enumerate(bindings):
        refs = ', '.join(f'<Picture {n}>' for n in b['picture_slots'])
        native += f"\n<Subject {i + 1}> uses the identity and appearance from {refs} and follows its selected performer in <Video 1>. Keep this assignment through position changes, occlusion and cuts."
    fixed = mode in ('headswap', 'sharpness')
    direction = {'schema_version': 2, 'project': project, 'mode': mode, 'quality': quality,
                 'processing': {**({'split_points': split_points} if split_points else {}), 'mode': 'context_window' if duration > 15 else 'single', 'max_shots': 0, 'requested_seconds_per_shot': seconds_per_shot, 'frames_per_shot': frames,
                                'timeline_fps': 24, 'frame_grid': '17n+5', 'trim_to_source_length': True, 'join': 'ordered', 'execution_status': 'comfy_backend', 'context_frames': 22, 'cut_mode': 'fit'},
                 'audio_conditioning': {'enabled': audio_conditioning, 'source': 'guide' if audio_conditioning else None}, 'output_audio': {'keep_source': keep_audio and not generate_audio, 'generate': generate_audio},
                 'prompt': '' if fixed else native.strip(), 'editor_prompt': '' if fixed else prompt,
                 'subject_guidance': {'representation': guide_representation, 'mark_opacity': mark_opacity, 'bindings': [] if mode == 'sharpness' else bindings, 'status': 'selection_only', 'marker_colors_are_output_appearance': False},
                 'video': {'name': source.name, 'source_signature': f'{source.name}:{source.stat().st_size}', 'conditioning': 'guide_latents', 'source_duration': meta['duration'],
                           'start_seconds': start, 'end_seconds': end, 'duration': duration},
                 'pictures': [{'slot': i + 1, 'token': f'<Picture {i + 1}>', 'name': p.name} for i, p in enumerate(pictures)], 'generation_status': 'not_submitted'}
    if processing: direction['processing'].update(processing)
    if first_frame_slot is not None: direction['first_frame_slot'] = first_frame_slot
    opts = {'auto_approve': auto_approve, 'enhance_prompt': True, **(options or {})}
    files = [('video', (source.name, source.open('rb'), 'video/mp4'))] + [(f'picture_{i + 1}', (p.name, p.open('rb'), 'application/octet-stream')) for i, p in enumerate(pictures)]
    if background: files.append(('background', (Path(background).name, Path(background).expanduser().open('rb'), 'application/octet-stream')))
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
