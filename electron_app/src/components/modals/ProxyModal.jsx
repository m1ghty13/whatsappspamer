import React, { useEffect, useState } from 'react';
import { api } from '../../api';

const DEFAULT = {
  enabled: false,
  type: 'HTTP',
  host: '',
  port: '',
  login: '',
  password: '',
};

export default function ProxyModal({ onClose }) {
  const [form, setForm] = useState(DEFAULT);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api.get('/api/config/proxy').then((data) => {
      setForm({ ...DEFAULT, ...data });
    }).catch((e) => setError(e.message));
  }, []);

  function set(key, value) {
    setForm((f) => ({ ...f, [key]: value }));
    setTestResult(null);
  }

  async function handleTest() {
    setTesting(true);
    setTestResult(null);
    setError('');
    try {
      const result = await api.post('/api/config/proxy/test', form);
      setTestResult(result);
    } catch (e) {
      setTestResult({ ok: false, error: e.message });
    } finally {
      setTesting(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    setError('');
    try {
      await api.post('/api/config/proxy', form);
      onClose();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Proxy Settings</h2>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        <div className="modal-body">
          {error && <div className="status-message error">{error}</div>}

          <div className="form-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(e) => set('enabled', e.target.checked)}
              />
              Enable proxy
            </label>
          </div>

          <div className="form-group">
            <label className="form-label">Proxy Type</label>
            <div className="radio-group">
              {['HTTP', 'SOCKS5'].map((t) => (
                <label key={t} className="radio-label">
                  <input
                    type="radio"
                    name="proxy-type"
                    value={t}
                    checked={form.type === t}
                    onChange={() => set('type', t)}
                  />
                  {t}
                </label>
              ))}
            </div>
          </div>

          <div className="form-row">
            <div className="form-group flex-2">
              <label className="form-label">Host</label>
              <input
                className="form-input"
                placeholder="proxy.example.com"
                value={form.host}
                onChange={(e) => set('host', e.target.value)}
              />
            </div>
            <div className="form-group flex-1">
              <label className="form-label">Port</label>
              <input
                className="form-input"
                placeholder="8080"
                value={form.port}
                onChange={(e) => set('port', e.target.value)}
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group flex-1">
              <label className="form-label">Username</label>
              <input
                className="form-input"
                placeholder="(optional)"
                value={form.login}
                onChange={(e) => set('login', e.target.value)}
                autoComplete="off"
              />
            </div>
            <div className="form-group flex-1">
              <label className="form-label">Password</label>
              <input
                className="form-input"
                type="password"
                placeholder="(optional)"
                value={form.password}
                onChange={(e) => set('password', e.target.value)}
                autoComplete="off"
              />
            </div>
          </div>

          {testResult && (
            <div className={`status-message ${testResult.ok ? 'success' : 'error'}`}>
              {testResult.ok
                ? `Connected! Your IP: ${testResult.ip}`
                : `Test failed: ${testResult.error}`}
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button
            className="btn btn-secondary"
            onClick={handleTest}
            disabled={testing || !form.host}
          >
            {testing ? 'Testing…' : 'Test'}
          </button>
          <div style={{ flex: 1 }} />
          <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
