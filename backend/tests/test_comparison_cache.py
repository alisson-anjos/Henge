import os,sys
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import comparison_preview

def test_cached_comparison_with_refs_is_rebuilt_after_a_redo(tmp_path):
    comparison,result,cached=(tmp_path/n for n in ('comparison.mp4','result.mp4','comparison_with_refs_v3.mp4'))
    for f in (comparison,result,cached):f.write_bytes(b'x')
    os.utime(comparison,(100,100));os.utime(result,(100,100));os.utime(cached,(200,200))
    assert comparison_preview.create_comparison_with_refs(comparison,result,[],cached)==cached
    # A redone shot rebuilds comparison.mp4: the cached video is stale and gets encoded again.
    os.utime(comparison,(300,300))
    with mock.patch.object(comparison_preview.subprocess,'check_output',side_effect=RuntimeError('rebuild')) as probe:
        try:comparison_preview.create_comparison_with_refs(comparison,result,[],cached)
        except RuntimeError:pass
    assert probe.called
