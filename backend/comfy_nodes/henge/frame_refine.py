"""Frame-by-frame video refinement with any ComfyUI image model, with temporal carry.

Each output frame starts from the previous output frame warped onto the current one by optical flow (DIS, OpenCV),
blended with the current source frame where the warp is unreliable (occlusion / large photometric error), then is
re-noised to the first sigma given and sampled with the same noise draw every frame. The current source frame is the
edit input: encoded per frame by the model's own edit encoder (Fibo 2.0, MOSS-Image Edit), or attached as a reference
latent to fixed conditioning (FLUX.2 Klein and other `reference_latents` models). A final carry blend pulls static
regions back onto the warped previous output to suppress residual flicker.

Experimental (Rerender-A-Video / TokenFlow style without cross-frame attention).
"""
import logging

import cv2
import numpy as np
import torch

import comfy.model_management as mm
import comfy.sample
import comfy.utils
import latent_preview
import node_helpers


def gray(frame):
    return cv2.cvtColor((frame.clamp(0, 1).numpy() * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)


def flow_between(dis, a, b):
    """Backward flow b -> a on uint8 gray frames: for each pixel of b, where it came from in a."""
    return dis.calc(b, a, None)


def warp(image, flow):
    """image [H,W,C] float numpy sampled at pixel + flow."""
    h, w = flow.shape[:2]
    grid = np.stack(np.meshgrid(np.arange(w), np.arange(h)), -1).astype(np.float32) + flow
    return cv2.remap(image, grid[..., 0], grid[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def match_color(image, reference):
    """Per-channel mean/std of image matched to reference (keeps the model from drifting the grade frame to frame)."""
    mu, sd = image.mean((0, 1), keepdim=True), image.std((0, 1), keepdim=True) + 1e-5
    rmu, rsd = reference.mean((0, 1), keepdim=True), reference.std((0, 1), keepdim=True)
    return ((image - mu) / sd * rsd + rmu).clamp(0, 1)


class HengeFrameRefine:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'model': ('MODEL',), 'vae': ('VAE',),
            'encoder': (['fibo2', 'moss edit', 'reference latent', 'none'], {'tooltip': 'How the current source frame reaches the model: its own edit encoder per frame (needs clip), as a reference latent on positive/negative, or only through the init latent.'}),
            'sampler': ('SAMPLER',), 'sigmas': ('SIGMAS', {'tooltip': 'Full schedule; denoise keeps its last part.'}),
            'frames': ('IMAGE', {'tooltip': 'Source video frames.'}),
            'width': ('INT', {'default': 1024, 'min': 64, 'max': 8192, 'step': 16}),
            'height': ('INT', {'default': 1024, 'min': 64, 'max': 8192, 'step': 16}),
            'seed': ('INT', {'default': 0, 'min': 0, 'max': 0xFFFFFFFFFFFFFFFF}),
            'cfg': ('FLOAT', {'default': 1.0, 'min': 0.0, 'max': 30.0, 'step': 0.1}),
            'denoise': ('FLOAT', {'default': 0.45, 'min': 0.05, 'max': 1.0, 'step': 0.01}),
            'carry': ('FLOAT', {'default': 0.85, 'min': 0.0, 'max': 1.0, 'step': 0.05, 'tooltip': 'How much of the warped previous output seeds each frame where the flow is reliable.'}),
            'deflicker': ('FLOAT', {'default': 0.3, 'min': 0.0, 'max': 1.0, 'step': 0.05, 'tooltip': 'Final pull of reliable regions onto the warped previous output.'}),
            'color_match': ('BOOLEAN', {'default': True}),
        }, 'optional': {
            'clip': ('CLIP',),
            'prompt': ('STRING', {'multiline': True, 'default': 'Enhance this image with sharp, crisp details while keeping the content, composition and colors identical.'}),
            'positive': ('CONDITIONING',), 'negative': ('CONDITIONING',),
            'moss_edit_format': ('STRING', {'default': '', 'tooltip': 'MOSS-Image edit layout (TextEncodeMOSSImageEdit edit_format); empty = its first option.'}),
        }}
    RETURN_TYPES = ('IMAGE',)
    FUNCTION = 'refine'
    CATEGORY = 'Henge'

    def encode(self, encoder, clip, prompt, positive, negative, vae, current, moss_edit_format):
        frame = current[None, ..., :3]
        if encoder == 'fibo2':
            from comfy_extras.nodes_fibo2 import TextEncodeFibo2
            pos, neg, _ = TextEncodeFibo2.execute(clip=clip, prompt=prompt, vae=vae, images={'image_1': frame}, width=frame.shape[2], height=frame.shape[1]).args
            return pos, neg
        if encoder == 'moss edit':
            from comfy_extras.nodes_moss_image import TextEncodeMOSSImageEdit, EDIT_FORMATS
            fmt = moss_edit_format or next(iter(EDIT_FORMATS))
            pos = TextEncodeMOSSImageEdit.execute(clip=clip, prompt=prompt, edit_format=fmt, images={'image_1': frame}, vae=vae).args[0]
            neg = TextEncodeMOSSImageEdit.execute(clip=clip, prompt='', edit_format=fmt, images={'image_1': frame}, vae=vae).args[0]
            return pos, neg
        if encoder == 'reference latent':
            ref = vae.encode(frame)
            return (node_helpers.conditioning_set_values(positive, {'reference_latents': [ref]}, append=True),
                    node_helpers.conditioning_set_values(negative, {'reference_latents': [ref]}, append=True))
        return positive, negative

    def refine(self, model, vae, encoder, sampler, sigmas, frames, width, height, seed, cfg, denoise, carry, deflicker, color_match,
               clip=None, prompt='', positive=None, negative=None, moss_edit_format=''):
        if encoder in ('fibo2', 'moss edit') and clip is None:
            raise ValueError(f'The {encoder} encoder needs the clip input')
        if encoder in ('reference latent', 'none') and (positive is None or negative is None):
            raise ValueError('Connect positive and negative conditioning, or pick an edit encoder')
        steps = len(sigmas) - 1
        keep = max(1, round(steps * denoise))
        sigmas = sigmas[-(keep + 1):]
        up = comfy.utils.common_upscale(frames.movedim(-1, 1), width, height, 'lanczos', 'disabled').movedim(1, -1).clamp(0, 1)
        dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        small = [gray(f) for f in frames]
        sx, sy = width / frames.shape[2], height / frames.shape[1]
        out, prev = [], None
        noise = None
        pbar = comfy.utils.ProgressBar(len(frames))
        for i in range(len(frames)):
            mm.throw_exception_if_processing_interrupted()
            current = up[i]
            init, reliable = current, None
            if prev is not None:
                back = flow_between(dis, small[i - 1], small[i])          # current -> previous
                fwd = flow_between(dis, small[i], small[i - 1])           # previous -> current
                # forward-backward consistency on the source frames: big round-trip error = occlusion
                round_trip = back + warp(fwd, back)
                err = np.linalg.norm(round_trip, axis=-1)
                photo = np.abs(warp(small[i - 1].astype(np.float32), back) - small[i].astype(np.float32)) / 255.0
                ok = np.exp(-(err / 1.5) ** 2) * np.exp(-(photo / 0.08) ** 2)
                flow_up = cv2.resize(back, (width, height), interpolation=cv2.INTER_LINEAR) * np.array([sx, sy], np.float32)
                warped = torch.from_numpy(warp(prev.numpy(), flow_up))
                reliable = torch.from_numpy(cv2.resize(ok.astype(np.float32), (width, height), interpolation=cv2.INTER_LINEAR))[..., None]
                init = current * (1 - carry * reliable) + warped * (carry * reliable)
            latent = vae.encode(init[None, ..., :3])
            latent = comfy.sample.fix_empty_latent_channels(model, latent)
            if noise is None:  # one draw for every frame: the same noise pattern does not crawl
                noise = comfy.sample.prepare_noise(latent, seed)
            pos, neg = self.encode(encoder, clip, prompt, positive, negative, vae, current, moss_edit_format)
            samples = comfy.sample.sample_custom(model, noise, cfg, sampler, sigmas, pos, neg, latent, noise_mask=None, callback=None, disable_pbar=True, seed=seed)
            image = vae.decode(samples).reshape(-1, height, width, 3)[0].float().cpu()
            if color_match:
                image = match_color(image, current)
            if reliable is not None and deflicker > 0:
                image = image * (1 - deflicker * reliable) + warped * (deflicker * reliable)
            prev = image
            out.append(image)
            pbar.update_absolute(i + 1, len(frames))
        logging.info(f'[Henge frame refine] {len(frames)} frames at {width}x{height}, {keep} steps each')
        return (torch.stack(out),)
