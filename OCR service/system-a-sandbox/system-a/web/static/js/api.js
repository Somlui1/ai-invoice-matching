/* API client.  The portal's frontend talks only to these endpoints — never to Paperless,
   Oracle or LiteLLM directly. */
'use strict';

const API = {
  async get(path) {
    const r = await fetch(path, { headers: { Accept: 'application/json' } });
    if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 300)}`);
    return r.json();
  },

  async post(path, body) {
    const r = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 300)}`);
    return r.status === 204 ? null : r.json();
  },

  async upload(file) {
    const fd = new FormData();
    fd.append('file', file, file.name);
    const r = await fetch('/api/upload', { method: 'POST', body: fd });
    if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 300)}`);
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
      if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 300)}`);
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
