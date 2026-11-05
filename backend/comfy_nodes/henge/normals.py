"""Surface-normal guide (MoGe-2): shapes, poses, motion and camera of the guide without anyone's colours, clothes or light.

With an edited first frame, the look of every person and of the place comes from that frame, so the original performers
cannot leak back into later frames. ComfyUI sizes MoGe by its weights alone and keeps a cached H3 loaded, so the batched
inference ran out of memory on a 32 GB card: this node frees VRAM before it and runs in small batches.
"""
import comfy.model_management as mm

NORMALS_HEADROOM = 8 * 1024 ** 3


class HengeNormalMap:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'images': ('IMAGE',), 'moge_model': ('MOGE_MODEL',),
                             'batch_size': ('INT', {'default': 2, 'min': 1, 'max': 16, 'tooltip': 'Frames per MoGe pass; small keeps the peak low next to H3.'})}}

    RETURN_TYPES = ('IMAGE',)
    FUNCTION = 'render'
    CATEGORY = 'Henge'

    def render(self, images, moge_model, batch_size):
        from comfy_extras.nodes_moge import MoGeInference, MoGeRender
        mm.free_memory(NORMALS_HEADROOM, mm.get_torch_device())
        geometry = MoGeInference.execute(moge_model=moge_model, image=images, resolution_level=6, fov_x_degrees=0., batch_size=int(batch_size),
                                         force_projection=True, apply_mask=False, refine_steps=0).args[0]
        normals = MoGeRender.execute(moge_geometry=geometry, output='normal_opengl').args[0]
        print(f'[Henge] normal-map guide: {normals.shape[0]} frames (MoGe-2, batch {batch_size})', flush=True)
        return (normals,)
