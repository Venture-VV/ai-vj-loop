"""Offline checks for spending, failure and resume boundaries. No real API keys or requests."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('tripo_batch', Path(__file__).with_name('tripo_batch.py'))
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)


class BatchSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.state = root / 'tasks.json'
        manifest = root / 'assets.json'
        manifest.write_text(json.dumps({'defaults': {'model': 'v3.1-20260211', 'geometry_quality': 'detailed'},
                                        'assets': [{'id': 'first', 'prompt': 'angel'}, {'id': 'second', 'prompt': 'angel'}]}))
        for name, value in {'STATE': str(self.state), 'MANIFEST': str(manifest), 'MODELS': str(root / 'models'),
                            'IMAGES': str(root / 'images')}.items():
            p = patch.object(batch, name, value)
            p.start()
            self.addCleanup(p.stop)
        sleep = patch.object(batch.time, 'sleep')
        sleep.start()
        self.addCleanup(sleep.stop)
        curl = patch.object(batch.shutil, 'which', return_value=None)
        curl.start()
        self.addCleanup(curl.stop)

    def run_batch(self, call, *args):
        with patch.object(batch, 'call', call), patch.object(batch, 'download') as download, \
             patch.object(batch.sys, 'argv', ['tripo_batch.py', *args]), contextlib.redirect_stdout(io.StringIO()):
            batch.main()
        return download

    def test_budget_stops_before_any_request(self):
        requests = []
        with self.assertRaisesRegex(SystemExit, 'exceed'):
            self.run_batch(lambda *a: requests.append(a), '--max-credits', '30')
        self.assertEqual(requests, [])
        self.assertFalse(self.state.exists())

    def test_failed_task_keeps_id_and_never_submits_next(self):
        requests = []
        def call(method, path, body=None):
            requests.append((method, path))
            if method == 'POST':
                return {'task_id': 'task-one'}
            return {'status': 'failed', 'error_code': 2008, 'error_message': 'original failure'}
        with self.assertRaisesRegex(SystemExit, 'original failure'):
            self.run_batch(call)
        self.assertEqual([m for m, _ in requests], ['POST', 'GET'])
        self.assertEqual(json.loads(self.state.read_text()), {'first': 'task-one'})
        requests.clear()
        with self.assertRaises(SystemExit):
            self.run_batch(call)
        self.assertEqual([m for m, _ in requests], ['GET'])

    def test_uncertain_submit_is_not_repeated(self):
        def uncertain(*args):
            raise TimeoutError('connection lost after POST')
        with self.assertRaises(TimeoutError):
            self.run_batch(uncertain)
        self.assertTrue(json.loads(self.state.read_text())['first']['submission_pending'])
        requests = []
        with self.assertRaisesRegex(SystemExit, 'Uncertain earlier submission'):
            self.run_batch(lambda *a: requests.append(a))
        self.assertEqual([request[0] for request in requests], ['GET', 'GET'])
        self.assertTrue(requests[0][1].startswith('/account/usage/history?'))
        self.assertEqual(requests[1][1], '/account/balance')

    def test_success_completes_before_next_submission(self):
        requests = []
        def call(method, path, body=None):
            requests.append((method, path))
            if method == 'POST':
                return {'task_id': 'task-' + str(len(requests))}
            return {'status': 'success', 'credits_consumed': 30, 'output': {'model_url': 'https://example.invalid/model.glb'}}
        download = self.run_batch(call, '--max-credits', '60')
        self.assertEqual([m for m, _ in requests], ['POST', 'GET', 'POST', 'GET'])
        self.assertEqual(download.call_count, 2)

    def test_unexpected_charge_and_unknown_status_stop(self):
        for result in [{'status': 'success', 'credits_consumed': 31, 'output': {'model_url': 'https://example.invalid/model.glb'}},
                       {'status': 'unexpected', 'progress': 0}]:
            with self.subTest(result=result):
                self.state.write_text(json.dumps({'first': 'existing'}))
                requests = []
                def call(*args):
                    requests.append(args)
                    return result
                with self.assertRaises(SystemExit):
                    self.run_batch(call)
                self.assertEqual(len(requests), 1)
                self.assertEqual(requests[0][0], 'GET')

    def test_timeout_preserves_id_and_stops(self):
        self.state.write_text(json.dumps({'first': 'existing'}))
        requests = []
        with self.assertRaisesRegex(SystemExit, 'timed out'):
            self.run_batch(lambda *a: requests.append(a), '--timeout', '0')
        self.assertEqual(requests, [])
        self.assertEqual(json.loads(self.state.read_text())['first'], 'existing')

    def test_incomplete_download_never_becomes_model(self):
        dest = Path(self.tmp.name) / 'models' / 'broken.glb'
        with patch.object(batch.urllib.request, 'urlopen', return_value=io.BytesIO(b'not a GLB')):
            with self.assertRaisesRegex(SystemExit, 'Invalid or incomplete'):
                batch.download_once('https://example.invalid/model.glb', str(dest))
        self.assertFalse(dest.exists())
        blob = b'glTF' + struct.pack('<II', 2, 12)
        with patch.object(batch.urllib.request, 'urlopen', return_value=io.BytesIO(blob)):
            batch.download('https://example.invalid/model.glb', str(dest))
        self.assertEqual(dest.read_bytes(), blob)

    def test_truncated_download_retries_existing_result(self):
        dest = Path(self.tmp.name) / 'models' / 'recover.glb'
        blob = b'glTF' + struct.pack('<II', 2, 12)
        with patch.object(batch.urllib.request, 'urlopen', side_effect=[io.BytesIO(blob[:8]), io.BytesIO(blob)]) as request, \
             contextlib.redirect_stdout(io.StringIO()):
            batch.download('https://example.invalid/model.glb', str(dest))
        self.assertEqual(request.call_count, 2)
        self.assertEqual(dest.read_bytes(), blob)

    def test_ranged_download_retries_only_truncated_range(self):
        class Response(io.BytesIO):
            status = 206
            def __init__(self, data, content_range):
                super().__init__(data)
                self.headers = {'Content-Range': content_range}
        blob = b'glTF' + struct.pack('<II', 2, 20) + b'12345678'
        responses = [Response(blob[:5], 'bytes 0-7/20'), Response(blob[:8], 'bytes 0-7/20'),
                     Response(blob[8:16], 'bytes 8-15/20'), Response(blob[16:], 'bytes 16-19/20')]
        dest = Path(self.tmp.name) / 'models' / 'ranged.glb'
        with patch.object(batch, 'DOWNLOAD_CHUNK', 8), \
             patch.object(batch.urllib.request, 'urlopen', side_effect=responses) as request, \
             contextlib.redirect_stdout(io.StringIO()):
            batch.download('https://example.invalid/model.glb', str(dest))
        self.assertEqual(dest.read_bytes(), blob)
        self.assertEqual([c.args[0].get_header('Range') for c in request.call_args_list],
                         ['bytes=0-7','bytes=0-7','bytes=8-15','bytes=16-19'])
        self.assertTrue(all(c.args[0].get_header('Authorization') is None for c in request.call_args_list))

    def test_transport_retry_is_read_only(self):
        error = batch.http.client.RemoteDisconnected('original network interruption')
        with patch.object(batch, 'call_once', side_effect=[error, {'status': 'running'}]) as request, \
             patch.object(batch, 'key', return_value='test-credential'), contextlib.redirect_stdout(io.StringIO()):
            result = batch.call('GET', '/tasks/existing')
        self.assertEqual(result['status'], 'running')
        self.assertEqual(request.call_count, 2)
        with patch.object(batch, 'call_once', side_effect=error) as request:
            with self.assertRaises(batch.http.client.RemoteDisconnected):
                batch.call('POST', '/generation/text-to-model', {})
        self.assertEqual(request.call_count, 1)

    def test_curl_download_does_not_receive_api_key(self):
        blob = b'glTF' + struct.pack('<II', 2, 12)
        dest = Path(self.tmp.name) / 'models' / 'curl.glb'
        def transfer(command, **kwargs):
            self.assertNotIn('TRIPO_API_KEY', kwargs['env'])
            self.assertNotIn('test-credential', str(command))
            Path(command[command.index('--output')+1]).write_bytes(blob)
            return SimpleNamespace(returncode=0,stdout='http=200 bytes=12',stderr='')
        with patch.object(batch.shutil, 'which', return_value='/usr/bin/curl'), \
             patch.dict(batch.os.environ, {'TRIPO_API_KEY':'test-credential'}), \
             patch.object(batch.subprocess, 'run', side_effect=transfer), contextlib.redirect_stdout(io.StringIO()):
            batch.download('https://example.invalid/model.glb',str(dest))
        self.assertEqual(dest.read_bytes(),blob)

    def test_curl_api_uses_stdin_and_never_retries_creation(self):
        def request(command, **kwargs):
            self.assertNotIn('TRIPO_API_KEY',kwargs['env'])
            self.assertNotIn('test-credential',str(command))
            self.assertIn('Authorization: Bearer test-credential',kwargs['input'])
            self.assertNotIn('--retry',command)
            return SimpleNamespace(returncode=0,stdout='{"code":0,"data":{"task_id":"created"}}\n__TRIPO_HTTP__200',stderr='')
        with patch.object(batch.shutil,'which',return_value='/usr/bin/curl'), \
             patch.dict(batch.os.environ,{'TRIPO_API_KEY':'test-credential'}), \
             patch.object(batch.subprocess,'run',side_effect=request):
            result=batch.call('POST','/generation/text-to-model',{'prompt':'angel'})
        self.assertEqual(result,{'task_id':'created'})

    def test_curl_resumes_valid_partial_glb(self):
        blob=b'glTF'+struct.pack('<II',2,20)+b'12345678'
        dest=Path(self.tmp.name)/'models'/'resume.glb'
        dest.parent.mkdir()
        partial=Path(str(dest)+'.part')
        partial.write_bytes(blob[:16])
        def transfer(command,**kwargs):
            self.assertIn('--continue-at',command)
            with partial.open('ab') as handle: handle.write(blob[16:])
            return SimpleNamespace(returncode=0,stdout='http=206 bytes=4',stderr='')
        with patch.object(batch.shutil,'which',return_value='/usr/bin/curl'), \
             patch.object(batch.subprocess,'run',side_effect=transfer),contextlib.redirect_stdout(io.StringIO()):
            batch.download('https://example.invalid/model.glb',str(dest))
        self.assertEqual(dest.read_bytes(),blob)


if __name__ == '__main__':
    unittest.main()
