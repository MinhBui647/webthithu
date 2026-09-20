// Event-logic tests, with a minimal DOM. These do not replace visual browser QA.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

async function setup(existingStore, initialState = {}) {
  const elements = new Map(), events = {}, stored = existingStore || new Map(), intervals = [];
  let focused = true, offline = false, requestCount = 0, id = 0;
  let state = { id: 'test-attempt', name: 'Minh Anh', status: 'active', strikes: 0, answers: {}, scoreReleased: false,
    questions: [{ id: 1, content: 'Câu hỏi?', options: ['Một', 'Hai', 'Ba', 'Bốn'] }], ...initialState };
  const received = new Set();
  function element() { return { hidden: false, open: false, children: [], value: '',
    classList: { toggle() {} }, setAttribute() {}, addEventListener() {},
    append(...children) { this.children.push(...children); }, replaceChildren() { this.children = []; },
    showModal() { this.open = true; }, close() { this.open = false; } }; }
  const document = { hidden: false, visibilityState: 'visible', hasFocus: () => focused,
    createElement: element, getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
    addEventListener(type, handler) { events[type] = handler; } };
  const context = vm.createContext({ document, window: { addEventListener(type, handler) { events[type] = handler; } },
    navigator: { sendBeacon() { return !offline; } }, Blob, crypto: { randomUUID: () => `event-uuid-${++id}` },
    localStorage: { getItem: key => stored.get(key) || null, setItem: (key, value) => stored.set(key, value), removeItem: key => stored.delete(key) },
    location: { reload() {} }, setInterval(fn, delay) { intervals.push({ fn, delay }); }, console,
    fetch: async (url, options) => {
      if (offline) throw new Error('Offline');
      if (url.endsWith('/info')) return { ok: true, json: async () => ({ count: 1 }) };
      if (url.endsWith('/violation')) {
        requestCount++;
        const { eventId } = JSON.parse(options.body);
        if (!received.has(eventId) && state.status === 'active') {
          received.add(eventId); state.strikes++;
          if (state.strikes >= 3) { state.status = 'locked'; }
        }
      }
      if (url.endsWith('/answer')) { state.answers[1] = JSON.parse(options.body).answer; }
      return { ok: true, json: async () => structuredClone(state) };
    } });
  vm.runInContext(source, context); await tick();
  return { context, elements, stored, get state() { return state; }, get requests() { return requestCount; },
    offline(value) { offline = value; },
    leave() { focused = false; events.blur(); document.hidden = true; document.visibilityState = 'hidden'; events.visibilitychange(); },
    return() { document.hidden = false; document.visibilityState = 'visible'; events.visibilitychange(); focused = true; events.focus(); },
    pagehide() { events.pagehide(); }, online() { events.online(); },
    async poll() { intervals.filter(i => i.delay === 5000).forEach(i => i.fn()); await tick(); } };
}

test('blur + hidden + pagehide count once; third departure locks the exam', async () => {
  const app = await setup();
  for (let i = 1; i <= 3; i++) {
    app.leave(); app.pagehide(); await tick();
    assert.equal(app.state.strikes, i);
    assert.equal(app.requests, i);
    app.return(); await tick();
    assert.equal(app.elements.get('warning-dialog').open, true);
    assert.match(app.elements.get('warning-title').textContent, new RegExp(`${i}/3`));
    app.elements.get('warning-close').onclick();
  }
  assert.equal(app.state.status, 'locked');
  assert.equal(app.elements.get('exam').hidden, true);
  assert.equal(app.elements.get('result').hidden, false);
  assert.equal(app.elements.get('score-panel').hidden, true);
  assert.equal(app.elements.get('score').textContent, '');
  await vm.runInContext('saveAnswer(1, "A")', app.context);
  assert.deepEqual(app.state.answers, {});
  app.leave(); await tick(); assert.equal(app.requests, 3);
});

test('offline violations disable answers, persist across reload, and retry', async () => {
  const app = await setup(); app.offline(true); app.leave(); await tick(); app.return();
  const options = app.elements.get('options').children;
  assert.equal(options.length, 4);
  assert.ok(options.every(label => label.children[0].disabled));
  assert.equal(JSON.parse(app.stored.get('focus:test-attempt')).pending.length, 1);
  const reloaded = await setup(app.stored);
  assert.equal(reloaded.state.strikes, 1);
  assert.equal(JSON.parse(reloaded.stored.get('focus:test-attempt')).pending.length, 0);
  assert.ok(reloaded.elements.get('options').children.every(label => !label.children[0].disabled));
});

test('only one of four radio choices is saved, and a later choice replaces it', async () => {
  const app = await setup();
  const options = app.elements.get('options').children;
  assert.equal(options.length, 4);
  assert.deepEqual(options.map(o => o.children[0].value), ['A', 'B', 'C', 'D']);
  await vm.runInContext('saveAnswer(1, "B")', app.context);
  await vm.runInContext('saveAnswer(1, "D")', app.context);
  assert.deepEqual(app.state.answers, { 1: 'D' });
});

test('completed scores stay hidden until release, then polling reveals even zero scores', async () => {
  for (const status of ['submitted', 'locked']) {
    const app = await setup(null, { status });
    assert.equal(app.elements.get('score-panel').hidden, true);
    assert.equal(app.elements.get('score').textContent, '');
    assert.equal(app.elements.get('score-waiting').hidden, false);
    assert.match(app.elements.get('score-waiting').textContent, /quản trị viên/);
    app.state.scoreReleased = true;
    app.state.score = 0;
    await app.poll();
    assert.equal(app.elements.get('score-panel').hidden, false);
    assert.equal(app.elements.get('score').textContent, '0 / 1');
    assert.equal(app.elements.get('score-waiting').hidden, true);
    const reloaded = await setup(app.stored, app.state);
    assert.equal(reloaded.elements.get('score').textContent, '0 / 1');
  }
});

test('a score field alone never grants permission to display results', async () => {
  const app = await setup(null, { status: 'submitted', score: 1 });
  assert.equal(app.elements.get('score-panel').hidden, true);
  assert.equal(app.elements.get('score').textContent, '');
});
