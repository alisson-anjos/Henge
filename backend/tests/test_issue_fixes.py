"""Regressions for GitHub issues #9 (FFmpeg JPEG range) and #10 (removed download profile)."""
import importlib.util,json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
import server


def downloader():
    spec=importlib.util.spec_from_file_location('download_models',ROOT/'scripts/download_models.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_removed_or_unknown_profiles_do_not_block_downloads(capsys):
    manifest=json.loads((ROOT/'config/model-repos.example.json').read_text())
    ids={m['id'] for m in downloader().selected_models(manifest,['character','omniref','typo'])}
    assert 'bg_removal' in ids and 'h3' in ids
    out=capsys.readouterr().out
    assert 'removed model profile: omniref' in out and 'unknown model profile: typo' in out


def test_jpeg_grabs_allow_limited_range_yuv():
    args=server.ffmpeg_args(['ffmpeg','-i','in.mp4','-frames:v','1','-y','out.jpg'])
    assert args==['ffmpeg','-i','in.mp4','-frames:v','1','-y','-strict','unofficial','out.jpg']
    assert server.ffmpeg_args(['ffmpeg','-i','in.mp4','-y','out.png'])==['ffmpeg','-i','in.mp4','-y','out.png']
