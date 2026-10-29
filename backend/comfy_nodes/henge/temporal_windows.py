"""Pure, per-step temporal prediction fusion for native MiniMax H3 AV sampling.

Independent implementation on ComfyUI's ContextHandler protocol. No sequential warmup,
per-window noise draws, sampler replacement, crossfade, or process-wide monkeypatch.
"""
from dataclasses import dataclass
import bisect
import logging
import torch


# H3's causal temporal grid repeats 1,4,4,4,4 pixel frames per latent row.
def pixel_boundary(row):
    groups, tail = divmod(int(row), 5)
    return groups * 17 + sum((1, 4, 4, 4, 4)[:tail])


def latent_rows(frames):
    return 2 + ((frames - 5) // 17) * 5


def validate_window(frames, overlap):
    if type(frames) is not int or not 22 <= frames <= 362 or frames % 17 != 5:
        raise ValueError('Temporal window must be 22..362 frames on the H3 17n+5 grid')
    if type(overlap) is not int or not 5 <= overlap < frames or overlap % 17 != 5:
        raise ValueError('Temporal overlap must be smaller than the window and on the H3 17n+5 grid')


@dataclass(frozen=True)
class Window:
    video_start: int
    video_end: int
    audio_start: int
    audio_end: int

    @property
    def start_frame(self):return pixel_boundary(self.video_start)
    @property
    def end_frame(self):return pixel_boundary(self.video_end)


def plan_windows(video_t, audio_t, frames=107, overlap=22):
    validate_window(frames, overlap)
    if video_t < 2 or video_t % 5 != 2:
        raise ValueError('Pure windows require a native H3 video latent (5n+2 temporal rows)')
    expected_audio=round(pixel_boundary(video_t)*40/24)
    if audio_t != expected_audio:
        raise ValueError(f'H3 video/audio timelines disagree: expected {expected_audio} audio columns, got {audio_t}')
    size=min(latent_rows(frames),video_t)
    stride=latent_rows(frames)-latent_rows(overlap)
    starts=list(range(0,max(1,video_t-size+1),stride))
    if starts[-1]+size < video_t:starts.append(video_t-size)
    # A final shifted window still starts on the causal 17-frame boundary.
    def audio_at(row):return audio_t if row==video_t else round(pixel_boundary(row)*40/24)
    return tuple(Window(start,start+size,audio_at(start),audio_at(start+size)) for start in starts)


def _slice_audio(value, start, end):return value[...,start:end]


def crop_keyframes(keyframes, window):
    """Keep relevant anchors, crop aligned clips, and move them to the window's local clock."""
    cropped=[]
    for original in keyframes or ():
        origin=int(original['resolved_frame_index']);video=original.get('latent');audio=original.get('audio_latent')
        vt=video.shape[2] if video is not None else 0
        duration=pixel_boundary(vt) if vt else (audio.shape[-1]*24/40 if audio is not None else 0)
        if origin+duration <= window.start_frame or origin >= window.end_frame:continue
        item=dict(original)
        if vt==1:
            if not window.start_frame <= origin < window.end_frame:continue
            item['resolved_frame_index']=origin-window.start_frame
        else:
            clip_start=max(origin,window.start_frame);clip_end=min(origin+duration,window.end_frame)
            if video is not None:
                boundaries=[origin+pixel_boundary(i) for i in range(vt+1)]
                a=bisect.bisect_left(boundaries,clip_start);b=bisect.bisect_left(boundaries,clip_end)
                if a>=b or boundaries[a]!=clip_start or boundaries[b]!=clip_end:
                    raise ValueError('Clip guide is not aligned to this H3 window; use frame-0 aligned guide clips')
                item['latent']=video[:,:,a:b]
            item['resolved_frame_index']=clip_start-window.start_frame
        if audio is not None:
            a=max(0,round((window.start_frame-origin)*40/24));b=min(audio.shape[-1],round((window.end_frame-origin)*40/24))
            item['audio_latent']=_slice_audio(audio,a,b)
        cropped.append(item)
    return cropped


def crop_payload(original, window, total_video):
    payload=dict(original)
    # The packed layout belongs to the original shape; native H3 rebuilds it for each window.
    payload.pop('layout',None)
    payload['keyframes']=crop_keyframes(original.get('keyframes'),window)
    refs=[]
    for source in original.get('refs') or ():
        item=dict(source)
        if source.get('kind') in ('video','video_audio'):
            z=source['latent']
            if z.shape[2]!=total_video:
                raise ValueError('Windowed native motion reference must match the target temporal length')
            item['latent']=z[:,:,window.video_start:window.video_end]
            item['latent_t']=window.video_end-window.video_start
            a=source.get('audio_latent')
            if a is not None:
                if a.shape[-1] < window.audio_end:raise ValueError('Motion reference soundtrack is too short')
                item['audio_latent']=_slice_audio(a,window.audio_start,window.audio_end)
                item['ref_audio_t']=item['audio_latent'].shape[-1]
        refs.append(item)
    payload['refs']=refs
    payload['cond_video_latents']=[k['latent'] for k in payload['keyframes'] if k.get('latent') is not None]+[r['latent'] for r in refs if r.get('latent') is not None]
    payload['cond_audio_latents']=[k['audio_latent'] for k in payload['keyframes'] if k.get('audio_latent') is not None]+[r['audio_latent'] for r in refs if r.get('audio_latent') is not None]
    return payload


def _make_layout(text_length,shapes,payload):
    from comfy.ldm.minimax.model import PackedLayout
    video,audio=shapes
    return PackedLayout(text_length,video[2],(video[3]+1)//2*2,(video[4]+1)//2*2,audio[-1],keyframes=payload.get('keyframes'),refs=payload.get('refs'))


def _runtime():
    import comfy.utils,comfy.conds,comfy.model_management
    return comfy.utils,comfy.conds,comfy.model_management.throw_exception_if_processing_interrupted


class PureH3Windows:
    """Called once per model prediction by the stock sampler, including CFG branches."""
    dim=2
    freenoise=False
    def __init__(self,window_frames=107,overlap_frames=22,accumulator_device='cpu'):
        validate_window(window_frames,overlap_frames)
        if accumulator_device not in ('cpu','gpu'):raise ValueError('Unknown accumulator device')
        self.window_frames=window_frames;self.overlap_frames=overlap_frames
        self.context_length=latent_rows(window_frames);self.accumulator_device=accumulator_device

    def should_use_context(self,model,conds,x_in,timestep,model_options):return True

    def get_resized_cond(self,cond_in,x_in,window,device=None):
        if cond_in is None:return None
        span,shapes,total_video=window;_,cond_types,_=_runtime();result=[]
        for original in cond_in:
            if original.get('control') is not None:raise ValueError('Pure H3 windows do not yet support ControlNet')
            entry=dict(original);items=dict(original['model_conds'])
            if 'minimax_payload' not in items:raise ValueError('Pure windows require native MiniMax H3 conditioning')
            payload=items['minimax_payload'];cropped=crop_payload(payload.cond,span,total_video)
            text=items.get('c_crossattn')
            if text is None:raise ValueError('Pure H3 windows require text conditioning')
            # TARA inspects the packed layout BEFORE native H3 forward; build it here, not lazily.
            cropped['layout']=_make_layout(text.cond.shape[-2],shapes,cropped)
            items['minimax_payload']=payload._copy_with(cropped)
            items['latent_shapes']=cond_types.CONDConstant(shapes)
            for key,dim,a,b in [('denoise_mask',2,span.video_start,span.video_end),('audio_denoise_mask',3,span.audio_start,span.audio_end)]:
                if key in items:
                    value=items[key];items[key]=value._copy_with(value.cond.narrow(dim,a,b-a))
            entry['model_conds']=items;result.append(entry)
        return result

    def execute(self,calc_cond_batch,model,conds,x_in,timestep,model_options):
        utils,_,interrupted=_runtime()
        shape_cond=next((entry['model_conds'].get('latent_shapes') for group in conds if group for entry in group if entry['model_conds'].get('latent_shapes') is not None),None)
        if shape_cond is None:raise ValueError('Pure H3 windows need joint video/audio latent shapes')
        shapes=shape_cond.cond
        if len(shapes)!=2 or len(shapes[0])!=5 or len(shapes[1])!=4 or shapes[0][1]!=24 or tuple(shapes[1][1:3])!=(32,2):
            raise ValueError('Unsupported H3 AV latent layout')
        video,audio=utils.unpack_latents(x_in,shapes)
        windows=plan_windows(video.shape[2],audio.shape[-1],self.window_frames,self.overlap_frames)
        device=torch.device('cpu') if self.accumulator_device=='cpu' else x_in.device
        accum=[[torch.zeros(part.shape,dtype=torch.float32,device=device) for part in (video,audio)] if group is not None else None for group in conds]
        counts=[torch.zeros(video.shape[2],dtype=torch.float32,device=device),torch.zeros(audio.shape[-1],dtype=torch.float32,device=device)]
        for index,span in enumerate(windows):
            interrupted()
            parts=[video[:,:,span.video_start:span.video_end],audio[:,:,:,span.audio_start:span.audio_end]]
            packed,sub_shapes=utils.pack_latents(parts)
            sub_conds=[self.get_resized_cond(c,x_in,(span,sub_shapes,video.shape[2])) for c in conds]
            # Native H3 and TARA may annotate transformer_options: never leak a window's layout.
            options={**model_options,'transformer_options':dict(model_options.get('transformer_options',{}))}
            options['transformer_options']['henge_temporal_window']={'index':index,'start_frame':span.start_frame,'end_frame':span.end_frame}
            predictions=calc_cond_batch(model,sub_conds,packed,timestep,options)
            ranges=[(span.video_start,span.video_end,2),(span.audio_start,span.audio_end,3)]
            weights=[]
            for modality,(a,b,dim) in enumerate(ranges):
                size=b-a
                # Positive symmetric center weighting, normalized only after all windows.
                weight=torch.minimum(torch.arange(1,size+1,device=device),torch.arange(size,0,-1,device=device)).float()
                counts[modality][a:b]+=weight;view=[1]*len(shapes[modality]);view[dim]=size;weights.append(weight.reshape(view))
            for branch,buffer in enumerate(accum):
                if buffer is None:continue
                prediction_parts=utils.unpack_latents(predictions[branch],sub_shapes)
                for modality,(a,b,dim) in enumerate(ranges):
                    buffer[modality].narrow(dim,a,b-a).add_(prediction_parts[modality].to(device=device,dtype=torch.float32)*weights[modality])
        for count in counts:
            if not bool(torch.all(count>0)):raise RuntimeError('Temporal windows left uncovered AV rows')
        output=[]
        for buffer in accum:
            if buffer is None:output.append(torch.zeros_like(x_in));continue
            parts=[]
            for modality,dim in ((0,2),(1,3)):
                view=[1]*len(shapes[modality]);view[dim]=counts[modality].numel()
                parts.append((buffer[modality]/counts[modality].reshape(view)).to(device=x_in.device,dtype=x_in.dtype))
            output.append(utils.pack_latents(parts)[0])
        return output


class HengeH3PureWindows:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'model':('MODEL',),'window_frames':('INT',{'default':107,'min':22,'max':362,'step':17}),
            'overlap_frames':('INT',{'default':22,'min':5,'max':345,'step':17}),
            'accumulator_device':(['cpu','gpu'],{'default':'cpu'})}}
    RETURN_TYPES=('MODEL',);FUNCTION='apply';CATEGORY='Henge/experimental'
    DESCRIPTION='Pure temporal windows at every denoise step. No sequential warmup or frame crossfade. Use inside each shot; initial support for native H3 Guide Latents and TARA. Experimental; not compatible with Causal/ControlNet/another context handler.'
    def apply(self,model,window_frames=107,overlap_frames=22,accumulator_device='cpu'):
        if model.model_options.get('context_handler') is not None:raise ValueError('Remove the existing context-window handler before enabling pure H3 windows')
        handler=PureH3Windows(window_frames,overlap_frames,accumulator_device)
        from comfy.context_windows import create_prepare_sampling_wrapper
        patched=model.clone();patched.model_options['context_handler']=handler
        create_prepare_sampling_wrapper(patched)
        logging.info('[Henge] PURE temporal windows: %d frames / %d overlap; all denoise steps, no sequential warmup; accumulator=%s',window_frames,overlap_frames,accumulator_device)
        return (patched,)
