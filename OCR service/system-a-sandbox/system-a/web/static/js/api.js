/* API client.  The portal's frontend talks only to these endpoints — never to Paperless,
   Oracle or LiteLLM directly. */
'use strict';

/* FastAPI answers every failure as {"detail": "<one readable sentence>"}.  Show that sentence and
   keep the status code in front of it, so a toast reads "404 DMS-9 is not in Paperless-ngx" instead
   of a JSON envelope the operator has to decode. */
async function failure(r) {
  const body = (await r.text().catch(() => '')).slice(0, 300);
  let msg = body;
  try {
    const detail = JSON.parse(body).detail;
    if (typeof detail === 'string' && detail) msg = detail;
  } catch (_) { /* not JSON (a proxy error page, an empty body) — keep the raw text */ }
  return new Error(`${r.status} ${msg || r.statusText || 'no message from the portal'}`);
}

const API = {
  async get(path) {
    const r = await fetch(path, { headers: { Accept: 'application/json' } });
    if (!r.ok) throw await failure(r);
    return r.json();
  },

  async post(path, body) {
    const r = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!r.ok) throw await failure(r);
    return r.status === 204 ? null : r.json();
  },

  async upload(file) {
    const fd = new FormData();
    fd.append('file', file, file.name);
    const r = await fetch('/api/upload', { method: 'POST', body: fd });
    if (!r.ok) throw await failure(r);
    return r.json();
  },

  /* POST + streamed response body.  The backend frames Server-Sent Events
     ("event: <type>\ndata: <json>\n\n"); fetch() is used instead of EventSource because
     EventSource cannot issue a POST.  Returns a controller with .abort(). */
  stream(path, onEvent) {
    const ctrl = new AbortController();
    const done = (async () => {
      const r = await fetch(path, { method: 'POST', signal: ctrl.signal,
                                    headers: { Accept: 'text/event-stream' } });
      if (!r.ok) throw await failure(r);
      const reader = r.body.getReader();
      const dec = new TextDecoder('utf-8');
      let buf = '';
      for (;;) {
        const { value, done: fin } = await reader.read();
        if (fin) break;
        buf += dec.decode(value, { stream: true });
        let i;
        while ((i = buf.indexOf('\n\n')) >= 0) {
          const frame = buf.slice(0, i); buf = buf.slice(i + 2);
          let type = 'message', data = null;
          for (const line of frame.split('\n')) {
            if (line.startsWith('event:')) type = line.slice(6).trim();
            else if (line.startsWith('data:')) {
              try { data = JSON.parse(line.slice(5).trim()); } catch (_) { data = { raw: line.slice(5).trim() }; }
            }
          }
          try { onEvent(type, data || {}); } catch (e) { console.error('event handler', e); }
        }
      }
    })();
    return { promise: done, abort: () => ctrl.abort() };
  },
};
