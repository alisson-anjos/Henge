import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock,patch
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app_updates

class UpdatesTests(unittest.TestCase):
    def setUp(self):app_updates.CACHE.clear()
    def tearDown(self):app_updates.CACHE.clear()
    def test_current_build_metadata_does_not_require_git(self):
        with patch.dict(app_updates.os.environ,{'HENGE_BUILD_SHA':'a'*40}),patch.object(app_updates.subprocess,'check_output') as git:
            self.assertEqual(app_updates.current_version(),'a'*40);git.assert_not_called()
    def test_offline_fallback_never_claims_an_update(self):
        with patch.object(app_updates,'current_version',return_value='a'*40),patch.object(app_updates.requests,'get',side_effect=requests.ConnectionError):
            value=app_updates.snapshot()
        self.assertFalse(value['check_ok']);self.assertFalse(value['update_available'])
        self.assertTrue(value['manifest']['models']);self.assertIn('Henge changelog',value['changelog'])
    def test_catalog_and_changelog_are_pinned_and_cached(self):
        urls=[]
        def fetch(url):
            urls.append(url)
            if url.endswith('/commits/main'):return Mock(json=lambda:{'sha':'b'*40})
            if url.endswith('example.json'):return Mock(json=lambda:{'models':[{'id':'new-model'}]})
            if url.endswith('CHANGELOG.md'):return Mock(text='New model. [Details](docs/new.md)')
            return Mock(json=lambda:{'status':'ahead'})
        with patch.object(app_updates,'current_version',return_value='a'*40),patch.object(app_updates,'fetch',side_effect=fetch) as network:
            first=app_updates.snapshot();second=app_updates.snapshot()
        self.assertIs(first,second);self.assertEqual(network.call_count,4)
        self.assertTrue(first['update_available']);self.assertEqual(first['catalog_revision'],'b'*40)
        self.assertIn('/'+'b'*40+'/config/',urls[1]);self.assertIn('https://github.com/',first['changelog'])
    def test_unknown_or_ahead_local_version_does_not_get_false_update_notice(self):
        def fetch(url):
            if url.endswith('/commits/main'):return Mock(json=lambda:{'sha':'b'*40})
            if url.endswith('example.json'):return Mock(json=lambda:{'models':[]})
            if url.endswith('CHANGELOG.md'):return Mock(text='notes')
            return Mock(json=lambda:{'status':'behind'})
        with patch.object(app_updates,'current_version',return_value='a'*40),patch.object(app_updates,'fetch',side_effect=fetch):
            self.assertFalse(app_updates.snapshot()['update_available'])
