"""MCP contract checks; run with the optional MCP SDK installed, without a live backend."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    FastMCP = None

if FastMCP:
    spec = importlib.util.spec_from_file_location('henge_mcp', Path(__file__).resolve().parents[2] / 'mcp' / 'henge_mcp.py')
    henge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(henge)


@unittest.skipUnless(FastMCP, 'Optional MCP SDK not installed')
class MCPContracts(unittest.TestCase):
    def test_settings_routes_are_explicit_and_backend_validated(self):
        with patch.object(henge, 'api', return_value=Mock(json=lambda: {'enabled': False})) as api:
            self.assertEqual(henge.set_settings('molmo', {'enabled': False}), {'enabled': False})
            api.assert_called_once_with('POST', '/molmo/settings', json={'enabled': False})
            with self.assertRaises(ValueError): henge.set_settings('../jobs', {})
            with self.assertRaises(ValueError): henge.get_settings('unknown')

    def test_create_job_defaults_original_and_preserves_advanced_options(self):
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / 'guide.mp4'; video.write_bytes(b'fixture')
            options = {'temporal_windows': {'enabled': False}, 'upscale_method': 'none', 'seed': 123}
            with patch.object(henge, 'probe', return_value={'duration': 7.2, 'width': 480, 'height': 864}), patch.object(henge, 'api', return_value=Mock(json=lambda: {'id': 'fixture'})) as api:
                henge.create_job('motion', str(video), prompt='Transfer the motion', options=options, processing={'cut_mode':'every'}, audio_conditioning=True)
                data = api.call_args.kwargs['data']
                direction = json.loads(data['direction']); effective = json.loads(data['options'])
                self.assertEqual(direction['subject_guidance']['representation'], 'original')
                self.assertEqual(direction['processing']['cut_mode'], 'every')
                self.assertTrue(direction['audio_conditioning']['enabled'])
                self.assertEqual(effective['temporal_windows'], options['temporal_windows'])
                self.assertEqual(effective['seed'], 123)
                api.reset_mock()
                with self.assertRaisesRegex(ValueError, 'Mask requires'):
                    henge.create_job('motion', str(video), guide_representation='mask')
                api.assert_not_called()

    def test_status_includes_windows_and_optional_analysis_readiness(self):
        health = {'temporal_windows_ready': False, 'turbos': {'dmad4': {'available':True,'steps':4}}, 'bases': {'h3':{'available':True}}}
        with patch.object(henge, 'api', return_value=Mock(json=lambda: health)), patch.object(henge, 'pointing_status', return_value={'configured':False}):
            state = henge.status()
        self.assertFalse(state['temporal_windows_ready'])
        self.assertFalse(state['video_analysis']['configured'])
        self.assertEqual(state['turbos']['dmad4']['steps'],4)
