/* BBox overlay engine (Phase 2 + the drawing half of Phase 4).

   Geometry rule: the overlay never assumes a bounding-box convention.  It reads
   ``package.coordinate_system`` from the Contract 3.0 result — origin, unit, range and
   ``bbox_format`` — and converts accordingly.  (The current contract stores normalised
   [0,1] boxes as [x, y, w, h] relative to the rendered page after rotation correction.)

   Boxes are DOM divs layered over the page; word boxes are numerous (up to ~2.5k) so they stay
   non-interactive and are only created when their layer is switched on. */
'use strict';

const Overlay = (() => {
  let host = null;
  let cs = { origin: 'top-left', unit: 'normalized', range: [0, 1], bbox_format: '[x, y, w, h]' };
  let boxes = [];                 // current page boxes
  let layers = [];                // [{id,label,count,color,default,on}]
  let selected = new Set();       // element ids currently highlighted
  let dimOthers = false;
  let clickCb = null;
  const byElement = new Map();    // element_id -> [div]

  function init() {
    host = document.getElementById('overlay');
    buildLayerChips();
  }

  function setContract(contract) { cs = Object.assign({}, cs, contract || {}); }

  function setLayers(defs) {
    const prev = new Map(layers.map(l => [l.id, l.on]));
    layers = (defs || []).map(l => ({
      id: l.id, label: l.label, count: l.count || 0, color: l.color || '#46b7ff',
      on: prev.has(l.id) ? prev.get(l.id) : !!l.default,
    }));
    buildLayerChips();
  }

  function layerOn(id) {
    const l = layers.find(x => x.id === id);
    return !l || l.on;
  }

  function toggle(id, on) {
    const l = layers.find(x => x.id === id);
    if (!l) return;
    l.on = (on === undefined) ? !l.on : !!on;
    buildLayerChips();
    render(lastForPage, true);
  }

  function buildLayerChips() {
    const wrap = document.getElementById('layers');
    if (!wrap) return;
    wrap.innerHTML = '';
    layers.forEach(l => {
      const chip = document.createElement('button');
      chip.className = 'layer' + (l.on ? ' on' : '');
      chip.type = 'button';
      chip.innerHTML = `<span class="sw" style="background:${l.color}"></span>${l.label}<span class="n">${l.count}</span>`;
      chip.addEventListener('click', () => toggle(l.id));
      wrap.appendChild(chip);
    });
  }

  /* ---- coordinate conversion, driven by coordinate_system ---- */
  function toCss(b) {
    if (!Array.isArray(b) || b.length < 4) return null;
    const { w: W, h: H, pt } = Viewer.size();
    const fmt = String(cs.bbox_format || '[x, y, w, h]').replace(/\s+/g, '').toLowerCase();
    let x = b[0], y = b[1], bw, bh;
    if (fmt.includes('x1') || fmt.includes('x0')) { bw = b[2] - b[0]; bh = b[3] - b[1]; }
    else { bw = b[2]; bh = b[3]; }

    const unit = String(cs.unit || 'normalized').toLowerCase();
    const range = Array.isArray(cs.range) && cs.range[1] ? cs.range : [0, 1];
    let sx, sy;
    if (unit.startsWith('norm')) {                       // normalised to a declared range
      sx = W / range[1]; sy = H / range[1];
    } else if (unit === 'point' || unit === 'pt') {       // PDF points (1/72 inch)
      sx = W / ((pt && pt.width_pt) || 612); sy = H / ((pt && pt.height_pt) || 792);
    } else if (unit === 'pixel' || unit === 'px') {       // raster pixels of the source render
      const d = (pt && pt.display_px) || [W, H];
      sx = W / d[0]; sy = H / d[1];
    } else { sx = 1; sy = 1; }

    let top = y * sy;
    if (String(cs.origin || 'top-left') === 'bottom-left') top = H - (y + bh) * sy;
    return { left: x * sx, top, width: Math.max(3, bw * sx), height: Math.max(3, bh * sy) };
  }

  let lastForPage = [];

  /* boxes: [{id, element_id, page, bbox, layer, cls, label, meta}] */
  function render(list, keepSelection) {
    if (!host) init();
    lastForPage = list || [];
    byElement.clear();
    if (!keepSelection && !selected.size) dimOthers = false;
    host.innerHTML = '';
    const frag = document.createDocumentFragment();
    for (const b of lastForPage) {
      if (!b.layer && b.layer !== '') continue;
      if (!layerOn(b.layer)) continue;
      const r = toCss(b.bbox);
      if (!r) continue;
      const d = document.createElement('div');
      d.className = 'bbox ' + (b.cls || '') + (clickable(b) ? ' clickable' : '');
      d.style.left = Math.round(r.left) + 'px';
      d.style.top = Math.round(r.top) + 'px';
      d.style.width = Math.round(r.width) + 'px';
      d.style.height = Math.round(r.height) + 'px';
      d.dataset.id = b.id || '';
      d.dataset.element = b.element_id || '';
      d.dataset.layer = b.layer;
      if (clickable(b)) {
        d.addEventListener('click', ev => {
          ev.stopPropagation();
          if (clickCb) clickCb(b, ev);
        });
      }
      if (b.label && b.layer !== 'ocr_words' && (selected.size === 0 || b.alwaysLabel)) {
        const lab = document.createElement('span');
        lab.className = 'lab';
        lab.textContent = b.label;
        d.appendChild(lab);
      }
      if (b.element_id) {
        if (!byElement.has(b.element_id)) byElement.set(b.element_id, []);
        byElement.get(b.element_id).push(d);
      }
      frag.appendChild(d);
    }
    host.appendChild(frag);
    applySelection();
  }

  function clickable(b) {
    if (b.layer === 'ocr_words') return false;
    return b.clickable !== false;
  }

  function relayout() { render(lastForPage, true); }

  /* ---- highlight (Phase 4 visual half) ---- */
  function selectElements(ids, dim) {
    selected = new Set(ids || []);
    dimOthers = dim !== false && selected.size > 0;
    applySelection();
    const first = [...selected].flatMap(e => byElement.get(e) || [])[0];
    if (first) first.scrollIntoView({ block: 'center', inline: 'center', behavior: 'smooth' });
  }

  function applySelection() {
    host.querySelectorAll('.bbox').forEach(d => {
      const on = selected.size > 0 && d.dataset.element && selected.has(d.dataset.element);
      d.classList.toggle('sel', !!on);
      d.classList.toggle('dim', dimOthers && !on);
    });
  }

  function clearSelection() { selected = new Set(); dimOthers = false; applySelection(); }

  function elementIds() { return [...byElement.keys()]; }
  function hasElement(id) { return byElement.has(id); }
  function onBoxClick(cb) { clickCb = cb; }

  return { init, setContract, setLayers, toggle, layerOn, render, relayout, selectElements,
           clearSelection, onBoxClick, elementIds, hasElement, toCss, get selectedIds() { return [...selected]; } };
})();
