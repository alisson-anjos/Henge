"""Optional local Molmo2 runner. No torch/transformers imports in the bridge.

Molmo2 returns points (object_id, timestamp, x, y), not masks or calibrated scores. Points are proposals for SAM.
Two requests: point_video (a described target in one shot) and match_people (find the person shown in a photo in
every shot: Molmo2 cannot read images and a video together, so it compares the photo with keyframes of each shot).
"""
import base64
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import threading

from PIL import Image, ImageDraw

LOCK = threading.Lock()
ACTIVE_LOCK = threading.Lock()
ACTIVE = {}
CANCELLED = set()
class MolmoCancelled(RuntimeError): pass
# Set by the bridge: frees the VRAM of a ComfyUI on this same machine before Molmo2 loads (one GPU, two models).
BEFORE_RUN = None
# Set by the bridge: the user's Molmo2 settings {model_path, keep_warm_minutes, image_quality}.
SETTINGS = lambda: {}
_WARM = {'process': None, 'key': None, 'timer': None}
COLORS = ['#ff3b30', '#34c759', '#0a84ff', '#ffd60a', '#bf5af2', '#ff9f0a']
MAX_MATCH_SECONDS = 120
MAX_PEOPLE = 6


def normalize_points(raw, width, height, start, end):
    points, rejected = [], 0
    for row in raw:
        if not isinstance(row, (list, tuple)) or len(row) != 4:
            rejected += 1; continue
        try:
            object_id, timestamp, x, y = map(float, row)
        except (ValueError, TypeError):
            rejected += 1; continue
        absolute = start + timestamp
        if not all(math.isfinite(v) for v in (object_id, timestamp, x, y)) or object_id < 0 or object_id != int(object_id) or not start <= absolute < end or not 0 <= x < width or not 0 <= y < height:
            rejected += 1; continue
        point = dict(object_id=int(object_id), time_seconds=absolute, x=x/width, y=y/height,
            frame_index_24fps=int(math.floor(absolute*24+.5)), frame_width=width, frame_height=height)
        if point not in points: points.append(point)
    points.sort(key=lambda p: (p['time_seconds'], p['object_id']))
    warnings = [f'{rejected} invalid/out-of-interval points discarded'] if rejected else []
    return points, warnings


def validate_request(query, start, end):
    if not isinstance(query, str) or not query.strip() or len(query) > 1500:
        raise ValueError('Supply a nonempty target description of at most 1500 characters')
    if not all(math.isfinite(x) for x in (start, end)) or start < 0 or not start < end or end-start > 30:
        raise ValueError('Point one shot at a time: interval must be positive, at most 30 seconds, with start >= 0')


def validate_match(people, start, end):
    if not 1 <= people <= MAX_PEOPLE:
        raise ValueError(f'Send between 1 and {MAX_PEOPLE} photos of the people to find')
    if not all(math.isfinite(x) for x in (start, end)) or start < 0 or not start < end or end-start > MAX_MATCH_SECONDS:
        raise ValueError(f'The interval must be positive, at most {MAX_MATCH_SECONDS} seconds, with start >= 0')


def configured():
    if (SETTINGS() or {}).get('enabled') is False:
        raise ValueError('Molmo2 is turned off in Settings → Molmo2; the planner VLM does the video analysis')
    python = os.environ.get('HENGE_MOLMO_PYTHON', '')
    model = (SETTINGS() or {}).get('model_path') or os.environ.get('HENGE_MOLMO_MODEL', '')
    if not python or not model or not Path(python).is_file() or not (Path(model)/'config.json').is_file():
        raise ValueError('Local Molmo2 is not configured. Set HENGE_MOLMO_PYTHON and HENGE_MOLMO_MODEL; see docs/molmo-pointing.md')
    return python, model


def release():
    """Unload a warm Molmo2 (before ComfyUI uses this GPU, or after its idle time)."""
    with LOCK:
        release_locked()


def _cli_to_request(args):
    """['--mode', 'ask', '--refs', 'a', 'b', ...] -> {'mode': 'ask', 'refs': ['a', 'b'], ...} for the warm worker."""
    out, key = {}, None
    for item in args:
        if item.startswith('--'):
            key = item[2:].replace('-', '_'); out[key] = None
        elif key == 'refs':
            out['refs'] = (out.get('refs') or []) + [item]
        else:
            out[key] = float(item) if key in ('start', 'end', 'fps') else item
    if 'refs' in out and out['refs'] is None: out['refs'] = []
    return out


def run_worker(args, request_id=None):
    python, model = configured()
    cfg = SETTINGS() or {}
    crops = 4 if cfg.get('image_quality') == 'fast' else 8
    warm = max(0., min(60., float(cfg.get('keep_warm_minutes') or 0)))
    command = [python, str(Path(__file__).with_name('molmo_pointing_worker.py')), '--model', model, '--max-crops', str(crops)]
    # Before Molmo2 loads, a local ComfyUI unloads its models so the two never sit in VRAM together.
    with LOCK:
        if BEFORE_RUN is not None:
            try:
                BEFORE_RUN()
            except Exception as exc:
                print(f'[Henge] could not free ComfyUI VRAM before Molmo2: {exc}', flush=True)
        if not warm:
            # Default: one process per request, exiting after it, so no Molmo weights stay resident.
            if _WARM['process']: release_locked()
            with ACTIVE_LOCK:
                if request_id in CANCELLED: raise MolmoCancelled('Molmo2 request cancelled')
            proc = subprocess.Popen(command + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if request_id:
                with ACTIVE_LOCK: ACTIVE[request_id] = proc
            try:
                try: stdout, stderr = proc.communicate(timeout=900)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    try: proc.wait(timeout=10)
                    except subprocess.TimeoutExpired: proc.kill(); proc.wait()
                    raise RuntimeError('Molmo2 request timed out after 15 minutes')
            finally:
                if request_id:
                    with ACTIVE_LOCK: ACTIVE.pop(request_id, None)
            with ACTIVE_LOCK:
                cancelled = request_id in CANCELLED
                if cancelled: CANCELLED.discard(request_id)
            if cancelled: raise MolmoCancelled('Molmo2 request cancelled')
            if proc.returncode: raise RuntimeError('Molmo2 failed: '+(stderr or stdout)[-2200:])
            return
        key = (model, crops)
        proc = _WARM['process']
        if proc is None or proc.poll() is not None or _WARM['key'] != key:
            if proc: release_locked()
            proc = subprocess.Popen(command + ['--serve'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            _WARM.update(process=proc, key=key)
        if request_id:
            with ACTIVE_LOCK:
                if request_id in CANCELLED:
                    release_locked(); CANCELLED.discard(request_id); raise MolmoCancelled('Molmo2 request cancelled')
                ACTIVE[request_id] = proc
        if _WARM['timer']: _WARM['timer'].cancel()
        proc.stdin.write(json.dumps(_cli_to_request(args)) + '\n'); proc.stdin.flush()
        tail = []
        for line in proc.stdout:
            if line.startswith('HENGE-REPLY '):
                reply = json.loads(line[len('HENGE-REPLY '):]); break
            tail = (tail + [line])[-40:]
        else:
            _WARM.update(process=None, key=None)
            if request_id:
                with ACTIVE_LOCK:
                    ACTIVE.pop(request_id, None)
                    cancelled = request_id in CANCELLED
                    if cancelled: CANCELLED.discard(request_id)
                if cancelled: raise MolmoCancelled('Molmo2 request cancelled')
            raise RuntimeError('Molmo2 stopped: ' + ''.join(tail)[-2200:])
        if request_id:
            with ACTIVE_LOCK:
                ACTIVE.pop(request_id, None)
                cancelled = request_id in CANCELLED
                if cancelled: CANCELLED.discard(request_id)
            if cancelled: raise MolmoCancelled('Molmo2 request cancelled')
        timer = threading.Timer(warm * 60, release); timer.daemon = True; timer.start(); _WARM['timer'] = timer
    if not reply.get('ok'):
        raise RuntimeError('Molmo2 failed: ' + str(reply.get('error'))[-2200:])


def cancel_request(request_id):
    """Stop a Molmo worker subprocess if the user cancels an in-flight request."""
    if not isinstance(request_id, str) or not request_id or len(request_id) > 100: return False
    with ACTIVE_LOCK:
        CANCELLED.add(request_id)
        proc = ACTIVE.get(request_id)
        if proc and proc.poll() is None:
            proc.terminate()
            return True
        return False


def release_locked():
    proc, timer = _WARM['process'], _WARM['timer']
    _WARM.update(process=None, key=None, timer=None)
    if timer: timer.cancel()
    if proc and proc.poll() is None:
        proc.terminate()
        try: proc.wait(timeout=20)
        except subprocess.TimeoutExpired: proc.kill()


def point_video(video, query, start, end, work):
    validate_request(query, start, end)
    output = Path(work)/'points.json'
    run_worker(['--mode', 'point', '--video', str(video), '--query', query, '--start', str(start), '--end', str(end), '--output', str(output)])
    payload = json.loads(output.read_text())
    payload['previews'] = point_previews(video, payload['points'], work)
    return payload


MAX_ASK_SECONDS = 120
GUIDE_CAPTION = ('Describe this video for someone who will recreate its performance with other characters. Give a short '
                 'timeline with seconds: how many people there are and where they are in the frame, what each one does '
                 '(actions, gestures, who speaks or sings), the camera (framing and motion) and any camera cuts. '
                 'Do not describe faces, clothing colours or identities. Plain text, at most 12 lines.')


def validate_ask(question, start, end):
    if not isinstance(question, str) or not question.strip() or len(question) > 2000:
        raise ValueError('Ask a nonempty question of at most 2000 characters')
    if not all(math.isfinite(x) for x in (start, end)) or start < 0 or not start < end or end-start > MAX_ASK_SECONDS:
        raise ValueError(f'The interval must be positive, at most {MAX_ASK_SECONDS} seconds, with start >= 0')


def ask_video(video, question, start, end, work, fps=2., request_id=None):
    """Molmo2 answers a question about the video interval (it sees the whole clip with timestamps)."""
    validate_ask(question, start, end)
    output = Path(work)/'answer.json'
    run_worker(['--mode', 'ask', '--video', str(video), '--query', question, '--start', str(start), '--end', str(end),
        '--fps', str(fps), '--output', str(output)], request_id=request_id)
    return json.loads(output.read_text())


def available():
    try:
        configured(); return True
    except ValueError:
        return False


def detect_cuts(video, start, end, threshold=.3):
    """Camera cuts (absolute seconds) inside [start, end), from ffmpeg's scene score."""
    result = subprocess.run(['ffmpeg', '-hide_banner', '-ss', str(start), '-t', str(end-start), '-i', str(video), '-an',
        '-vf', f"select='gt(scene,{threshold})',showinfo", '-f', 'null', '-'], capture_output=True, text=True, timeout=300)
    return [start+float(t) for t in re.findall(r'pts_time:([0-9.]+)', result.stderr) if .05 < float(t) < end-start-.05]


def shot_keyframes(start, end, cuts, min_shot=.25):
    """Three keyframes per shot (at 20%, 50% and 80% of it), so a person is accepted only when found in two."""
    bounds = [start, *sorted(cuts), end]; shots = []
    for i, (a, b) in enumerate(zip(bounds, bounds[1:])):
        if b-a < min_shot: continue
        shots.append(dict(shot=len(shots), start=a, end=b, times=[round(a+(b-a)*f, 3) for f in (.2, .5, .8)]))
    return shots


def match_people(video, refs, start, end, work):
    """Find each reference person in every shot. Returns per person one anchor per shot where Molmo2 found them
    and the reverse check (crop at the point -> which reference) agreed."""
    validate_match(len(refs), start, end)
    configured()
    work = Path(work)
    shots = shot_keyframes(start, end, detect_cuts(video, start, end))
    keys = []
    for shot in shots:
        for t in shot['times']:
            dest = work/f'key_{shot["shot"]:02d}_{t:.3f}.jpg'
            subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(t), '-i', str(video), '-frames:v', '1', '-q:v', '2', '-y', str(dest)],
                check=True, capture_output=True, timeout=120)
            keys.append(dict(shot=shot['shot'], time=t, path=str(dest)))
    (work/'keys.json').write_text(json.dumps(keys))
    output = work/'matches.json'
    run_worker(['--mode', 'match', '--keys', str(work/'keys.json'), '--refs', *map(str, refs), '--output', str(output)])
    raw = json.loads(output.read_text())
    return {**summarize_matches(raw['matches'], shots, len(refs)), 'model': raw.get('model'), 'seconds': raw.get('seconds'),
            'previews': match_previews(keys, raw['matches']),
            'note': 'One anchor per shot where the person was found and the reverse check agreed in at least two of its three keyframes. SAM tracks from these points.'}


def summarize_matches(matches, shots, people):
    result = []
    for ref in range(people):
        anchors, missing = [], []
        for shot in shots:
            hits = [m for m in matches if m['ref'] == ref and m['shot'] == shot['shot'] and m['ok']]
            # A look-alike passes the reverse check in one keyframe at most; the real person in most of them.
            if len(hits) >= min(2, len(shot['times'])):
                h = hits[0]; anchors.append(dict(x=h['x'], y=h['y'], time_seconds=h['time'], shot=shot['shot']))
            else:
                missing.append(shot['shot'])
        result.append(dict(person=ref+1, anchors=anchors, missing_shots=missing))
    return {'people': result, 'shots': [{k: s[k] for k in ('shot', 'start', 'end')} for s in shots]}


def match_previews(keys, matches, limit=8):
    previews, seen = [], set()
    for key in keys:
        hits = [m for m in matches if m['time'] == key['time'] and m['ok']]
        if key['shot'] in seen or not hits: continue
        seen.add(key['shot'])
        with Image.open(key['path']) as source:
            im = source.convert('RGB'); im = im.resize((960, im.height*960//im.width)); draw = ImageDraw.Draw(im)
        for m in hits:
            x, y = m['x']*im.width, m['y']*im.height; color = COLORS[m['ref'] % len(COLORS)]
            draw.ellipse((x-9, y-9, x+9, y+9), fill=color, outline='white', width=3)
            draw.text((x+12, y-10), f"person {m['ref']+1} @ {key['time']:.2f}s", fill='white', stroke_width=2, stroke_fill='black')
        buf = io.BytesIO(); im.save(buf, 'JPEG', quality=85)
        previews.append('data:image/jpeg;base64,'+base64.b64encode(buf.getvalue()).decode())
        if len(previews) >= limit: break
    return previews


def point_previews(video, points, work):
    times = sorted({p['time_seconds'] for p in points})
    if len(times) > 4:
        times = [times[round(i*(len(times)-1)/3)] for i in range(4)]
    previews = []
    for i, timestamp in enumerate(times):
        dest = Path(work)/f'point_{i}.jpg'
        subprocess.run(['ffmpeg','-v','error','-ss',str(timestamp),'-i',str(video),'-frames:v','1',
            '-vf','scale=960:-2','-y',str(dest)],check=True,capture_output=True)
        with Image.open(dest) as source:
            im=source.convert('RGB'); draw=ImageDraw.Draw(im)
            for point in points:
                if point['time_seconds'] != timestamp: continue
                x,y=point['x']*im.width,point['y']*im.height
                draw.ellipse((x-7,y-7,x+7,y+7),fill='#ff00ff',outline='white',width=2)
                draw.text((x+10,y-10),f"#{point['object_id']} @ {timestamp:.2f}s",fill='white',stroke_width=2,stroke_fill='black')
            im.save(dest)
            buf=io.BytesIO();im.save(buf,'JPEG',quality=85)
        previews.append('data:image/jpeg;base64,'+base64.b64encode(buf.getvalue()).decode())
    return previews
