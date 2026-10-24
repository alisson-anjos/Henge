"""H3 video context in Qwen embeddings without a native video-latent reference."""
import math
import time
from dataclasses import replace

from comfy_extras.nodes_minimax_h3 import MiniMaxH3ReferenceToVideo
from comfy_api.latest import io


class _VideoContextClip:
    """Request-local adapter; never changes the user's CLIP or cached conditioning."""

    def __init__(self, clip, items):
        self._clip = clip
        self._items = items

    def __getattr__(self, name):
        return getattr(self._clip, name)

    def tokenize(self, text, **kwargs):
        items = list(kwargs.get("minimax_ref_items") or [])
        # Pictures keep their numbering. Context videos precede any explicit
        # native video/audio references, so the shot remains <Video 1>.
        index = 0
        while index < len(items) and items[index].get("type") == "image":
            index += 1
        kwargs["minimax_ref_items"] = items[:index] + self._items + items[index:]
        tokens = self._clip.tokenize(text, **kwargs)
        def count_video_blocks(value):
            if isinstance(value, dict):
                if value.get("minimax_video_block") is True:
                    return 1
                return sum(count_video_blocks(v) for k, v in value.items() if k != "data")
            if isinstance(value, (list, tuple)):
                return sum(count_video_blocks(v) for v in value)
            return 0
        expected = sum((item["data"].shape[0] + 1) // 2 for item in self._items)
        actual = count_video_blocks(tokens)
        if actual < expected:
            raise ValueError("CLIP did not produce the H3 video vision blocks. Use the native MiniMax H3 CLIP loader.")
        print(f"[BFS H3 CLIP context] tokenizer confirmed {actual} video vision blocks "
              f"(guide requires {expected}); encoding next", flush=True)
        return tokens

    def encode_from_tokens_scheduled(self, tokens, *args, **kwargs):
        start = time.perf_counter()
        result = self._clip.encode_from_tokens_scheduled(tokens, *args, **kwargs)
        shapes = [tuple(entry[0].shape) for entry in result]
        print(f"[BFS H3 CLIP context] Qwen encoding complete in {time.perf_counter() - start:.2f}s; "
              f"conditioning shapes={shapes}. Guide native video reference blocks: 0", flush=True)
        return result


def clip_with_video_context(clip, videos, length, source_fps=24.0, context_fps=2.0):
    """Native H3 24-fps frame convention, presented to Qwen at a selectable sampling rate.

    Only selected frames are resized. No video VAE encoding or minimax_refs
    video block is created here. Real image reference blocks are unaffected.
    """
    from comfy_extras.nodes_minimax_h3 import (
        CANVAS_MULTIPLE, _resize, adapt_canvas, temporal_shape,
    )

    if not math.isfinite(source_fps) or source_fps <= 0:
        raise ValueError("CLIP video context needs a positive source frame rate")
    if not math.isfinite(context_fps) or not 0.5 <= context_fps <= 24:
        raise ValueError("clip_video_fps must be between 0.5 and 24")
    effective_fps = min(context_fps, source_fps)
    frame_count = temporal_shape(length)[0]
    items = []
    for frames in (videos or {}).values():
        if frames is None:
            continue
        if frames.ndim != 4 or frames.shape[-1] < 3:
            raise ValueError("CLIP video context needs IMAGE frames [frames, height, width, channels]")
        n = min(frames.shape[0], frame_count)
        if n < 5:
            raise ValueError("H3 CLIP video context needs at least 5 frames at the native 24 fps")
        n -= (n - 5) % 17
        height, width = frames.shape[1:3]
        cw, ch = adapt_canvas(width, height)
        if width * height < cw * ch:
            cw = max(CANVAS_MULTIPLE, round(width / CANVAS_MULTIPLE) * CANVAS_MULTIPLE)
            ch = max(CANVAS_MULTIPLE, round(height / CANVAS_MULTIPLE) * CANVAS_MULTIPLE)
        indices = sorted({round(i * source_fps / effective_fps)
                          for i in range(math.ceil(n / source_fps * effective_fps))
                          if round(i * source_fps / effective_fps) < n})
        selected = _resize(frames[indices], cw, ch, "disabled")
        times = [index / source_fps for index in indices]
        preview = times if len(times) <= 6 else times[:3] + times[-3:]
        print(f"[BFS H3 CLIP context] guide: input={frames.shape[0]} frames at {source_fps:g} fps; "
              f"used={n}; requested={context_fps:g} fps, effective={effective_fps:g} fps; "
              f"sent={len(indices)} RGB frames at {cw}x{ch}; "
              f"timestamps={[round(t, 3) for t in preview]} seconds (first/last); "
              "native guide video reference latents: OFF", flush=True)
        items.append({"type": "video", "data": selected,
                      "timestamps": [index / source_fps for index in indices]})
    return _VideoContextClip(clip, items) if items else clip


class BFSMiniMaxH3ReferenceToVideoGuideContext(MiniMaxH3ReferenceToVideo):
    @classmethod
    def define_schema(cls):
        schema = MiniMaxH3ReferenceToVideo.define_schema()
        # Keep native image/video/audio reference semantics. The separately
        # named guide is the only video excluded from native reference latents.
        inputs = list(schema.inputs)
        inputs.insert(1, io.Image.Input(
            "guide_video_0", optional=True,
            tooltip=("The motion guide / current shot, as native 24-fps frames. Qwen sees it at clip_video_fps "
                     "as <Video 1>; no native guide video reference latents are added. Connect the "
                     "same frames to Add Guide for motion. Other ref_videos start at <Video 2>."),
        ))
        inputs.append(io.Float.Input(
            "clip_video_fps", default=2.0, min=0.5, max=24.0, step=0.5,
            tooltip=("Guide 0 sampling rate for Qwen only. Default/native presentation is 2 fps; "
                     "try 4 or 8 fps. Higher values increase context and encoding cost, not output fps. "
                     "Never duplicates frames above the source rate. Actual reference videos stay native 2 fps."),
        ))
        for item in inputs:
            if item.id == "ref_images":
                item.template = io.Autogrow.TemplatePrefix(
                    input=io.Image.Input("ref_image", tooltip="Reference image, in <Picture N> order"),
                    prefix="ref_image_", min=0, max=100,
                )
            elif item.id == "ref_videos":
                item.tooltip = ("Actual native video references, separate from guide_video_0. With a guide "
                                "connected, these are <Video 2>, <Video 3>, etc. They enter both CLIP and "
                                "native reference latents, as in the original node. Up to 3 reference videos.")
                item.template.input.tooltip = item.tooltip
        return replace(
            schema, node_id="BFSMiniMaxH3ReferenceToVideoGuideContext",
            display_name="MiniMax H3 Reference to Video — Guide 0 CLIP Context (BFS)",
            description=("guide_video_0 enters Qwen/CLIP only as <Video 1>, without native guide video "
                         "reference latents. Pictures and other reference videos retain native semantics. "
                         "Use Add Guide separately for aligned motion. The target latent starts empty."),
            inputs=inputs,
        )

    @classmethod
    def execute(cls, clip, prompt, width, height, length, ref_image_size="match", vae=None,
                audio_vae=None, guide_video_0=None, ref_images=None, ref_videos=None,
                ref_video_audios=None, ref_audios=None, clip_video_fps=2.0):
        if guide_video_0 is not None:
            clip = clip_with_video_context(clip, {"guide_video_0": guide_video_0}, length, context_fps=clip_video_fps)
        return MiniMaxH3ReferenceToVideo.execute(
            clip=clip, prompt=prompt, width=width, height=height, length=length,
            ref_image_size=ref_image_size, vae=vae, audio_vae=audio_vae,
            ref_images=ref_images, ref_videos=ref_videos,
            ref_video_audios=ref_video_audios, ref_audios=ref_audios,
        )


NODE_CLASS_MAPPINGS = {
    "BFSMiniMaxH3ReferenceToVideoGuideContext": BFSMiniMaxH3ReferenceToVideoGuideContext,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "BFSMiniMaxH3ReferenceToVideoGuideContext": "MiniMax H3 Reference to Video — Guide 0 CLIP Context (BFS)",
}
