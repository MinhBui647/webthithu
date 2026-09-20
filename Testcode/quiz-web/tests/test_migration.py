"""Ensure the new sample bank does not overwrite teacher content or attempts."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('migration_server', Path(__file__).resolve().parents[1] / 'server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        server.DB = Path(self.temp.name) / 'test.sqlite3'
        server.initialize()

    def tearDown(self):
        self.temp.cleanup()

    def test_upgrade_preserves_edited_questions_and_attempts(self):
        original = ('HTML được dùng để làm gì?', json.dumps(['Xây dựng cấu trúc trang web', 'Quản lý cơ sở dữ liệu', 'Chỉnh sửa video', 'Bảo vệ mạng máy tính'], ensure_ascii=False), 'A')
        edited = ('Câu hỏi do giảng viên biên soạn', json.dumps(['1', '2', '3', '4']), 'C')
        snapshot = json.dumps([{'id': 1, 'content': original[0], 'options': json.loads(original[1]), 'correct': 'A'}])
        with server.connect() as db:
            db.execute('DELETE FROM questions')
            db.execute("DELETE FROM metadata WHERE key='calculus_v1'")
            db.executemany('INSERT INTO questions(content,options,correct) VALUES(?,?,?)', [original, edited])
            db.execute('INSERT INTO attempts(id,name,questions,answers,status,strikes,created) VALUES(?,?,?,?,?,?,?)', ('old-attempt', 'Student', snapshot, '{"1":"A"}', 'locked', 3, 1))
        server.initialize()
        server.initialize()
        with server.connect() as db:
            rows = db.execute('SELECT * FROM questions').fetchall()
            self.assertEqual(len(rows), 13)
            self.assertIn(edited[0], [r['content'] for r in rows])
            self.assertNotIn(original[0], [r['content'] for r in rows])
            attempt = db.execute('SELECT * FROM attempts').fetchone()
            self.assertEqual(attempt['questions'], snapshot)
            self.assertEqual(attempt['answers'], '{"1":"A"}')
            self.assertEqual(attempt['status'], 'locked')
            self.assertEqual(attempt['strikes'], 3)

    def test_restart_does_not_restore_deleted_or_edited_samples(self):
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM questions').fetchone()[0], 12)
            db.execute('DELETE FROM questions WHERE id=1')
            db.execute("UPDATE questions SET content='Giảng viên đã chỉnh sửa' WHERE id=2")
        server.initialize()
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM questions').fetchone()[0], 11)
            self.assertEqual(db.execute('SELECT content FROM questions WHERE id=2').fetchone()[0], 'Giảng viên đã chỉnh sửa')

    def test_existing_attempts_get_hidden_scores_without_losing_results(self):
        with server.connect() as db:
            db.execute('DROP TABLE attempts')
            db.execute('''CREATE TABLE attempts (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, questions TEXT NOT NULL,
                answers TEXT NOT NULL DEFAULT '{}', strikes INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active', created REAL NOT NULL)''')
            questions = json.dumps([{'id': 1, 'content': 'Test', 'options': ['1','2','3','4'], 'correct': 'A'}])
            for status in ('active', 'submitted', 'locked'):
                db.execute('INSERT INTO attempts VALUES(?,?,?,?,?,?,?)', (status, 'Student', questions, '{"1":"A"}', 3 if status == 'locked' else 0, status, 123))
        server.initialize()
        server.initialize()
        with server.connect() as db:
            rows = db.execute('SELECT * FROM attempts').fetchall()
            self.assertEqual(len(rows), 3)
            for row in rows:
                self.assertEqual(row['score_released'], 0)
                self.assertEqual(row['questions'], questions)
                self.assertEqual(row['answers'], '{"1":"A"}')
                self.assertEqual(row['status'], row['id'])
                self.assertEqual(row['created'], 123)
                self.assertNotIn('score', server.attempt_view(row))
                self.assertEqual(server.calculate_score(row), 1)


if __name__ == '__main__':
    unittest.main()
