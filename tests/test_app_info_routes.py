"""Settings window routes: the version and the real saves folder, and opening that folder."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server
from core import save_manager, version


class AppInfoRoutesTests(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()

    def test_app_info_gives_version_and_saves_folder(self):
        info = self.client.get('/api/app_info').get_json()
        self.assertEqual(info['version'], version.label())
        self.assertEqual(info['saves_dir'], os.path.abspath(save_manager.get_saves_dir()))

    def test_open_saves_folder_opens_the_saves_dir(self):
        with mock.patch.object(server, '_open_folder') as opener:
            res = self.client.post('/api/open_saves_folder')
        self.assertEqual(res.status_code, 200)
        opener.assert_called_once_with(os.path.abspath(save_manager.get_saves_dir()))

    def test_open_saves_folder_reports_a_failure(self):
        with mock.patch.object(server, '_open_folder', side_effect=OSError('no shell')):
            res = self.client.post('/api/open_saves_folder')
        self.assertEqual(res.status_code, 500)
        self.assertFalse(res.get_json()['ok'])


if __name__ == '__main__':
    unittest.main()
