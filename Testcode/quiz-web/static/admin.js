const $ = id => document.getElementById(id);
let questions = [], editing = null, confirmedAction = null;
async function api(path, method = 'GET', data) {
  const response = await fetch(path, { method, headers: data ? { 'Content-Type': 'application/json' } : {}, body: data ? JSON.stringify(data) : undefined });
  const result = await response.json();
  if (!response.ok) { if (response.status === 401) showLogin(); const error = new Error(result.error); error.status = response.status; throw error; }
  return result;
}
function message(text, error = false) { $('admin-message').textContent = text; $('admin-message').hidden = !text; $('admin-message').classList.toggle('danger', error); }
function showLogin() { $('login-panel').hidden = false; $('dashboard').hidden = true; $('logout').hidden = true; }
function button(text, className, action) { const b = document.createElement('button'); b.textContent = text; b.className = className; b.onclick = action; return b; }
for (const letter of 'ABCD') {
  const row = document.createElement('div'); row.className = 'admin-option';
  const label = document.createElement('label'); label.className = 'correct-choice';
  const radio = document.createElement('input'); radio.type = 'radio'; radio.name = 'correct'; radio.value = letter; radio.required = true; radio.setAttribute('aria-label', `Chọn ${letter} làm đáp án đúng`);
  label.append(radio, document.createTextNode(letter));
  const input = document.createElement('input'); input.id = `option-${letter}`; input.required = true; input.maxLength = 500; input.placeholder = `Nội dung đáp án ${letter}`; input.setAttribute('aria-label', `Nội dung đáp án ${letter}`);
  row.append(label, input); $('option-inputs').append(row);
}
function resetEditor() { editing = null; $('question-form').reset(); $('editor-title').textContent = 'Thêm câu hỏi mới'; $('save-question').textContent = 'Lưu câu hỏi'; }
function editQuestion(q) {
  editing = q.id; $('content').value = q.content;
  [...'ABCD'].forEach((letter, i) => { $('option-' + letter).value = q.options[i]; });
  document.querySelector(`input[name="correct"][value="${q.correct}"]`).checked = true;
  $('editor-title').textContent = `Chỉnh sửa câu hỏi #${q.id}`; $('save-question').textContent = 'Lưu thay đổi';
  $('content').focus(); $('question-form').scrollIntoView({ behavior: 'smooth', block: 'center' });
}
function confirmAction(title, description, action) { $('delete-title').textContent = title; $('delete-description').textContent = description; confirmedAction = action; $('delete-dialog').showModal(); }
function renderQuestions() {
  $('bank-count').textContent = `${questions.length} câu`;
  const query = $('search').value.toLocaleLowerCase('vi'); $('question-list').replaceChildren();
  const filtered = questions.filter(q => q.content.toLocaleLowerCase('vi').includes(query));
  if (!filtered.length) { const p = document.createElement('p'); p.className = 'empty-state'; p.textContent = 'Chưa có câu hỏi phù hợp.'; $('question-list').append(p); }
  filtered.forEach(q => {
    const item = document.createElement('article'); item.className = 'bank-item';
    const meta = document.createElement('div'); meta.className = 'bank-meta';
    const id = document.createElement('span'); id.textContent = `CÂU #${q.id}`;
    const correct = document.createElement('span'); correct.textContent = `Đáp án đúng: ${q.correct}`; meta.append(id, correct);
    const title = document.createElement('h3'); title.textContent = q.content;
    const actions = document.createElement('div'); actions.className = 'bank-actions';
    actions.append(button('Chỉnh sửa', 'text-button', () => editQuestion(q)), button('Xóa', 'text-button red', () => confirmAction('Xóa câu hỏi này?', 'Câu hỏi sẽ được gỡ khỏi ngân hàng. Các bài đã bắt đầu vẫn giữ nguyên nội dung.', async () => { await api('/api/admin/questions/' + q.id, 'DELETE'); if (editing === q.id) resetEditor(); await loadQuestions(); message('Đã xóa câu hỏi.'); })));
    item.append(meta, title, actions); $('question-list').append(item);
  });
}
async function loadQuestions() { questions = await api('/api/admin/questions'); renderQuestions(); }
async function loadAttempts() {
  const attempts = await api('/api/admin/attempts'); $('attempt-list').replaceChildren();
  const statuses = { active: 'Đang làm', locked: 'Đã khóa', submitted: 'Đã nộp' };
  if (!attempts.length) { const tr = document.createElement('tr'); const td = document.createElement('td'); td.colSpan = 6; td.className = 'empty-state'; td.textContent = 'Chưa có lượt làm bài nào.'; tr.append(td); $('attempt-list').append(tr); }
  attempts.forEach(a => {
    const tr = document.createElement('tr');
    [a.name, `${a.answered}/${a.total}`, `${a.strikes}/3`, statuses[a.status]].forEach((text, index) => { const td = document.createElement('td'); td.textContent = text; if (index === 3) td.className = a.status === 'locked' ? 'red' : 'green'; tr.append(td); });
    const score = document.createElement('td');
    score.textContent = a.status === 'active' ? 'Chưa hoàn thành' : `${a.score}/${a.total} câu đúng`;
    const visibility = document.createElement('small'); visibility.className = 'score-visibility';
    visibility.textContent = a.scoreReleased ? 'Đã cho phép xem' : 'Đang ẩn với người làm bài';
    score.append(visibility); tr.append(score);
    const actions = document.createElement('td');
    const actionGroup = document.createElement('div'); actionGroup.className = 'attempt-actions';
    if (a.status !== 'active' && !a.scoreReleased) {
      const release = button('Cho phép xem điểm', 'button secondary', async () => {
        release.disabled = true;
        try {
          await api('/api/admin/attempts/' + a.id + '/release-score', 'POST', {});
          await loadAttempts();
          message(`Đã cho phép ${a.name} xem điểm. Trang làm bài sẽ tự cập nhật.`);
        } catch (error) { message(error.message, true); }
        finally { release.disabled = false; }
      });
      actionGroup.append(release);
    }
    actionGroup.append(button('Cấp lượt mới', 'text-button', () => confirmAction('Cấp lượt làm bài mới?', `Bài làm cũ của ${a.name} sẽ bị xóa, bao gồm đáp án và cảnh cáo.`, async () => { await api('/api/admin/attempts/' + a.id, 'DELETE'); await loadAttempts(); message('Đã cấp lượt mới. Người làm bài có thể tải lại trang để bắt đầu.'); })));
    actions.append(actionGroup);
    tr.append(actions); $('attempt-list').append(tr);
  });
}
async function dashboard() { await loadQuestions(); await loadAttempts(); $('login-panel').hidden = true; $('dashboard').hidden = false; $('logout').hidden = false; }
$('login-form').onsubmit = async e => {
  e.preventDefault(); const b = e.submitter; b.disabled = true;
  try { await api('/api/admin/login', 'POST', { password: $('password').value }); $('password').value = ''; await dashboard(); message(''); }
  catch (error) { message(error.message, true); } finally { b.disabled = false; }
};
$('logout').onclick = async () => { try { await api('/api/admin/logout', 'POST'); showLogin(); resetEditor(); message('Đã đăng xuất.'); } catch (error) { message(error.message, true); } };
$('question-form').onsubmit = async e => {
  e.preventDefault(); $('save-question').disabled = true;
  try {
    const data = { content: $('content').value.trim(), options: [...'ABCD'].map(l => $('option-' + l).value.trim()), correct: document.querySelector('input[name="correct"]:checked').value };
    await api('/api/admin/questions' + (editing === null ? '' : '/' + editing), editing === null ? 'POST' : 'PUT', data);
    resetEditor(); await loadQuestions(); message('Đã lưu câu hỏi thành công.');
  } catch (error) { message(error.message, true); } finally { $('save-question').disabled = false; }
};
$('cancel-edit').onclick = resetEditor;
$('search').oninput = renderQuestions;
$('refresh-attempts').onclick = async () => { try { await loadAttempts(); message('Đã cập nhật danh sách bài làm.'); } catch (error) { message(error.message, true); } };
$('delete-cancel').onclick = () => $('delete-dialog').close();
$('delete-confirm').onclick = async () => { $('delete-confirm').disabled = true; try { await confirmedAction(); $('delete-dialog').close(); } catch (error) { $('delete-dialog').close(); message(error.message, true); } finally { $('delete-confirm').disabled = false; } };
dashboard().catch(error => { if (error.status !== 401) message(error.message, true); });
