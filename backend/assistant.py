"""Studio assistant: an LLM that drives the Henge studio for the user.

The conversation is kept by the browser in a provider-neutral form and sent back on every step:
  {'role': 'user', 'text': str, 'images': [data_url]}
  {'role': 'assistant', 'text': str, 'tool_calls': [{'id', 'name', 'input'}], 'native': <provider blocks>}
  {'role': 'tool', 'results': [{'id', 'name', 'text', 'images': [data_url], 'is_error': bool}]}
The history is only ever appended to; Claude's own content blocks (thinking included) are kept in 'native' and
sent back unchanged.

Tools are of two kinds. Studio tools change what the user sees (mode, marks, prompt, Generate) and run in the
browser; job tools read and steer jobs on the bridge and run here. One step calls the model until it answers or asks
for studio tools, which the browser runs before the next step.

Providers: Claude through the official Anthropic SDK, and any OpenAI-compatible chat completions API (OpenAI, and
local servers such as LM Studio, Ollama or vLLM)."""
import base64
import json
import re
from pathlib import Path

import requests

DEFAULTS = {'provider': 'anthropic', 'model': 'claude-opus-5-5', 'base_url': '', 'api_key': '', 'effort': 'medium'}
PROVIDERS = ('anthropic', 'openai')

SYSTEM = """You are the Henge studio assistant. Henge turns a guide video plus reference pictures into a new video with MiniMax H3. You operate the studio for the user: you see its state, look at frames, mark people, set options and start generations. The user watches the screen change as you work.

Modes: swap (Character Swap: a person in the video becomes the character in a picture), motion (Motion Transfer: a new character performs the guide's motion), headswap (only the head changes; one face picture), sharpness (sharpen the video; no pictures, no marks).

Guide representation (how marked people reach the model):
- original: the video goes in as it is. Fine for one person. With two or more people the model cannot tell who becomes whom.
- 2d: each marked person is tracked and tinted with its color; mark_opacity 0.35 keeps the face and expression visible, 1 is a solid color. Best for keeping several people apart (swap, motion).
- 3d: each person becomes a colored 3D body with face. People only.
- mask: only the area around the marked people is generated again; the rest keeps the source pixels. Works in swap, motion and headswap.
TARA (method) was trained without color marks: with TARA use only original or mask, never 2d/3d.

How to work:
1. Read the studio state. If the guide video or the pictures are missing, ask the user to attach them in the chat or in the studio. Chat videos are automatically loaded as the guide and chat images as reference Pictures in attachment order.
2. Look before you act: view_pictures to see the references, view_frame or find_people to see the video.
3. To bind people: call find_people at a time where everyone is visible; it returns the frame with numbered people. Then mark_subject each person you need, with the matching picture slots. Marks must be inside the selected interval.
4. Choose the guide: several people -> 2d (or mask to keep the scene untouched); one person -> original is fine, mask keeps the scene. If find_people fails with two or more people, do not fall back to original silently: say so and ask the user to mark them with 'Mark in video' (or retry), because with original the model can swap who becomes whom.
5. Write the prompt with set_prompt only when the user asked for something the mode needs (motion and swap use the user's request; headswap and sharpness ignore it). Refer to pictures as @Picture1, @Picture2.
6. Before generate, summarize what will run (mode, who becomes whom, guide, quality) in two or three lines. If the user has not asked you to generate, ask first.
7. Videos with camera cuts: people seen only after a cut are not recognised automatically. When marks are used, generate with auto-approve off, wait_for_job 'plan', get_job_shots, and for every shot that starts after a cut call find_people a little after its start and mark_subject each visible person with subject=<their number> (people can change places); then send_marks_to_job. Skip people who are not in that shot.
8. You can change anything the user can: options (get_options / set_options: model, TARA, turbo, steps...), interval, shots, output, project name, pictures and subjects. Say what you changed.
9. Jobs run in the background. After generate, check the job once; if it is still running, tell the user they can keep chatting and do not repeatedly poll. When they write again, the studio state contains the current job status. Once the plan is ready, inspect its color or mask preview; once the render is done, inspect the result.
10. Every generation has a visible 8-character reference such as #a1b2c3d4. The user may identify a generation with that reference; job tools accept it with or without # as well as the full id. When a generation starts, mention its visible reference so the user can refer to it later.
The studio state's selected_job is the generation selected on screen. When the user says "this generation", "essa geração" or an equivalent expression, use selected_job.id; do not ask them to copy its id.
11. If the user says an active generation looks wrong or that you made a mistake, inspect its state and call confirm_cancel_job to ask whether they want to cancel it. Criticism is not permission to cancel: only call cancel_job when that approval result is true. If they decline, leave it running and continue the conversation.
12. A completed generation can feed another mode: call use_generation_as_guide with its reference and the requested next mode, then configure that mode and ask before generating. Do not ask the user to download and upload a Henge result again.

Be brief. Always answer in the language of the user's latest message, even when it differs from the interface or earlier messages. Write approval questions in that same language. Never invent people, pictures or results you have not seen."""

STUDIO_TOOLS = [
    {'name': 'get_studio_state', 'description': 'The current studio state: mode, guide video (duration, selected interval, size), pictures, marked subjects, guide representation, prompt, quality and the selected job.',
     'input_schema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
    {'name': 'view_pictures', 'description': 'See the attached reference pictures (Picture 1, Picture 2...).',
     'input_schema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
    {'name': 'view_frame', 'description': 'See one frame of the guide video at a time in seconds (within the selected interval).',
     'input_schema': {'type': 'object', 'properties': {'time': {'type': 'number'}}, 'required': ['time'], 'additionalProperties': False}},
    {'name': 'find_people', 'description': 'Detect and number every person (or animal) in the guide frame at a time. Returns the frame with numbers drawn on each one; use the numbers with mark_subject.',
     'input_schema': {'type': 'object', 'properties': {'time': {'type': 'number'}, 'kind': {'type': 'string', 'enum': ['person', 'animal']}}, 'required': ['time'], 'additionalProperties': False}},
    {'name': 'set_mode', 'description': 'Switch the studio mode.',
     'input_schema': {'type': 'object', 'properties': {'mode': {'type': 'string', 'enum': ['swap', 'motion', 'headswap', 'sharpness']}}, 'required': ['mode'], 'additionalProperties': False}},
    {'name': 'set_prompt', 'description': 'Replace the request text in the prompt editor. Use @Picture1, @Picture2 for the pictures.',
     'input_schema': {'type': 'object', 'properties': {'text': {'type': 'string'}}, 'required': ['text'], 'additionalProperties': False}},
    {'name': 'mark_subject', 'description': 'Mark a person found by find_people (same time). Without subject: a new subject with its own color bound to picture_slots. With subject (its number): another mark of that same subject, e.g. the same person in a later shot after a camera cut.',
     'input_schema': {'type': 'object', 'properties': {'person': {'type': 'integer', 'description': 'number from find_people'}, 'time': {'type': 'number', 'description': 'the time used in find_people'},
                                                       'picture_slots': {'type': 'array', 'items': {'type': 'integer'}}, 'label': {'type': 'string'}, 'subject': {'type': 'integer', 'description': 'existing subject number to add this mark to'}},
                      'required': ['person', 'time'], 'additionalProperties': False}},
    {'name': 'remove_subject', 'description': 'Remove one marked subject (its number in the studio state).',
     'input_schema': {'type': 'object', 'properties': {'subject': {'type': 'integer'}}, 'required': ['subject'], 'additionalProperties': False}},
    {'name': 'remove_pictures', 'description': 'Remove reference pictures: the given slots, or all of them when slots is empty.',
     'input_schema': {'type': 'object', 'properties': {'slots': {'type': 'array', 'items': {'type': 'integer'}}}, 'additionalProperties': False}},
    {'name': 'set_interval', 'description': 'Select the part of the guide video to use, in seconds of the source video.',
     'input_schema': {'type': 'object', 'properties': {'start': {'type': 'number'}, 'end': {'type': 'number'}}, 'required': ['start', 'end'], 'additionalProperties': False}},
    {'name': 'set_shots', 'description': "How long videos are split: seconds per shot (2-20), cut_mode ('fit' = shot length ending at camera cuts, 'every' = a new shot at every cut, 'off' = fixed length) and context_frames carried between shots (0-48). With marks, cuts always start a new shot.",
     'input_schema': {'type': 'object', 'properties': {'seconds': {'type': 'number'}, 'cut_mode': {'type': 'string', 'enum': ['fit', 'every', 'off']}, 'context_frames': {'type': 'integer'}}, 'additionalProperties': False}},
    {'name': 'set_output', 'description': 'Output audio and frame rate: keep_audio (the source audio in the result), audio_conditioning (the guide audio drives the generation), timeline_fps.',
     'input_schema': {'type': 'object', 'properties': {'keep_audio': {'type': 'boolean'}, 'audio_conditioning': {'type': 'boolean'}, 'timeline_fps': {'type': 'number'}}, 'additionalProperties': False}},
    {'name': 'set_project', 'description': 'Name the project (shown in History).',
     'input_schema': {'type': 'object', 'properties': {'name': {'type': 'string'}}, 'required': ['name'], 'additionalProperties': False}},
    {'name': 'get_options', 'description': 'The generation options now (model profile, method, turbo, steps, cfg, seed, structure guidance, FIBO, reference preparation, sharpness upscale...) and what is installed: models, turbos, bases, upscalers, TARA.',
     'input_schema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
    {'name': 'set_options', 'description': "Change generation options; only the keys given change. Keys: profile (a model id from get_options), conditioning_mode ('guide' | 'tara'), turbo, steps, cfg, seed, structure_cfg (TARA, 1-3), base, fibo ('auto' | 'off'), prepare_references, reference_scale, clip_fps, attention, upscale_method ('h3' | 'nvidia' | 'none'), upscale_steps, upscale_denoise, lora_strength, mask (latent mask settings).",
     'input_schema': {'type': 'object', 'properties': {'options': {'type': 'object'}}, 'required': ['options'], 'additionalProperties': False}},
    {'name': 'send_marks_to_job', 'description': "Copy the studio's current marked subjects to a job that waits for approval (after adding marks in shots that start after a cut); its color/mask preview is rebuilt.",
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}}, 'required': ['job_id'], 'additionalProperties': False}},
    {'name': 'select_job', 'description': 'Show a job in the generation panel (its plan, previews, result).',
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}}, 'required': ['job_id'], 'additionalProperties': False}},
    {'name': 'use_generation_as_guide', 'description': "Load a completed generation's result as the guide video for another mode. Use this for a second pass such as Swap -> Sharpness. This changes the studio but does not start the next generation.",
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}, 'mode': {'type': 'string', 'enum': ['swap', 'motion', 'headswap', 'sharpness']}}, 'required': ['job_id', 'mode'], 'additionalProperties': False}},
    {'name': 'confirm_cancel_job', 'description': "Show the user an explicit approval dialog before cancelling an active generation. question must be a complete yes/no question in the language of the user's latest message and include the reason and visible generation reference. This only asks; it never cancels. Call cancel_job only if the result says approved=true.",
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}, 'question': {'type': 'string'}}, 'required': ['job_id', 'question'], 'additionalProperties': False}},
    {'name': 'clear_subjects', 'description': 'Remove every marked subject.',
     'input_schema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
    {'name': 'set_guide', 'description': 'Set the guide representation, and for 2d the mark opacity (0.1-1).',
     'input_schema': {'type': 'object', 'properties': {'representation': {'type': 'string', 'enum': ['original', '2d', '3d', 'mask']}, 'mark_opacity': {'type': 'number'}},
                      'required': ['representation'], 'additionalProperties': False}},
    {'name': 'set_quality', 'description': 'Output resolution (short side). 1440p and 2160p are only for sharpness.',
     'input_schema': {'type': 'object', 'properties': {'quality': {'type': 'string', 'enum': ['480p', '720p', '1080p', '1440p', '2160p']}}, 'required': ['quality'], 'additionalProperties': False}},
    {'name': 'set_auto_approve', 'description': 'Whether a generation runs straight after planning (true) or stops at the plan for review (false, recommended when you want to check previews).',
     'input_schema': {'type': 'object', 'properties': {'enabled': {'type': 'boolean'}}, 'required': ['enabled'], 'additionalProperties': False}},
    {'name': 'generate', 'description': 'Press Generate with the current studio state. Returns the new job id.',
     'input_schema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
]
JOB_TOOLS = [
    {'name': 'get_job', 'description': 'Status, stage, message, plan summary, prompt and warnings of a job. job_id accepts the full id or its visible 8-character generation reference, with or without #.',
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}}, 'required': ['job_id'], 'additionalProperties': False}},
    {'name': 'wait_for_job', 'description': "Check whether a background job reached the plan review ('plan') or finished ('done'). Returns immediately; if it is still running, tell the user and let them keep chatting instead of polling.",
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}, 'until': {'type': 'string', 'enum': ['plan', 'done']}}, 'required': ['job_id', 'until'], 'additionalProperties': False}},
    {'name': 'view_job_video', 'description': "See a few frames of a job video: 'marks' (2d color guide at full opacity), 'mask' (latent mask preview), 'guide' (prepared guide), 'result' or 'comparison'.",
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}, 'which': {'type': 'string', 'enum': ['marks', 'mask', 'guide', 'result', 'comparison']}, 'frames': {'type': 'integer'}},
                      'required': ['job_id', 'which'], 'additionalProperties': False}},
    {'name': 'set_job_mark_opacity', 'description': 'Change the 2d mark opacity of a job waiting for approval.',
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}, 'opacity': {'type': 'number'}}, 'required': ['job_id', 'opacity'], 'additionalProperties': False}},
    {'name': 'get_job_shots', 'description': 'How a job splits the video into shots: index, start and end (seconds in the source), and whether each starts after a camera cut (people may have moved or changed there).',
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}}, 'required': ['job_id'], 'additionalProperties': False}},
    {'name': 'redo_shot', 'description': 'Render one shot (1-based) of a finished job again with a new seed (or the given one) and join the video again; the other shots are kept. job_id accepts the visible generation reference. Then wait_for_job done.',
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}, 'shot': {'type': 'integer'}, 'seed': {'type': 'integer'}}, 'required': ['job_id', 'shot'], 'additionalProperties': False}},
    {'name': 'retry_job', 'description': 'Run a failed or cancelled job again.',
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}}, 'required': ['job_id'], 'additionalProperties': False}},
    {'name': 'approve_job', 'description': 'Approve a plan waiting for review so the video renders.',
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}}, 'required': ['job_id'], 'additionalProperties': False}},
    {'name': 'cancel_job', 'description': 'Cancel a job.',
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}}, 'required': ['job_id'], 'additionalProperties': False}},
]
TOOLS = STUDIO_TOOLS + JOB_TOOLS
STUDIO_NAMES = {t['name'] for t in STUDIO_TOOLS}
JOB_NAMES = {t['name'] for t in JOB_TOOLS}


def load_config(path: Path) -> dict:
    try:
        stored = json.loads(path.read_text()) if path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        stored = {}
    return {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS}}


def public_config(cfg: dict) -> dict:
    """The config for the browser: the key is never sent back, only whether one is saved."""
    key = cfg.get('api_key') or ''
    return {**{k: v for k, v in cfg.items() if k != 'api_key'}, 'has_key': bool(key), 'key_hint': f'…{key[-4:]}' if len(key) > 8 else ''}


def save_config(path: Path, update: dict) -> dict:
    cfg = load_config(path)
    for k in ('provider', 'model', 'base_url', 'effort'):
        if k in update and isinstance(update[k], str):
            cfg[k] = update[k].strip()
    if isinstance(update.get('api_key'), str) and update['api_key'].strip():
        cfg['api_key'] = update['api_key'].strip()
    if update.get('clear_key'):
        cfg['api_key'] = ''
    if cfg['provider'] not in PROVIDERS:
        raise ValueError('Unknown provider')
    if cfg['effort'] not in ('', 'low', 'medium', 'high', 'xhigh', 'max'):   # '' = the model's default
        raise ValueError('Unknown effort')
    if not cfg['model']:
        raise ValueError('Choose a model')
    if cfg['base_url'] and not re.match(r'^https?://', cfg['base_url']):
        raise ValueError('The base URL must start with http:// or https://')
    path.write_text(json.dumps(cfg, indent=2))
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return cfg


def _split_data_url(url: str) -> tuple[str, str]:
    m = re.match(r'^data:(image/[a-z+]+);base64,(.+)$', url, re.S)
    if not m:
        raise ValueError('Images must be data URLs')
    return m.group(1), m.group(2)


# --- Claude (official Anthropic SDK) ---

def _to_anthropic(messages: list) -> list:
    out = []
    for m in messages:
        if m['role'] == 'user':
            content = [{'type': 'image', 'source': {'type': 'base64', 'media_type': t, 'data': d}} for t, d in map(_split_data_url, m.get('images') or [])]
            out.append({'role': 'user', 'content': content + [{'type': 'text', 'text': m.get('text') or '…'}]})
        elif m['role'] == 'assistant':
            if m.get('native') and m.get('native_provider') == 'anthropic':
                out.append({'role': 'assistant', 'content': m['native']})
            else:
                content = ([{'type': 'text', 'text': m['text']}] if m.get('text') else []) + [{'type': 'tool_use', 'id': c['id'], 'name': c['name'], 'input': c['input']} for c in m.get('tool_calls') or []]
                out.append({'role': 'assistant', 'content': content or [{'type': 'text', 'text': '…'}]})
        elif m['role'] == 'tool':
            blocks = []
            for r in m['results']:
                inner = [{'type': 'text', 'text': r.get('text') or 'done'}] + [{'type': 'image', 'source': {'type': 'base64', 'media_type': t, 'data': d}} for t, d in map(_split_data_url, r.get('images') or [])]
                blocks.append({'type': 'tool_result', 'tool_use_id': r['id'], 'content': inner, **({'is_error': True} if r.get('is_error') else {})})
            out.append({'role': 'user', 'content': blocks})
    return out


def _call_anthropic(cfg: dict, messages: list) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=cfg['api_key'] or None, **({'base_url': cfg['base_url']} if cfg['base_url'] else {}))
    tools = list(TOOLS)
    tools[-1] = {**tools[-1], 'cache_control': {'type': 'ephemeral'}}   # tools + system are the stable prefix
    kwargs = dict(model=cfg['model'], max_tokens=16000, system=[{'type': 'text', 'text': SYSTEM}], tools=tools,
                  messages=_to_anthropic(messages), **({'output_config': {'effort': cfg['effort']}} if cfg['effort'] else {}))
    try:
        # Claude Opus 5.5 / Sonnet 5.5 / Fable 5.1: if a safety classifier declines, the API reruns on a fallback model.
        response = client.beta.messages.create(betas=['server-side-fallback-2026-07-01'], extra_body={'fallbacks': 'default'}, **kwargs)
    except anthropic.BadRequestError as e:
        if 'fallback' not in str(e).lower():
            raise
        response = client.beta.messages.create(**kwargs)   # models or gateways without fallbacks
    if response.stop_reason == 'refusal':
        return {'text': 'The model declined this request.', 'tool_calls': [], 'native': None}
    native = [b.model_dump(exclude_none=True) for b in response.content]
    text = '\n'.join(b.text for b in response.content if b.type == 'text').strip()
    calls = [{'id': b.id, 'name': b.name, 'input': b.input} for b in response.content if b.type == 'tool_use']
    return {'text': text, 'tool_calls': calls, 'native': native, 'native_provider': 'anthropic'}


# --- OpenAI-compatible chat completions (OpenAI, LM Studio, Ollama, vLLM...) ---

def _to_openai(messages: list) -> list:
    out = [{'role': 'system', 'content': SYSTEM}]
    for m in messages:
        if m['role'] == 'user':
            parts = [{'type': 'text', 'text': m.get('text') or '…'}] + [{'type': 'image_url', 'image_url': {'url': u}} for u in m.get('images') or []]
            out.append({'role': 'user', 'content': parts if m.get('images') else (m.get('text') or '…')})
        elif m['role'] == 'assistant':
            msg = {'role': 'assistant', 'content': m.get('text') or None}
            if m.get('tool_calls'):
                msg['tool_calls'] = [{'id': c['id'], 'type': 'function', 'function': {'name': c['name'], 'arguments': json.dumps(c['input'])}} for c in m['tool_calls']]
            out.append(msg)
        elif m['role'] == 'tool':
            images = []
            for r in m['results']:
                out.append({'role': 'tool', 'tool_call_id': r['id'], 'content': ('ERROR: ' if r.get('is_error') else '') + (r.get('text') or 'done')})
                images += [(r['name'], u) for u in r.get('images') or []]
            if images:
                # Tool messages carry text only in this API: the pictures follow as a user message.
                out.append({'role': 'user', 'content': [{'type': 'text', 'text': 'Images returned by the tools above, in order: ' + ', '.join(n for n, _ in images)}]
                            + [{'type': 'image_url', 'image_url': {'url': u}} for _, u in images]})
    return out


def _call_openai(cfg: dict, messages: list) -> dict:
    base = (cfg['base_url'] or 'https://api.openai.com/v1').rstrip('/')
    tools = [{'type': 'function', 'function': {'name': t['name'], 'description': t['description'], 'parameters': t['input_schema']}} for t in TOOLS]
    headers = {'Authorization': f"Bearer {cfg['api_key']}"} if cfg['api_key'] else {}
    body = {'model': cfg['model'], 'messages': _to_openai(messages), 'tools': tools}
    # OpenAI's current models take max_completion_tokens and reject max_tokens; local servers (LM Studio, Ollama,
    # vLLM) still read max_tokens. Start with the one the server is likely to take, switch once if it refuses.
    limits = ['max_completion_tokens', 'max_tokens'] if 'api.openai.com' in base else ['max_tokens', 'max_completion_tokens']
    for i, name in enumerate(limits):
        r = requests.post(base + '/chat/completions', headers=headers, timeout=300, json={**body, name: 8192})
        if r.ok or i or r.status_code != 400 or name not in r.text:
            break
    if not r.ok:
        raise RuntimeError(f'{base} HTTP {r.status_code}: {r.text[:400]}')
    msg = r.json()['choices'][0]['message']
    calls = []
    for c in msg.get('tool_calls') or []:
        try:
            args = json.loads(c['function'].get('arguments') or '{}')
        except json.JSONDecodeError:
            args = {'_invalid_json': c['function'].get('arguments')}
        calls.append({'id': c['id'], 'name': c['function']['name'], 'input': args})
    return {'text': (msg.get('content') or '').strip(), 'tool_calls': calls, 'native': None}


def call_model(cfg: dict, messages: list) -> dict:
    if cfg['provider'] == 'anthropic':
        return _call_anthropic(cfg, messages)
    return _call_openai(cfg, messages)


def jpeg_data_url(path: Path) -> str:
    return 'data:image/jpeg;base64,' + base64.b64encode(Path(path).read_bytes()).decode()


def step(cfg: dict, messages: list, run_job_tool, max_rounds: int = 8) -> dict:
    """Run the model until it answers or needs studio tools. Job tools run here through run_job_tool(name, input) ->
    (text, images). Returns the appended history and, when needed, the studio calls for the browser plus the job
    results to send back with theirs (all results of one turn go in one message)."""
    messages = list(messages)
    for _ in range(max_rounds):
        reply = call_model(cfg, messages)
        messages.append({'role': 'assistant', **reply})
        if not reply['tool_calls']:
            return {'messages': messages, 'studio_calls': [], 'job_results': [], 'done': True}
        job_results = []
        for c in reply['tool_calls']:
            if c['name'] in JOB_NAMES:
                try:
                    text, images = run_job_tool(c['name'], c['input'])
                    job_results.append({'id': c['id'], 'name': c['name'], 'text': text, 'images': images})
                except Exception as e:  # the model sees the error and can recover
                    job_results.append({'id': c['id'], 'name': c['name'], 'text': str(e)[:800], 'images': [], 'is_error': True})
            elif c['name'] not in STUDIO_NAMES:
                job_results.append({'id': c['id'], 'name': c['name'], 'text': f"Unknown tool {c['name']}", 'images': [], 'is_error': True})
        studio = [c for c in reply['tool_calls'] if c['name'] in STUDIO_NAMES]
        if studio:
            return {'messages': messages, 'studio_calls': studio, 'job_results': job_results, 'done': False}
        messages.append({'role': 'tool', 'results': job_results})
    return {'messages': messages, 'studio_calls': [], 'job_results': [], 'done': True}
