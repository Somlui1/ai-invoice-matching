/* Panel renderers: catalog, verdict card, rules, exceptions, fields, lines, receipts, JSON.
   Every value that has a box on the page is registered with Linker so both highlight directions work. */
'use strict';

const Panels = (() => {
  let ov = null;                 // overlay payload from /api/overlays/{key}
  let raw = null;                // full Contract 3.0 result
  let docSel = null;
  const LAYER_COLOR = { ocr_words: '#7f8fa4', table_rows: '#35c9e6', header_fields: '#ffb454',
                        signatures: '#b07bff', exceptions: '#ff6b6b' };

  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const short = (s, n = 42) => { s = String(s == null ? '' : s); return s.length > n ? s.slice(0, n - 1) + '…' : s; };
  const el = id => document.getElementById(id);
  const fmtConf = c => (c == null ? '' : `<span class="conf${c < 0.75 ? ' lo' : ''}">${Math.round(c * 100)}%</span>`);

  /* ------------------------------------------------------------------ catalog */
  function renderDocs(data, selectedId, onSelect) {
    const ul = el('doclist');
    ul.innerHTML = '';
    (data.results || []).forEach(d => {
      const li = document.createElement('li');
      li.className = 'doc' + (String(d.id) === String(selectedId) ? ' sel' : '');
      const v = (d.verdict || {}).recommendation || 'NONE';
      li.innerHTML = `<span class="t" title="${esc(d.title || d.file_name)}">${esc(d.title || d.file_name || ('DMS-' + d.id))}</span>
        <span class="b ${v}">${d.verdict ? esc(v) : '·'}</span>
        <span class="m">DMS-${esc(d.id)} · ${esc(d.page_count || '?')}p · ${esc((d.tags || []).join(', ') || 'no tags')}
          ${d.verdict ? '· ' + esc(((d.verdict.exception_codes || []).join(' ') || 'no exceptions')) : ''}</span>`;
      li.addEventListener('click', () => onSelect(d));
      ul.appendChild(li);
    });
    el('doc-count').textContent = `${data.count || 0} documents`;
    el('pagenum').textContent = `page ${data.page}`;
    el('btn-prev').disabled = (data.page || 1) <= 1;
    const shown = (data.page * (data.page_size || 50));
    el('btn-next').disabled = shown >= (data.count || 0);
  }

  function renderUploads(items, onSelect) {
    const box = el('uploads');
    if (!items || !items.length) { box.innerHTML = ''; return; }
    box.innerHTML = '<h3>Uploaded this session</h3>';
    items.forEach(it => {
      const d = document.createElement('div');
      d.className = 'uprow';
      d.innerHTML = `⤒ ${esc(short(it.name, 30))} <span class="muted">${it.page_count}p</span>`;
      d.addEventListener('click', () => onSelect(it));
      box.appendChild(d);
    });
  }

  /* ------------------------------------------------------------------ overlay boxes for one page */
  function boxesFor(page) {
    if (!ov) return [];
    const out = [];
    let n = 0;
    const push = (b) => { b.id = b.layer + '-' + (n++); out.push(b); };

    for (const [layer, list] of Object.entries(ov.by_type || {})) {
      if (layer === 'page') continue;
      const map = layer === 'word' ? 'ocr_words'
                : (layer === 'cell' || layer === 'row' || layer === 'table') ? 'table_rows'
                : layer === 'field' ? 'header_fields'
                : (layer === 'signature' || layer === 'stamp') ? 'signatures' : null;
      if (!map) continue;
      for (const e of list) {
        if (e.page !== page || !e.bbox) continue;
        const cls = 't-' + (e.type || '');
        const lab = e.type === 'cell' || e.type === 'field'
          ? `${(e.field || e.element_id).replace('lines[', 'L').replace(']', '')}=${short(e.raw, 18)}` : '';
        push({ page, bbox: e.bbox, element_id: e.element_id, layer: map, cls, label: lab,
               alwaysLabel: false, meta: { kind: e.type, raw: e.raw, conf: e.confidence, field: e.field } });
      }
    }

    for (const ex of ov.exceptions || []) {
      for (const b of ex.boxes || []) {
        if (b.page !== page) continue;
        push({ page, bbox: b.bbox, element_id: b.element_id, layer: 'exceptions',
               cls: `exc sev-${ex.severity}`, label: `${ex.code}${ex.line_no ? ' L' + ex.line_no : ''}`,
               alwaysLabel: true,
               meta: { kind: 'exception', code: ex.code, severity: ex.severity, rule: ex.rule_id,
                       elementIds: (ex.element_ids || []).slice(0, 40),
                       actual: ex.actual_value, expected: ex.expected_value } });
      }
    }
    return out;
  }

  function showResult(key, result, overlays) {
    raw = result; ov = overlays;
    Linker.reset();
    Overlay.setContract(ov.coordinate_system);
    Overlay.setLayers(ov.layers || []);
    renderVerdict();
    el('verdict-empty').hidden = true;
    el('verdict').hidden = false;
    el('jsonbox').textContent = JSON.stringify(compactResult(result, key), null, 2);
  }

  function pageOf(elements) {
    for (const id of elements || []) {
      for (const list of Object.values(ov.by_type || {})) {
        const hit = list.find(e => e.element_id === id);
        if (hit && hit.page) return hit.page;
      }
    }
    return null;
  }

  /* ------------------------------------------------------------------ verdict card */
  function renderVerdict() {
    const rec = ov.recommendation || {};
    const codes = (rec.exception_codes || []).join(' ');
    el('verdict-card').innerHTML = `
      <div class="rec"><span class="value ${esc(rec.value)}">${esc(rec.value || '–')}</span>
        <span class="sev ${esc(rec.max_severity || 'None')}">max severity ${esc(rec.max_severity || 'None')}</span>
        ${rec.reasons && rec.reasons.length ? `<span class="muted">${esc(short(rec.reasons.join('; '), 150))}</span>` : ''}</div>
      <div class="meta">
        <span>document <b>${esc((raw.request || {}).dms_doc_id || '–')}</b></span>
        <span>pages <b>${(ov.pages || []).length}</b></span>
        <span>standard <b>${esc((ov.versions || {}).standard || '–')}</b></span>
        <span>ruleset <b>${esc((ov.versions || {}).ruleset || '–')}</b></span>
        <span>validation <b>${esc((raw.request || {}).validation_id || '–')}</b></span>
        <span>invoice <b>${esc(ov.normalized_fields.invoice_num || '–')}</b></span>
        <span>PO <b>${esc(ov.normalized_fields.po_number || '–')}</b></span>
        <span>supplier <b>${esc(short(ov.normalized_fields.supplier_name || '–', 26))}</b></span>
        <span>ORG_ID <b>${esc((raw.oracle_snapshot || {}).org_id ?? '–')}</b></span>
        <span>receipt <b>${esc(((raw.oracle_snapshot || {}).receipt_nums || []).join(',') || '–')}</b></span>
        <span>step timing <b>${esc(((ov.metrics || {}).duration_ms || {}).total_ms ?? '–')} ms</b></span>
        <span>finished <b>${esc(((raw.request || {}).completed_at || '').slice(0, 19) || '–')}</b></span>
      </div>
      <div class="codes">${codes ? (rec.exception_codes || []).map(c => {
        const ex = (ov.exceptions || []).find(e => e.code === c) || {};
        return `<span class="code ${esc(ex.severity || '')}" data-code="${esc(c)}" title="${esc(ex.name || '')}">${esc(c)} · ${esc(ex.severity || '')}</span>`;
      }).join('') : '<span class="muted">no exceptions</span>'}</div>`;

    el('verdict-card').querySelectorAll('.code').forEach(chip => {
      chip.addEventListener('click', () => {
        const code = chip.dataset.code;
        const ex = (ov.exceptions || []).filter(e => e.code === code);
        focusException(ex);
      });
    });

    renderRules(); renderExceptions(); renderFields(); renderLines(); renderOracle();
  }

  /* ------------------------------------------------------------------ rules */
  function renderRules() {
    const host = el('tab-rules'); host.innerHTML = '';
    const byRule = {};
    (ov.exceptions || []).forEach(ex => { (byRule[ex.rule_id] = byRule[ex.rule_id] || []).push(ex); });
    (ov.rules || []).forEach(r => {
      const wrap = document.createElement('div'); wrap.className = 'rule';
      const exs = byRule[r.rule_id] || [];
      const els = [...new Set(exs.flatMap(e => e.element_ids || []))];
      wrap.innerHTML = `<span class="rid">${esc(r.rule_id)}</span>
        <span class="rbody"><span class="tag ${esc(r.result)}">${esc(r.result)}</span>
          ${r.halted_by ? `<span class="tag halted">halted by ${esc(r.halted_by)}</span>` : ''}
          ${exs.length ? `<span class="muted"> ${exs.map(e => e.code).join(', ')}</span>` : ''}
          ${r.detail ? `<div class="detail">${esc(r.detail)}</div>` : ''}
          ${r.data_keys && r.data_keys.length ? `<div class="detail">data: ${esc(r.data_keys.join(', '))}</div>` : ''}
        </span>`;
      if (els.length) {
        wrap.classList.add('click');
        wrap.addEventListener('click', () => {
          const page = pageOf(els);
          if (page && page !== Viewer.page) Viewer.showPage(page).then(() => Overlay.selectElements(els));
          else Overlay.selectElements(els);
        });
      }
      host.appendChild(wrap);
    });
  }

  /* ------------------------------------------------------------------ exceptions */
  function renderExceptions() {
    const host = el('tab-exceptions'); host.innerHTML = '';
    if (!(ov.exceptions || []).length) { host.innerHTML = '<p class="muted">No exceptions raised.</p>'; return; }
    const table = document.createElement('table'); table.className = 't';
    table.innerHTML = '<thead><tr><th>Exc</th><th>Sev</th><th>Rule</th><th>Actual / expected</th><th>Boxes</th></tr></thead>';
    const tb = document.createElement('tbody');
    (ov.exceptions || []).forEach(ex => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td><b class="cid">${esc(ex.code)}</b><div class="muted">${esc(short(ex.name, 34))}</div></td>
        <td><span class="sev ${esc(ex.severity)}">${esc(ex.severity)}</span></td>
        <td>${esc(ex.rule_id)}</td>
        <td class="vals">${ex.actual_value != null ? `<span class="act">${esc(short(ex.actual_value, 60))}</span><br>` : ''}
            ${ex.expected_value != null ? `<span class="exp">${esc(short(ex.expected_value, 60))}</span>` : ''}
            ${(ex.actual_value == null && ex.expected_value == null) ? '<span class="miss">no values recorded</span>' : ''}</td>
        <td class="num">${(ex.boxes || []).length}</td>`;
      tb.appendChild(tr);
      tr.title = (ex.element_ids || []).slice(0, 8).join('\n');
      Linker.bindRow(tr, { page: (ex.boxes || [])[0] ? (ex.boxes[0].page) : null,
                           elements: [ (ex.boxes || [])[0] && (ex.boxes[0].element_id) ].filter(Boolean)
                                    .concat((ex.element_ids || []).slice(0, 24)),
                           label: ex.code });
      tr.dataset.exc = ex.exception_id || '';
    });
    table.appendChild(tb);
    host.appendChild(table);
  }

  function focusException(list) {
    const ex = list[0]; if (!ex) return;
    const els = (ex.boxes || []).map(b => b.element_id).filter(Boolean).concat(ex.element_ids || []);
    const uniq = [...new Set(els)];
    const page = (ex.boxes || [])[0] ? ex.boxes[0].page : pageOf(uniq);
    const go = () => Overlay.selectElements(uniq);
    if (page && page !== Viewer.page) Viewer.showPage(page).then(go); else go();
    const row = [...document.querySelectorAll('#tab-exceptions tr')].find(r => (r.dataset.exc || '') === ex.exception_id);
    if (row) { row.classList.add('sel'); row.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }
  }

  /* ------------------------------------------------------------------ header fields */
  function renderFields() {
    const host = el('tab-fields'); host.innerHTML = '';
    const table = document.createElement('table'); table.className = 't';
    table.innerHTML = '<thead><tr><th>Field</th><th>Value read from the document</th><th>Norm.</th><th>Conf</th></tr></thead>';
    const tb = document.createElement('tbody');
    Object.entries(ov.fields || {}).forEach(([name, f]) => {
      const tr = document.createElement('tr');
      const val = f.ok ? esc(short(f.raw, 70))
                       : `<span class="bad">unread</span> <span class="muted">${esc(f.null_reason || '')}</span>`;
      tr.innerHTML = `<td>${esc(name)}</td>
        <td class="cellv">${val}</td>
        <td class="cellv muted">${esc(short(f.normalized, 40))}</td>
        <td>${fmtConf(f.confidence)}</td>`;
      Linker.bindRow(tr, { page: f.page, elements: [f.element_id].filter(Boolean), label: name });
      tb.appendChild(tr);
    });
    Object.entries(ov.signatures || {}).forEach(([name, s]) => {
      const tr = document.createElement('tr');
      /* the box for a signature carries element_id like D1-sig-receiver; find it by field_name */
      const sig = ((ov.by_type || {}).signature || []).find(e => e.field === `signatures.${name}`);
      tr.innerHTML = `<td>signature · ${esc(name)}</td>
        <td class="cellv">${s.present ? 'present' : 'not found'} <span class="muted">${esc(s.kind || '')}</span></td>
        <td class="cellv muted">page ${esc(s.page)}</td><td>${fmtConf(s.confidence)}</td>`;
      Linker.bindRow(tr, { page: s.page, elements: [sig && sig.element_id].filter(Boolean), label: 'signature ' + name });
      tb.appendChild(tr);
    });
    table.appendChild(tb);
    host.appendChild(table);
    const note = document.createElement('p');
    note.className = 'detail';
    note.textContent = 'click a row to jump to its box on the page';
    host.appendChild(note);
  }

  /* ------------------------------------------------------------------ invoice lines */
  function renderLines() {
    const host = el('tab-lines'); host.innerHTML = '';
    const lines = ov.lines || [];
    if (!lines.length) { host.innerHTML = '<p class="muted">No invoice lines were extracted.</p>'; return; }
    const matched = {};
    (ov.groups || []).forEach(g => (g.invoice_line_nos || []).forEach(n => { matched[n] = g; }));
    const table = document.createElement('table'); table.className = 't';
    table.innerHTML = `<thead><tr><th>#</th><th>Description</th><th>Qty</th><th>UOM</th><th>Unit</th><th>Amount</th><th>Match</th></tr></thead>`;
    const tb = document.createElement('tbody');
    lines.forEach(ln => {
      const c = ln.cells || {};
      const g = matched[ln.line_no];
      const tr = document.createElement('tr');
      const cell = (name) => {
        const cc = c[name] || {};
        const val = cc.ok ? cc.raw : (cc.null_reason === 'not_printed_on_invoice' ? '<span class="miss">not printed</span>'
                     : cc.raw ? esc(short(cc.raw, 20)) : '<span class="bad">unread</span>');
        return `<span class="cellv" data-el="${esc(cc.element_id || '')}" title="${esc(cc.element_id || '')} · ${esc(cc.normalized || '')}">${val}</span>`;
      };
      tr.innerHTML = `<td class="num">${esc(ln.line_no)}</td>
        <td>${cell('description')}</td><td>${cell('qty')}</td><td>${cell('uom')}</td>
        <td>${cell('unit_price')}</td><td>${cell('amount')}</td>
        <td>${g ? `<span class="tag pass">${esc(g.relation)} ${esc(g.level)}</span> <span class="muted">${esc((g.rcv_line_ids || []).join(','))}</span>`
                : '<span class="tag not_evaluated">unmatched</span>'}</td>`;
      Linker.bindRow(tr, { page: (ln.row && ln.row.page) || (ln.cells.description || {}).page,
                           elements: [ln.element_id].filter(Boolean).concat(Object.values(c).map(x => x.element_id).filter(Boolean)),
                           label: 'line ' + ln.line_no });
      tr.querySelectorAll('[data-el]').forEach(sp => {
        sp.addEventListener('click', ev => {
          ev.stopPropagation();
          const id = sp.dataset.el; if (!id) return;
          const cc = Object.values(c).find(x => x.element_id === id) || {};
          Linker.focusField({ page: cc.page, elements: [id], label: id });
        });
      });
      tb.appendChild(tr);
    });
    table.appendChild(tb);
    host.appendChild(table);

    const h = document.createElement('h4'); h.textContent = 'Line matching (V-07)'; host.appendChild(h);
    (ov.groups || []).forEach(g => {
      const d = document.createElement('div'); d.className = 'grp';
      d.innerHTML = `<div class="gh"><b>${esc(g.group_id)}</b><span class="tag pass">${esc(g.relation)} · ${esc(g.level)}</span>
          <span class="muted">inv ${(g.invoice_line_nos || []).join(',')} ↔ rcv ${(g.rcv_line_ids || []).join(',')}</span>
          ${fmtConf(g.confidence)} <span class="muted">${esc(g.source || '')}</span></div>
        <div class="detail">${esc(short(g.rationale, 180))}</div>`;
      const els = (g.invoice_line_nos || []).map(n => {
        const ln = lines.find(l => l.line_no === n); return ln && ln.element_id;
      }).filter(Boolean);
      d.classList.add('click');
      d.addEventListener('click', () => {
        const page = pageOf(els);
        const go = () => Overlay.selectElements(els);
        if (page && page !== Viewer.page) Viewer.showPage(page).then(go); else go();
      });
      host.appendChild(d);
    });
    if ((ov.ai_rejected || []).length) {
      const p = document.createElement('p'); p.className = 'detail';
      p.textContent = 'AI matcher rejected: ' + JSON.stringify(ov.ai_rejected).slice(0, 400);
      host.appendChild(p);
    }
  }

  /* ------------------------------------------------------------------ oracle receipts */
  function renderOracle() {
    const host = el('tab-oracle'); host.innerHTML = '';
    const snap = (raw && raw.oracle_snapshot) || {};
    const head = document.createElement('div');
    head.className = 'detail';
    head.innerHTML = `lookup <b>${esc(snap.lookup_path || '–')}</b> · keys ${esc(JSON.stringify(snap.query_keys || {}))}
      · row cap hit: ${snap.row_cap_hit ? 'YES' : 'no'} · fingerprint <b>${esc((snap.fingerprint || '').slice(0, 24))}</b>`;
    host.appendChild(head);
    const lines = ov.receipt_lines || [];
    if (!lines.length) { host.innerHTML += '<p class="muted">No receipt lines returned.</p>'; return; }
    const table = document.createElement('table'); table.className = 't';
    table.innerHTML = '<thead><tr><th>Receipt / line</th><th>Item</th><th>Qty</th><th>UOM</th><th>Unit</th><th>Amount</th></tr></thead>';
    const tb = document.createElement('tbody');
    lines.forEach(l => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td class="num">${esc(l.receipt_num)}-${esc(l.line)}</td>
        <td>${esc(short(l.item, 54))}</td><td class="num">${esc(l.qty)}</td>
        <td>${esc(l.uom)} <span class="muted">${esc(l.uom_group || '')}</span></td>
        <td class="num">${esc(l.unit_price)}</td><td class="num">${esc(l.line_amount)}</td>`;
      tb.appendChild(tr);
    });
    table.appendChild(tb);
    host.appendChild(table);
  }

  function compactResult(r, key) {
    return {
      contract: r.contract, request: r.request, versions: r.versions, package: r.package,
      pages: r.pages, documents: r.documents,
      extraction: { fields: (r.extraction || {}).fields, lines: ((r.extraction || {}).lines || []).length,
                    signatures: (r.extraction || {}).signatures, extra: (r.extraction || {}).extra },
      normalized_fields: r.normalized_fields,
      oracle_snapshot: { ...r.oracle_snapshot, receipt_lines: `${((r.oracle_snapshot || {}).receipt_lines || []).length} lines (see Receipts tab)` },
      line_matching: r.line_matching, rule_results: r.rule_results,
      exceptions: r.exceptions, evidence_count: (r.evidence || []).length,
      recommendation: r.recommendation, metrics: r.metrics, integrity: r.integrity,
      full_result: `/api/results/${encodeURIComponent(key || '')}`,
    };
  }

  return { renderDocs, renderUploads, boxesFor, showResult, focusException,
           get overlays() { return ov; }, get rawResult() { return raw; } };
})();
