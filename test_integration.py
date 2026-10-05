import json
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
import xaioq_api as api
from toolforge.app.engine.xyml import render_tool_call

TOOL = {'type':'function','function':{'name':'get_weather','description':'Weather','parameters':{'type':'object','properties':{'city':{'type':'string'}},'required':['city']}}}
class IntegrationTests(unittest.TestCase):
    def test_system_prompt(self):
        messages = [{'role': 'system', 'content': 'existing tools'}, {'role': 'user', 'content': 'Hello'}]
        original = json.dumps(messages)
        rendered = api.messages_to_prompt(messages)
        decoded = json.loads(rendered.split('\n', 1)[1])
        self.assertEqual(decoded[0], {'role': 'system', 'content': api.TOOLFORGE_SYSTEM_PROMPT})
        self.assertEqual(decoded[1:], messages)
        self.assertEqual(json.dumps(messages), original)
        print('PASS: system prompt prepended; history preserved; input unchanged')

    def test_reply_envelope(self):
        wrapped = '<toolforge>\n<action>reply</action>\n<content>你好呀～</content>\n</toolforge>'
        self.assertEqual(api.normalize_reply(wrapped), '你好呀～')
        for text in ['normal text', render_tool_call('get_weather', {'city':'Shanghai'}),
                     '<toolforge><action>execute</action><content>x</content></toolforge>',
                     'Example: ' + wrapped, '<toolforge>broken']:
            self.assertEqual(api.normalize_reply(text), text)
        self.assertNotIn('Do not use built-in tools or normal assistant capabilities.', api.TOOLFORGE_SYSTEM_PROMPT)

    def test_wrapped_gateway(self):
        async def mock_bot(prompt):
            return '<toolforge><action>reply</action><content>Hello</content></toolforge>'
        with patch.object(api, 'ask_bot', mock_bot), TestClient(api.app) as client:
            for stream in (False, True):
                r = client.post('/v1/chat/completions', headers={'Authorization':f'Bearer {api.config.api_key}'},
                    json={'model':'tenxun-hunyuan-3','messages':[{'role':'user','content':'Hello'}], 'stream':stream})
                self.assertEqual(r.status_code, 200)
                self.assertNotIn('<toolforge>', r.text)
                self.assertIn('Hello', r.text)

    def test_client_script(self):
        from openai import OpenAI
        from test_tools import run, execute_tool
        async def mock_bot(prompt):
            if '[Tool Result' in prompt:
                return '结果是 422。'
            return render_tool_call('add_numbers', {'a': 137, 'b': 285})
        with patch.object(api, 'ask_bot', mock_bot), TestClient(api.app) as http:
            client = OpenAI(base_url='http://testserver/v1', api_key=api.config.api_key,
                            http_client=http, max_retries=0)
            run(client, 'tenxun-hunyuan-3')
        with self.assertRaises(ValueError):
            execute_tool('unknown', '{}')
        with self.assertRaises(ValueError):
            execute_tool('add_numbers', '{"a":true,"b":2}')

    def test_gateway(self):
        prompts=[]
        async def mock_bot(prompt):
            prompts.append(prompt)
            assert api.TOOLFORGE_SYSTEM_PROMPT == json.loads(prompt.split('\n', 1)[1])[0]['content']
            if 'sunny-result' in prompt:
                return 'It is sunny.'
            if 'get_weather' in prompt:
                return render_tool_call('get_weather', {'city':'Shanghai'})
            return 'Hello'
        headers={'Authorization':f'Bearer {api.config.api_key}'}
        with patch.object(api,'ask_bot',mock_bot), TestClient(api.app) as client:
            self.assertEqual(client.get('/v1/models').status_code,401)
            self.assertEqual(client.get('/v1/models',headers=headers).status_code,200)
            body={'model':'tenxun-hunyuan-3','messages':[{'role':'user','content':'Hello'}]}
            r=client.post('/v1/chat/completions',headers=headers,json=body)
            self.assertEqual(r.json()['choices'][0]['message']['content'],'Hello')
            body['tools']=[TOOL]
            r=client.post('/v1/chat/completions',headers=headers,json=body)
            self.assertEqual(r.status_code,200,r.text)
            choice=r.json()['choices'][0]
            self.assertEqual(choice['finish_reason'],'tool_calls')
            call=choice['message']['tool_calls'][0]
            self.assertEqual(call['function']['name'],'get_weather')
            self.assertEqual(json.loads(call['function']['arguments']),{'city':'Shanghai'})
            self.assertIn('system',prompts[-1])
            body['stream']=True
            r=client.post('/v1/chat/completions',headers=headers,json=body)
            self.assertIn('tool_calls',r.text)
            self.assertIn('[DONE]',r.text)
            body['stream']=False
            body['messages'] += [choice['message'],{'role':'tool','tool_call_id':call['id'],'content':'sunny-result'}]
            r=client.post('/v1/chat/completions',headers=headers,json=body)
            self.assertEqual(r.json()['choices'][0]['message']['content'],'It is sunny.')
            self.assertIn('Hello',prompts[-1])
            self.assertIn('sunny-result',prompts[-1])
        print('PASS: auth, models, plain chat, tool calls, SSE, tool-result continuation')

if __name__=='__main__': unittest.main()
