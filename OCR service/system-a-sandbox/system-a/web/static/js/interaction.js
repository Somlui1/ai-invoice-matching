/* Bidirectional cross-highlighting (Phase 4).

   FieldToBBox : clicking a field value, a table cell, a rule row or an exception card asks the
                 overlay to switch to that box's page, outline the matching boxes and dim the rest.
   BBoxToField : clicking a box on the page looks the box's ``element_id`` up in the same registry
                 and selects + scrolls the row that produced it.

   Both directions share one registry keyed by the contract's ``element_id`` (D1-f-invoice_num,
   D1-L3-uom, …), so nothing depends on screen geometry or text matching. */
'use strict';

const Linker = (() => {
  const rowsByElement = new Map();       // element_id -> Set(HTMLElement)
  const specsByRow = new Map();          // HTMLElement -> {page, elements, codes, label}
  let boxClickBridge = null;             // (box) -> void, installed by app.js
  let lastFocus = null;

  function reset() {
    rowsByElement.clear();
    specsByRow.clear();
    lastFocus = null;
  }

  /* A panel row becomes highlightable: give it the element ids it stands for and its page. */
  function bindRow(rowEl, spec) {
    if (!rowEl) return rowEl;
    const s = { page: spec.page || null, elements: spec.elements || [], codes: spec.codes || [],
                label: spec.label || '' };
    specsByRow.set(rowEl, s);
    s.elements.forEach(id => {
      if (!rowsByElement.has(id)) rowsByElement.set(id, new Set());
      rowsByElement.get(id).add(rowEl);
    });
    rowEl.dataset.page = s.page || '';
    rowEl.classList.add('click');
    rowEl.addEventListener('click', ev => {
      ev.stopPropagation();
      focusField(s);
    });
    return rowEl;
  }

  /* ---- FieldToBBox ---- */
  async function focusField(spec) {
    lastFocus = { kind: 'field', spec };
    markRows([spec]);
    if (spec.page && spec.page !== Viewer.page) {
      await Viewer.showPage(spec.page);
    }
    Overlay.selectElements(spec.elements);
    revealBoxes(spec.elements);
  }

  /* ---- BBoxToField ---- */
  function focusBox(box) {
    const ids = [];
    if (box.element_id) ids.push(box.element_id);
    (box.meta && box.meta.elementIds || []).forEach(id => ids.includes(id) || ids.push(id));
    lastFocus = { kind: 'box', box, ids };
    Overlay.selectElements(ids);
    const rows = new Set();
    ids.forEach(id => (rowsByElement.get(id) || []).forEach(r => rows.add(r)));
    markRows([...rows].map(r => specsByRow.get(r)).filter(Boolean));
    return rows.size;
  }

  /* shared visual selection on the panel side */
  function markRows(specs) {
    document.querySelectorAll('#verdict tr.sel, #verdict .grp.sel, #verdict .exc.sel').forEach(e => e.classList.remove('sel'));
    let first = null;
    for (const s of specs || []) {
      for (const [rowEl, spec] of specsByRow.entries()) {
        if (spec !== s) continue;
        rowEl.classList.add('sel');
        if (!first) first = rowEl;
      }
    }
    if (first) first.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  function revealBoxes(ids) {
    /* if the target box belongs to a layer that is switched off, say so instead of looking broken */
    const hidden = (ids || []).filter(id => !Overlay.hasElement(id));
    if (hidden.length && ids.length === hidden.length) {
      toast('the box for this value is on a layer that is currently hidden — switch the layer on', true);
    }
  }

  function clear() {
    Overlay.clearSelection();
    document.querySelectorAll('#verdict tr.sel, #verdict .grp.sel, #verdict .exc.sel').forEach(e => e.classList.remove('sel'));
    lastFocus = null;
  }

  /* box clicks arriving from the overlay */
  function onBox(cb) { boxClickBridge = cb; }
  function handleBox(box) {
    const n = focusBox(box);
    if (boxClickBridge) boxClickBridge(box, n);
  }

  return { reset, bindRow, focusField, focusBox, handleBox, clear, onBox,
           get registrySize() { return rowsByElement.size; } };
})();
