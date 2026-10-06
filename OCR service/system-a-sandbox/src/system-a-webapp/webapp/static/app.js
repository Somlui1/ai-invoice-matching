/* AIVA System A - test portal.

   ซ้าย  = รายการเอกสารจากแหล่งข้อมูล (Paperless หรือ batch report)
   กลาง = หน้าเอกสารจริง + กรอบ bounding box ที่ System A อ่านได้ + ปุ่ม Process
   ขวา  = Final Result / ผล OCR / Verify Result ของเอกสารที่เปิดอยู่เท่านั้น

   ผลที่ประมวลแล้วเก็บใน browser นี้เท่านั้น (localStorage) - restart server แล้วก็ไม่เหลือ case ค้าง
*/
const $ = id => document.getElementById(id), esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
let DOCS = [], list = [], cur = 0, COLORS = {}, META = {}, qIds = null, note = '';
const RES = {};                 // id -> state of that document (one entry per document, never shared)
const POLL = {};                // id -> poll timer of a running document
const INV_RC = { pass: 'ok', fail: 'error', manual_review: 'partial', not_evaluated: 'idle' };

// --------------------------------------------------------------------------- cases live in this browser
const CASE_KEY = 'aiva.sysA.cases.v1', CASE_MAX = 12;
let CASES = {};
function loadCases() { try { CASES = JSON.parse(localStorage.getItem(CASE_KEY) || '{}') || {} } catch (e) { CASES = {} } }
function writeCases() {                         // the quota is per origin: drop the oldest cases until it fits
  for (let n = 0; n <= CASE_MAX; n++) {
    try { localStorage.setItem(CASE_KEY, JSON.stringify(CASES)); return true }
    catch (e) {
      const old = Object.keys(CASES).sort((a, b) => (CASES[a].at || 0) - (CASES[b].at || 0));
      if (!old.length) { CASES = {}; return false }
      delete CASES[old[0]];
    }
  }
  return false;
}
function saveCase(id, view) {
  CASES[id] = { at: Date.now(), run: view.run, cls: view.cls, rec: view.recommendation, view };
  Object.keys(CASES).sort((a, b) => (CASES[b].at || 0) - (CASES[a].at || 0)).slice(CASE_MAX).forEach(k => delete CASES[k]);
  if (!writeCases()) note = 'เก็บ case ไม่ไหว: พื้นที่ browser เต็ม';
}
function dropCase(id) { delete CASES[id]; writeCases() }

// --------------------------------------------------------------------------- API
const api = {
  async j(url, opt) {
    const r = await fetch(url, opt); let b = null; try { b = await r.json() } catch (e) { }
    if (!r.ok) throw Object.assign(new Error((b && b.detail) || ('HTTP ' + r.status)), { status: r.status }); return b
  },
  meta: () => api.j('/api/meta'),
  documents: () => api.j('/api/documents'),
  status: id => api.j('/api/documents/' + id),
  refresh: () => api.j('/api/documents/refresh', { method: 'POST' }),
  process: id => api.j('/api/documents/' + id + '/process', { method: 'POST' }),
  result: id => api.j('/api/documents/' + id + '/result'),
  forget: id => api.j('/api/documents/' + id + '/result', { method: 'DELETE' }),
  search: q => api.j('/api/search?q=' + encodeURIComponent(q)),
  img: (id, p) => '/api/documents/' + id + '/pages/' + p + '/image',
  pdf: id => '/api/documents/' + id + '/pdf'
};
const stOf = id => RES[id] || (RES[id] = { id: id, state: 'idle', run: 0, step: null, cls: null, rec: null, error: null,
  seconds: null, types: [], kept: 0, dropped: 0, started: 0, view: null, from: null, src_err: null });
const hasView = r => !!(r.view && (r.state === 'done' || r.state === 'cached'));
const isBusy = r => r.state === 'processing';
const rcls = r => isBusy(r) ? 'partial' : r.state === 'error' ? 'error' : hasView(r) ? (r.cls || 'ok') : 'idle';

function applyServer(m) {                       // one row of /api/documents -> the local state of that document
  const r = stOf(m.id);
  Object.assign(r, { state: m.state, run: m.run, step: m.step, cls: m.cls, rec: m.recommendation, error: m.error,
    types: m.types || [], kept: m.kept || 0, dropped: m.dropped || 0 });
  if (m.seconds != null) r.seconds = m.seconds;
  if (m.src_err != null) r.src_err = m.src_err;
  if (isBusy(r)) { r.started = performance.now() - (m.elapsed || 0) * 1000; r.view = null; r.from = null }
  else if (m.state === 'done') { if (r.from === 'server' && r.view && r.view.run !== m.run) { r.view = null; r.from = null } }
  else if (r.from === 'server') { r.view = null; r.from = null }   // a case held by this browser survives an idle server
  return r;
}
function useCase(id, c) {                       // a case that only exists in localStorage
  const r = stOf(id), v = c.view || {};
  r.view = v; r.from = 'browser'; r.cls = c.cls; r.rec = c.rec; r.run = c.run || v.run || 0;
  r.types = v.types || []; r.kept = v.kept || 0; r.dropped = v.dropped || 0; r.seconds = v.seconds;
  if (r.state !== 'done') r.state = 'cached';
  return r;
}
function hydrate() {
  for (const m of DOCS) { const r = applyServer(m);
    if (!hasView(r)) { const c = CASES[m.id]; if (c) useCase(m.id, c) } }
}

// --------------------------------------------------------------------------- list header / stats
function syncTypes() {
  const have = new Set([...$('ft').options].map(o => o.value)), add = new Set();
  for (const m of DOCS) { const r = stOf(m.id); if (hasView(r)) (r.types || []).forEach(t => { if (!have.has(t)) add.add(t) }) }
  add.forEach(t => $('ft').add(new Option(t, t)));
}
function updStat() {
  syncTypes();
  let done = 0, run = 0, box = 0, drop = 0, cached = 0; const c = {};
  for (const m of DOCS) { const r = stOf(m.id);
    if (isBusy(r)) run++;
    if (hasView(r)) { done++; c[r.cls] = (c[r.cls] || 0) + 1; box += r.kept || 0; drop += r.dropped || 0; if (r.from === 'browser') cached++ } }
  $('stat').innerHTML = `${DOCS.length} ฉบับ · ${DOCS.reduce((a, d) => a + (d.pages_total || 0), 0)} หน้า`
    + ` · ประมวลแล้ว ${done}${cached ? ` <span class=case>(ใน browser ${cached})</span>` : ''}`
    + `${run ? ` · <span class=partial>กำลังประมวล ${run}</span>` : ''} · ${box} กรอบ (ตัดทิ้ง ${drop})`
    + ` · <span class=ok>ok ${c.ok || 0}</span> <span class=partial>partial ${c.partial || 0}</span> <span class=error>error ${c.error || 0}</span>`;
  const S = META.source || {};
  $('src').innerHTML = (S.kind === 'paperless'
    ? `Paperless <b>${esc(String(S.base_url || '').replace(/^https?:\/\//, ''))}</b> · DMS มี ${S.dms_total ?? '?'} ฉบับ · แสดง ${S.documents} ฉบับ`
    : `batch <b>${esc(String(S.report || '').split(/[\\/]/).slice(-2).join('/'))}</b> · ${S.documents} ฉบับ`)
    + ` · ${esc(META.perception)}/${esc(META.engine)} · <b>${META.persist ? 'ผลเก็บที่ server' : 'ผลเก็บใน browser เท่านั้น'}</b>`;
}

// --------------------------------------------------------------------------- ขวา: Final Result / ผล OCR / Verify
function resultHtml(id) {
  const r = stOf(id), v = r.view, F = v.final;
  const refAttr = rf => (rf && rf.i != null) ? ` data-d="${v.id}" data-ref="${rf.page}:${rf.i}"` : '';
  const cell = x => x == null ? '<span class=error>—</span>' : (x.ok ? esc(x.value ?? x.raw) : `<span class=error>${esc(x.raw ?? '—')}</span>`);
  const f = F.fields.map(x => `<tr${refAttr(x.ref)}><td>${esc(x.name)}</td><td>${x.value == null && x.raw == null
    ? `<span class=error>— ${esc(x.null_reason || '')}</span>`
    : (x.ok ? esc(x.value ?? x.raw) : `<span class=error>${esc(x.raw ?? '')}</span> <span class=idle>(ใช้ไม่ได้${x.null_reason ? ' · ' + esc(x.null_reason) : ''})</span>`)}</td></tr>`).join('');
  const sg = Object.entries(F.signatures).map(([k, s]) => `<tr${refAttr(s.ref)}><td>signature · ${esc(k)}</td><td>${s.present === true ? 'พบ' : s.present === false ? 'ไม่พบ' : 'ไม่แน่ใจ'}${s.kind ? ' · ' + esc(s.kind) : ''}</td></tr>`).join('');
  const ln = F.lines.length ? `<table class=rt><tr><th>line</th><th>description</th><th>qty</th><th>uom</th><th>unit_price</th><th>amount</th></tr>${F.lines.map(l =>
    `<tr${refAttr(l.ref)}><td>${l.line_no}${l.uom_group ? ' · ' + esc(l.uom_group) : ''}</td><td>${cell(l.cells.description)}</td><td>${cell(l.cells.qty)}</td><td>${cell(l.cells.uom)}</td><td>${cell(l.cells.unit_price)}</td><td>${cell(l.cells.amount)}</td></tr>`).join('')}</table>` : '';
  const vr = v.verify.map(x => {
    const ev = x.evidence.map(e => `${e.code ? esc(e.code) + ' ' : ''}${e.severity ? '· ' + esc(e.severity) + ' ' : ''}${esc(e.message || '')}`
      + ((e.actual != null || e.expected != null) ? ` <span class=idle>[${esc(e.actual ?? '')} ≠ ${esc(e.expected ?? '')}]</span>` : '')
      + (e.refs && e.refs.length ? ` <span class=idle>กล่อง ${e.refs.map(z => z.page + ':' + z.i).join(', ')}</span>` : '')).join('<br>');
    return `<tr${refAttr(x.ref)}><td>${esc(x.rule_id)} ${esc(x.name)}</td><td><span class=${INV_RC[x.result] || 'idle'}>${esc(x.result)}${x.code ? ' ' + esc(x.code) : ''}</span></td>`
      + `<td>${esc(x.detail)}${x.halted_by ? ` <span class=idle>[halted_by ${esc(x.halted_by)}]</span>` : ''}${ev ? '<br>' + ev : ''}</td></tr>`}).join('');
  const o = v.oracle ? ` · Oracle: ${esc(v.oracle.lookup_path || 'ไม่พบ')}${v.oracle.receipt_nums.length ? ' · ใบรับ ' + esc(v.oracle.receipt_nums.join(', ')) : ''}${v.oracle.matched_on_column ? ' · ' + esc(v.oracle.matched_on_column) : ''}` : '';
  return `<div class=sec><b>Final Result</b> · <span class=${v.cls}>${esc(v.recommendation)}</span>`
    + `${v.exception_codes.length ? ' · ' + esc(v.exception_codes.join(', ')) : ''} · run ${v.run} · ${v.seconds}s · ${esc(v.perception)}/${esc(v.engine)}${o}</div>
    <table class=rt><tr><th>field</th><th>value</th></tr>${f}${sg}</table>${ln}
    <div class=sec><a href="/api/documents/${id}/payload" target=_blank>payload JSON</a> · <a href="/api/documents/${id}/extraction" target=_blank>extraction JSON</a>
      · ${esc(v.versions.standard || '')} ${esc(v.versions.ruleset || '')}`
    + `${v.replay ? ` · <span class=idle>replay: OCR ชุดเดียว${v.replay.assume_agreement ? ' (ถือว่า agree)' : ''}</span>` : ''}`
    + `${r.from === 'browser' ? ' · <span class=case>case ที่เปิดจาก browser</span>' : ''}</div>
    <div class=sec><b>Verify Result</b></div>
    <table class=rt><tr><th>rule</th><th>result</th><th>detail</th></tr>${vr}</table>
    ${v.system_errors.length ? `<div class=error>✗ ${esc(v.system_errors.map(e => (e.code || '') + ' ' + (e.detail || '')).join(' | '))}</div>` : ''}`;
}
function ocrHtml(id) {
  const v = stOf(id).view, showDrop = $('dp').checked;
  return v.pages.map(p => {
    const rows = p.kept.map((i, ix) => `<tr data-i=${ix} data-d=${v.id} data-p=${p.page}><td><span class=sw style="background:${COLORS[i.type] || COLORS.other}"></span>${esc(i.type)}</td>`
      + `<td>${esc(i.label)}</td><td>${esc(i.text)}</td><td>${i.confidence != null ? i.confidence : ''}</td></tr>`).join('');
    const drops = showDrop ? p.dropped.map(i => `<tr class=dr><td>${esc(i.type)}</td><td>${esc(i.label)}</td><td>${esc(i.text)} <span class=idle>[${esc(i.drop_reason)}]</span></td></tr>`).join('') : '';
    return `<div class=ocrsec><div class=ocrh>หน้า ${p.page} · ${esc(p.doc_type)} · ${p.kept.length} กรอบ · ตัดทิ้ง ${p.dropped.length}`
      + ` · coord=${esc(p.coord)}${p.seconds != null ? ' · ' + p.seconds + 's' : ''}</div>`
      + `${p.error ? `<div class=err>⚠ ${esc(p.error)}</div>` : ''}
      <table><tr><th>type</th><th>label</th><th>text</th><th>conf</th></tr>${rows || '<tr><td colspan=4><span class=ph>ไม่มีรายการที่เก็บไว้บนหน้านี้</span></td></tr>'}${drops}</table></div>`;
  }).join('');
}
function panelHtml(m) {
  const r = stOf(m.id);
  if (isBusy(r)) return `<div class=ph><span class=partial>กำลังประมวลผล… <span class=el data-d=${m.id}>0.0</span>s</span><br>`
    + `${esc(r.step === 'validate' ? 'System A กำลังตรวจกติกา' : r.step === 'view' ? 'กำลังสรุปผล' : 'VLM กำลังอ่านหน้าเอกสารจริงจาก Paperless')}
    ${r.src_err ? `<div class=err>${esc(r.src_err)}</div>` : ''}</div>`;
  if (r.state === 'error') return `<div class=ph><span class=error>✗ ${esc(r.error || 'ประมวลผลไม่สำเร็จ')}</span><br>กด Process อีกครั้ง</div>`;
  if (!hasView(r)) return `<div class=ph>ยังไม่ได้ประมวลผลเอกสารนี้ — กด <b>Process</b><br><br>`
    + `ระบบจะอ่านไฟล์ของเอกสารจากแหล่งข้อมูลด้วยโค้ดของ System A เอง: VisionPipeline → normalize → engine → กติกา V-01..V-09</div>`;
  return resultHtml(m.id) + `<div class=sec><b>ผล OCR</b> <span class=idle>(${r.view.kept} รายการที่เก็บไว้ · ชี้แถวเพื่อดูกรอบบนเอกสาร)</span></div>` + ocrHtml(m.id);
}

// --------------------------------------------------------------------------- กลาง: หน้าเอกสาร + กรอบ bbox
function pagesHtml(m) {
  const r = stOf(m.id), v = hasView(r) ? r.view : null;
  const pageNos = v ? v.pages.map(p => p.page) : ((m.pages && m.pages.length) ? m.pages : [1]);
  return pageNos.map(pn => {
    const p = v ? v.pages.find(z => z.page === pn) : null;
    const ar = p && p.size_px ? `aspect-ratio:${p.size_px[0]}/${p.size_px[1]}` : '';
    const img = `<img loading=lazy src="${api.img(m.id, pn)}">`;
    if (!p) {
      const msg = isBusy(r) ? `<span class=partial>กำลังประมวลผล… <span class=el data-d=${m.id}>${((performance.now() - r.started) / 1000).toFixed(1)}</span>s</span>`
        : r.state === 'error' ? `<span class=error>✗ ${esc(r.error || 'ไม่สำเร็จ')} — กด Process ใหม่</span>`
          : hasView(r) ? 'หน้านี้ไม่มีอยู่ในผลที่เก็บไว้' : 'ยังไม่ได้ประมวลผล — ยังไม่มีกรอบของ System A';
      return `<div class=pg data-d=${m.id} data-p=${pn}><div class=cap><b>หน้า ${pn}</b> · ${msg}</div><div class=imgbox>${img}</div></div>`;
    }
    const boxes = p.kept.map((i, ix) => {
      if (!i.bbox_norm) return '';
      const b = i.bbox_norm;
      return `<div class=bx data-i=${ix} data-d=${m.id} data-p=${p.page} data-t="${esc(i.type || 'other')}"`
        + ` style="left:${b[0] * 100}%;top:${b[1] * 100}%;width:${b[2] * 100}%;height:${b[3] * 100}%;border-color:${COLORS[i.type] || COLORS.other}"></div>`}).join('');
    return `<div class=pg data-d=${m.id} data-p=${p.page}><div class=cap><b>หน้า ${p.page}</b> · ${esc(p.doc_type)} · ${p.kept.length} กรอบ`
      + ` · ตัดทิ้ง ${p.dropped.length} · coord=${esc(p.coord)}${p.seconds != null ? ' · ' + p.seconds + 's' : ''}`
      + `${p.error ? ` · <span class=error>⚠ ${esc(p.error)}</span>` : ''}</div><div class=imgbox style="${ar}">${img}${boxes}</div></div>`;
  }).join('');
}
function docHtml(m) {
  const r = stOf(m.id), done = hasView(r);
  const status = isBusy(r) ? 'กำลังประมวลผล' : r.state === 'error' ? 'error' : done ? `${esc(r.cls || '')} ${esc(r.rec || '')}` : 'รอ Process';
  const pageNos = done ? r.view.pages.length : (m.pages_total || '?');
  return `<div class=wb id="d${m.id}">
    <div class=wbh><span class=wbt title="${esc(m.title)}">#${m.id} · ${esc(m.title)}</span>
      <button class="run pill" data-id=${m.id} ${isBusy(r) ? 'disabled' : ''}>${isBusy(r) ? 'Processing…' : done ? 'Process ใหม่' : 'Process'}</button>
      <span class="pill ${rcls(r)}">${status}</span>
      ${done ? `<span class=case title="ผลรอบนี้เก็บไว้ใน browser นี้เท่านั้น (localStorage)">▣ case ใน browser${r.from === 'server' ? ' + server' : ''} · run ${r.run}</span>` : ''}
      <span class=src>${pageNos}/${m.pages_total || '?'} หน้า · ${esc(m.file_class || m.mime || '')}${m.created ? ' · ' + esc(m.created) : ''}`
      + ` · <a href="${api.pdf(m.id)}" target=_blank>เปิด PDF</a>`
      + `${m.viewer_url ? ` · <a href="${m.viewer_url}" target=_blank>เปิดใน DMS</a>` : ''}`
      + `${done ? ' · <span class=case data-forget=' + m.id + ' title="ลบผลของเอกสารนี้ทิ้ง (ทั้งใน browser และ server)">ลืม case นี้</span>' : ''}</span></div>
    ${r.src_err ? `<div class=err>${esc(r.src_err)}</div>` : ''}
    <div class=wbm><div class=pages>${pagesHtml(m)}</div><div class=panel>${panelHtml(m)}</div></div></div>`;
}
const rowHtml = (m, i) => {
  const r = stOf(m.id), done = hasView(r);
  return `<div data-i=${i} data-id=${m.id} title="${esc(m.title)}${m.created ? ' · ' + esc(m.created) : ''}${m.correspondent ? ' · ' + esc(m.correspondent) : ''}">`
    + `<span class=${rcls(r)}>${done ? '●' : r.state === 'processing' ? '◐' : r.state === 'error' ? '✗' : '○'}</span> #${m.id}`
    + `${done && r.types && r.types[0] ? ' ' + esc(r.types[0]) : ''} · ${esc(m.title)}</div>`;
};

// --------------------------------------------------------------------------- วาดรายการ + เอกสารที่เปิดอยู่
function apply() {
  const ft = $('ft').value, fs = $('fs').value, q = $('q').value.trim().toLowerCase();
  list = DOCS.filter(m => {
    const r = stOf(m.id), done = hasView(r);
    return (!ft || (done && (r.types || []).includes(ft))) && (!fs || (done && r.cls === fs))
      && (!q || String(m.id) === q || String(m.title || '').toLowerCase().includes(q) || (qIds && qIds.has(m.id)))
  });
  cur = Math.max(0, Math.min(cur, Math.max(0, list.length - 1)));
  $('side').innerHTML = list.map(rowHtml).join('');
  render();
}
function render() {
  unpin();
  $('main').innerHTML = list.length ? docHtml(list[cur]) : '<div class=ph>ไม่มีเอกสารตามเงื่อนไข</div>';
  [...$('side').children].forEach((el, i) => el.classList.toggle('cur', i === cur));
  if (list[cur]) ensureView(list[cur].id);
  syncRun(); updStat();
}
const loading = new Set();
async function ensureView(id) {                  // ผลของรอบที่ server ประมวลไว้ ยังไม่เคยเปิดในรอบนี้
  const r = stOf(id);
  if (r.state !== 'done' || r.view || loading.has(id)) return;
  loading.add(id);
  try {
    const v = await api.result(id);
    if (stOf(id).state === 'done' && stOf(id).run === v.run) { r.view = v; r.from = 'server'; r.types = v.types; refresh(id) }
  } catch (e) {
    if (e.status === 409 && CASES[id]) { useCase(id, CASES[id]); refresh(id) }   // server ลืมไปแล้ว: เปิด case จาก browser
    else r.error = 'โหลดผลไม่ได้: ' + e.message;
  } finally { loading.delete(id) }
}
function refresh(id) {                           // วาดใหม่เฉพาะเอกสารนี้ - เอกสารอื่นไม่ถูกแตะ
  if (pinned && String(pinned.d) === String(id)) unpin();
  const i = list.findIndex(m => m.id === id);
  if (i >= 0) { const el = $('side').children[i]; if (el) { el.outerHTML = rowHtml(list[i], i); $('side').children[i].classList.toggle('cur', i === cur) } }
  const blk = $('d' + id);
  if (blk) { const t = document.createElement('div'); t.innerHTML = docHtml(DOCS.find(m => m.id === id)); blk.replaceWith(t.firstElementChild) }
  updStat(); syncRun();
}

// --------------------------------------------------------------------------- Process
let last = 'พร้อม';
function syncRun() {
  const m = list[cur], r = m && stOf(m.id), b = $('run');
  b.disabled = !m || isBusy(r);
  b.textContent = !m ? 'Process' : isBusy(r) ? 'Processing…' : hasView(r) ? 'Process ใหม่' : 'Process';
  document.querySelectorAll('.wb .run').forEach(x => { const rr = stOf(+x.dataset.id);
    x.disabled = isBusy(rr); x.textContent = isBusy(rr) ? 'Processing…' : hasView(rr) ? 'Process ใหม่' : 'Process' });
  const run = DOCS.filter(d => isBusy(stOf(d.id)));
  $('pst').textContent = run.length ? run.map(d => { const x = stOf(d.id);
    return `กำลังประมวล #${d.id} (${x.step || 'อ่านเอกสาร'}) ${((performance.now() - x.started) / 1000).toFixed(1)}s` }).join(' · ') : (note || last);
}
async function startRun(id) {
  const r = stOf(id); if (isBusy(r)) return;
  note = '';
  try { applyServer(await api.process(id)) }
  catch (e) {
    if (e.status === 409) { applyServer(await api.status(id)) }
    else { r.state = 'error'; r.error = e.message; last = `ไม่สำเร็จ #${id}: ${e.message}`; refresh(id); return }
  }
  r.view = null; r.from = null; refresh(id); watch(id);
}
function watch(id) {                              // ถามสถานะเอกสารนี้จนกว่าจะหลุดจาก processing
  if (POLL[id]) return;
  POLL[id] = setInterval(async () => {
    try {
      const m = await api.status(id);
      const err = m.source_error;
      applyServer(Object.assign(m, { src_err: err }));
      if (m.state === 'processing') { syncRun(); return }
      clearInterval(POLL[id]); delete POLL[id];
      last = m.state === 'done' ? `เสร็จ #${id} · ${m.recommendation} · ${m.seconds}s` : `ไม่สำเร็จ #${id}: ${m.error || ''}`;
      if (m.state === 'done') {
        try { const v = await api.result(id); stOf(id).view = v; stOf(id).from = 'server'; saveCase(id, v) }
        catch (e) { stOf(id).error = e.message }
      }
      refresh(id);
    } catch (e) { clearInterval(POLL[id]); delete POLL[id]; stOf(id).state = 'error'; stOf(id).error = e.message; refresh(id) }
  }, 500);
}
async function forget(id) {                       // ลืม case: ทั้งใน browser นี้และที่ server เก็บไว้
  try { const m = await api.forget(id); applyServer(m) } catch (e) { }
  dropCase(id);
  const r = stOf(id);
  Object.assign(r, { state: 'idle', run: r.run, step: null, cls: null, rec: null, error: null, seconds: null,
    types: [], kept: 0, dropped: 0, view: null, from: null });
  note = `ลืม case ของ #${id} แล้ว`; refresh(id);
}
$('run').onclick = () => { if (list[cur]) startRun(list[cur].id) };
setInterval(() => {
  let any = false;
  for (const m of DOCS) { const r = stOf(m.id); if (!isBusy(r)) continue; any = true;
    document.querySelectorAll(`.el[data-d="${m.id}"]`).forEach(e => e.textContent = ((performance.now() - r.started) / 1000).toFixed(1)) }
  if (any) syncRun();
}, 200);

// --------------------------------------------------------------------------- เลือกเอกสาร / ค้นหา / ตัวกรอง
async function openDoc(i) {
  cur = i; render();
  const m = list[cur]; if (!m) return;
  try { const s = await api.status(m.id);            // แหล่งข้อมูลนับหน้าจริงให้ (Paperless: จากไฟล์ PDF)
    Object.assign(m, { pages: s.pages, pages_total: s.pages_total });
    applyServer(Object.assign(s, { src_err: s.source_error }));
    refresh(m.id);
  } catch (e) { stOf(m.id).src_err = 'อ่านสถานะเอกสารไม่สำเร็จ: ' + e.message; refresh(m.id) }
}
$('side').onclick = e => { const el = e.target.closest('[data-i]'); if (!el) return; openDoc(+el.dataset.i) };
$('prev').onclick = () => { if (list.length) openDoc(Math.max(0, cur - 1)) };
$('next').onclick = () => { if (list.length) openDoc(Math.min(list.length - 1, cur + 1)) };
document.onkeydown = e => { if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
  if (e.key === 'ArrowLeft') $('prev').click(); if (e.key === 'ArrowRight') $('next').click() };
['ft', 'fs', 'dp'].forEach(id => $(id).onchange = apply);
let qTimer = null;
$('q').oninput = () => {
  clearTimeout(qTimer);
  qTimer = setTimeout(async () => {
    const q = $('q').value.trim(); qIds = null;
    if (q) {
      qIds = new Set();
      try { (await api.search(q)).ids.forEach(i => qIds.add(i)) } catch (e) { }
      const low = q.toLowerCase();
      Object.keys(CASES).forEach(id => { const s = (CASES[id].view && CASES[id].view.search) || ''; if (s.includes(low)) qIds.add(+id) });
    }
    apply();
  }, 250);
};
$('tb').onchange = e => document.body.classList.toggle('hide-tbl', !e.target.checked);
$('ov').onchange = e => document.body.classList.toggle('no-ov', !e.target.checked);   // เปิด/ปิดกรอบ bbox
$('clr').onclick = () => {
  const n = Object.keys(CASES).length;
  CASES = {}; try { localStorage.removeItem(CASE_KEY) } catch (e) { }
  for (const id of Object.keys(RES)) { const r = RES[id];
    if (r.from === 'browser' || r.state === 'cached') Object.assign(r, { state: 'idle', view: null, from: null, cls: null, rec: null, types: [], kept: 0, dropped: 0 }) }
  note = `ล้าง case ${n} รายการออกจาก browser แล้ว`; apply();
};
$('rf').onclick = async () => {
  $('pst').textContent = 'กำลังอ่านรายการเอกสาร…';
  try {
    const r = await api.refresh();
    DOCS = await api.documents(); hydrate();
    note = r.error ? `รีเฟรชไม่สำเร็จ: ${r.error}` : `รีเฟรชแล้ว: ${r.documents} ฉบับ`;
    apply();
  } catch (e) { note = 'รีเฟรชไม่สำเร็จ: ' + e.message; syncRun() }
};
$('main').onclick = e => {
  const b = e.target.closest('.run'); if (b) { startRun(+b.dataset.id); return }
  const f = e.target.closest('[data-forget]'); if (f) { forget(+f.dataset.forget); return }
};

// --------------------------------------------------------------------------- ชี้/คลิกกรอบ เพื่อดูข้อมูล + sync กับตาราง
const tip = $('tip'), pin = $('pin');
let hot = null, pinned = null;
const boxEl = (d, p, i) => document.querySelector(`.bx[data-d="${d}"][data-p="${p}"][data-i="${i}"]`);
function itemOf(d, p, i) {
  const r = RES[d]; if (!r || !hasView(r)) return null;
  const pp = r.view.pages.find(z => String(z.page) === String(p));
  return pp && pp.kept[i];
}
function tipHtml(it) {
  const b = it.bbox_norm || [], px = it.bbox_px || [];
  return `<b style="color:${COLORS[it.type] || COLORS.other}">${esc(it.type)} · ${esc(it.label)}</b>\n${esc(it.text)}`
    + `\n<span style="color:#aaa">px [${px.join(', ')}] · norm [${b.join(', ')}]${it.confidence != null ? ' · conf ' + it.confidence : ''}</span>`;
}
function mark(d, p, i, cls, on) {
  document.querySelectorAll(`.bx[data-d="${d}"][data-p="${p}"][data-i="${i}"],tr[data-d="${d}"][data-p="${p}"][data-i="${i}"]`)
    .forEach(e => e.classList.toggle(cls, on));
}
function clearHot() { if (hot) mark(hot.d, hot.p, hot.i, 'hot', false); hot = null; tip.style.display = 'none' }
function moveTip(e) {
  const r = tip.getBoundingClientRect(); let x = e.clientX + 14, y = e.clientY + 14;
  if (x + r.width > innerWidth - 6) x = e.clientX - r.width - 12;
  if (y + r.height > innerHeight - 6) y = innerHeight - r.height - 6;
  tip.style.left = Math.max(4, x) + 'px'; tip.style.top = Math.max(4, y) + 'px';
}
function pinIt(d, p, i) {
  const it = itemOf(d, p, i); if (!it) return;
  if (pinned) mark(pinned.d, pinned.p, pinned.i, 'sel', false);
  pinned = { d, p, i }; mark(d, p, i, 'sel', true);
  pin.innerHTML = tipHtml(it) + '<span id=unc onclick=unpin()>✕</span>'; pin.style.display = 'block';
  const t = document.querySelector(`tr[data-d="${d}"][data-p="${p}"][data-i="${i}"]`);
  if (t && t.scrollIntoView) t.scrollIntoView({ block: 'center' });
}
function unpin() { if (pinned) mark(pinned.d, pinned.p, pinned.i, 'sel', false); pinned = null; pin.style.display = 'none' }
function idxOf(e) {
  const bx = e.target.closest('.bx');
  if (bx && bx.dataset.i != null) return { d: +bx.dataset.d, p: bx.dataset.p, i: +bx.dataset.i };
  const tr = e.target.closest('tr[data-i]');
  if (tr && tr.dataset.d) return { d: +tr.dataset.d, p: tr.dataset.p, i: +tr.dataset.i };
  return null;
}
document.addEventListener('mousemove', e => {
  const h = idxOf(e), it = h && itemOf(h.d, h.p, h.i);
  if (!h || !it) { clearHot(); return }
  if (!hot || hot.d !== h.d || hot.p !== h.p || hot.i !== h.i) {
    clearHot(); hot = h; mark(h.d, h.p, h.i, 'hot', true); tip.innerHTML = tipHtml(it); tip.style.display = 'block';
  }
  moveTip(e);
});
document.addEventListener('click', e => {
  const rr = e.target.closest('tr[data-ref]');        // ช้อมูลใน Final / Verify -> ตรึงกรอบที่เป็นที่มา
  if (rr) {
    const [p, i] = rr.dataset.ref.split(':'), d = +rr.dataset.d;
    pinIt(d, p, +i);
    const b = boxEl(d, p, +i); if (b && b.scrollIntoView) b.scrollIntoView({ block: 'center' });
    return;
  }
  const h = idxOf(e); if (!h) return;
  if (pinned && pinned.d === h.d && String(pinned.p) === String(h.p) && pinned.i === h.i) { unpin(); return }
  pinIt(h.d, h.p, h.i);
});
document.addEventListener('keydown', e => { if (e.key === 'Escape' || e.key.startsWith('Arrow')) unpin() });
window.addEventListener('scroll', () => { if (hot) tip.style.display = 'none' }, { passive: true });

// --------------------------------------------------------------------------- เปิดหน้า
(async function boot() {
  loadCases();
  try { META = await api.meta(); COLORS = META.colors || {}; DOCS = await api.documents() }
  catch (e) { $('main').innerHTML = `<span class=error>โหลดรายการเอกสารไม่ได้: ${esc(e.message)}</span>`; return }
  hydrate();
  const types = new Set(); DOCS.forEach(m => (m.types || []).forEach(t => types.add(t)));
  $('ft').innerHTML += [...types].sort().map(t => `<option>${esc(t)}</option>`).join('');
  apply();
  if (list.length) openDoc(cur);
  DOCS.filter(m => m.state === 'processing').forEach(m => watch(m.id));   // รอบที่ยังรันอยู่ตอนเปิดหน้า
})();
