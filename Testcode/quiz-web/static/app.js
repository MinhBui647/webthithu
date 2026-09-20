const $ = (id) => document.getElementById(id);
let attempt = null, position = 0, busy = false, syncing = false, away = false;
let pending = [], localStrikes = 0, savingError = false;
const letters = ['A', 'B', 'C', 'D'];

async function api(path, data) {
  const response = await fetch(path, { method: data === undefined ? 'GET' : 'POST',
    headers: data === undefined ? {} : { 'Content-Type': 'application/json' },
    body: data === undefined ? undefined : JSON.stringify(data) });
  const body = await response.json();
  if (!response.ok) { const error = new Error(body.error || 'Không thể kết nối máy chủ.'); error.status = response.status; throw error; }
  return body;
}
function message(text = '') { $('page-error').textContent = text; $('page-error').hidden = !text; }
function persist() {
  if (attempt) localStorage.setItem('focus:' + attempt.id, JSON.stringify({ pending, localStrikes }));
}
function active() { return attempt?.status === 'active' && localStrikes < 3; }
function render() {
  if (!attempt) return;
  $('welcome').hidden = true;
  const ended = attempt.status !== 'active' || localStrikes >= 3;
  $('exam').hidden = ended; $('result').hidden = !ended;
  if (ended) {
    const locked = attempt.status === 'locked' || localStrikes >= 3;
    $('result-icon').textContent = locked ? '!' : '✓';
    $('result-icon').classList.toggle('locked', locked);
    $('result-kicker').textContent = locked ? 'GIỚI HẠN CẢNH CÁO ĐÃ ĐẠT' : 'BÀI LÀM ĐÃ ĐƯỢC LƯU';
    $('result-title').textContent = locked ? 'Bài làm đã bị khóa.' : 'Bạn đã hoàn thành bài kiểm tra!';
    const canSeeScore = attempt.status !== 'active' && attempt.scoreReleased === true && Number.isFinite(attempt.score);
    $('result-description').textContent = locked ? 'Bạn đã rời trang 3 lần. Không thể chọn hoặc thay đổi đáp án nữa.' : 'Bài làm của bạn đã được lưu. Cảm ơn bạn đã dành thời gian tập trung.';
    $('score-panel').hidden = !canSeeScore;
    $('score').textContent = canSeeScore ? `${attempt.score} / ${attempt.questions.length}` : '';
    $('score-waiting').hidden = canSeeScore;
    $('score-waiting').textContent = pending.length || attempt.status === 'active'
      ? 'Đang đồng bộ bài làm. Điểm sẽ được giữ kín cho đến khi quản trị viên cho phép xem.'
      : 'Điểm đang được ẩn. Vui lòng chờ quản trị viên cho phép xem điểm. Trang sẽ tự cập nhật khi có kết quả.';
    $('result-detail').textContent = `${attempt.name} · Đã trả lời ${Object.keys(attempt.answers).length}/${attempt.questions.length} câu · ${Math.max(localStrikes, attempt.strikes)}/3 cảnh cáo`;
    $('submit-dialog').close();
    return;
  }
  const q = attempt.questions[position];
  $('student-label').textContent = attempt.name;
  $('avatar').textContent = attempt.name.trim().split(/\s+/).pop().slice(0, 1).toUpperCase();
  $('question-label').textContent = `CÂU ${String(position + 1).padStart(2, '0')} / ${String(attempt.questions.length).padStart(2, '0')}`;
  $('question-title').textContent = q.content;
  $('question-position').textContent = `${position + 1} / ${attempt.questions.length}`;
  $('options').replaceChildren();
  letters.forEach((letter, index) => {
    const label = document.createElement('label'); label.className = 'option';
    const input = document.createElement('input'); input.type = 'radio'; input.name = 'answer';
    input.value = letter; input.checked = attempt.answers[q.id] === letter;
    input.disabled = busy || syncing || pending.length > 0 || savingError;
    input.addEventListener('change', () => saveAnswer(q.id, letter));
    const badge = document.createElement('span'); badge.className = 'option-letter'; badge.textContent = letter;
    const text = document.createElement('span'); text.className = 'option-text'; text.textContent = q.options[index];
    const check = document.createElement('span'); check.className = 'option-check'; check.textContent = '✓';
    label.append(input, badge, text, check); $('options').append(label);
  });
  const done = Object.keys(attempt.answers).length;
  $('progress-label').textContent = `${done}/${attempt.questions.length}`;
  $('progress').max = attempt.questions.length; $('progress').value = done;
  $('question-grid').replaceChildren();
  attempt.questions.forEach((question, index) => {
    const button = document.createElement('button'); button.textContent = String(index + 1).padStart(2, '0');
    button.className = 'grid-button' + (attempt.answers[question.id] ? ' answered' : '') + (index === position ? ' current' : '');
    button.setAttribute('aria-label', `Câu ${index + 1}${attempt.answers[question.id] ? ', đã trả lời' : ''}`);
    if (index === position) button.setAttribute('aria-current', 'step');
    button.onclick = () => { position = index; render(); }; $('question-grid').append(button);
  });
  $('previous').disabled = position === 0;
  $('next').disabled = position === attempt.questions.length - 1;
  $('submit').disabled = busy || syncing || pending.length > 0 || savingError;
  $('strike-count').textContent = `${Math.max(localStrikes, attempt.strikes)} / 3`;
  $('save-status').textContent = busy ? 'Đang lưu đáp án…' : syncing || pending.length ? 'Đang đồng bộ cảnh cáo…' : savingError ? 'Mất kết nối · đang thử lại' : '✓ Đã đồng bộ';
}
async function saveAnswer(questionId, answer) {
  if (!active() || busy || pending.length || savingError) return;
  busy = true; render(); message();
  try { attempt = await api('/api/attempt/answer', { questionId, answer }); }
  catch (error) { message(error.message); if (error.status === 423) await refresh(); }
  finally { busy = false; render(); }
}
async function refresh() {
  if (busy || syncing || pending.length) return;
  const previousStatus = attempt?.status;
  try {
    const updated = await api('/api/attempt');
    if (busy || syncing || pending.length || attempt?.status !== previousStatus) return;
    attempt = updated; localStrikes = Math.max(localStrikes, attempt.strikes);
    savingError = false; persist(); render();
  } catch (error) {
    if (error.status === 404) { attempt = null; location.reload(); return; }
    savingError = true; message('Chưa thể đồng bộ với máy chủ. Đáp án tạm khóa cho đến khi kết nối trở lại.'); render();
  }
}
async function flush() {
  if (syncing || !attempt || !pending.length) return;
  syncing = true; render();
  try {
    while (pending.length) {
      const eventId = pending[0];
      const updated = await api('/api/attempt/violation', { eventId });
      attempt = updated; pending = pending.filter(id => id !== eventId);
      localStrikes = Math.max(localStrikes, attempt.strikes); persist();
    }
    savingError = false; message();
  } catch (error) { savingError = true; message('Chưa lưu được cảnh cáo. Tạm khóa trả lời và tự thử lại khi có kết nối.'); }
  finally { syncing = false; render(); }
}
function warn() {
  if (!attempt || attempt.status === 'submitted') return;
  $('warning-title').textContent = localStrikes >= 3 ? 'Cảnh cáo 3/3 — Bài làm đã khóa' : `Cảnh cáo ${localStrikes}/3`;
  $('warning-message').textContent = localStrikes >= 3 ? 'Bạn đã rời trang đủ 3 lần. Các đáp án đã lưu được giữ lại, nhưng bạn không thể trả lời thêm.' : `Bạn vừa rời tab hoặc cửa sổ làm bài. Còn ${3 - localStrikes} lần trước khi bài bị khóa.`;
  $('warning-close').textContent = localStrikes >= 3 ? 'Xem trạng thái bài làm' : 'Mình đã hiểu, tiếp tục làm bài';
  $('submit-dialog').close();
  if (!$('warning-dialog').open) $('warning-dialog').showModal();
}
function leave() {
  if (!active() || away) return;
  away = true; localStrikes += 1;
  const eventId = crypto.randomUUID ? crypto.randomUUID() : Array.from(crypto.getRandomValues(new Uint32Array(4)), n => n.toString(16).padStart(8, '0')).join('');
  pending.push(eventId); persist();
  // One event ID is reused by beacon and retry: the backend counts it only once.
  navigator.sendBeacon('/api/attempt/violation', new Blob([JSON.stringify({ eventId })], { type: 'application/json' }));
  render(); flush();
}
function returnToExam() {
  if (document.visibilityState !== 'visible' || !document.hasFocus()) return;
  if (away) { away = false; warn(); }
  flush();
}
window.addEventListener('blur', leave);
document.addEventListener('visibilitychange', () => document.hidden ? leave() : returnToExam());
window.addEventListener('focus', returnToExam);
window.addEventListener('pagehide', leave);
window.addEventListener('pageshow', returnToExam);
window.addEventListener('online', () => pending.length ? flush() : refresh());
$('warning-close').onclick = () => $('warning-dialog').close();
$('warning-dialog').addEventListener('cancel', e => e.preventDefault());
$('previous').onclick = () => { if (position > 0) position--; render(); };
$('next').onclick = () => { if (position < attempt.questions.length - 1) position++; render(); };
$('submit').onclick = () => {
  const remaining = attempt.questions.length - Object.keys(attempt.answers).length;
  $('submit-summary').textContent = remaining ? `Bạn còn ${remaining} câu chưa trả lời. Sau khi nộp, bạn không thể chỉnh sửa đáp án.` : 'Bạn đã trả lời tất cả câu hỏi. Sau khi nộp, bạn không thể chỉnh sửa đáp án.';
  $('submit-dialog').showModal();
};
$('cancel-submit').onclick = () => $('submit-dialog').close();
$('confirm-submit').onclick = async () => {
  if (!active() || busy || syncing || pending.length || savingError) return;
  busy = true; $('confirm-submit').disabled = true;
  try { attempt = await api('/api/attempt/submit', {}); $('submit-dialog').close(); }
  catch (error) { message(error.message); $('submit-dialog').close(); if (error.status === 423) await refresh(); }
  finally { busy = false; $('confirm-submit').disabled = false; render(); }
};
$('start-form').onsubmit = async e => {
  e.preventDefault(); $('start-button').disabled = true; message();
  try {
    // Verify storage is available before starting a protected attempt.
    localStorage.setItem('focus:storage-check', 'ok'); localStorage.removeItem('focus:storage-check');
    attempt = await api('/api/attempt', { name: $('student-name').value.trim() });
    loadLocal(); away = false; render(); await flush();
  } catch (error) { message(error.message); }
  finally { $('start-button').disabled = false; }
};
function loadLocal() {
  const stored = JSON.parse(localStorage.getItem('focus:' + attempt.id) || '{}');
  pending = Array.isArray(stored.pending) ? stored.pending : [];
  localStrikes = Math.max(attempt.strikes, Number(stored.localStrikes) || 0);
}
async function init() {
  try {
    const info = await api('/api/info'); $('question-count').textContent = String(info.count).padStart(2, '0');
    $('start-button').disabled = info.count === 0;
    try { attempt = await api('/api/attempt'); loadLocal(); render(); await flush(); }
    catch (error) { if (error.status !== 404) throw error; $('welcome').hidden = false; }
  } catch (error) { message('Không tải được bài kiểm tra: ' + error.message + ' Hãy tải lại trang để thử lại.'); }
}
setInterval(() => { if (pending.length) flush(); else if (attempt && document.visibilityState === 'visible') refresh(); }, 5000);
init();
