import React, { useEffect, useRef, useState } from 'react';
import { api } from '../../api';

const DEFAULT = { name: '', photo_path: '' };

export default function ProfileModal({ onClose }) {
  const [form, setForm] = useState(DEFAULT);
  const [photoPreview, setPhotoPreview] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const fileInputRef = useRef(null);

  useEffect(() => {
    api.get('/api/accounts/auto_profile').then((data) => {
      setForm({ name: data.name || '', photo_path: data.photo_path || '' });
      // If there's a saved photo path, we can't show preview (just show path)
    }).catch((e) => setError(e.message));
  }, []);

  function handlePhotoChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;

    // Show local preview
    const reader = new FileReader();
    reader.onload = (ev) => {
      setPhotoPreview(ev.target.result);
      setForm((f) => ({ ...f, photo_path: file.path || file.name }));
    };
    reader.readAsDataURL(file);
  }

  function clearPhoto() {
    setPhotoPreview(null);
    setForm((f) => ({ ...f, photo_path: '' }));
    if (fileInputRef.current) fileInputRef.current.value = '';
  }

  async function handleSave() {
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      await api.post('/api/accounts/auto_profile', form);
      setSuccess('Profile settings saved. New accounts will use this profile.');
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  const displayPhoto = photoPreview || (form.photo_path ? null : null);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Auto Profile</h2>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        <div className="modal-body">
          {error && <div className="status-message error">{error}</div>}
          {success && <div className="status-message success">{success}</div>}

          <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem', fontSize: '0.9rem' }}>
            This name and photo will be applied automatically when a new account connects.
          </p>

          {/* Photo preview */}
          <div className="profile-photo-section">
            <div className="profile-photo-wrap">
              {photoPreview ? (
                <img
                  src={photoPreview}
                  alt="Profile"
                  className="profile-photo-circle"
                />
              ) : (
                <div className="profile-photo-placeholder">
                  {form.name ? form.name[0].toUpperCase() : '?'}
                </div>
              )}
            </div>
            <div className="profile-photo-actions">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                style={{ display: 'none' }}
                onChange={handlePhotoChange}
              />
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => fileInputRef.current?.click()}
              >
                Choose Photo
              </button>
              {(photoPreview || form.photo_path) && (
                <button className="btn btn-ghost btn-sm" onClick={clearPhoto}>
                  Clear
                </button>
              )}
            </div>
          </div>

          {form.photo_path && !photoPreview && (
            <div className="form-group">
              <label className="form-label">Current Photo Path</label>
              <input
                className="form-input"
                value={form.photo_path}
                onChange={(e) => setForm((f) => ({ ...f, photo_path: e.target.value }))}
                placeholder="/path/to/photo.jpg"
              />
            </div>
          )}

          <div className="form-group">
            <label className="form-label">Display Name</label>
            <input
              className="form-input"
              placeholder="Your WhatsApp name"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
