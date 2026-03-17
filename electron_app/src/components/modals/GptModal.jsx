import React, { useEffect, useState } from 'react';
import { api } from '../../api';

const MODELS = ['gpt-4.1-mini', 'gpt-4o-mini', 'gpt-4o', 'gpt-4-turbo'];

const DEFAULT = {
  enabled: false,
  api_key: '',
  model: 'gpt-4.1-mini',
  temperature: 0.3,
  skip_proxy: false,
  has_key: false,
};

export default function GptModal({ onClose }) {
  const [form, setForm] = useState(DEFAULT);
  const [showKey, setShowKey] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api.get('/api/config/gpt').then((data) => {
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
      const result = await api.post('/api/config/gpt/test', form);
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
      await api.post('/api/config/gpt', form);
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
          <h2>GPT Settings</h2>
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
              Enable GPT text variations
            </label>
          </div>

          <div className="form-group">
            <label className="form-label">
              API Key
              {form.has_key && <span className="tag success" style={{ marginLeft: 8 }}>Saved</span>}
            </label>
            <div className="input-with-action">
              <input
                className="form-input"
                type={showKey ? 'text' : 'password'}
                placeholder={form.has_key ? '••••••••••••••••' : 'sk-…'}
                value={form.api_key}
                onChange={(e) => set('api_key', e.target.value)}
                autoComplete="off"
              />
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setShowKey((v) => !v)}
              >
                {showKey ? 'Hide' : 'Show'}
              </button>
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Model</label>
            <select
              className="form-select"
              value={form.model}
              onChange={(e) => set('model', e.target.value)}
            >
              {MODELS.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">
              Temperature
              <span className="char-count">{form.temperature.toFixed(2)}</span>
            </label>
            <input
              type="range"
              className="form-range"
              min={0}
              max={1}
              step={0.05}
              value={form.temperature}
              onChange={(e) => set('temperature', parseFloat(e.target.value))}
            />
            <div className="range-labels">
              <span>Precise (0)</span>
              <span>Creative (1)</span>
            </div>
          </div>

          <div className="form-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={form.skip_proxy}
                onChange={(e) => set('skip_proxy', e.target.checked)}
              />
              Skip proxy for GPT requests
            </label>
          </div>

          {testResult && (
            <div className={`status-message ${testResult.ok ? 'success' : 'error'}`}>
              {testResult.ok ? 'Connection successful!' : `Error: ${testResult.error}`}
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button
            className="btn btn-secondary"
            onClick={handleTest}
            disabled={testing || (!form.api_key && !form.has_key)}
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
