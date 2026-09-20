import concurrent.futures
import http.cookiejar
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

spec = importlib.util.spec_from_file_location('quiz_server', Path(__file__).resolve().parents[1] / 'server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        server.DB = Path(cls.temp.name) / 'quiz.sqlite3'
        server.initialize()
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.base = f'http://127.0.0.1:{cls.http.server_port}'
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def setUp(self):
        self.student = self.client()
        self.admin = self.client()
        self.assertEqual(self.call(self.admin, '/api/admin/login', {'password': server.ADMIN_PASSWORD})[0], 200)

    def client(self):
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, client, path, data=None, method=None, headers=None):
        request = urllib.request.Request(self.base + path, data=None if data is None else json.dumps(data).encode(),
                                         method=method or ('POST' if data is not None else 'GET'),
                                         headers=headers or {'Content-Type': 'application/json'})
        try:
            with client.open(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.loads(error.read())

    def start(self):
        code, data = self.call(self.student, '/api/attempt', {'name': 'Nguyễn Minh Anh'})
        self.assertEqual(code, 200)
        return data

    def test_admin_auth_crud_and_validation(self):
        self.assertEqual(self.call(self.student, '/api/admin/questions')[0], 401)
        data = {'content': '<script>alert(1)</script> Câu mới', 'options': ['Một', 'Hai', 'Ba', 'Bốn'], 'correct': 'B'}
        self.assertEqual(self.call(self.admin, '/api/admin/questions', data)[0], 200)
        qs = self.call(self.admin, '/api/admin/questions')[1]
        q = next(q for q in qs if q['content'] == data['content'])
        path = f"/api/admin/questions/{q['id']}"
        data['content'] = 'Câu đã sửa'
        self.assertEqual(self.call(self.admin, path, data, 'PUT')[0], 200)
        data['options'] = ['Thiếu đáp án']
        self.assertEqual(self.call(self.admin, path, data, 'PUT')[0], 400)
        self.assertEqual(self.call(self.admin, path, method='DELETE')[0], 200)
        self.assertFalse(any(x['id'] == q['id'] for x in self.call(self.admin, '/api/admin/questions')[1]))

    def test_three_strikes_lock_reload_and_idempotent_retry(self):
        a = self.start()
        self.assertNotIn('correct', a['questions'][0])
        answer = {'questionId': a['questions'][0]['id'], 'answer': 'A'}
        self.assertEqual(self.call(self.student, '/api/attempt/answer', answer)[0], 200)
        for i in range(1, 4):
            event = {'eventId': f'violation-{i}'}
            state = self.call(self.student, '/api/attempt/violation', event)[1]
            self.assertEqual(state['strikes'], i)
            state = self.call(self.student, '/api/attempt/violation', event)[1]
            self.assertEqual(state['strikes'], i)
        self.assertEqual(state['status'], 'locked')
        self.assertEqual(self.call(self.student, '/api/attempt')[1]['status'], 'locked')
        self.assertEqual(self.call(self.student, '/api/attempt', {'name': 'Tên khác'})[1]['id'], a['id'])
        self.assertEqual(self.call(self.student, '/api/attempt/answer', answer)[0], 423)
        self.assertEqual(self.call(self.student, '/api/attempt/submit', {})[0], 423)

    def test_snapshot_scoring_and_submission_are_final(self):
        a = self.start()
        qs = self.call(self.admin, '/api/admin/questions')[1]
        first = qs[0]
        changed = dict(first, content='Thay đổi trong lúc thi')
        self.call(self.admin, f"/api/admin/questions/{first['id']}", changed, 'PUT')
        try:
            self.assertEqual(self.call(self.student, '/api/attempt')[1]['questions'][0]['content'], first['content'])
            for q in qs:
                self.assertEqual(self.call(self.student, '/api/attempt/answer', {'questionId': q['id'], 'answer': q['correct']})[0], 200)
            code, result = self.call(self.student, '/api/attempt/submit', {})
            self.assertEqual(code, 200)
            self.assertNotIn('score', result)
            self.assertFalse(result['scoreReleased'])
            self.assertEqual(result['status'], 'submitted')
            self.assertEqual(self.call(self.admin, f"/api/admin/attempts/{a['id']}/release-score", {})[0], 200)
            self.assertEqual(self.call(self.student, '/api/attempt')[1]['score'], len(qs))
            self.assertEqual(self.call(self.student, '/api/attempt/answer', {'questionId': first['id'], 'answer': 'A'})[0], 423)
            self.assertEqual(self.call(self.student, '/api/attempt/violation', {'eventId': 'after-submit'})[1]['strikes'], 0)
        finally:
            self.call(self.admin, f"/api/admin/questions/{first['id']}", first, 'PUT')

    def test_invalid_answers_origin_and_admin_reset(self):
        a = self.start()
        for answer in ['E', '', ['A'], None]:
            self.assertEqual(self.call(self.student, '/api/attempt/answer', {'questionId': a['questions'][0]['id'], 'answer': answer})[0], 400)
        self.assertEqual(self.call(self.student, '/api/attempt/answer', {'questionId': -1, 'answer': 'A'})[0], 400)
        self.assertEqual(self.call(self.student, '/api/attempt/submit', {}, headers={'Origin': 'https://other.example'})[0], 403)
        self.assertEqual(self.call(self.student, f"/api/admin/attempts/{a['id']}", method='DELETE')[0], 401)
        self.assertEqual(self.call(self.admin, f"/api/admin/attempts/{a['id']}", method='DELETE')[0], 200)
        self.assertEqual(self.call(self.student, '/api/attempt')[0], 404)
        self.assertNotEqual(self.start()['id'], a['id'])

    def test_concurrent_strikes_count_once_each(self):
        self.start()
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(lambda i: self.call(self.student, '/api/attempt/violation', {'eventId': f'concurrent-{i % 3}'}), range(6)))
        self.assertTrue(all(code == 200 for code, _ in results))
        result = self.call(self.student, '/api/attempt')[1]
        self.assertEqual(result['strikes'], 3)
        self.assertEqual(result['status'], 'locked')

    def test_logout_and_login_limit(self):
        self.assertEqual(self.call(self.admin, '/api/admin/logout', {})[0], 200)
        self.assertEqual(self.call(self.admin, '/api/admin/questions')[0], 401)
        for _ in range(10):
            self.assertEqual(self.call(self.student, '/api/admin/login', {'password': 'wrong'})[0], 401)
        self.assertEqual(self.call(self.student, '/api/admin/login', {'password': 'wrong'})[0], 429)
        with server.connect() as db:
            db.execute('DELETE FROM login_limits')

    def test_score_release_permissions_and_visibility(self):
        for final_status in ('submitted', 'locked'):
            with self.subTest(status=final_status):
                self.student = self.client()
                a = self.start()
                release = f"/api/admin/attempts/{a['id']}/release-score"
                self.assertNotIn('score', a)
                self.assertFalse(a['scoreReleased'])
                self.assertEqual(self.call(self.admin, release, {})[0], 409)
                q = self.call(self.admin, '/api/admin/questions')[1][0]
                answer = self.call(self.student, '/api/attempt/answer', {'questionId': q['id'], 'answer': q['correct'], 'scoreReleased': True})[1]
                self.assertNotIn('score', answer)
                if final_status == 'submitted':
                    code, result = self.call(self.student, '/api/attempt/submit', {'scoreReleased': True})
                else:
                    for i in range(3):
                        code, result = self.call(self.student, '/api/attempt/violation', {'eventId': f'hide-score-{i}'})
                self.assertEqual(code, 200)
                self.assertNotIn('score', result)
                self.assertFalse(result['scoreReleased'])
                self.assertEqual(self.call(self.student, release, {})[0], 401)
                self.assertEqual(self.call(self.client(), release, {})[0], 401)
                # Every route returning an existing student attempt stays private.
                responses = [
                    self.call(self.student, '/api/attempt')[1],
                    self.call(self.student, '/api/attempt', {'name': 'Retry', 'scoreReleased': True})[1],
                    self.call(self.student, '/api/attempt/violation', {'eventId': 'after-finished'})[1],
                ]
                for response in responses:
                    self.assertEqual(response['status'], final_status)
                    self.assertNotIn('score', response)
                    self.assertFalse(response['scoreReleased'])
                    self.assertTrue(all('correct' not in question for question in response['questions']))
                admin_row = next(r for r in self.call(self.admin, '/api/admin/attempts')[1] if r['id'] == a['id'])
                self.assertEqual(admin_row['score'], 1)
                self.assertFalse(admin_row['scoreReleased'])
                for _ in range(2):
                    self.assertEqual(self.call(self.admin, release, {})[0], 200)
                server.initialize()
                published = self.call(self.student, '/api/attempt')[1]
                self.assertTrue(published['scoreReleased'])
                self.assertEqual(published['score'], 1)
                self.assertEqual(published['status'], final_status)
                self.assertEqual(self.call(self.student, '/api/attempt/answer', {'questionId': q['id'], 'answer': 'A'})[0], 423)
                admin_row = next(r for r in self.call(self.admin, '/api/admin/attempts')[1] if r['id'] == a['id'])
                self.assertTrue(admin_row['scoreReleased'])

    def test_release_is_per_attempt_and_reset_requires_new_permission(self):
        first = self.start()
        self.call(self.student, '/api/attempt/submit', {})
        other = self.client()
        self.call(other, '/api/attempt', {'name': 'Another Student'})
        self.call(other, '/api/attempt/submit', {})
        self.assertEqual(self.call(self.admin, f"/api/admin/attempts/{first['id']}/release-score", {})[0], 200)
        self.assertEqual(self.call(self.student, '/api/attempt')[1]['score'], 0)
        self.assertNotIn('score', self.call(other, '/api/attempt')[1])
        self.assertEqual(self.call(self.admin, '/api/admin/attempts/missing/release-score', {})[0], 404)
        self.call(self.admin, f"/api/admin/attempts/{first['id']}", method='DELETE')
        fresh = self.start()
        self.assertNotEqual(fresh['id'], first['id'])
        result = self.call(self.student, '/api/attempt/submit', {})[1]
        self.assertFalse(result['scoreReleased'])
        self.assertNotIn('score', result)


if __name__ == '__main__':
    unittest.main()
