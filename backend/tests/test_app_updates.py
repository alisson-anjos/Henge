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
            if '/actions/' in url:return Mock(json=lambda:{'workflow_runs':[{'head_sha':'b'*40}]})
            return Mock(json=lambda:{'status':'ahead','files':[{'filename':'backend/server.py'}]})
        with patch.object(app_updates,'current_version',return_value='a'*40),patch.object(app_updates,'fetch',side_effect=fetch) as network:
            first=app_updates.snapshot();second=app_updates.snapshot()
        self.assertIs(first,second);self.assertEqual(network.call_count,5)
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

class PublishedImageTests(unittest.TestCase):
    def setUp(self):app_updates.CACHE.clear()
    def tearDown(self):app_updates.CACHE.clear()
    def run_check(self,published,files):
        def fetch(url):
            if url.endswith('/commits/main'):return Mock(json=lambda:{'sha':'c'*40})
            if url.endswith('example.json'):return Mock(json=lambda:{'models':[]})
            if url.endswith('CHANGELOG.md'):return Mock(text='notes')
            if '/actions/' in url:return Mock(json=lambda:{'workflow_runs':[{'head_sha':published}]})
            self.compared=url;return Mock(json=lambda:{'status':'ahead','files':[{'filename':f} for f in files]})
        with patch.object(app_updates,'current_version',return_value='a'*40),patch.object(app_updates,'fetch',side_effect=fetch):
            return app_updates.snapshot()
    def test_running_the_newest_built_image_is_up_to_date_even_if_main_moved(self):
        # Main has a newer commit whose image is still building: the running image is the latest one available.
        value=self.run_check('a'*40,['backend/server.py'])
        self.assertFalse(value['update_available']);self.assertEqual(value['published'],'a'*40);self.assertEqual(value['latest'],'c'*40)
    def test_documentation_only_commits_are_not_an_update(self):
        self.assertFalse(self.run_check('b'*40,['CHANGELOG.md','docs/pika-h3-flex.md'])['update_available'])
    def test_a_built_image_with_code_changes_is_offered(self):
        value=self.run_check('b'*40,['CHANGELOG.md','components/studio.tsx'])
        self.assertTrue(value['update_available']);self.assertIn('...'+'b'*40,self.compared)
