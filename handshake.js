const panel = document.querySelector('[data-handshake]');
const handOutline = new Path2D(
  'M5 52 H30 C40 52 47 48 55 42 L73 24 Q79 18 85 23 Q90 28 85 34 L76 45 ' +
  'L133 32 Q141 31 142 37 Q143 42 137 44 L111 50 L149 44 Q156 44 156 50 ' +
  'Q156 55 150 56 L113 62 L143 58 Q150 58 150 64 Q150 69 144 70 ' +
  'L108 74 L130 73 Q137 73 137 79 Q137 84 130 85 L78 90 ' +
  'Q61 92 49 84 Q42 80 30 80 H5 Z'
);

for (const canvas of panel.querySelectorAll('canvas')) {
  const context = canvas.getContext('2d');
  if (!context) continue;
  const palette = getComputedStyle(canvas);
  context.scale(2, 2);
  context.lineWidth = 1.25;
  context.lineJoin = 'round';
  context.fillStyle = '#102a39';
  context.strokeStyle = palette.getPropertyValue('--sky').trim();
  context.fill(handOutline);
  context.stroke(handOutline);
}

const mode = panel.dataset.mode;
const participant = panel.querySelector('[data-participant]');
const statusText = panel.querySelector('#handshake-status');
const notice = panel.querySelector('[data-notice]');
const result = panel.querySelector('[data-result]');
const resultLink = panel.querySelector('[data-result-link]');
const sendButton = panel.querySelector('[data-send]');
const queue = document.querySelector('[data-queue]');
const emptyQueue = document.querySelector('[data-empty]');
const duration = Number(panel.dataset.animationMs);
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');

let state = null;
let start = null;
let noticeKey = null;
let phaseTimer;
let posting = false;
let signedOut = false;
let pollVersion = 0;
const queueButtons = new Map();

panel.style.setProperty('--handshake-duration', `${duration}ms`);

function setText(element, text) {
  if (element.textContent !== text) element.textContent = text;
}

function renderQueue(pending, copy, disabled) {
  for (const {id, guest_name: guestName} of pending) {
    if (!queueButtons.has(id)) {
      const item = document.createElement('li');
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'contact btn btn-outline-info';
      button.addEventListener('click', () => update(`/handshake/api/${id}/accept`));
      item.append(button);
      queue.append(item);
      queueButtons.set(id, button);
    }
    const button = queueButtons.get(id);
    setText(button, copy.acceptHighFive.replace('{name}', () => guestName || copy.visitor));
    button.disabled = disabled;
  }
  const visible = new Set(pending.map(({id}) => id));
  for (const [id, button] of queueButtons) {
    if (!visible.has(id)) {
      button.parentElement.remove();
      queueButtons.delete(id);
    }
  }
  emptyQueue.hidden = pending.length > 0;
}

function render() {
  clearTimeout(phaseTimer);
  const copy = translations[document.documentElement.lang] || translations.en;
  const current = state?.current;
  const untilStart = start === null ? null : start - performance.now();
  const active = untilStart !== null && untilStart + duration > 0;
  const guestName = current?.guest_name || panel.dataset.name;
  let phase = 'idle';
  let label = mode === 'guest' && state ? copy.ready : '';

  if (current && untilStart === null) {
    phase = 'waiting';
    label = copy.waiting;
  } else if (untilStart > 0) {
    phase = 'starting';
    label = copy.starting;
    phaseTimer = setTimeout(render, untilStart);
  } else if (active && !reducedMotion.matches) {
    phase = 'connecting';
    label = copy.starting;
    if (panel.dataset.phase !== phase) panel.style.setProperty('--handshake-offset', `${untilStart}ms`);
    phaseTimer = setTimeout(render, untilStart + duration);
  } else if (start !== null) {
    phase = 'completed';
    label = copy.completed;
    if (active) phaseTimer = setTimeout(render, untilStart + duration);
  }

  panel.dataset.phase = phase;
  setText(participant, mode === 'owner' && !current ? copy.visitor : guestName || copy.visitor);
  setText(statusText, label);
  setText(notice, noticeKey ? copy[noticeKey] : '');
  notice.hidden = !noticeKey;

  const completed = phase === 'completed';
  if (completed) setText(result, `${copy.ownerName} × ${guestName || copy.visitor}`);
  result.hidden = !completed;
  resultLink.hidden = !completed;
  if (sendButton) {
    sendButton.disabled = !state || signedOut || posting || active || phase === 'waiting';
    sendButton.dataset.i18n = completed ? 'sendAgain' : 'sendHighFive';
    setText(sendButton, copy[sendButton.dataset.i18n]);
  }
  if (queue && state) renderQueue(state.pending, copy, signedOut || posting || active);
}

async function update(path, method = 'POST') {
  if (signedOut || posting) return;
  if (method === 'POST') {
    posting = true;
    pollVersion += 1;
    render();
  }
  const version = pollVersion;
  const sent = performance.now();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 6000);
  try {
    const response = await fetch(path, {
      method, headers: {'X-CSRF-Token': panel.dataset.csrf}, signal: controller.signal,
    });
    const received = performance.now();
    const data = await response.json();
    if (version !== pollVersion) return;
    if (!response.ok) {
      signedOut = response.status === 401 || data.error === 'signInRequired';
      noticeKey = data.error || 'connectionLost';
      return;
    }

    const previous = state?.current;
    const current = data.current;
    if (!current?.starts_at) {
      start = null;
    } else if (previous?.id !== current.id || previous.starts_at !== current.starts_at) {
      start = (sent + received) / 2 + current.starts_at - data.server_now;
    }
    state = data;
    noticeKey = null;
  } catch {
    if (version === pollVersion) noticeKey = 'connectionLost';
  } finally {
    clearTimeout(timeout);
    if (method === 'POST') posting = false;
    if (version === pollVersion) render();
  }
}

async function poll() {
  await update('/handshake/api/status', 'GET');
  if (!signedOut) setTimeout(poll, 1000);
}

document.addEventListener('site-language-change', render);
document.addEventListener('visibilitychange', render);
reducedMotion.addEventListener('change', render);
sendButton?.addEventListener('click', () => update('/handshake/api/request'));
render();
if (mode !== 'inactive') poll();
