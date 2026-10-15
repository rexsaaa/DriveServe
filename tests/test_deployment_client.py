"""Exercise the actual completion sender against local SSE protocol fixtures.

The benchmark is a CLI with import-time service startup. Extract its unchanged
send function AST to test its real network code without launching GPUs. Fixture
results establish protocol handling, never model quality or performance.
"""
import ast
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
import unittest

from driveserve.evidence import now
from driveserve.task import generate, score

class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    mode = 'valid'

    def log_message(self, *_):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        mode = self.server.mode
        if mode == 'timeout':
            time.sleep(.15)
        content = '{"action":"stop","speed_band":"stopped","must_yield":true}'
        events = [json.dumps({'choices':[{'text':content[:20],'finish_reason':None}]}),
                  json.dumps({'choices':[{'text':content[20:],'finish_reason':'stop'}]}),
                  json.dumps({'usage':{'prompt_tokens':len(body['prompt']),'completion_tokens':12}}), '[DONE]']
        if mode == 'truncated': events.pop()
        if mode == 'no-usage': events.pop(2)
        if mode == 'bad-json': events[1] = '{bad'
        if mode == 'error-event': events[1] = json.dumps({'error':'fixture server failure'})
        if mode == 'wrong-prompt-count': events[2] = json.dumps({'usage':{'prompt_tokens':999,'completion_tokens':12}})
        if mode == 'one-token': events[2] = json.dumps({'usage':{'prompt_tokens':len(body['prompt']),'completion_tokens':1}})
        payload = ''.join('data: '+event+'\n\n' for event in events).encode()
        try:
            self.send_response(500 if mode == 'http-error' else 200)
            self.send_header('Content-Type','text/event-stream')
            self.send_header('Content-Length',str(len(payload))); self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

class DeploymentClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path('scripts/benchmark_deployments.py')
        tree = ast.parse(source.read_text(), filename=str(source))
        function = next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='send')
        cls.ns = {'http':__import__('http.client'),'json':json,'time':time,'now':now,'score':score}
        exec(compile(ast.Module(body=[function],type_ignores=[]),str(source),'exec'),cls.ns)
        cls.server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.server.mode = 'valid'
        cls.thread = threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.ns['services'] = [('0',1,cls.server.server_port,8)]
        cls.record = {'scene':generate()[0]['scene'],'request_id':'fixture-0','tokens':[1,2,3],'prompt_sha256':'protocol-fixture'}

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()

    def send(self, mode):
        self.server.mode = mode
        return self.ns['send'](0,self.record)

    def test_complete_multitoken_chunks(self):
        r=self.send('valid')
        self.assertEqual(r['status'],'completed');self.assertEqual(r['completion_tokens'],12)
        self.assertEqual(len(r['chunks']),3);self.assertLessEqual(r['ttft_s'],r['e2e_s'])
        self.assertEqual(r['tpot_s'],(r['last_content_s']-r['ttft_s'])/11)

    def test_incomplete_and_invalid_streams(self):
        for mode in ['truncated','no-usage','bad-json','error-event','wrong-prompt-count','http-error']:
            with self.subTest(mode=mode):
                r=self.send(mode);self.assertEqual(r['status'],'failed')
                self.assertIsNotNone(r['error']);self.assertGreater(r['e2e_s'],0)
        self.assertEqual(self.send('valid')['status'],'completed')

    def test_one_token_has_no_tpot(self):
        r=self.send('one-token');self.assertEqual(r['status'],'completed');self.assertIsNone(r['tpot_s'])

    def test_transport_timeout_recorded(self):
        # Shorten only the socket transport timeout; don't wait the production
        # 120 seconds. This checks timeout classification, not a whole-stream
        # hard deadline under a malicious slow drip.
        from unittest.mock import patch
        real=http.client.HTTPConnection
        with patch('http.client.HTTPConnection',side_effect=lambda host,port,timeout:real(host,port,timeout=.03)):
            r=self.send('timeout')
        self.assertEqual(r['status'],'timeout');self.assertIsNotNone(r['error'])

if __name__=='__main__':unittest.main(verbosity=2)
