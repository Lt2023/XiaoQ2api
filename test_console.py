"""Console tests use isolated temporary storage and never contact a real NapCat."""
import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from toolforge.app.auth import require_client_auth
from toolforge.app.config import AppConfig
from webui.admin import install_console


class ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / 'console.json'
        self.runtime = SimpleNamespace(base_url='http://127.0.0.1:3000', token='fixture-token', api_key='fixture-admin')
        self.prompt = ['initial prompt']
        self.app = FastAPI()
        self.app.state.config = AppConfig()
        self.store = install_console(self.app, self.runtime, {}, asyncio.Lock(), lambda: self.prompt[0],
            lambda value: self.prompt.__setitem__(0, value), state_path=self.path)

        @self.app.get('/v1/models', dependencies=[Depends(require_client_auth)])
        async def models():
            return {'data': []}

        self.client = TestClient(self.app)
        self.client.__enter__()
        self.headers = {'Authorization': 'Bearer fixture-admin'}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.folder.cleanup()

    def test_assets_and_auth(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        page = self.client.get('/')
        self.assertIn('XiaoQ', page.text)
        self.assertIn('登录状态会保存在此浏览器。刷新或重启后仍可使用。点击“退出登录”可清除记忆。', page.text)
        self.assertNotIn('小Q', page.text)
        self.assertNotIn('ToolForge', page.text)
        self.assertNotIn('系统提示词', page.text)
        self.assertIn('frame-ancestors', page.headers['content-security-policy'])
        self.assertIn('https://q.qlogo.cn', page.headers['content-security-policy'])
        self.assertIn('id="workspace-avatar"', page.text)
        self.assertIn('id="profile-avatar"', page.text)
        self.assertEqual(self.client.get('/openapi.json').json()['info']['title'], 'XiaoQ API Console')
        self.assertEqual(self.client.get('/logo.png').headers['content-type'], 'image/png')
        for path in ['/assets/app.js', '/assets/styles.css', '/assets/icons/dashboard.svg', '/assets/icons/playground.svg', '/assets/icons/send.svg']:
            self.assertEqual(self.client.get(path).status_code, 200)
        script = self.client.get('/assets/app.js').text
        self.assertNotIn('ToolForge', script)
        self.assertNotIn('system_prompt', script)
        self.assertIn('function logsPage()', script)
        self.assertIn('function playgroundPage()', script)
        self.assertIn('const ADMIN_KEY_STORAGE = "xiaoq-console-admin-key";', script)
        self.assertIn('function loadSavedAdminKey()', script)
        self.assertIn('localStorage.setItem(ADMIN_KEY_STORAGE, value)', script)
        self.assertIn('localStorage.removeItem(ADMIN_KEY_STORAGE)', script)
        self.assertIn('saveSavedAdminKey(state.adminKey)', script)
        self.assertIn('error.status === 401', script)
        self.assertIn('if (state.adminKey) {\n  refresh().catch', script)
        self.assertIn('loginDialog.showModal();', script)
        self.assertIn('XiaoQ', script)
        self.assertNotIn('小Q', script)
        self.assertIn('class=\"playground-model-label\"', script)
        self.assertIn('class=\"playground-send\"', script)
        self.assertIn('class=\"playground-role\">${role}</span><article class=\"playground-message ${kind}\"', script)
        self.assertIn('fetch("/v1/chat/completions"', script)
        self.assertIn('state.playgroundMessages.slice(-24)', script)
        self.assertIn('data-page="playground"', page.text)
        self.assertIn('添加后会自动测试连接并同步 QQ 头像。', script)
        self.assertIn('>测试</button>', script)
        self.assertIn('theme-toggle', script)
        self.assertIn('function qqAvatarId(account)', script)
        self.assertIn('headimg_dl?dst_uin=${qqId}&spec=640&img_type=jpg', script)
        self.assertIn('await request(`/accounts/${saved.id}/test`, { method: \"POST\" });', script)
        self.assertIn('await request(`/accounts/${saved.id}/activate`, { method: \"POST\" });', script)
        self.assertIn('账号已添加、测试通过并设为当前，头像已同步', script)
        self.assertIn('添加并测试', script)
        style = self.client.get('/assets/styles.css').text
        self.assertIn('--canvas: #171717', style)
        self.assertIn('--accent: #747474', style)
        self.assertIn('.icon-send { --icon: url(\"/assets/icons/send.svg\"); }', style)
        self.assertIn('.playground-composer { display: flex; flex-direction: column;', style)
        self.assertIn('.playground-composer-footer { display: flex;', style)
        self.assertIn('height: clamp(420px, calc(100dvh - 300px), 720px);', style)
        self.assertIn('.playground-messages {\n    flex: 1 1 0;\n    min-height: 0;\n    max-height: none;', style)
        self.assertIn('overscroll-behavior: contain;', style)
        self.assertIn('.playground-header { flex-wrap: wrap; }', style)
        self.assertIn('.theme-toggle .icon { width: 18px; height: 18px; transform: none; animation: none; }', style)
        self.assertIn('data-page="logs"', page.text)
        self.assertIn('logs: logsPage', script)
        self.assertIn('external-link.svg', style)
        self.assertIn('html[data-theme="dark"] .theme-toggle { color: #a3a3a3; }', style)
        self.assertIn('html[data-theme="dark"] .stat-icon.blue { color: #b2b2b2; }', style)
        self.assertIn('.qq-avatar-image { display: block; width: 100%; height: 100%; object-fit: cover;', style)
        for path in ['/assets/../data/console.json', '/webui/admin.py', '/config.env', '/webui/data/console.json']:
            self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.get('/admin/api/overview').status_code, 401)
        data = self.client.get('/admin/api/overview', headers=self.headers).json()
        self.assertEqual(data['accounts'], [])
        self.assertIsNone(self.store.data['active_account'])
        self.assertNotIn('digest', data['keys'][0])
        self.assertNotIn('fixture-admin', json.dumps(data))

    def test_default_has_no_accounts_and_migrates_legacy_placeholder(self):
        self.assertEqual(self.store.data['accounts'], [])
        self.assertIsNone(self.store.data['active_account'])
        data = dict(self.store.data)
        data['accounts'] = [
            {'id': 'default', 'name': '默认 NapCat 账号', 'qq_id': '', 'nickname': '',
             'base_url': 'http://localhost:3000', 'token': 'placeholder', 'created_at': 'old'},
            {'id': 'manual', 'name': '我的账号', 'qq_id': '123456789', 'nickname': '我',
             'base_url': 'http://localhost:3001', 'token': 'manual-token', 'created_at': 'old'},
        ]
        data['active_account'] = 'default'
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        from webui.admin import ConsoleStore
        migrated = ConsoleStore(self.path, self.runtime, 'initial')
        self.assertEqual([item['id'] for item in migrated.data['accounts']], ['manual'])
        self.assertEqual(migrated.data['active_account'], 'manual')

    def test_key_lifecycle_and_persistence(self):
        created = self.client.post('/admin/api/keys', headers=self.headers, json={'name': 'Test client'})
        self.assertEqual(created.status_code, 200)
        key = created.json()
        auth = {'Authorization': 'Bearer ' + key['secret']}
        self.assertEqual(self.client.get('/v1/models', headers=auth).status_code, 200)
        self.assertNotIn(key['secret'], self.path.read_text(encoding="utf-8"))
        self.assertEqual(self.client.get('/admin/api/overview', headers=auth).status_code, 401)
        self.client.patch('/admin/api/keys/' + key['id'], headers=self.headers, json={'enabled': False})
        self.assertEqual(self.client.get('/v1/models', headers=auth).status_code, 401)
        self.client.patch('/admin/api/keys/' + key['id'], headers=self.headers, json={'enabled': True})
        self.assertEqual(self.client.get('/v1/models', headers=auth).status_code, 200)
        from webui.admin import ConsoleStore
        loaded = ConsoleStore(self.path, self.runtime, 'initial')
        self.assertTrue(loaded.valid_key(key['secret']))
        self.client.delete('/admin/api/keys/' + key['id'], headers=self.headers)
        self.assertEqual(self.client.get('/v1/models', headers=auth).status_code, 401)

    def test_accounts_and_settings(self):
        bad = self.client.post('/admin/api/accounts', headers=self.headers, json={'name': 'Bad', 'base_url': 'file:///tmp'})
        self.assertEqual(bad.status_code, 422)
        self.assertEqual(self.client.delete('/admin/api/accounts/default', headers=self.headers).status_code, 404)
        account = self.client.post('/admin/api/accounts', headers=self.headers,
            json={'name': 'Second', 'base_url': 'http://localhost:3001/', 'token': 'new-token'}).json()['id']
        self.store.account(account).update(qq_id='123456789', nickname='Second')
        self.store.save()
        self.client.put('/admin/api/accounts/' + account, headers=self.headers,
            json={'name': 'Edited', 'base_url': 'http://localhost:3002', 'token': ''})
        updated = self.client.get('/admin/api/overview', headers=self.headers).json()
        edited = next(item for item in updated['accounts'] if item['id'] == account)
        self.assertEqual(edited['qq_id'], '')
        self.assertEqual(edited['nickname'], '')
        self.client.post('/admin/api/accounts/' + account + '/activate', headers=self.headers)
        self.assertEqual(self.runtime.base_url, 'http://localhost:3002')
        self.assertEqual(self.runtime.token, 'new-token')
        settings = {'system_prompt': 'do not expose', 'fc_mode': 'auto', 'enable_fc_error_retry': False}
        self.assertEqual(self.client.put('/admin/api/settings', headers=self.headers, json=settings).status_code, 200)
        self.assertEqual(self.prompt[0], 'initial prompt')
        self.assertEqual(self.app.state.config.features.fc_mode, 'auto')
        overview = self.client.get('/admin/api/overview', headers=self.headers)
        self.assertNotIn('system_prompt', overview.text)
        self.assertNotIn('do not expose', self.path.read_text(encoding='utf-8'))
        self.assertEqual(overview.json()['activity'][0]['action'], 'settings_updated')
        self.assertEqual(self.client.delete('/admin/api/accounts/' + account, headers=self.headers).status_code, 200)
        self.assertEqual(self.runtime.base_url, 'http://127.0.0.1:3000')
        self.assertEqual(self.runtime.token, 'fixture-token')
        self.assertEqual(self.store.data['accounts'], [])
        self.assertIsNone(self.store.data['active_account'])
        self.assertEqual(self.client.delete('/admin/api/accounts/missing', headers=self.headers).status_code, 404)

    def test_metrics_and_connection_check(self):
        self.client.get('/v1/models', headers=self.headers)
        self.client.get('/v1/models')
        overview = self.client.get('/admin/api/overview', headers=self.headers).json()
        self.assertEqual(overview['total'], 2)
        self.assertEqual(overview['errors'], 1)
        self.assertEqual(sum(overview['traffic']), 2)
        account_id = self.client.post('/admin/api/accounts', headers=self.headers,
            json={'name': 'Test QQ', 'base_url': 'http://localhost:3001', 'token': 'test-token'}).json()['id']
        import httpx
        response = httpx.Response(200, json={'retcode': 0, 'data': {'nickname': 'Mock QQ', 'user_id': 123456789}}, request=httpx.Request('POST', 'http://fixture/get_login_info'))
        async def mocked_post(*args, **kwargs):
            return response
        with patch('webui.admin.httpx.AsyncClient.post', mocked_post):
            result = self.client.post('/admin/api/accounts/' + account_id + '/test', headers=self.headers)
            self.assertEqual(result.json()['nickname'], 'Mock QQ')
            self.assertEqual(result.json()['user_id'], '123456789')
            account = next(item for item in self.client.get('/admin/api/overview', headers=self.headers).json()['accounts'] if item['id'] == account_id)
            self.assertEqual(account['qq_id'], '123456789')
            self.assertEqual(account['nickname'], 'Mock QQ')

    def test_old_prompt_is_removed_and_theme_is_logged(self):
        self.store.save()
        data = json.loads(self.path.read_text(encoding='utf-8'))
        data['settings']['system_prompt'] = 'legacy private value'
        self.path.write_text(json.dumps(data), encoding='utf-8')
        from webui.admin import ConsoleStore
        migrated = ConsoleStore(self.path, self.runtime, 'internal system message')
        self.assertNotIn('system_prompt', migrated.data['settings'])
        self.assertNotIn('legacy private value', self.path.read_text(encoding='utf-8'))
        for theme in ('dark', 'light'):
            result = self.client.post('/admin/api/activity', headers=self.headers, json={'theme': theme})
            self.assertEqual(result.status_code, 200)
        overview = self.client.get('/admin/api/overview', headers=self.headers).json()
        self.assertEqual([row['action'] for row in overview['activity'][:2]], ['theme_changed', 'theme_changed'])
        self.assertNotIn('internal system message', json.dumps(overview))


if __name__ == '__main__':
    unittest.main()
