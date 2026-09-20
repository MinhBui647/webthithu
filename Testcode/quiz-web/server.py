"""Quiz web: Python standard library + SQLite. Run: python server.py."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from contextlib import contextmanager
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('QUIZ_DB', ROOT / 'data' / 'quiz.sqlite3'))
ADMIN_PASSWORD = os.environ.get('QUIZ_ADMIN_PASSWORD') or secrets.token_urlsafe(12)
ADMIN_HASH = hashlib.sha256(ADMIN_PASSWORD.encode()).digest()
HOST = os.environ.get('HOST', '127.0.0.1')
PORT = int(os.environ.get('PORT', '8000'))
LETTERS = 'ABCD'
CALCULUS_SAMPLES = [
    ('Tính giới hạn lim (x → 0) sin(x)/x, với x tính bằng radian.', ['0', '1', '+∞', 'Không tồn tại'], 'B'),
    ('Tính giới hạn lim (x → 2) (x² − 4)/(x − 2).', ['0', '2', '4', '8'], 'C'),
    ('Tính giới hạn lim (n → +∞) (1 + 1/n)ⁿ.', ['1', '0', '+∞', 'e'], 'D'),
    ('Cho f(x) = x³ − 3x + 2. Đạo hàm f′(x) là gì?', ['3x² − 3', '3x² + 2', 'x² − 3', '3x − 3'], 'A'),
    ('Cho f(x) = ln(x² + 1). Đạo hàm f′(x) là gì?', ['1/(x² + 1)', '2x/(x² + 1)', '2x ln(x² + 1)', '1/(2x)'], 'B'),
    ('Cho f(x) = x eˣ. Đạo hàm f′(x) là gì?', ['x eˣ', 'eˣ', '(x + 1)eˣ', '(x − 1)eˣ'], 'C'),
    ('Hàm số f(x) = x³ − 3x đạt cực đại địa phương tại x bằng bao nhiêu?', ['0', '1', '3', '−1'], 'D'),
    ('Tìm họ nguyên hàm ∫ 2x dx.', ['x² + C', '2x² + C', 'x + C', '2 + C'], 'A'),
    ('Tính tích phân xác định ∫ từ 0 đến 1 của x² dx.', ['1/2', '1/3', '1', '2/3'], 'B'),
    ('Tính tích phân xác định ∫ từ 1 đến e của (1/x) dx.', ['0', 'e − 1', '1', 'e'], 'C'),
    ('Tính tích phân suy rộng ∫ từ 1 đến +∞ của (1/x²) dx.', ['Phân kỳ', '0', '2', '1'], 'D'),
    ('Tổng của chuỗi hình học ∑ từ n = 0 đến +∞ của (1/2)ⁿ bằng bao nhiêu?', ['2', '1', '1/2', 'Chuỗi phân kỳ'], 'A'),
]


@contextmanager
def connect():
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY, content TEXT NOT NULL,
                options TEXT NOT NULL, correct TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, questions TEXT NOT NULL,
                answers TEXT NOT NULL DEFAULT '{}', strikes INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active', created REAL NOT NULL,
                score_released INTEGER NOT NULL DEFAULT 0 CHECK(score_released IN (0,1)));
            CREATE TABLE IF NOT EXISTS violations (
                attempt_id TEXT NOT NULL, event_id TEXT NOT NULL,
                PRIMARY KEY (attempt_id, event_id));
            CREATE TABLE IF NOT EXISTS admin_sessions (
                token TEXT PRIMARY KEY, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS login_limits (
                ip TEXT PRIMARY KEY, failures INTEGER NOT NULL, since REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY);
        ''')
        db.execute('BEGIN IMMEDIATE')
        if 'score_released' not in {row['name'] for row in db.execute('PRAGMA table_info(attempts)')}:
            db.execute('ALTER TABLE attempts ADD COLUMN score_released INTEGER NOT NULL DEFAULT 0 CHECK(score_released IN (0,1))')
        if not db.execute("SELECT 1 FROM metadata WHERE key='calculus_v1'").fetchone():
            legacy_samples = [
                ('HTML được dùng để làm gì?', ['Xây dựng cấu trúc trang web', 'Quản lý cơ sở dữ liệu', 'Chỉnh sửa video', 'Bảo vệ mạng máy tính'], 'A'),
                ('Thuộc tính CSS nào thay đổi màu chữ?', ['background', 'font-size', 'color', 'display'], 'C'),
                ('Ngôn ngữ nào chạy trực tiếp trong trình duyệt để tạo tương tác?', ['C++', 'JavaScript', 'SQL', 'Python'], 'B'),
                ('HTTP là viết tắt của cụm từ nào?', ['High Text Transfer Program', 'Hyper Tool Transport Process', 'Home Text Transfer Protocol', 'Hypertext Transfer Protocol'], 'D'),
                ('Thẻ HTML nào tạo một liên kết?', ['<a>', '<p>', '<div>', '<span>'], 'A'),
                ('Lệnh SQL nào dùng để lấy dữ liệu?', ['INSERT', 'DELETE', 'SELECT', 'UPDATE'], 'C'),
            ]
            # Replace untouched original samples; preserve custom questions and
            # existing attempts, which already contain question snapshots.
            for row in db.execute('SELECT * FROM questions').fetchall():
                if (row['content'], json.loads(row['options']), row['correct']) in legacy_samples:
                    db.execute('DELETE FROM questions WHERE id=?', (row['id'],))
            db.executemany('INSERT INTO questions(content,options,correct) VALUES(?,?,?)',
                           [(q, json.dumps(o, ensure_ascii=False), c) for q, o, c in CALCULUS_SAMPLES])
            db.execute("INSERT OR IGNORE INTO metadata VALUES('seeded')")
            db.execute("INSERT INTO metadata VALUES('calculus_v1')")


def question(row):
    return dict(id=row['id'], content=row['content'], options=json.loads(row['options']), correct=row['correct'])


def calculate_score(row):
    answers = json.loads(row['answers'])
    return sum(answers.get(str(q['id'])) == q['correct'] for q in json.loads(row['questions']))


def attempt_view(row):
    questions = json.loads(row['questions'])
    answers = json.loads(row['answers'])
    result = dict(id=row['id'], name=row['name'], answers=answers, strikes=row['strikes'],
                  status=row['status'], created=row['created'],
                  scoreReleased=bool(row['score_released']) and row['status'] != 'active',
                  questions=[{k: v for k, v in q.items() if k != 'correct'} for q in questions])
    # Unreleased results must never leave the backend through student APIs.
    if result['scoreReleased']:
        result['score'] = calculate_score(row)
    return result


class APIError(Exception):
    def __init__(self, message, code=400):
        self.message, self.code = message, code


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Avoid recording session tokens or request bodies.
        if '/api/admin/attempts/' in self.path:
            return
        super().log_message(fmt, *args)

    def reply(self, body, status=200, cookie=None, mime='application/json; charset=utf-8'):
        data = json.dumps(body, ensure_ascii=False).encode() if isinstance(body, (dict, list)) else body
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(data)

    def cookie(self, key):
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get('Cookie', ''))
            return cookies[key].value if key in cookies else None
        except Exception:
            return None

    def make_cookie(self, key, value, age):
        secure = '; Secure' if os.environ.get('COOKIE_SECURE') == '1' else ''
        return f'{key}={value}; HttpOnly; SameSite=Strict; Path=/; Max-Age={age}{secure}'

    def body(self):
        try:
            size = int(self.headers.get('Content-Length', 0))
            if size < 0 or size > 65536:
                raise APIError('Dữ liệu quá lớn.', 413)
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except (ValueError, UnicodeDecodeError):
            raise APIError('Dữ liệu JSON không hợp lệ.')

    def admin(self, db):
        token = self.cookie('admin_session')
        if not token or not db.execute('SELECT 1 FROM admin_sessions WHERE token=? AND expires>?',
                                       (token, time.time())).fetchone():
            raise APIError('Vui lòng đăng nhập quản trị.', 401)

    def attempt(self, db):
        row = db.execute('SELECT * FROM attempts WHERE id=?', (self.cookie('quiz_attempt'),)).fetchone()
        if not row:
            raise APIError('Chưa có bài làm. Hãy bắt đầu bài kiểm tra.', 404)
        return row

    def do_GET(self):
        self.dispatch('GET')

    def do_POST(self):
        self.dispatch('POST')

    def do_PUT(self):
        self.dispatch('PUT')

    def do_DELETE(self):
        self.dispatch('DELETE')

    def dispatch(self, method):
        try:
            path = urlsplit(self.path).path
            if method != 'GET':
                origin = self.headers.get('Origin')
                if (origin and origin not in ('http://' + self.headers.get('Host', ''),
                                               'https://' + self.headers.get('Host', ''))) or self.headers.get('Sec-Fetch-Site') == 'cross-site':
                    raise APIError('Yêu cầu từ nguồn không hợp lệ.', 403)
            if not path.startswith('/api/'):
                files = {'/': ('index.html', 'text/html'), '/admin': ('admin.html', 'text/html'),
                         '/app.js': ('app.js', 'text/javascript'), '/admin.js': ('admin.js', 'text/javascript'),
                         '/style.css': ('style.css', 'text/css'),
                         '/club.css': ('club.css', 'text/css'),
                         '/club-logo.png': ('club-logo.png', 'image/png'),
                         '/favicon.ico': ('club-logo.png', 'image/png')}
                if method != 'GET' or path not in files:
                    raise APIError('Không tìm thấy trang.', 404)
                filename, mime = files[path]
                return self.reply((ROOT / 'static' / filename).read_bytes(), mime=mime + '; charset=utf-8')
            with connect() as db:
                # Serialize every mutation, including the check for an active attempt.
                if method != 'GET':
                    db.execute('BEGIN IMMEDIATE')
                result, cookie = self.route(db, method, path)
            self.reply(result, cookie=cookie)
        except APIError as error:
            self.reply({'error': error.message}, error.code)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            import traceback
            traceback.print_exc()
            self.reply({'error': 'Máy chủ gặp lỗi. Vui lòng thử lại.'}, 500)

    def route(self, db, method, path):
        if path == '/api/info' and method == 'GET':
            return {'count': db.execute('SELECT COUNT(*) FROM questions').fetchone()[0]}, None
        if path == '/api/attempt' and method == 'GET':
            return attempt_view(self.attempt(db)), None
        if path == '/api/attempt' and method == 'POST':
            data = self.body()
            existing = db.execute('SELECT * FROM attempts WHERE id=?', (self.cookie('quiz_attempt'),)).fetchone()
            if existing:
                return attempt_view(existing), None
            name = data.get('name', '')
            if not isinstance(name, str) or not 2 <= len(name.strip()) <= 80:
                raise APIError('Họ tên cần có từ 2 đến 80 ký tự.')
            qs = [question(q) for q in db.execute('SELECT * FROM questions ORDER BY id')]
            if not qs:
                raise APIError('Chưa có câu hỏi. Hãy liên hệ người quản trị.')
            token = secrets.token_urlsafe(32)
            db.execute('INSERT INTO attempts(id,name,questions,created) VALUES(?,?,?,?)',
                       (token, name.strip(), json.dumps(qs, ensure_ascii=False), time.time()))
            row = db.execute('SELECT * FROM attempts WHERE id=?', (token,)).fetchone()
            return attempt_view(row), self.make_cookie('quiz_attempt', token, 86400 * 365)
        if path == '/api/attempt/violation' and method == 'POST':
            data = self.body()
            row = self.attempt(db)
            event = data.get('eventId')
            if not isinstance(event, str) or not 8 <= len(event) <= 100:
                raise APIError('Mã cảnh cáo không hợp lệ.')
            if row['status'] == 'active':
                added = db.execute('INSERT OR IGNORE INTO violations VALUES(?,?)', (row['id'], event)).rowcount
                if added:
                    strikes = min(3, row['strikes'] + 1)
                    db.execute('UPDATE attempts SET strikes=?,status=? WHERE id=?',
                               (strikes, 'locked' if strikes >= 3 else 'active', row['id']))
            return attempt_view(self.attempt(db)), None
        if path in ('/api/attempt/answer', '/api/attempt/submit') and method == 'POST':
            data = self.body()
            row = self.attempt(db)
            if row['status'] != 'active':
                raise APIError('Bài làm đã bị khóa hoặc đã nộp. Không thể đổi đáp án.', 423)
            if path.endswith('/answer'):
                key, answer = str(data.get('questionId')), data.get('answer')
                if key not in [str(q['id']) for q in json.loads(row['questions'])] or answer not in list(LETTERS):
                    raise APIError('Chỉ được chọn đáp án A, B, C hoặc D của câu hỏi trong bài.')
                answers = json.loads(row['answers'])
                answers[key] = answer
                db.execute('UPDATE attempts SET answers=? WHERE id=?', (json.dumps(answers), row['id']))
            else:
                db.execute("UPDATE attempts SET status='submitted' WHERE id=?", (row['id'],))
            return attempt_view(self.attempt(db)), None
        if path == '/api/admin/login' and method == 'POST':
            data = self.body()
            ip = self.client_address[0]
            now = time.time()
            limit = db.execute('SELECT * FROM login_limits WHERE ip=?', (ip,)).fetchone()
            if limit and limit['failures'] >= 10 and now - limit['since'] < 300:
                raise APIError('Đăng nhập sai quá nhiều lần. Thử lại sau 5 phút.', 429)
            password = data.get('password', '')
            if not isinstance(password, str) or not hmac.compare_digest(hashlib.sha256(password.encode()).digest(), ADMIN_HASH):
                failures = limit['failures'] + 1 if limit and now - limit['since'] < 300 else 1
                since = limit['since'] if failures > 1 else now
                db.execute('INSERT OR REPLACE INTO login_limits VALUES(?,?,?)', (ip, failures, since))
                db.commit()
                raise APIError('Mật khẩu quản trị chưa đúng.', 401)
            db.execute('DELETE FROM login_limits WHERE ip=?', (ip,))
            db.execute('DELETE FROM admin_sessions WHERE expires<?', (now,))
            token = secrets.token_urlsafe(32)
            db.execute('INSERT INTO admin_sessions VALUES(?,?)', (token, now + 28800))
            return {'ok': True}, self.make_cookie('admin_session', token, 28800)
        if path.startswith('/api/admin/'):
            self.admin(db)
            if path == '/api/admin/logout' and method == 'POST':
                db.execute('DELETE FROM admin_sessions WHERE token=?', (self.cookie('admin_session'),))
                return {'ok': True}, self.make_cookie('admin_session', '', 0)
            if path == '/api/admin/questions' and method == 'GET':
                return [question(q) for q in db.execute('SELECT * FROM questions ORDER BY id')], None
            if path == '/api/admin/attempts' and method == 'GET':
                rows = db.execute('SELECT * FROM attempts ORDER BY created DESC LIMIT 100')
                return [dict(id=r['id'], name=r['name'], status=r['status'], strikes=r['strikes'],
                             scoreReleased=bool(r['score_released']),
                             score=calculate_score(r) if r['status'] != 'active' else None,
                             answered=len(json.loads(r['answers'])), total=len(json.loads(r['questions']))) for r in rows], None
            if path.startswith('/api/admin/attempts/') and path.endswith('/release-score') and method == 'POST':
                self.body()
                token = path[len('/api/admin/attempts/'):-len('/release-score')]
                row = db.execute('SELECT * FROM attempts WHERE id=?', (token,)).fetchone()
                if not row:
                    raise APIError('Lượt làm bài không tồn tại.', 404)
                if row['status'] == 'active':
                    raise APIError('Chỉ được cho xem điểm khi bài đã nộp hoặc bị khóa.', 409)
                db.execute('UPDATE attempts SET score_released=1 WHERE id=?', (token,))
                return {'ok': True, 'scoreReleased': True}, None
            if path.startswith('/api/admin/attempts/') and method == 'DELETE':
                token = path.rsplit('/', 1)[1]
                db.execute('DELETE FROM violations WHERE attempt_id=?', (token,))
                db.execute('DELETE FROM attempts WHERE id=?', (token,))
                return {'ok': True}, None
            if path == '/api/admin/questions' and method == 'POST' or path.startswith('/api/admin/questions/') and method == 'PUT':
                data = self.body()
                content, options, correct = data.get('content'), data.get('options'), data.get('correct')
                if not isinstance(content, str) or not 1 <= len(content.strip()) <= 2000:
                    raise APIError('Nội dung câu hỏi cần có từ 1 đến 2000 ký tự.')
                if not isinstance(options, list) or len(options) != 4 or any(not isinstance(o, str) or not 1 <= len(o.strip()) <= 500 for o in options):
                    raise APIError('Cần đủ 4 đáp án, mỗi đáp án từ 1 đến 500 ký tự.')
                if correct not in list(LETTERS):
                    raise APIError('Chọn một đáp án đúng A, B, C hoặc D.')
                values = (content.strip(), json.dumps([o.strip() for o in options], ensure_ascii=False), correct)
                if method == 'POST':
                    db.execute('INSERT INTO questions(content,options,correct) VALUES(?,?,?)', values)
                else:
                    if not db.execute('UPDATE questions SET content=?,options=?,correct=? WHERE id=?', values + (path.rsplit('/', 1)[1],)).rowcount:
                        raise APIError('Câu hỏi không tồn tại.', 404)
                return {'ok': True}, None
            if path.startswith('/api/admin/questions/') and method == 'DELETE':
                db.execute('DELETE FROM questions WHERE id=?', (path.rsplit('/', 1)[1],))
                return {'ok': True}, None
        raise APIError('Không tìm thấy API.', 404)


if __name__ == '__main__':
    initialize()
    print(f'Quiz web: http://{HOST}:{PORT}', flush=True)
    print(f'Admin: http://{HOST}:{PORT}/admin', flush=True)
    if not os.environ.get('QUIZ_ADMIN_PASSWORD'):
        print(f'Admin password (generated for this run): {ADMIN_PASSWORD}', flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
