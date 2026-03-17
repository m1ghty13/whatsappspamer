const BASE = 'http://localhost:8765';

async function request(method, path, body, isFormData = false) {
  const opts = {
    method,
    headers: isFormData ? {} : { 'Content-Type': 'application/json' },
  };

  if (body !== undefined) {
    opts.body = isFormData ? body : JSON.stringify(body);
  }

  const resp = await fetch(`${BASE}${path}`, opts);

  if (!resp.ok) {
    let msg = `HTTP ${resp.status}`;
    try {
      const err = await resp.json();
      msg = err.detail || err.message || msg;
    } catch (_) {}
    throw new Error(msg);
  }

  return resp.json();
}

export const api = {
  get:    (path)          => request('GET',    path),
  post:   (path, body)    => request('POST',   path, body),
  put:    (path, body)    => request('PUT',    path, body),
  del:    (path)          => request('DELETE', path),
  upload: (path, formData) => request('POST',  path, formData, true),
};

/**
 * Creates a WebSocket connection to the backend.
 * @param {(event: object) => void} onMessage - callback for parsed JSON events
 * @returns {{ close: () => void }}
 */
export function createWebSocket(onMessage) {
  let ws = null;
  let reconnectTimer = null;
  let stopped = false;

  function connect() {
    if (stopped) return;

    ws = new WebSocket('ws://localhost:8765/ws');

    ws.onopen = () => {
      console.log('[WS] Connected');
      // Keep-alive ping every 30s
      if (ws._pingTimer) clearInterval(ws._pingTimer);
      ws._pingTimer = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send('ping');
        }
      }, 30000);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data !== 'pong') {
          onMessage(data);
        }
      } catch (e) {
        // ignore non-JSON
      }
    };

    ws.onclose = () => {
      if (ws._pingTimer) clearInterval(ws._pingTimer);
      if (!stopped) {
        console.log('[WS] Disconnected, reconnecting in 2s…');
        reconnectTimer = setTimeout(connect, 2000);
      }
    };

    ws.onerror = (err) => {
      console.warn('[WS] Error:', err);
    };
  }

  connect();

  return {
    close() {
      stopped = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (ws) {
        if (ws._pingTimer) clearInterval(ws._pingTimer);
        ws.close();
      }
    },
  };
}
