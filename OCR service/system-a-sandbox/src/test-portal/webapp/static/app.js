/* AIVA System A - test portal.

   ซ้าย  = เอกสารจริงจาก Paperless (อ่านผ่าน Paperless reader ของ System A เอง)
   กลาง  = ภาพหน้าเอกสาร + กรอบ bbox ทุกกรอบจาก ocr.elements[] ใน payload ของ System A
   ขวา   = ผลที่ System A คืน (result/3.0) เท่านั้น — final, lines, signatures, rules, exceptions
   ประมวลผล = ให้ System A ทำงานจริงจาก entrypoint ของมันเอง ผลเสียให้ error ลอยขึ้นมาแสดงตามนั้น

   เก็บ view ที่คำนวณเสร็จแล้วไว้ใน browser (localStorage) - restart server แล้วเปิดดูได้ทันที
*/
'use strict';

const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
let DOCS = [], list = [], cur = 0, COLORS = {}, META = {}, qIds = null, note = '';
const RES = {};                 // id -> สถานะของเอกสารนั้น (ตละฉบับ ไม่แชร์กัน)
const POLL = {};                // id -> timer ที่กำลังรอผล
const RC = { pass: 'ok', fail: 'error', manual_review: 'partial', not_evaluated: 'idle' };
const num = x => x == null ? '' : String(x);
let SHOW = new Set();           // ชนิดกรอบที่เปิดแสดงอยู่ (จำไว้ใน browser)

// --------------------------------------------------------------------------- ชนิดกรอบที่เปิดแสดง
function initTypes() {
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem('aiva.sysA.types.v1') || 'null') } catch (e) { }
  SHOW = new Set(Array.isArray(saved) && saved.length ? saved : (META.default_types || []));
}
function writeTypes() { try { localStorage.setItem('aiva.sysA.types.v1', JSON.stringify([...SHOW])) } catch (e) { } }
function typeChips(v) {
  return (v.types || []).map(t => `<label class="tg${SHOW.has(t) ? ' on' : ''}" `
    + `style="border-color:${COLORS[t] || '#888'}"><input type=checkbox data-t="${esc(t)}"${SHOW.has(t) ? ' checked' : ''}>`
    + `<span class=sw style="background:${COLORS[t] || '#888'}"></span>${esc(t)}</label>`).join('');
}

// --------------------------------------------------------------------------- case เก็บใน browser ของผู้ทดสอบ
const CASE_KEY = 'aiva.sysA.cases.v1', CASE_MAX = 12;
let CASES = {};
function loadCases() { try { CASES = JSON.parse(localStorage.getItem(CASE_KEY) || '{}') || {} } catch (e) { CASES = {} } }
function writeCases() {                          // quota ต่อ origin: เก็บไม่พอค่อย ๆ ทิ้ง case ที่เก่าสุด
  for (let i = 0; i < 6; i++) {
    try { localStorage.setItem(CASE_KEY, JSON.stringify(CASES)); return } catch (e) {
      const old = Object.entries(CASES).sort((a, b) => (a[1].saved_at || 0) - (b[1].saved_at || 0))[0];
      if (!old) return; delete CASES[old[0]];
    }
  }
}
function saveCase(id, view) {
  const keys = Object.keys(CASES).filter(k => +k !== +id);
  while (keys.length >= CASE_MAX) {
    const old = keys.map(k => ({ k, t: (CASES[k] || {}).saved_at || 0 })).sort((a, b) => a.t - b.t)[0];
    if (!old) break; delete CASES[old.k]; keys.splice(keys.indexOf(old.k), 1);
  }
  CASES[id] = { view: view, saved_at: Date.now() };
  writeCases();
}
function dropCase(id) { delete CASES[id]; writeCases() }

// --------------------------------------------------------------------------- API
const api = {
  async j(url, opt) {
    const r = await fetch(url, opt); let b = null; try { b = await r.json() } catch (e) { }
    if (!r.ok) throw Object.assign(new Error((b && b.detail) || ('HTTP ' + r.status)), { status: r.status });
    return b;
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
const stOf = id => RES[id] || (RES[id] = { id: id, state: 'idle', run: 0, step: null, cls: null, rec: null,
  error: null, tb: null, seconds: null, types: [], boxes: 0, started: 0, view: null, from: null, src_err: null,
  probed: false });
// /api/documents ส่ง "pages" เป็นเลขหน้า เช่น [1,2,3] ไม่ใช่วัตถุ — ต้องแปลงเป็นเลขก่อนต่อ url ของรูปหน้า
const pageNums = m => {
  const got = (m.pages || []).map(p => +((p && typeof p === 'object') ? p.page : p)).filter(n => n > 0);
  const total = Math.max(+m.pages_total || 0, ...got, 0) || 1;
  return [...new Set(got.concat(Array.from({ length: total }, (_, i) => i + 1)))].sort((a, b) => a - b);
};
const hasView = r => !!(r.view && r.state === 'done');
const isBusy = r => r.state === 'processing';
const rcls = r => isBusy(r) ? 'partial' : r.state === 'error' ? 'error' : hasView(r) ? (r.cls || 'ok') : 'idle';

function applyServer(m) {                        // 1 แถวของ /api/documents -> สถานะของเอกสารนั้น
  const r = stOf(m.id), first = r.state;
  r.state = m.state; r.run = m.run || 0; r.step = m.step; r.cls = m.cls; r.rec = m.recommendation || null;
  r.error = m.error; r.tb = m.traceback; r.seconds = m.seconds; r.types = m.types || [];
  r.boxes = m.boxes || 0; r.src_err = m.source_error || null;
  if (m.state === 'done') { r.error = null; r.tb = null; if (!r.view) r.probed = false }   // ให้ไปเอาผลมาแสดง
  if (first === 'processing' && m.state === 'error' && m.error) note = `error #${m.id}: ${m.error}`;
  if (m.state !== 'processing' && POLL[m.id]) { clearInterval(POLL[m.id]); delete POLL[m.id] }
}
function useCase(id, c) {                        // case ที่ browser เก็บไว้ (server restart แล้ว)
  const r = stOf(id);
  if (!c || !c.view) return;
  r.view = c.view; r.from = 'browser'; r.types = c.view.types || [];
  r.cls = c.view.cls; r.rec = c.view.rec; r.boxes = (c.view.counts || {}).boxes || 0;
}
function hydrate() {
  for (const m of DOCS) {
    const r = stOf(m.id);
    if (r.state === 'processing' || (r.view && r.from === 'server')) continue;
    if (CASES[m.id] && !r.view) useCase(m.id, CASES[m.id]);
  }
}

// --------------------------------------------------------------------------- element_id -> element (จาก payload)
const elOf = (v, id) => (v.elements || {})[id];
function refAttr(v, id) {                        // แถวที่ชี้ element หนึ่งของ System A -> ขยับกรอบนั้นเมื่อชี้แถว
  const e = elOf(v, id);
  return e ? ` data-ref="${esc(id)}" title="${esc(id)} · ${esc(e.type)} · หน้า ${e.page}"` : '';
}
const refSpans = (v, refs) => (refs || []).filter(Boolean).map(r =>
  `<span class=idle data-ref="${esc(r)}">[${esc(r)}]</span>`).join(' ');
const refFirst = (v, refs) => (refs || []).find(r => elOf(v, r)) || null;

// --------------------------------------------------------------------------- แถบสถานะ
function updStat() {
  let done = 0, run = 0, box = 0, cached = 0; const c = {};
  for (const m of DOCS) {
    const r = stOf(m.id);
    if (isBusy(r)) run++;
    if (hasView(r)) { done++; c[r.cls] = (c[r.cls] || 0) + 1; box += r.boxes || 0; if (r.from === 'browser') cached++ }
  }
  $('stat').innerHTML = `${DOCS.length} ฉบับ · ${DOCS.reduce((a, d) => a + (d.pages_total || 0), 0)} หน้า`
    + ` · ประมวลแล้ว ${done}${cached ? ` <span class=case>(ใน browser ${cached})</span>` : ''}`
    + `${run ? ` · <span class=partial>กำลังประมวล ${run}</span>` : ''} · ${box} กรอบจาก payload`
    + ` · <span class=ok>ok ${c.ok || 0}</span> <span class=partial>partial ${c.partial || 0}</span>`
    + ` <span class=error>error ${c.error || 0}</span>`;
  const S = META.source || {};
  $('src').innerHTML = `Paperless <b>${esc(String(S.base_url || '').replace(/^https?:\/\//, ''))}</b>`
    + ` · tag <b>${esc(S.tag || '')}</b> · DMS มี ${S.dms_total ?? '?'} ฉบับ · แสดง ${S.documents} ฉบับ`
    + ` · engine <b>${esc(META.engine)}</b>/${esc(META.mode)}`
    + ` · <b>${META.persist ? 'ผลเก็บที่ server' : 'ผลเก็บใน browser เท่านั้น'}</b>`
    + `${S.error ? ` · <span class=error>${esc(S.error)}</span>` : ''}`;
}

// --------------------------------------------------------------------------- ขวา: Final Result / Verify Result
function resultHtml(id) {
  const v = stOf(id).view, F = v.final || {}, R = v.recommendation || {}, rc = v.receipt || {};
  const M = v.metrics || {}, dur = M.duration_ms || {}, V = v.versions || {}, Q = v.request || {};
  const sha = (v.integrity || {}).payload_sha256 || '';
  const f = (F.items || []).map(x => `<tr${refAttr(v, refFirst(v, x.refs))}><td>${esc(x.label)}</td><td>`
    + (x.value == null || x.value === '' ? '<span class=error>— ไม่มีใน payload</span>' : esc(x.value))
    + ` ${refSpans(v, x.refs)}</td></tr>`).join('');
  const sg = (v.signatures || []).map(s => `<tr${refAttr(v, refFirst(v, s.refs))}><td>signature · ${esc(s.slot)}</td>`
    + `<td>${s.present === true ? 'พบ' : s.present === false ? 'ไม่พบ' : 'ไม่แน่ใจ'}`
    + `${s.conf != null ? ` <span class=idle>conf ${s.conf}</span>` : ''} · หน้า ${s.page} ${refSpans(v, s.refs)}</td></tr>`).join('');
  const sum = F.summary || {}, L = v.lines || {};
  const ln = (L.items || []).length
    ? `<table class=rt><tr><th>line</th><th>description</th><th>qty</th><th>uom</th><th>price</th><th>amount</th><th>System A จับคู่กับ</th></tr>`
    + L.items.map(l => `<tr${refAttr(v, l.ref)}><td>${esc(num(l.no))} <span class=idle>หน${esc(num(l.page))}</span></td>`
      + `<td>${esc(l.desc)} <span class=idle>${esc(l.ref || 'ไม่มี element_id')}</span></td>`
      + `<td>${esc(num(l.qty))}</td><td>${esc(num(l.uom))}</td><td>${esc(num(l.unit_price))}</td><td>${esc(num(l.amount))}</td>`
      + `<td>${l.match ? `<span class=ok>${esc(l.match.level || '')} ${esc(l.match.relation || '')}</span> `
        + `<span class=idle>${esc((l.match.rcv_line_ids || []).join(', ') || l.match.group_id || '')} · ${esc(l.match.source || '')}`
        + `${l.match.confidence != null ? ' · ' + l.match.confidence : ''}</span>${l.match.rationale ? '<br>' + esc(l.match.rationale) : ''}`
        : '<span class=error>ไม่พบกลุ่มที่จับคู่</span>'}</td></tr>`).join('') + '</table>'
    : '<div class=sec>payload ไม่มีรายการสินค้า (normalized_fields.items ว่าง)</div>';
  const bad = (L.ai_rejected || []).concat(L.unmatched_rcv_line_ids || []);
  const excBy = {}; (v.exceptions || []).forEach(x => { (excBy[x.rule_id] = excBy[x.rule_id] || []).push(x) });
  const vr = (v.rules || []).map(x => {
    const ev = (excBy[x.id] || []).map(e => `<b>${esc(e.code)} ${esc(e.name)}</b> <span class=error>${esc(e.severity)}</span> `
      + `${esc(e.detail || '')} ${refSpans(v, e.refs)}`
      + `${(e.missing_refs || []).length ? `<br><span class=error>${esc(e.missing_refs.join(' | '))}</span>` : ''}`).join('<br>');
    const data = Object.keys(x.data || {}).length ? ` <span class=idle>${esc(JSON.stringify(x.data))}</span>` : '';
    return `<tr><td>${esc(x.id)} <span class=idle>v${esc(x.version || '')}</span></td>`
      + `<td><span class=${RC[x.result] || 'idle'}>${esc(x.result)}</span></td>`
      + `<td>${esc(x.detail || '')}${x.halted_by ? ` <span class=idle>[halted_by ${esc(x.halted_by)}]</span>` : ''}`
      + `${ev ? '<br>' + ev : ''}${data}</td></tr>`;
  }).join('');
  return `<div class=sec><b>Final Result</b> · <span class=${v.cls}>${esc(v.rec)}</span>`
    + `${(R.codes || []).length ? ' · ' + esc(R.codes.join(', ')) : ''}`
    + `${R.halted_by ? ` · halted_by ${esc(R.halted_by)}` : ''}`
    + `${v.incomplete ? ' · <span class=partial>payload มี system_errors</span>' : ''}`
    + `${v.seconds != null ? ` · ${v.seconds}s` : ''} · engine ${esc(META.engine)}/${esc(META.mode)}</div>`
    + `${(R.reasons || []).length ? `<div class=sec>${R.reasons.map(esc).join('<br>')}</div>` : ''}`
    + `<div class=sec>Oracle: ${rc.queried ? `${esc(rc.path || 'ไม่พบเส้นทางสืบ')} · ใบรับ ${esc((rc.receipt_nums || []).join(', ') || '-')}`
      + ` · PO ${esc((rc.po_numbers || []).join(', ') || '-')}` : 'ไม่ได้สืบ/ไม่พบข้อมูล'}`
    + `${rc.receiver ? ` · ผู้รับ ${esc(rc.receiver)}` : ''}${rc.matched_on ? ` · match ด้วย ${esc(rc.matched_on)}` : ''}`
    + ` · เรียก ${esc(String(M.oracle_calls ?? '?'))} ครั้ง${rc.row_cap_hit ? ' · <span class=error>ชนเพดานจำนวนแถว</span>' : ''}`
    + `${rc.fingerprint ? ` <span class=idle title="${esc(rc.fingerprint)}">fingerprint ${esc(String(rc.fingerprint).slice(7, 19))}</span>` : ''}</div>`
    + `<table class=rt><tr><th>field</th><th>value (จาก payload เท่านั้น)</th></tr>${f}${sg}</table>`
    + `<div class=sec>สรุปบรรทัด: ${esc(num(sum.line_count))} บรรทัด · ใช้ได้ ${esc(num(sum.lines_usable))}`
    + ` · คณิตฯ ผ่าน ${esc(num(sum.lines_math_ok))} · จับคู่ได้ ${esc(num(sum.lines_matched))}`
    + ` · รวม ${esc(num(sum.sum_amount))} vs subtotal ${esc(num(sum.sub_total))}`
    + ` (ต่าง ${esc(num(sum.sum_vs_sub_total_diff))})`
    + `${(F.buyer || {}).name ? `<br>ผู้ซื้อ: ${esc(F.buyer.name)} · ${esc(F.buyer.tax_id || '')}` : ''}</div>${ln}`
    + `${bad.length ? `<div class=sec><b>ที่ System A ปฏิเสธ / จับคู่ไม่ได้</b> <span class=error>${esc(JSON.stringify(bad))}</span></div>` : ''}`
    + `<div class=sec><a href="/api/documents/${id}/payload" target=_blank>payload JSON</a>`
    + ` · <a href="/api/documents/${id}/extraction" target=_blank>extraction block</a>`
    + ` · ${esc(v.contract)} · standard ${esc(V.standard || '')} ruleset ${esc(V.ruleset || '')}`
    + ` · ${(V.models || {}).line_matcher || ''} · run ${esc(Q.run_id || '')} · ${esc(Q.validation_id || '')}`
    + `${sha ? ` · <span class=idle title="${esc(sha)}">sha ${esc(sha.slice(7, 19))}</span>` : ''}`
    + ` · ${Object.entries(dur).map(([k, x]) => `${k} ${x}ms`).join(' ')}`
    + `${stOf(id).from === 'browser' ? ' · <span class=case>case จาก browser</span>' : ''}</div>`
    + `<div class=sec><b>Verify Result</b> <span class=idle>(คลิก [element_id] เพื่อตรึงกรอบที่ System A ระบุ)</span></div>`
    + `<table class=rt><tr><th>rule</th><th>result</th><th>detail / evidence</th></tr>${vr}</table>`
    + `${(v.dropped || []).length ? `<div class=err>✗ system_errors ${esc(JSON.stringify(v.dropped))}</div>` : ''}`;
}
function elementsHtml(id) {
  const v = stOf(id).view;
  return (v.pages || []).map(p => {
    const rows = (p.elements || []).map(eid => {
      const e = elOf(v, eid) || {};
      return `<tr${refAttr(v, eid)}><td><span class=sw style="background:${COLORS[e.type] || '#888'}"></span>${esc(e.type)}</td>`
        + `<td>${esc(e.field || eid)} <span class=idle>${esc(eid)}</span></td>`
        + `<td>${esc(e.value ?? e.raw ?? '')}</td><td>${e.conf != null ? e.conf : ''}</td>`
        + `<td>${e.has_bbox ? e.bbox.map(z => (+z).toFixed(3)).join(' ') : '<span class=error>no bbox</span>'}</td></tr>`;
    }).join('');
    return `<div class=ocrsec><div class=ocrh>หน้า ${p.page} · ${esc(p.page_type || '?')}`
      + `${p.type_confidence != null ? ' · conf ' + p.type_confidence : ''}`
      + `${p.ocr_quality != null ? ' · OCR ' + p.ocr_quality : ''} · ${(p.elements || []).length} element`
      + ` · ${p.width_pt ?? '?'}×${p.height_pt ?? '?'}pt rot ${p.rotation ?? 0} @${p.render_dpi ?? '?'}dpi</div>`
      + `<table><tr><th>type</th><th>field / id</th><th>value</th><th>conf</th><th>bbox [x y w h]</th></tr>`
      + `${rows || '<tr><td colspan=5><span class=ph>หน้านี้ไม่มี element ใน payload</span></td></tr>'}</table></div>`;
  }).join('');
}
function errorHtml(r) {
  return `<div class=ph><span class=error>✗ ${esc(r.error || 'System A คืน error')}</span>`
    + `${r.tb ? `<details open><summary>traceback ของ System A</summary><pre>${esc(r.tb)}</pre></details>` : ''}`
    + `<br>ไม่มีผลบางส่วนให้ดู - แก้สาเหตุแล้วกด Process ใหม่</div>`;
}
function panelHtml(m) {
  const r = stOf(m.id);
  if (isBusy(r)) return `<div class=ph><span class=partial>กำลังประมวลผล… <span class=el data-d=${m.id}>0.0</span>s</span><br>`
    + `System A กำลังอ่านไฟล์จริงของเอกสารนี้ แล้วตรวจกับ Oracle และกติกาของมันเอง`
    + `${r.src_err ? `<div class=err>${esc(r.src_err)}</div>` : ''}</div>`;
  if (r.state === 'error') return errorHtml(r);
  if (!hasView(r)) return `<div class=ph>ยังไม่ได้ประมวลผลเอกสารนี้ — กด <b>Process</b><br><br>`
    + `portal เรียก entrypoint ของ System A โดยตรง: Paperless → vision → Oracle → กติกา → result 3.0<br>`
    + `กรอบทุกกรอบที่เห็นมาจาก <code>ocr.elements[]</code> ใน payload เท่านั้น`
    + `${r.src_err ? `<div class=err>⚠ ${esc(r.src_err)}</div>` : ''}</div>`;
  const C = (r.view.counts || {});
  return resultHtml(m.id)
    + `<div class=sec><b>element ใน payload</b> <span class=idle>(${C.elements ?? '?'} element · วาดได้ ${C.boxes ?? '?'} กล่อง`
    + `${C.no_bbox ? ` · <span class=error>ไม่มี bbox ${C.no_bbox}</span>` : ''} · ชี้แถวเพื่อดูกรอบบนเอกสาร)</span></div>`
    + elementsHtml(m.id);
}

// --------------------------------------------------------------------------- กลาง: หน้าเอกสาร + กรอบ bbox
function boxesOf(v, p) {
  return (p.elements || []).filter(eid => {
    const e = elOf(v, eid);
    return e && e.has_bbox && SHOW.has(e.type);
  }).map(eid => {
    const e = elOf(v, eid), [x, y, w, h] = e.bbox;
    const lab = String(e.field || e.type || '').slice(0, 22);
    return `<div class=bx data-ref="${esc(eid)}" style="left:${(x * 100).toFixed(3)}%;top:${(y * 100).toFixed(3)}%;`
      + `width:${(w * 100).toFixed(3)}%;height:${Math.max(h * 100, 0.35).toFixed(3)}%;border-color:${COLORS[e.type] || '#888'}">`
      + `<span style="background:${COLORS[e.type] || '#888'}">${esc(lab)}</span></div>`;
  }).join('');
}
function pagesHtml(m) {
  const r = stOf(m.id), v = r.view, show = $('ov').checked;
  const pages = pageNums(m).map(page => ({ page }));
  return pages.map(p => {
    const full = v && (v.pages || []).find(x => x.page === p.page);
    const img = `<img src="${api.img(m.id, p.page)}" data-p="${p.page}" alt="page ${p.page}">`;
    if (!show || !v || !full) return `<div class=pg data-page="${p.page}"><div class=pgh>หน้า ${p.page}</div>`
      + `<div class=imgbox style="aspect-ratio:${(full && full.width_pt) || 595}/${(full && full.height_pt) || 842}">${img}</div></div>`;
    const drawn = (full.elements || []).filter(eid => {
      const e = elOf(v, eid); return e && e.has_bbox && SHOW.has(e.type);
    }).length;
    return `<div class=pg data-page="${p.page}"><div class=pgh>หน้า ${p.page} · ${esc(full.page_type || '?')}`
      + ` · ${(full.elements || []).length} element · ${full.width_pt}×${full.height_pt}pt rot ${full.rotation || 0}`
      + ` · วาด ${drawn} กรอบ</div>`
      + `<div class=imgbox style="aspect-ratio:${full.width_pt}/${full.height_pt}">${img}${boxesOf(v, full)}</div></div>`;
  }).join('');
}
function docHtml(m) {
  const r = stOf(m.id), cls = rcls(r);
  const link = x => `<span class=pglink data-jump="${m.id}:${x}">หน${x}</span>`;
  const nums = pageNums(m);
  const jump = nums.length > 1 ? nums.map(link).join(' ') : '';
  return `<div class=card id=doc-${m.id}><div class=ch><span class="${cls}">[${esc(r.rec || cls)}]</span> <b>#${m.id}</b>`
    + ` · ${esc(m.title || '')} <span class=idle>(${esc(m.file_name || m.mime || '')} · ${esc(m.file_class || '')}`
    + ` · <a href="${esc(m.dms_url || m.viewer_url)}" target=_blank>Paperless</a>`
    + ` · <a href="${api.pdf(m.id)}" target=_blank>ไฟล์เดิม</a>)</span></div>`
    + `<div class=meta><span class=chip>#${m.id}${m.tagged ? ' · มี tag' : ' · ไม่มี tag'}</span>`
    + `<span class=chip>${m.pages_total || "?"} หน้า</span>`
    + (m.correspondent ? `<span class=chip>${esc(m.correspondent)}</span>` : '')
    + (m.created ? `<span class=chip>${esc(String(m.created).slice(0, 10))}</span>` : '') + jump + `</div>`
    + `<div class=pgs>${pagesHtml(m)}</div>`
    + `<div class=acts><button data-act=run data-id="${m.id}">Process เอกสารนี้</button>`
    + `<button data-act=del data-id="${m.id}">ลบผล</button>`
    + `<span class=st data-id="${m.id}">${esc(r.state === 'done' ? 'ประมวลแล้ว' : r.state === 'error' ? 'error' : 'รอประมวลผล')}</span></div>`
    + panelHtml(m) + `</div>`;
}
const rowHtml = (m, i) => {
  const r = stOf(m.id), cls = rcls(r), step = isBusy(r) && r.step ? `<span class=step>${esc(r.step)}</span>` : '';
  return `<div class="row${i === cur ? ' cur' : ''}" data-id="${m.id}" data-cur="${i}"><span class="${cls}">[${esc(r.rec || cls)}]</span> #${m.id}`
    + ` <span class=d>${esc(m.title || '')}</span> <span class=idle>${m.pages_total || "?"}n</span>${step}</div>`;
};

// --------------------------------------------------------------------------- วาดรายการ + เอกสารที่เปิดอยู่
function typeOptions() {
  const seen = [...new Set(DOCS.flatMap(x => stOf(x.id).types || []).concat(META.element_types || []))].filter(Boolean);
  $('ft').innerHTML = '<option value="">ชนิดกรอบทั้งหมด</option>' + seen.map(t => `<option value="${esc(t)}">${esc(t)}</option>`).join('');
  $('ft').value = '';
}
function apply() {
  if (!DOCS.length) { $('main').innerHTML = '<div class=ph>ไม่มีเอกสารใน DMS ที่ตรงกับ tag นี้</div>'; $('types').innerHTML = ''; return }
  const q = $('q').value.trim().toLowerCase();
  list = q ? DOCS.filter(m => String(m.id) === q || (m.title || '').toLowerCase().includes(q)
    || (m.file_name || '').toLowerCase().includes(q) || (m.correspondent || '').toLowerCase().includes(q)) : DOCS;
  if (cur >= list.length) cur = 0;
  $('side').innerHTML = list.map((m, i) => rowHtml(m, i)).join('') || '<div class=row>ไม่พบที่ตรงคำค้น</div>';
  const m = list[cur];
  $('main').innerHTML = m ? docHtml(m) : '<div class=ph>ไม่พบเอกสาร</div>';
  $('run').onclick = () => (m ? startRun(m.id) : alert('ยังไม่มีเอกสารที่เปิดอยู่'));
  $('run').disabled = !!m && isBusy(stOf(m.id));
  typeOptions();
  $('types').innerHTML = m && hasView(stOf(m.id)) ? typeChips(stOf(m.id).view) : '';
  if (m) ensureView(m.id);
  updStat(); renderPin();
}
$('ov').onchange = apply;

const loading = new Set();
async function ensureView(id) {                  // ผลที่ server ประมวลไว้แล้ว แต่ยังไม่ได้เปิดดู
  if (loading.has(id)) return;
  const r = stOf(id);
  if (r.state === 'done' && r.view) return;
  if (r.state === 'processing' || r.state === 'error') return;
  if (r.probed) return;                                  // ถามครั้งเดียว: ที่ server ไม่มีผลของเอกสารนี้เก็บไว้
  r.probed = true;
  loading.add(id);
  try {
    const v = await api.result(id);
    if (v && v.elements) {
      r.state = 'done'; r.view = v; r.from = 'server'; r.types = v.types || r.types;
      r.cls = v.cls; r.rec = v.rec; r.boxes = (v.counts || {}).boxes || 0;
      saveCase(id, v); refresh(id);
    }
  } catch (e) {
    if (e.status === 404 || e.status === 409) { if (CASES[id]) useCase(id, CASES[id]); }
    else { r.error = e.message; refresh(id) }
  } finally { loading.delete(id) }
}
function refresh(id) {                           // วาดใหม่เฉพาะเอกสารนี้
  const i = list.findIndex(x => String(x.id) === String(id));
  const m = i >= 0 ? list[i] : DOCS.find(x => String(x.id) === String(id));
  if (!m) return apply();
  if (i === cur) $('main').innerHTML = docHtml(m);
  const row = $('side').querySelector(`.row[data-id="${m.id}"]`);
  if (row) row.outerHTML = rowHtml(m, i); else apply();
  updStat();
}

// --------------------------------------------------------------------------- Process (ให้ System A ทำงานจริง)
let last = 'พร้อม';
function syncRun() {
  const ids = Object.keys(RES).filter(k => isBusy(stOf(+k)));
  $('strip').innerHTML = ids.map(k => {
    const r = stOf(+k);
    return `<span class="t${r.state === 'error' ? ' f' : ''}">#${k} ${esc(r.step || 'รอ')} ${((performance.now() - r.started) / 1000).toFixed(1)}s</span>`;
  }).join('') || `<span class="t${note.startsWith('error') ? ' f' : ''}">${esc(last)}</span>`;
}
function startTimer(id) {
  stOf(id).started = performance.now();
  const t = setInterval(() => {
    const r = stOf(id);
    document.querySelectorAll(`.el[data-d="${id}"]`).forEach(e =>
      e.textContent = ((performance.now() - r.started) / 1000).toFixed(1));
    syncRun();
    if (!isBusy(r)) clearInterval(t);
  }, 250);
}
async function startRun(id) {
  if (isBusy(stOf(id))) return alert('เอกสารนี้กำลังประมวลผลอยู่');
  const r = stOf(id);
  r.error = null; r.tb = null;
  try {
    const m = await api.process(id);
    applyServer(Object.assign({}, m, { state: 'processing' }));
    startTimer(id); watch(id); apply();
    last = `เริ่ม #${id}`; syncRun();
  } catch (e) {
    if (e.status === 409) { last = 'กำลังประมวลเอกสารอื่นอยู่'; setTimeout(apply, 800); return syncRun(); }
    alert('เริ่มงานไม่ได้: ' + e.message);
  }
}
function watch(id) {                             // ถามสถานะเอกสารนี้จน System A ตอบกลับมา
  POLL[id] = setTimeout(async () => {
    delete POLL[id];
    try {
      const m = await api.status(id);
      applyServer(m);
      if (m.state === 'done') {
        last = `เสร็จ #${id} · ${m.recommendation || '-'} · ${m.seconds}s`;
        const r0 = stOf(id); r0.probed = true;
        try { const v = await api.result(id); const r = stOf(id); r.view = v; r.from = 'server'; saveCase(id, v) } catch (e) { }
        apply();
      } else if (m.state === 'error') { last = `error #${id} · ${m.error}`; apply(); }
      else { watch(id); apply(); }
      syncRun();
    } catch (e) { last = `poll ไม่ได้: ${e.message}`; watch(id); syncRun(); }
  }, 2000);
}
async function forget(id) {                      // ลบผลของเอกสารนี้ทิ้งทั้งใน browser และที่ server
  if (!confirm(`ลบผลของเอกสาร #${id} ?`)) return;
  try { await api.forget(id) } catch (e) { }
  dropCase(id);
  const r = stOf(id);
  Object.assign(r, { state: 'idle', view: null, cls: null, rec: null, error: null, tb: null, boxes: 0, from: null,
    probed: true });                             // เพิ่งลบผล — ไม่ต้องไปถาม server ซ้ำ
  apply();
}

// --------------------------------------------------------------------------- ชี้ = ดูข้อมูล · คลิก = ตรึงกรอบของ element
const tip = $('tip'), pin = $('pin');
let pinned = null;
const anchor = el => el.closest ? (el.closest('.bx') || el.closest('[data-ref]')) : null;

function boxDescr(v, e) {
  if (!e) return '';
  const b = e.has_bbox ? e.bbox.map(z => (+z).toFixed(3)).join(' ') : 'ไม่มี bbox';
  return `<div><b>${esc(e.id)}</b> · <span style="color:${COLORS[e.type] || '#888'}">${esc(e.type)}</span>`
    + ` · หน้า ${e.page}${e.parent ? ` · ใน ${esc(e.parent)}` : ''}${e.field ? ` · <b>${esc(e.field)}</b>` : ''}</div>`
    + `<div class=big>${esc(e.text)}</div>`
    + `${e.raw != null ? `<div>raw = ${esc(e.raw)}</div>` : ''}`
    + `${e.value != null && e.value !== e.raw ? `<div>normalized = ${esc(e.value)}</div>` : ''}`
    + `${e.conf != null ? `<div>conf = ${e.conf}</div>` : ''}`
    + `<div>bbox [x y w h] = ${esc(b)}</div>`
    + `${e.source_ref ? `<div>source = ${esc(e.source_ref)}</div>` : ''}`;
}
function showTip(text, x, y) {
  tip.innerHTML = text; tip.style.display = 'block';
  const w = tip.offsetWidth, h = tip.offsetHeight;
  tip.style.left = Math.min(Math.max(8, x - w / 2), innerWidth - w - 8) + 'px';
  tip.style.top = (y + 16 + h > innerHeight ? Math.max(8, y - h - 10) : y + 16) + 'px';
}
const hideTip = () => { tip.style.display = 'none' };
function setMark(id, page, on) {
  document.querySelectorAll(`#main .pg[data-page="${page}"] .bx[data-ref="${id}"]`).forEach(bx =>
    bx.classList[on ? 'add' : 'remove']('hl'));
  document.querySelectorAll(`#main [data-ref="${id}"]`).forEach(row => row.classList[on ? 'add' : 'remove']('hl'));
}
function tipFrom(a, x, y) {
  const m = list[cur]; if (!m) return hideTip();
  const r = stOf(m.id); if (!r.view) return hideTip();
  const id = a.dataset.ref, e = elOf(r.view, id);
  if (!e) return hideTip();
  if (!pinned) showTip(boxDescr(r.view, e), x, y);
}
function renderPin() {
  if (!pinned) { pin.style.display = 'none'; return }
  const m = list[cur], r = m && m.id === pinned.doc ? stOf(pinned.doc) : null, v = r && r.view;
  const e = v && elOf(v, pinned.id);
  if (!e) { pin.style.display = 'none'; return }
  pin.innerHTML = `<div class=ttl>ผลจาก payload · element_id <b>${esc(pinned.id)}</b>`
    + ` <span class=idle>· กด Esc หรือคลิกที่เดิมเพื่อปิด</span></div>` + boxDescr(v, e);
  pin.style.display = 'block';
}
function clickAnchor(a) {
  const m = list[cur]; if (!m) return;
  const id = a.dataset.ref;
  if (pinned && pinned.id === id && pinned.doc === m.id) pinned = null;
  else { const r = stOf(m.id); if (!elOf(r.view, id)) return; pinned = { doc: m.id, id: id } }
  renderPin();
}
document.addEventListener('mouseover', e => { const a = anchor(e.target); if (a) tipFrom(a, e.clientX, e.clientY) });
document.addEventListener('mousemove', e => { const a = anchor(e.target); if (a && tip.style.display === 'block') tipFrom(a, e.clientX, e.clientY) });
document.addEventListener('mouseout', e => { if (anchor(e.target)) hideTip() });
document.addEventListener('click', e => {
  const t = e.target, chip = t.closest && t.closest('label.tg');
  if (chip) {
    const cb = chip.querySelector('input[data-t]'), k = cb.dataset.t;
    SHOW.has(k) ? SHOW.delete(k) : SHOW.add(k);
    writeTypes();
    chip.classList[SHOW.has(k) ? 'add' : 'remove']('on');
    cb.checked = SHOW.has(k);
    apply();
    return;
  }
  if (t.closest && t.closest('#pin')) { if (pinned) setMark(pinned.id, pinned.page, false); pinned = null; renderPin(); return }
  if (t.tagName === 'IMG') {                       // คลิกที่ภาพหน้า: ตรึงกรอบแรกของหน้านี้ไว้
    const pg = t.closest('.pg'), b = pg && pg.querySelector('.bx');
    if (b) { pinned = { doc: list[cur] && list[cur].id, id: b.dataset.ref }; renderPin() }
    return;
  }
  const bx = t.closest && t.closest('.bx'), a = bx || (t.closest && t.closest('[data-ref]'));
  if (a && a.dataset.ref) return clickAnchor(a);
  const jump = t.closest && t.closest('[data-jump]');
  if (jump) {
    const [id, page] = jump.dataset.jump.split(':');
    const i = list.findIndex(x => String(x.id) === String(id));
    if (i >= 0 && i !== cur) { cur = i; apply(); }
    const el = document.querySelector(`#main .pg[data-page="${page}"]`);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    return;
  }
  const ft = t.closest && t.closest('select#ft');
  if (ft) {
    if (ft.value) SHOW = new Set([ft.value]); else SHOW = new Set(META.element_types || []);
    writeTypes(); apply();
    return;
  }
  const row = t.closest && t.closest('.row');
  if (row) { cur = +row.dataset.cur; pinned = null; hideTip(); apply(); return }
  const act = t.closest && t.closest('button[data-act]');
  if (act) {
    const id = +act.dataset.id;
    if (act.dataset.act === 'run') startRun(id); else forget(id);
    return;
  }
});
document.addEventListener('mouseover', e => {
  if (!$('strip').contains(e.target)) return;
  const m = /#(\d+)/.exec(e.target.textContent || '');
  if (!m) return;
  const id = +m[1], r = stOf(id);
  const el = document.querySelector(`#main #doc-${id} img[data-p="1"]`) || document.querySelector(`#main #doc-${id} img`);
  const pg = el && el.closest('.pg'), page = pg && pg.dataset.page;
  if (r.view && r.view.elements) Object.keys(r.view.elements).forEach(x => setMark(x, page, true));
});
document.addEventListener('mouseout', e => {
  if (!$('strip').contains(e.target)) return;
  const m = /#(\d+)/.exec(e.target.textContent || '');
  if (!m) return;
  const r = stOf(+m[1]);
  const el = document.querySelector(`#main #doc-${m[1]} img`), pg = el && el.closest('.pg'), page = pg && pg.dataset.page;
  if (r.view && r.view.elements) Object.keys(r.view.elements).forEach(x => setMark(x, page, false));
});
document.addEventListener('keydown', e => {
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    if (!list.length) return;
    cur = Math.min(list.length - 1, Math.max(0, cur + (e.key === 'ArrowDown' ? 1 : -1)));
    e.preventDefault(); pinned = null; apply();
    const row = $('side').querySelector(`.row[data-cur="${cur}"]`);
    if (row) row.scrollIntoView({ block: 'nearest' });
  } else if (e.key === 'PageDown' || e.key === 'PageUp') {
    e.preventDefault(); $('main').scrollBy({ top: (e.key === 'PageDown' ? 1 : -1) * $('main').clientHeight * 0.82 });
  } else if (e.key === 'f') { $('ov').checked = !$('ov').checked; apply() }
  else if (e.key === 'Escape') { if (pinned) setMark(pinned.id, pinned.page, false); pinned = null; hideTip(); renderPin() }
});

// --------------------------------------------------------------------------- คำค้น: คำนี้อยู่ในกรอบ/บรรทัดไหน
let qTimer = null;
$('q').addEventListener('input', () => {
  clearTimeout(qTimer);
  const t = $('q').value.trim();
  if (!t) { qIds = null; note = ''; apply(); return }
  qTimer = setTimeout(async () => {
    try {
      const g = await api.search(t);
      qIds = g.ids || [];
      const v = stOf(list[cur] ? list[cur].id : 0).view;
      const local = (v && v.search && v.search.phrases && v.search.phrases[t]) || [];
      if (local.length) qIds = qIds.concat(stOf(list[cur].id).id);
      note = `${qIds.length} เอกสารที่ตรง "${t}"` + (local.length ? ` · พบในผลที่เปิดอยู่ ${local.length} ที่` : '');
      apply();
    } catch (e) { qIds = null; note = 'ค้นหาไม่ได้: ' + e.message; apply() }
  }, 400);
});
$('rf').onclick = async () => {
  $('rf').disabled = true; $('rf').textContent = 'กำลังโหลด…';
  try { DOCS = await api.documents(); hydrate(); cur = 0; qIds = null; $('q').value = ''; apply(); }
  catch (e) { $('main').innerHTML = `<div class=err>โหลดรายการจาก Paperless ไม่ได้: ${esc(e.message)}</div>` }
  finally { $('rf').disabled = false; $('rf').textContent = 'รีเฟรชรายการ' }
};
$('clr').onclick = () => {                      // case ที่เก็บใน browser ทั้งหมด (ผลที่ server ยังเก็บอยู่ไม่หาย)
  if (!confirm('ลบ case ที่เก็บไว้ใน browser นี้ทั้งหมด?')) return;
  CASES = {}; writeCases();
  for (const id of Object.keys(RES)) { const r = stOf(+id); if (r.from === 'browser') { r.view = null; r.from = null } }
  apply();
};
addEventListener('resize', () => { if (pinned) renderPin() });

// --------------------------------------------------------------------------- เริ่มงาน
(async function boot() {
  try {
    META = await api.meta();
    COLORS = META.colors || {};
    initTypes(); loadCases();
    updStat(); syncRun();
    DOCS = await api.documents();
    hydrate();
    apply();
  } catch (e) {
    $('main').innerHTML = `<div class=err>โหลดรายการจาก Paperless ไม่ได้: ${esc(e.message)}<br>`
      + `<span class=idle>ตรวจ PAPERLESS_BASE_URL / PAPERLESS_API_TOKEN / PAPERLESS_TAG ใน .env</span></div>`;
    updStat(); syncRun();
  }
})();
