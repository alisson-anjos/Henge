"""Run with the isolated Molmo2 environment; the bridge only exchanges JSON/files."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time

from molmo_pointing import normalize_points, validate_request

COORDS = re.compile(r"<(?:points|tracks).*? coords=\"([0-9\t:;, .]+)\"/?>")
FRAMES = re.compile(r"(?:^|\t|:|,|;)([0-9\.]+) ([0-9\. ]+)")
POINTS = re.compile(r"([0-9]+) ([0-9]{3,4}) ([0-9]{3,4})")
MATCH_PROMPT = 'Point to the person in Image 2 who is the same individual shown in Image 1.'


def parse(text):
    """Molmo2 points: (frame or image index, object id, x, y) with x/y from 0 to 1."""
    out = []
    for coord in COORDS.finditer(text):
        for group in FRAMES.finditer(coord.group(1)):
            for m in POINTS.finditer(group.group(2)):
                out.append((float(group.group(1)), int(m.group(1)), float(m.group(2))/1000, float(m.group(3))/1000))
    return out


def generate(model, processor, inputs, tokens):
    import torch
    inputs = {key: value.to('cuda') for key, value in inputs.items()}
    with torch.inference_mode():
        output = model.generate(**inputs, max_new_tokens=tokens, do_sample=False)
    return processor.tokenizer.decode(output[0, inputs['input_ids'].size(1):], skip_special_tokens=True)


def point(model, processor, args):
    from molmo_utils import process_vision_info
    validate_request(args.query, args.start, args.end)
    with tempfile.TemporaryDirectory(prefix='henge-molmo-') as folder:
        clip = Path(folder)/'shot.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(args.start), '-i', args.video, '-t', str(args.end-args.start),
            '-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-y', str(clip)], check=True)
        messages = [{'role': 'user', 'content': [dict(type='text', text=args.query), dict(type='video', video=str(clip), max_fps=8)]}]
        _, videos, video_kwargs = process_vision_info(messages)
        videos, metadata = zip(*videos)
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(videos=list(videos), video_metadata=list(metadata), text=text, padding=True, return_tensors='pt', **video_kwargs)
        print('Running video pointing', flush=True)
        generated = generate(model, processor, inputs, 2048)
    width, height = int(metadata[0]['width']), int(metadata[0]['height'])
    points, warnings = normalize_points([(i, t, x*width, y*height) for t, i, x, y in parse(generated)], width, height, args.start, args.end)
    if not points: warnings.append('No valid target points returned; do not invent a SAM mark')
    return dict(query=args.query, start=args.start, end=args.end, points=points, warnings=warnings, generated_text=generated,
        note='Proposed points only. Object IDs are scoped to this query; inspect before binding Pictures. SAM tracking is a separate step.')


def ask(model, processor, args):
    """A free question about the video (caption, who does what when, how many people...), answered in text."""
    from molmo_utils import process_vision_info
    with tempfile.TemporaryDirectory(prefix='henge-molmo-') as folder:
        clip = Path(folder)/'clip.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(args.start), '-i', args.video, '-t', str(args.end-args.start),
            '-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-y', str(clip)], check=True)
        messages = [{'role': 'user', 'content': [dict(type='text', text=args.query), dict(type='video', video=str(clip), max_fps=args.fps)]}]
        _, videos, video_kwargs = process_vision_info(messages)
        videos, metadata = zip(*videos)
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(videos=list(videos), video_metadata=list(metadata), text=text, padding=True, return_tensors='pt', **video_kwargs)
        print('Answering about the video', flush=True)
        answer = generate(model, processor, inputs, 1024)
    return dict(question=args.query, start=args.start, end=args.end, answer=answer.strip(),
        note='Timestamps in the answer are seconds from the start of the interval.')


def crop_at(frame, x, y, width=.28, height=.62):
    # Narrow, so neighbours stay out; tall, with the point low in it, so the head is inside when it lands on the torso.
    # The width follows the shorter side: in a portrait video a height-based width would take in the next person.
    w, h = int(min(frame.width, frame.height)*width), int(frame.height*height); cx, cy = int(x*frame.width), int(y*frame.height)
    left = max(0, min(frame.width-w, cx-w//2)); top = max(0, min(frame.height-h, cy-int(h*.6)))
    return frame.crop((left, top, left+w, top+h))


def collage(refs, height=512, gap=24):
    from PIL import Image
    images = [r.resize((max(1, r.width*height//r.height), height)) for r in refs]
    board = Image.new('RGB', (sum(i.width for i in images)+gap*(len(images)-1), height), 'white'); x = 0; spans = []
    for im in images:
        board.paste(im, (x, 0)); spans.append((x/board.width, (x+im.width)/board.width)); x += im.width+gap
    return board, spans


def match(model, processor, args):
    """Forward: the reference photo -> a point in the keyframe. Backward: a crop at that point -> which of all the
    references (side by side). Only cycle-consistent points are kept: Molmo2 otherwise points at a look-alike."""
    from PIL import Image
    refs = [Image.open(r).convert('RGB') for r in args.refs]
    board, spans = collage(refs)

    def ask(first, second):
        messages = [{'role': 'user', 'content': [dict(type='text', text=MATCH_PROMPT), dict(type='image', image=first), dict(type='image', image=second)]}]
        inputs = processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, return_tensors='pt', return_dict=True)
        return [(x, y) for index, _, x, y in parse(generate(model, processor, inputs, 128)) if index == 2]

    def check(key, frame, ref_index, ref):
        forward = ask(ref, frame)
        if not forward:
            return dict(ref=ref_index, shot=key['shot'], time=key['time'], ok=False, reason='not found')
        x, y = forward[0]
        back = ask(crop_at(frame, x, y), board)
        back_ref = next((i for i, (a, b) in enumerate(spans) for bx, _ in back[:1] if a <= bx <= b), None)
        return dict(ref=ref_index, shot=key['shot'], time=key['time'], x=x, y=y, back_ref=back_ref, ok=back_ref == ref_index,
            reason='' if back_ref == ref_index else f'reverse check chose person {back_ref+1}' if back_ref is not None else 'reverse check found nobody')

    keys = json.loads(Path(args.keys).read_text()); matches = []
    for shot in sorted({k['shot'] for k in keys}):
        shot_keys = [k for k in keys if k['shot'] == shot]
        frames = [Image.open(k['path']).convert('RGB') for k in shot_keys]
        for ref_index, ref in enumerate(refs):
            # A person needs 2 of 3 keyframes: two agreeing answers decide; the third is looked at only on a split.
            results = []
            for key, frame in zip(shot_keys, frames):
                if len(results) >= 2 and results[0]['ok'] == results[1]['ok']:
                    break
                results.append(check(key, frame, ref_index, ref))
            matches += results
        print('shot', shot, [(m['ref'], m['time'], m['ok']) for m in matches if m['shot'] == shot], flush=True)
    return dict(matches=matches)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True); parser.add_argument('--output', required=True)
    parser.add_argument('--mode', choices=['point', 'match', 'ask'], default='point')
    parser.add_argument('--fps', type=float, default=2.)
    parser.add_argument('--video'); parser.add_argument('--query')
    parser.add_argument('--start', type=float, default=0.); parser.add_argument('--end', type=float)
    parser.add_argument('--keys'); parser.add_argument('--refs', nargs='*', default=[])
    args = parser.parse_args()
    if args.mode == 'point': validate_request(args.query, args.start, args.end)
    import torch
    from transformers import AutoProcessor, AutoModelForImageTextToText
    started = time.monotonic()
    print('Loading local Molmo2', flush=True)
    model = AutoModelForImageTextToText.from_pretrained(args.model, trust_remote_code=True, local_files_only=True,
        dtype=torch.bfloat16, device_map='cuda')
    processor = AutoProcessor.from_pretrained(args.model, trust_remote_code=True, local_files_only=True)
    payload = point(model, processor, args) if args.mode == 'point' else match(model, processor, args) if args.mode == 'match' else ask(model, processor, args)
    payload.update(model=Path(args.model).name, seconds=time.monotonic()-started, peak_vram_gb=torch.cuda.max_memory_allocated()/1024**3)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: v for k, v in payload.items() if k not in ('generated_text', 'matches', 'answer')}), flush=True)


if __name__ == '__main__': main()
