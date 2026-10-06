/* UI logic test — runs the real browser modules outside a browser.
 *
 *   node test_ui_logic.mjs <fixture.json>          # fixture = {result, overlays}
 *
 * The portal UI has no build step and no DOM library, so the modules use only a handful of DOM
 * calls; this file stubs exactly those, evaluates the real module sources in one shared context,
 * and asserts what they produce for a real contract result.  It exists for one specific failure
 * mode: the JS reading a key the API does not send (fields.raw vs fields.raw_value), which in a
 * browser is simply an empty panel and no error.
 */
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const fixturePath = process.argv[2];
if (!fixturePath) { console.error('usage: node test_ui_logic.mjs <fixture.json>'); process.exit(2); }
const { result, overlays } = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));

/* ------------------------------------------------------------------ minimal DOM */
class El {
  constructor(tag = 'div', id = '') {
    this.tagName = String(tag).toUpperCase(); this.id = id; this.className = '';
    this.children = []; this.style = {}; this.dataset = {};
    this._class = new Set(); this._html = ''; this.textContent = '';
    this.listeners = {}; this.hidden = false; this.disabled = false;
    this.clientWidth = 900; this.clientHeight = 700; this.scrollTop = 0;
    this.naturalWidth = 900; this.naturalHeight = 1275; this.complete = true;
  }
  get classList() {
    const self = this;
    const parse = () => String(self.className || '').split(/\s+/).filter(Boolean).forEach(c => self._class.add(c));
    return {
      add: (...c) => { parse(); c.forEach(x => self._class.add(x)); self.className = [...self._class].join(' '); },
      remove: (...c) => { parse(); c.forEach(x => self._class.delete(x)); self.className = [...self._class].join(' '); },
      toggle: (c, force) => { parse(); const on = force === undefined ? !self._class.has(c) : !!force;
                              on ? self._class.add(c) : self._class.delete(c);
                              self.className = [...self._class].join(' '); return on; },
      contains: (c) => { parse(); return self._class.has(c); },
    };
  }
  get innerHTML() { return this._html; }
  set innerHTML(v) { this._html = String(v); if (v === '') this.children = []; }
  appendChild(n) {
    if (n && n.tagName === 'FRAGMENT') { n.children.forEach(c => this.children.push(c)); n.children = []; }
    else this.children.push(n);
    return n;
  }
  removeChild(n) { this.children = this.children.filter(c => c !== n); return n; }
  remove() {}
  insertAdjacentHTML(_p, html) { this._html += String(html); }
  addEventListener(t, fn) { (this.listeners[t] ||= []).push(fn); }
  removeEventListener(t, fn) { this.listeners[t] = (this.listeners[t] || []).filter(f => f !== fn); }
  fire(t, ev = {}) { (this.listeners[t] || []).forEach(fn => fn({ target: this, preventDefault() {}, stopPropagation() {}, ...ev })); }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  querySelectorAll(sel) {
    const want = String(sel).match(/\.([A-Za-z0-9_-]+)/g)?.map(s => s.slice(1)) || [];
    const out = [];
    const walk = (node) => {
      for (const c of node.children) {
        if (want.every(k => c._class.has(k) || String(c.className).split(/\s+/).includes(k))) out.push(c);
        walk(c);
      }
    };
    walk(this);
    return out;
  }
  closest() { return null; }
  scrollIntoView() { this._scrolled = true; }
  setAttribute(k, v) { this['attr_' + k] = v; }
  getAttribute(k) { return this['attr_' + k] ?? null; }
  getBoundingClientRect() { return { left: 0, top: 0, width: 100, height: 40 }; }
  focus() {} blur() {}
  get text() { return (this.textContent || '') + (this._html || '') + this.children.map(c => c.text).join(' '); }
  countClass(cls) {
    let n = this._class.has(cls) || String(this.className).split(/\s+/).includes(cls) ? 1 : 0;
    for (const c of this.children) n += c.countClass(cls);
    if (this._html) n += (this._html.match(new RegExp('class="[^"]*\\b' + cls + '\\b', 'g')) || []).length;
    return n;
  }
}

const registry = new Map();
const toasts = [];                // what the operator would actually see
const document = {
  getElementById: (id) => { if (!registry.has(id)) registry.set(id, new El('div', id)); return registry.get(id); },
  createElement: (tag) => new El(tag),
  createDocumentFragment: () => new El('fragment'),
  querySelectorAll: () => [],
  querySelector: () => null,
  addEventListener() {},
  body: new El('body'),
};

const sandbox = {
  document, console,
  toast: (msg, isErr) => { toasts.push({ msg: String(msg), err: !!isErr }); },   // app.js provides the real one
  window: { addEventListener() {}, devicePixelRatio: 1, innerWidth: 1600, matchMedia: () => ({ matches: false }) },
  navigator: { clipboard: { writeText: async () => {} } },
  fetch: async () => ({ ok: true, status: 200, json: async () => ({}), text: async () => '', body: null }),
  setTimeout, clearTimeout, setInterval, clearInterval, URL, URLSearchParams, AbortController,
  requestAnimationFrame: (fn) => setTimeout(fn, 0),
  ResizeObserver: class { constructor() {} observe() {} unobserve() {} disconnect() {} },
  IntersectionObserver: class { constructor() {} observe() {} unobserve() {} disconnect() {} },
  Event: class { constructor(t) { this.type = t; } },
  CustomEvent: class { constructor(t, o) { this.type = t; Object.assign(this, o || {}); } },
};
sandbox.globalThis = sandbox;
sandbox.self = sandbox;

const MODULES = ['api.js', 'viewer.js', 'bbox-overlay.js', 'interaction.js', 'panels.js'];
const src = MODULES.map(f => `\n/* ==== ${f} ==== */\n` + fs.readFileSync(path.join(HERE, 'static', 'js', f), 'utf8')).join('\n')
  // top-level consts are script-scoped in a vm context, so publish them for the assertions
  + '\nglobalThis.__portal = { API, Viewer, Overlay, Linker, Panels };\n';
vm.createContext(sandbox);
vm.runInContext(src, sandbox, { filename: 'portal-modules.js' });
const { API, Overlay, Viewer, Linker, Panels } = sandbox.__portal;
/* ------------------------------------------------------------------ assertions */
let failures = 0;
const check = (name, cond, extra = '') => {
  if (cond) console.log('  ok   ' + name);
  else { failures++; console.log('  FAIL ' + name + (extra ? ' — ' + extra : '')); }
};

try {
  Overlay.init();
  Overlay.setContract(overlays.coordinate_system);
  Overlay.setLayers(overlays.layers);
  check('layer chips built from the API layer list',
        registry.get('layers').children.length === overlays.layers.length,
        `${registry.get('layers').children.length} vs ${overlays.layers.length}`);

  await Viewer.open({ kind: 'dms', id: 'DMS-9001' }, overlays.pages.length, overlays.page_meta);
  // app.js loads a result first (that is what fills Panels' view of the overlays)
  Panels.showResult('DMS-9001', result, overlays);
  /* Expectations come out of the payload under test, never out of one favourite document: the same
   * harness has to stay honest for every result the portal can serve (it used to hardcode E01,
   * "26/2691", "PCS" and 595x842, so DMS-25/36/99 produced eight false failures). */
  const frag = (s) => String(s ?? '').trim().slice(0, 12).replace(/[&<>"]/g, '');
  const fieldEntries = Object.entries(overlays.fields || {});
  /* Work on the page that carries the invoice, not page 1: on DMS-25 / DMS-99 page 1 is a cover sheet
   * and every field, cell and exception box sits on page 2. */
  const tally = new Map();
  for (const [, f] of fieldEntries) {
    if (!f || !f.page) continue;
    const withExc = (overlays.exceptions || []).some(e => (e.boxes || []).some(b => b.page === f.page));
    tally.set(f.page, (tally.get(f.page) || 0) + 1 + (withExc ? 10 : 0));
  }
  const PAGE = [...tally.entries()].sort((a, b) => b[1] - a[1])[0][0];
  await Viewer.showPage(PAGE);
  const dim = overlays.pages.find(p => p.page_no === PAGE) || overlays.pages[0];
  const boxes = Panels.boxesFor(PAGE);
  const pageField = fieldEntries.find(([, f]) => f && f.page === PAGE);
  const okField = fieldEntries.find(([, f]) => f.ok && f.raw);
  const badField = fieldEntries.find(([, f]) => !f.ok);
  const pageLine = (overlays.lines || []).find(l => l.page === PAGE && Object.keys(l.cells || {}).length);
  const cellEntry = pageLine && Object.entries(pageLine.cells).find(([, c]) => c && c.raw && c.element_id);
  const excHere = (overlays.exceptions || []).find(e => (e.boxes || []).some(b => b.page === PAGE))
                  || (overlays.exceptions || [])[0];
  const excRule = ((result.rule_results || []).find(r => excHere && r.rule_id === excHere.rule_id)) || {};
  const badDiffs = Object.entries(((excRule.data || {}).diffs) || {})
    .filter(([, v]) => Math.abs(parseFloat(String(v).replace(/,/g, '')) || 0) > 1e-9);

  check(`boxes assembled for the invoice page (${PAGE})`, boxes.length > 0, `n=${boxes.length}`);
  check(`a header field box exists (${pageField[0]})`,
        boxes.some(b => b.layer === 'header_fields' && b.element_id === pageField[1].element_id),
        JSON.stringify(boxes.filter(b => b.layer === 'header_fields').map(b => b.element_id).slice(0, 6)));
  // labels are truncated on purpose, so compare against the start of the value, not a token from it
  check('field label carries the raw value (not undefined)',
        boxes.some(b => b.element_id === pageField[1].element_id && (b.label || '').includes(frag(pageField[1].raw))),
        JSON.stringify(boxes.find(b => b.element_id === pageField[1].element_id)?.label));
  if (cellEntry) {
    check('cell label carries the raw value',
          boxes.some(b => b.element_id === cellEntry[1].element_id && (b.label || '').includes(frag(cellEntry[1].raw))),
          JSON.stringify(boxes.find(b => b.element_id === cellEntry[1].element_id)?.label));
  }
  check('an exception box exists and is labelled with its code',
        excHere ? boxes.some(b => b.layer === 'exceptions' && new RegExp('^' + excHere.code).test(b.label || ''))
                : boxes.every(b => b.layer !== 'exceptions'),
        JSON.stringify(boxes.filter(b => b.layer === 'exceptions').map(b => b.label)));
  check('words are on the ocr_words layer (off by default)',
        boxes.some(b => b.layer === 'ocr_words') && Overlay.layerOn('ocr_words') === false);

  Overlay.render(boxes);
  const drawn = registry.get('overlay').children.filter(c => c.tagName === 'DIV').length;
  const expect = boxes.filter(b => Overlay.layerOn(b.layer)).length;
  check('only enabled layers draw boxes', drawn === expect, `${drawn} drawn vs ${expect} enabled`);
  check('no box is drawn at a NaN position',
        boxes.every(b => { const r = Overlay.toCss(b.bbox); return r && Number.isFinite(r.left) && Number.isFinite(r.top); }));
  const ruleText = registry.get('tab-rules').text;
  check('rules panel shows every rule id and its result',
        (result.rule_results || []).every(r => ruleText.includes(r.rule_id))
        && (result.rule_results || []).every(r => new RegExp(r.result, 'i').test(ruleText)),
        ruleText.slice(0, 140));
  const excText = registry.get('tab-exceptions').text;
  // an exception whose actual/expected the contract left null must still say what failed:
  // for V-03 the number that differs lives in rule_results[].data.diffs
  const wantExcValues = !excHere ? '' : (badDiffs.length ? badDiffs[0][0]
    : (excHere.actual_value != null ? frag(excHere.actual_value)
       : excHere.expected_value != null ? frag(excHere.expected_value)
       : 'no values recorded'));
  check('exception panel shows code and the values that actually differ',
        excText.includes(excHere.code) && excText.includes(wantExcValues), excText.slice(0, 160));
  check('a failed total check is never shown as two identical numbers',
        !badDiffs.length || !/read [^v]*vs /.test(excText) || excText.includes(badDiffs[0][0]),
        excText.slice(0, 160));
  const fieldText = registry.get('tab-fields').text;
  check('field panel shows the value read, or the reason it was not',
        (!okField || fieldText.includes(frag(okField[1].raw)))
        && (!badField || fieldText.includes('unread')
            && (!badField[1].null_reason || fieldText.includes(badField[1].null_reason))),
        fieldText.slice(0, 200));
  const lineText = registry.get('tab-lines').text;
  check('line panel shows cell value' + (pageLine && pageLine.uom_group ? ' and UOM group' : ''),
        !cellEntry || lineText.includes(frag(cellEntry[1].raw))
        && (!pageLine.uom_group || lineText.includes(String(pageLine.uom_group))), lineText.slice(0, 200));
  check('verdict card shows the recommendation',
        registry.get('verdict-card').text.includes(result.recommendation.value),
        registry.get('verdict-card').text.slice(0, 120));
  check('raw JSON panel filled', registry.get('jsonbox').text.length > 50);
  check('cross-highlight registry bound element ids to rows', Linker.registrySize >= 4, `size=${Linker.registrySize}`);

  const rows = Linker.focusBox({ element_id: pageField[1].element_id });
  check('clicking a box finds its row (BBoxToField)', rows >= 1, `rows=${rows}`);
  check('the clicked element is selected on the overlay',
        Overlay.selectedIds.includes(pageField[1].element_id), JSON.stringify(Overlay.selectedIds));
  const selBoxes = registry.get('overlay').querySelectorAll('.bbox.sel');
  const dimBoxes = registry.get('overlay').querySelectorAll('.bbox.dim');
  // the same element can be drawn on two layers (a field that is also exception evidence), so the
  // assertion is: every .sel box is one of the selected ids, and everything else is dimmed
  check('selected boxes are marked and the rest dimmed',
        selBoxes.length >= 1 && dimBoxes.length > 0
        && selBoxes.every(d => Overlay.selectedIds.includes(d.dataset.element)),
        `sel=${selBoxes.length} dim=${dimBoxes.length}`);

  if (cellEntry) {
    await Linker.focusField({ page: PAGE, elements: [cellEntry[1].element_id], label: cellEntry[0] });
    check('clicking a cell selects its box (FieldToBBox)', Overlay.selectedIds.includes(cellEntry[1].element_id));
  }

  const tl = Overlay.toCss([0.5, 0.25, 0.1, 0.05]);
  check('[x,y,w,h] normalised top-left converts correctly',
        Math.abs(tl.left - 450) < 1 && Math.abs(tl.top - 175) < 1 && Math.abs(tl.width - 90) < 1 && Math.abs(tl.height - 35) < 1,
        JSON.stringify(tl));

  Overlay.setContract({ origin: 'bottom-left', unit: 'point', range: [0, 1], bbox_format: '[x1, y1, x2, y2]' });
  const bl = Overlay.toCss([50, 200, 100, 240]);   // PDF points, corner pair, origin bottom-left
  // the page under test may be landscape (DMS-36 is 842x595), so the maths follows the payload
  const W = dim.width_pt, H = dim.height_pt;
  check('point + corner + bottom-left converts correctly',
        Math.abs(bl.left - (50 / W) * 900) < 1 && Math.abs(bl.width - (50 / W) * 900) < 1
        && Math.abs(bl.top - (700 - (240 / H) * 700)) < 1 && Math.abs(bl.height - (40 / H) * 700) < 1,
        JSON.stringify(bl) + ` page ${W}x${H}`);
  Overlay.setContract({ origin: 'top-left', unit: 'pixel', range: [0, 1], bbox_format: '[x, y, w, h]' });
  const px = Overlay.toCss([150, 300, 60, 40]);    // pixels of the source raster (900x1275 here)
  check('pixel unit scales by the displayed raster',
        Math.abs(px.left - 150) < 1 && Math.abs(px.top - 300 * (700 / 1275)) < 1, JSON.stringify(px));
  Overlay.setContract(overlays.coordinate_system);

  Overlay.toggle('header_fields', false);
  Overlay.render(Panels.boxesFor(1));
  const after = registry.get('overlay').children.length;
  check('disabling a layer removes its boxes', after < drawn, `${after} after vs ${drawn} before`);
  Overlay.toggle('header_fields', true);

  Linker.clear();
  check('clear empties the selection', Overlay.selectedIds.length === 0);

  /* ---- failure paths: an error the operator cannot read is the bug this portal exists to avoid */
  const realFetch = sandbox.fetch;
  sandbox.fetch = async () => ({
    ok: false, status: 404, statusText: 'Not Found', json: async () => ({}),
    text: async () => '{"detail":"DMS-9 is not in Paperless-ngx"}',
  });
  let apiErr = null;
  try { await API.get('/api/documents/9/meta'); } catch (e) { apiErr = e.message; }
  check('API client shows the portal sentence rather than the JSON envelope',
        !!apiErr && /not in Paperless-ngx/.test(apiErr) && !/"detail"/.test(apiErr), apiErr);

  toasts.length = 0;
  registry.get('page-img').fire('error');
  await new Promise(r => setTimeout(r, 10));
  check('a page that will not render says why',
        toasts.some(t => t.err && /not rendered/.test(t.msg) && /not in Paperless/.test(t.msg)),
        JSON.stringify(toasts));
  sandbox.fetch = realFetch;
} catch (err) {
  failures++;
  console.log('  FAIL threw: ' + (err && err.stack || err));
}

console.log(failures ? `\nUI logic: ${failures} failure(s)` : '\nUI logic: all checks passed');
process.exit(failures ? 1 : 0);
