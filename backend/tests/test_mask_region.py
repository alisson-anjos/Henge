"""Mask only must follow the moving SAM silhouette, as in the BFS planner."""
import ast
from pathlib import Path

import torch

source = Path(__file__).resolve().parents[1] / 'comfy_nodes/henge/__init__.py'
tree = ast.parse(source.read_text())
selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('shape_mask', 'mask_region')]
namespace = {'torch': torch}
exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), 'exec'), namespace)


def test_mask_follows_each_frame_and_keeps_gaps_in_the_silhouette():
    mask = torch.zeros(2, 32, 32, dtype=torch.bool)
    mask[0, 3:12, 3:5] = True
    mask[0, 10:12, 3:12] = True
    mask[1, 20:25, 20:25] = True
    # Old saved box settings must not restore a bounding box.
    for shape in ('box', 'silhouette'):
        result = namespace['mask_region'](mask, {'shape': shape, 'padding': .15, 'expand': 0})
        assert torch.equal(result, mask.float())
        assert not result[0, 5, 10] and not result[0, 22, 22]


def test_expansion_matches_bfs_square_dilation_without_bridging_frames():
    mask = torch.zeros(2, 32, 32, dtype=torch.bool)
    mask[0, 5, 5] = True
    mask[1, 24, 24] = True
    result = namespace['mask_region'](mask, {'expand': 2})
    expected = torch.zeros_like(result)
    expected[0, 3:8, 3:8] = 1
    expected[1, 22:27, 22:27] = 1
    assert torch.equal(result, expected)
    assert not namespace['mask_region'](torch.zeros_like(mask), {'expand': 2}).any()


def test_temporal_expansion_still_uses_neighboring_sam_masks():
    mask = torch.zeros(5, 16, 16, dtype=torch.bool)
    mask[2, 5:8, 5:8] = True
    shaped = namespace['shape_mask'](mask, {'temporal_expand': 1})
    result = namespace['mask_region'](shaped, {'expand': 0})
    assert torch.equal(result[1:4], mask[2].float().expand(3, -1, -1))
    assert not result[0].any() and not result[4].any()
