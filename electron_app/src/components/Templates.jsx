import React, { useEffect, useState } from 'react';
import { api } from '../api';
import { useAppContext } from '../App';

const EMPTY_FORM = {
  name: '',
  text: '',
  url: '',
  button_text: '',
  button_url: '',
};

export default function Templates() {
  const { setTemplateToUse, setPage } = useAppContext();
  const [templates, setTemplates] = useState([]);
  const [editingId, setEditingId] = useState(null);   // null = no edit / 'new' = create
  const [form, setForm] = useState(EMPTY_FORM);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  async function loadTemplates() {
    try {
      const data = await api.get('/api/templates/');
      setTemplates(data);
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    loadTemplates();
  }, []);

  function openCreate() {
    setForm(EMPTY_FORM);
    setEditingId('new');
    setError('');
  }

  function openEdit(tmpl) {
    setForm({
      name: tmpl.name || '',
      text: tmpl.text || '',
      url: tmpl.url || '',
      button_text: tmpl.button_text || '',
      button_url: tmpl.button_url || '',
    });
    setEditingId(tmpl.id);
    setError('');
  }

  function cancelEdit() {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setError('');
  }

  async function saveTemplate() {
    if (!form.name.trim()) { setError('Name is required.'); return; }
    if (!form.text.trim()) { setError('Message text is required.'); return; }

    setSaving(true);
    setError('');
    try {
      if (editingId === 'new') {
        const created = await api.post('/api/templates/', form);
        setTemplates((prev) => [...prev, created]);
      } else {
        const updated = await api.put(`/api/templates/${editingId}`, form);
        setTemplates((prev) => prev.map((t) => (t.id === editingId ? updated : t)));
      }
      cancelEdit();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function deleteTemplate(id) {
    try {
      await api.del(`/api/templates/${id}`);
      setTemplates((prev) => prev.filter((t) => t.id !== id));
    } catch (e) {
      setError(e.message);
    }
    setDeleteConfirm(null);
  }

  function useTemplate(tmpl) {
    setTemplateToUse(tmpl);
    setPage('broadcast');
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">Templates</h1>
        <button className="btn btn-primary" onClick={openCreate}>
          + New Template
        </button>
      </div>

      {error && <div className="status-message error">{error}</div>}

      {/* Inline editor */}
      {editingId !== null && (
        <div className="card template-editor">
          <h3>{editingId === 'new' ? 'New Template' : 'Edit Template'}</h3>
          <div className="form-group">
            <label className="form-label">Name</label>
            <input
              className="form-input"
              placeholder="Template name"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label className="form-label">
              Message
              <span className="char-count">{form.text.length}</span>
            </label>
            <textarea
              className="form-textarea"
              rows={5}
              placeholder="Message text…"
              value={form.text}
              onChange={(e) => setForm((f) => ({ ...f, text: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label className="form-label">URL (optional)</label>
            <input
              className="form-input"
              type="url"
              placeholder="https://example.com"
              value={form.url}
              onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
            />
          </div>
          <div className="form-row">
            <div className="form-group flex-1">
              <label className="form-label">Button Text</label>
              <input
                className="form-input"
                placeholder="Open Website"
                value={form.button_text}
                onChange={(e) => setForm((f) => ({ ...f, button_text: e.target.value }))}
              />
            </div>
            <div className="form-group flex-1">
              <label className="form-label">Button URL</label>
              <input
                className="form-input"
                type="url"
                placeholder="https://example.com"
                value={form.button_url}
                onChange={(e) => setForm((f) => ({ ...f, button_url: e.target.value }))}
              />
            </div>
          </div>
          <div className="editor-actions">
            <button className="btn btn-secondary" onClick={cancelEdit} disabled={saving}>
              Cancel
            </button>
            <button className="btn btn-primary" onClick={saveTemplate} disabled={saving}>
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      )}

      {/* Template list */}
      {templates.length === 0 && editingId === null ? (
        <div className="empty-state">
          <p>No templates yet. Create one to reuse messages quickly.</p>
        </div>
      ) : (
        <div className="templates-list">
          {templates.map((tmpl) => (
            <div key={tmpl.id} className="template-card card">
              <div className="template-info">
                <h4 className="template-name">{tmpl.name}</h4>
                <p className="template-preview">
                  {tmpl.text.length > 120 ? tmpl.text.slice(0, 120) + '…' : tmpl.text}
                </p>
                {(tmpl.url || tmpl.button_text) && (
                  <div className="template-meta">
                    {tmpl.url && <span className="tag">🔗 {tmpl.url}</span>}
                    {tmpl.button_text && (
                      <span className="tag accent">
                        🔘 {tmpl.button_text}
                      </span>
                    )}
                  </div>
                )}
              </div>
              <div className="template-actions">
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => useTemplate(tmpl)}
                  title="Use in Broadcast"
                >
                  Use
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => openEdit(tmpl)}
                >
                  Edit
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => setDeleteConfirm(tmpl.id)}
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Delete confirm */}
      {deleteConfirm && (
        <div className="modal-overlay" onClick={() => setDeleteConfirm(null)}>
          <div className="modal-box modal-sm" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Confirm Delete</h2>
              <button className="modal-close" onClick={() => setDeleteConfirm(null)}>✕</button>
            </div>
            <div className="modal-body">
              <p>Delete this template? This cannot be undone.</p>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setDeleteConfirm(null)}>Cancel</button>
              <button className="btn btn-danger" onClick={() => deleteTemplate(deleteConfirm)}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
