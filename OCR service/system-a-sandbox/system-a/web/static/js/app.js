/* Portal front controller: state, wiring, verification streaming. */
'use strict';

const state = {
  page: 1, pageSize: 50, search: '', ordering: '-created',
  doc: null,                 // {id, title, ...} from Paperless
  upload: null,              // {key, name, page_count} from /api/upload
  uploads: [],
  key: null,                 // result key currently shown
  stream: null,              // {abort()}
  boxById: new Map(),
};

/* ------------------------------------------------------------------ toast */
let toastTimer = null;
function toast(msg, isErr) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast' + (isErr ? ' err' : '');
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, isErr ? 9000 : 4500);
}

const $ = id => document.getElementById(id);

/* ------------------------------------------------------------------ catalog */
async function loadDocs() {
  const q = new URLSearchParams({ page: state.page, page_size: state.pageSize, ordering: state.ordering,
                                  search: state.search });
  try {
    const data = await API.get('/api/documents?' + q);
    Panels.renderDocs(data, state.doc && state.doc.id, selectDoc);
  } catch (e) {
    toast('document list failed: ' + e.message, true);
  }
}

function currentKey() {
  return state.upload ? state.upload.key : (state.doc ? 'DMS-' + state.doc.id : null);
}

async function selectDoc(d) {
  state.doc = d; state.upload = null;
  document.querySelectorAll('.doc').forEach(n => n.classList.remove('sel'));
  const li = [...document.querySelectorAll('.doc')].find(n => n.textContent.includes('DMS-' + d.id));
  if (li) li.classList.add('sel');
  $('btn-verify').disabled = false;
  const badge = d.verdict && d.verdict.recommendation;
  $('btn-verify').textContent = badge ? `▶ Re-verify DMS-${d.id}` : `▶ Verify DMS-${d.id}`;

  Viewer.open({ kind: 'dms', id: d.id }, d.page_count || 1, []);
  const meta = await safeGet(`/api/documents/${d.id}/meta`);
  if (meta) Viewer.open({ kind: 'dms', id: d.id }, meta.page_count, meta.pages);
  await openStoredResult('DMS-' + d.id, { quiet: !badge });
}

function selectUpload(u) {
  state.upload = u; state.doc = null;
  document.querySelectorAll('.doc').forEach(n => n.classList.remove('sel'));
  $('btn-verify').disabled = false;
  $('btn-verify').textContent = `▶ Verify ${u.name.slice(0, 18)}`;
  Viewer.open({ kind: 'upload', key: u.key }, u.page_count, (u.pages || []).map(p => ({ page_no: p.page_no, width_pt: p.width_pt, height_pt: p.height_pt })));
  openStoredResult(u.key, { quiet: false });
}

/* ------------------------------------------------------------------ results */
async function openStoredResult(key, { quiet = false } = {}) {
  const result = await safeGet('/api/results/' + encodeURIComponent(key));
  if (!result) {
    Overlay.setLayers([]); Overlay.render([]);
    $('verdict').hidden = true; $('verdict-empty').hidden = false;
    if (!quiet) toast(`no stored result for ${key} yet — press Verify`);
    state.key = null;
    return false;
  }
  const ov = await safeGet('/api/overlays/' + encodeURIComponent(key));
  if (!ov) { toast('could not build the overlay layers for ' + key, true); return false; }
  state.key = key;
  Panels.showResult(key, result, ov);
  Viewer.showPage(1, ov.page_meta || []);
  drawPage();
  toast(`${key}: ${ov.recommendation.value || '–'} · ${ov.exceptions.length} exception boxes · ${(ov.element_count || 0).toLocaleString()} elements`);
  return true;
}

function drawPage() {
  const boxes = Panels.boxesFor(Viewer.page) || [];
  state.boxById = new Map(boxes.map(b => [b.id, b]));
  Overlay.render(boxes);
}

async function safeGet(path) {
  try { return await API.get(path); } catch (e) { return null; }
}

/* ------------------------------------------------------------------ verification */
const STEPS = [
  ['download', 'Fetch the original file from Paperless-ngx'],
  ['perception', 'Perception — VLM read of every page (OCR, layout, boxes)'],
  ['oracle', 'Oracle EBS lookup + rules V-01…V-09'],
  ['assemble', 'Assemble Contract 3.0 result'],
  ['summary', 'Recommendation'],
];

function startProgress() {
  $('progress').hidden = false;
  const ol = $('steps'); ol.innerHTML = '';
  STEPS.forEach(([id, label]) => {
    const li = document.createElement('li'); li.dataset.step = id; li.textContent = label;
    ol.appendChild(li);
  });
  $('engine-log').textContent = '';
}

function markActive(id) {
  const li = [...document.querySelectorAll('#steps li')];
  const target = li.find(l => l.dataset.step === id) || (id === 'perception_cached' ? li.find(l => l.dataset.step === 'perception') : null);
  if (!target) return;
  if (id === 'perception_cached') target.textContent = 'Perception — served from the local cache';
  li.forEach(l => { if (l !== target && l.classList.contains('active')) { l.classList.remove('active'); l.classList.add('done'); } });
  target.classList.add('active');
}

function logLine(line, level, hint) {
  const pre = $('engine-log');
  const span = document.createElement('span');
  span.textContent = line + '\n';
  if (level && level !== 'info') {
    span.className = 'lv-' + level;
    if (hint) span.title = hint;          // why this line is not a failure
  }
  pre.appendChild(span);
  pre.scrollTop = pre.scrollHeight;
}

function runVerify() {
  const key = currentKey();
  if (!key) { toast('select a document first', true); return; }
  const mode = $('mode').value, quick = $('quick').checked;
  const path = state.upload
    ? `/api/verify/upload?key=${encodeURIComponent(key)}&mode=${mode}&quick=${quick}`
    : `/api/verify/${state.doc.id}?mode=${mode}&quick=${quick}`;
  startProgress();
  $('btn-verify').disabled = true; $('btn-cancel').disabled = false;
  toast(`verifying ${key} in ${mode} mode — a production run can take several minutes`);
  let gotResult = false;

  state.stream = API.stream(path, (type, ev) => {
    if (type === 'step' || ev.type === 'step') markActive(ev.step || '');
    else if (ev.type === 'log') logLine(ev.line, ev.level, ev.hint);
    else if (type === 'result' || ev.type === 'result') {
      gotResult = true;
      finishProgress(true, ev.elapsed_s);
      Promise.all([Promise.resolve(ev.result), API.get('/api/overlays/' + encodeURIComponent(key))])
        .then(([result, ov]) => {
          Panels.showResult(key, result, ov);
          state.key = key;
          Viewer.showPage(1, ov.page_meta || []).then(drawPage);
          loadDocs();
          toast(`${key}: ${ov.recommendation.value || '–'} · ${(ov.exceptions || []).length} exceptions · ` +
                `AUTO_PASS ${ov.recommendation.value === 'AUTO_PASS' ? 'yes' : 'no'} · ${(ov.element_count || 0).toLocaleString()} boxes`);
        })
        .catch(e => toast('result arrived but could not be rendered: ' + e.message, true));
    } else if (ev.type === 'done') {
      finishProgress(!!ev.ok, ev.elapsed_s);
      if (!ev.ok) toast('engine failed: ' + (ev.error || 'see the engine log'), true);
      else if (!gotResult) openStoredResult(key, { quiet: true });
    } else if (ev.type === 'error') {
      toast(ev.message || 'engine error', true);
    }
  });
  state.stream.promise.then(() => {
    $('btn-verify').disabled = false; $('btn-cancel').disabled = true; state.stream = null;
  }).catch(e => {
    finishProgress(false); toast('stream error: ' + e.message, true);
    $('btn-verify').disabled = false; $('btn-cancel').disabled = true; state.stream = null;
  });
}

function finishProgress(ok, secs) {
  $('progress').hidden = true;
  $('btn-verify').disabled = false; $('btn-cancel').disabled = true;
  document.querySelectorAll('#steps li').forEach(l => l.classList.toggle('done', ok));
  if (secs) toast(`engine finished in ${secs}s`);
}

async function cancelRun() {
  const key = currentKey();
  if (state.stream) state.stream.abort();
  try { await API.post(`/api/runs/${encodeURIComponent(key)}/cancel`); toast('cancelled the engine process for ' + key); }
  catch (e) { toast('nothing to cancel: ' + e.message, true); }
  finishProgress(false);
}

/* ------------------------------------------------------------------ health */
async function checkHealth(deep) {
  const h = await safeGet('/api/health' + (deep ? '?deep=true' : ''));
  const pill = $('health');
  if (!h) { pill.textContent = 'portal unreachable'; pill.className = 'pill bad'; return; }
  const p = h.paperless || {}, l = h.litellm || {}, o = h.oracle || {};
  const parts = [['dms', p.ok !== false && p.configured !== false], ['llm', l.ok !== false && l.configured !== false],
                 ['erp', o.configured !== false ? (o.ok === undefined ? null : o.ok) : false]];
  pill.textContent = parts.map(([n, v]) => `${n}${v === null ? '?' : v ? '✓' : '✗'}`).join(' ');
  pill.className = 'pill ' + (parts.every(x => x[1] !== false) ? 'ok' : 'bad');
  pill.title = `paperless: ${JSON.stringify(p)}\nlitellm: ${JSON.stringify(l)}\noracle: ${JSON.stringify(o)}`;
}

async function pollRuns() {
  const r = await safeGet('/api/runs');
  if (!r) { $('runs').textContent = 'engine idle (portal unreachable)'; return; }
  const active = (r.active || []);
  $('runs').textContent = active.length
    ? `running: ${active.map(k => `${k}${r.sandbox ? ' [sandbox]' : ''}`).join(', ')}`
    : `engine idle · ${r.sandbox ? 'SANDBOX (no real AI/ERP)' : 'production (live AI + ERP)'} · ${r.sandbox ? 'sandbox' : 'prod'}`;
  if (!active.length) $('btn-cancel').disabled = true;
}

/* ------------------------------------------------------------------ wiring */
function boot() {
  Overlay.init();
  Overlay.onBoxClick((box, ev) => {
    const n = Linker.handleBox(box);
    const m = box.meta || {};
    const tip = $('bbox-tooltip');
    tip.hidden = false;
    tip.textContent = [`${box.layer} · ${m.kind || ''} ${box.element_id || ''}`.trim(),
                       m.code ? `${m.code} (${m.severity}) rule ${m.rule}` : '',
                       m.raw != null ? `raw: ${String(m.raw).slice(0, 120)}` : '',
                       m.actual != null ? `actual: ${String(m.actual).slice(0, 80)}` : '',
                       m.expected != null ? `expected: ${String(m.expected).slice(0, 80)}` : '',
                       m.conf != null ? `confidence ${Math.round(m.conf * 100)}%` : '',
                       n ? `→ ${n} linked row${n > 1 ? 's' : ''} selected` : '→ no panel row claims this box']
      .filter(Boolean).join('\n');
    tip.style.left = Math.min(window.innerWidth - 400, ev.clientX + 14) + 'px';
    tip.style.top = (ev.clientY + 12) + 'px';
    setTimeout(() => { tip.hidden = true; }, 4200);
  });

  Viewer.onLayout(() => { if (state.key || Panels.overlays) drawPage(); });

  $('btn-verify').addEventListener('click', runVerify);
  $('btn-cancel').addEventListener('click', cancelRun);
  $('btn-search').addEventListener('click', () => { state.search = $('search').value.trim(); state.page = 1; loadDocs(); });
  $('search').addEventListener('keydown', ev => { if (ev.key === 'Enter') { state.search = ev.target.value.trim(); state.page = 1; loadDocs(); } });
  $('btn-reload').addEventListener('click', () => { loadDocs(); checkHealth(true); });
  $('btn-prev').addEventListener('click', () => { if (state.page > 1) { state.page--; loadDocs(); } });
  $('btn-next').addEventListener('click', () => { state.page++; loadDocs(); });
  $('btn-page-prev').addEventListener('click', () => Viewer.prev());
  $('btn-page-next').addEventListener('click', () => Viewer.next());
  $('btn-zoom-in').addEventListener('click', () => Viewer.zoomBy(1.25));
  $('btn-zoom-out').addEventListener('click', () => Viewer.zoomBy(0.8));
  $('btn-zoom-fit').addEventListener('click', () => Viewer.fit());
  document.querySelectorAll('#rendermode button').forEach(b => b.addEventListener('click', () => Viewer.setMode(b.dataset.mode)));
  $('tabs').addEventListener('click', ev => {
    const b = ev.target.closest('.tab'); if (!b) return;
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t === b));
    document.querySelectorAll('.tabpane').forEach(p => p.classList.toggle('active', p.id === 'tab-' + b.dataset.tab));
  });
  $('stage').addEventListener('click', ev => { if (!ev.target.closest('.bbox')) { Linker.clear(); $('bbox-tooltip').hidden = true; } });
  $('file').addEventListener('change', async ev => {
    const f = ev.target.files && ev.target.files[0]; if (!f) return;
    toast(`uploading ${f.name}…`);
    try {
      const up = await API.upload(f);
      state.uploads.push(up);
      Panels.renderUploads(state.uploads, selectUpload);
      selectUpload(up);
      toast(`staged ${up.name} (${up.page_count} pages)`);
    } catch (e) { toast('upload failed: ' + e.message, true); }
    ev.target.value = '';
  });
  document.addEventListener('keydown', ev => {
    if (ev.target.matches('input, select, textarea')) return;
    if (ev.key === 'ArrowLeft') Viewer.prev();
    else if (ev.key === 'ArrowRight') Viewer.next();
    else if (ev.key === 'Escape') Linker.clear();
  });

  checkHealth(false);
  pollRuns();
  setInterval(pollRuns, 4000);
  loadDocs();
}

window.addEventListener('DOMContentLoaded', boot);
