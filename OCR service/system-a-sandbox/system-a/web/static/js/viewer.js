/* Page viewer: page navigation, zoom, and two render modes.
   - raster (default): the server rasterises the page with the same PyMuPDF path perception uses,
     so a box drawn here sits on exactly the pixels the model was shown.
   - vector: PDF.js vendored under /pdf (same origin, no CDN), for a selectable text layer;
     falls back to raster when the vendor bundle is missing.  Both modes expose the same displayed
     pixel size to the overlay, which is what keeps the bbox geometry identical. */
'use strict';

const Viewer = (() => {
  const PDFJS_MODULE = '/pdf/pdf.min.mjs';          // vendored in web/static/vendor/pdfjs
  const PDFJS_WORKER = '/pdf/pdf.worker.min.mjs';
  const el = {};
  let target = null;              // {kind:'dms'|'upload', id?, key?}
  let pageCount = 1, pageNo = 1;
  let zoom = 1, fitWidth = 900;
  let mode = 'raster';
  let pdfjsDoc = null, pdfjsLib = null, pdfjsFor = '';
  let pagePt = { width_pt: null, height_pt: null };
  const listeners = new Set();
  let rotating = null;            // in-flight page promise

  function bind() {
    el.wrap = document.getElementById('page-wrap');
    el.frame = document.getElementById('page-frame');
    el.img = document.getElementById('page-img');
    el.canvas = document.getElementById('page-canvas');
    el.ind = document.getElementById('pageind');
    el.zoomind = document.getElementById('zoomind');
    el.empty = document.getElementById('viewer-empty');
    el.stage = document.getElementById('stage');
    el.img.addEventListener('load', () => layout());
  }

  function baseUrl() {
    return target.kind === 'dms' ? `/api/documents/${target.id}` : `/api/uploads/${encodeURIComponent(target.key)}`;
  }

  function pageUrl(n, dpi) { return `${baseUrl()}/page/${n}.png${dpi ? '?dpi=' + dpi : ''}`; }

  function open(t, pages, metaPages) {
    target = t;
    pageCount = Math.max(1, pages || 1);
    pdfjsDoc = null; pdfjsFor = '';
    el.empty.hidden = false; el.wrap.hidden = true;
    showPage(1, metaPages);
  }

  async function showPage(n, metaPages) {
    pageNo = Math.min(Math.max(1, n || 1), pageCount);
    el.empty.hidden = true; el.wrap.hidden = false;
    el.ind.textContent = `${pageNo} / ${pageCount}`;
    const pm = (metaPages || []).find(p => p.page_no === pageNo);
    if (pm) pagePt = { width_pt: pm.width_pt, height_pt: pm.height_pt };
    rotating = (mode === 'vector') ? renderVector() : renderRaster();
    try {
      await rotating;
    } catch (e) {
      // vector failures never reach an <img>, so they would vanish into the console
      toast(`page ${pageNo} could not be rendered: ${e.message}`, true);
    }
    rotating = null;
    layout();
  }

  /* A failed <img> carries no status, so ask the endpoint once.  The portal answers a document that
     has left Paperless-ngx with a sentence, and the operator sees that instead of a broken image. */
  function reportRasterFailure(url, page) {
    fetch(url, { headers: { Accept: 'application/json' } })
      .then(async (r) => {
        if (r.ok) {   // the endpoint is fine, the <img> just did not draw — say that, not binary garbage
          toast(`page ${page} is served fine but the browser did not draw it — reload the page`, true);
          return;
        }
        const body = await r.text().catch(() => '');
        let msg = body;
        try { const d = JSON.parse(body).detail; if (typeof d === 'string' && d) msg = d; } catch (_) { /* html or empty */ }
        toast(`page ${page} not rendered: ${msg.slice(0, 200) || r.status}`, true);
      })
      .catch(() => toast(`page ${page} not rendered (the raster request itself failed)`, true));
  }

  function renderRaster() {
    el.canvas.hidden = true; el.img.hidden = false;
    const dpi = Math.min(300, Math.max(100, Math.round(110 * zoom) + 60));
    el.img.src = pageUrl(pageNo, dpi);
    return new Promise(res => {
      const ok = () => { el.img.removeEventListener('load', ok); pagePt.display_px = [el.img.naturalWidth, el.img.naturalHeight]; res(); };
      el.img.addEventListener('load', ok, { once: true });
      el.img.addEventListener('error', () => {
        el.img.removeEventListener('load', ok);
        reportRasterFailure(pageUrl(pageNo, dpi), pageNo);
        res();
      }, { once: true });
      if (el.img.complete && el.img.naturalWidth) ok();
    });
  }

  async function renderVector() {
    const key = target.kind === 'dms' ? `dms${target.id}` : target.key;
    if (!pdfjsLib) {
      try {
        const m = await import(PDFJS_MODULE);
        pdfjsLib = m;
        pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS_WORKER;
      } catch (e) {
        toast(`PDF.js is not available — staying in raster mode (${e.message})`, true);
        setMode('raster');
        return renderRaster();
      }
    }
    if (!pdfjsDoc || pdfjsFor !== key) {
      const task = pdfjsLib.getDocument({ url: baseUrl() + '/pdf' });
      pdfjsDoc = await task.promise; pdfjsFor = key;
    }
    const page = await pdfjsDoc.getPage(pageNo);
    const vp1 = page.getViewport({ scale: 1 });
    pagePt = { width_pt: vp1.width, height_pt: vp1.height };
    const cssW = Math.round(fitWidth * zoom);
    const scale = (cssW / vp1.width) * (window.devicePixelRatio || 1);
    const vp = page.getViewport({ scale });
    el.img.hidden = true; el.canvas.hidden = false;
    el.canvas.width = vp.width; el.canvas.height = vp.height;
    el.canvas.style.width = cssW + 'px';
    el.frame.style.width = cssW + 'px';
    el.frame.style.height = Math.round(vp.height / (window.devicePixelRatio || 1)) + 'px';
    await page.render({ canvasContext: el.canvas.getContext('2d'), viewport: vp }).promise;
  }

  function setMode(m) {
    mode = m;
    document.querySelectorAll('#rendermode button').forEach(b => b.classList.toggle('active', b.dataset.mode === m));
    showPage(pageNo);
  }

  /* frame size for raster mode + a re-layout signal for the overlay */
  function layout() {
    if (!target) return;
    const stageW = Math.max(320, (el.stage.clientWidth || 800) - 30);
    fitWidth = stageW;
    if (mode === 'raster') {
      const natW = el.img.naturalWidth || 1, natH = el.img.naturalHeight || 1;
      const w = Math.round(Math.max(220, stageW * zoom));
      el.frame.style.width = w + 'px';
      el.frame.style.height = Math.round(w * (natH / natW)) + 'px';
    }
    el.zoomind.textContent = Math.round(zoom * 100) + '%';
    listeners.forEach(cb => { try { cb(); } catch (e) { console.error(e); } });
  }

  function onLayout(cb) { listeners.add(cb); return () => listeners.delete(cb); }

  function fit() { zoom = 1; layout(); }
  function zoomBy(f) { zoom = Math.min(6, Math.max(0.25, zoom * f)); if (mode === 'vector') showPage(pageNo); else layout(); }
  function next() { if (pageNo < pageCount) showPage(pageNo + 1); }
  function prev() { if (pageNo > 1) showPage(pageNo - 1); }

  /* displayed size of the page, in CSS pixels — the overlay's coordinate target */
  function size() {
    const w = el.frame.clientWidth || 600;
    const h = el.frame.clientHeight || 600;
    return { w, h, pt: pagePt };
  }

  bind();
  new ResizeObserver(() => layout()).observe(el.stage);
  return { open, showPage, next, prev, fit, zoomBy, setMode, onLayout, size,
           get page() { return pageNo; }, get count() { return pageCount; },
           get mode() { return mode; }, get target() { return target; } };
})();
