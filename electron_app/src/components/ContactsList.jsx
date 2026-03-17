import React, { useRef, useState } from 'react';
import { api } from '../api';
import { useAppContext } from '../App';

export default function ContactsList() {
  const { selectedContacts, setSelectedContacts, setPage } = useAppContext();

  const [allContacts, setAllContacts] = useState([]);
  const [checked, setChecked] = useState(new Set());
  const [search, setSearch] = useState('');
  const [uploading, setUploading] = useState(false);
  const [validCount, setValidCount] = useState(0);
  const [invalidCount, setInvalidCount] = useState(0);
  const [error, setError] = useState('');

  const fileInputRef = useRef(null);

  async function handleFileChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setError('');

    const formData = new FormData();
    formData.append('file', file);

    try {
      const result = await api.upload('/api/contacts/upload', formData);
      setAllContacts(result.contacts);
      setChecked(new Set(result.contacts.map((_, i) => i)));
      setValidCount(result.total);
      setInvalidCount(result.invalid);

      // Update selected contacts in context
      setSelectedContacts(result.contacts);
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
      // Reset file input
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  function handleCheckAll(e) {
    if (e.target.checked) {
      setChecked(new Set(filtered.map((_, i) => allContacts.indexOf(filtered[i]))));
    } else {
      setChecked(new Set());
    }
  }

  function handleCheck(idx, checked_) {
    setChecked((prev) => {
      const next = new Set(prev);
      if (checked_) next.add(idx);
      else next.delete(idx);
      return next;
    });
  }

  function applySelection() {
    const sel = allContacts.filter((_, i) => checked.has(i));
    setSelectedContacts(sel);
    setPage('broadcast');
  }

  function handleClear() {
    setAllContacts([]);
    setChecked(new Set());
    setSelectedContacts([]);
    setValidCount(0);
    setInvalidCount(0);
    setError('');
  }

  const filtered = allContacts.filter((c) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return c.phone.includes(q) || (c.name || '').toLowerCase().includes(q);
  });

  const allFilteredChecked =
    filtered.length > 0 &&
    filtered.every((c) => checked.has(allContacts.indexOf(c)));

  const checkedCount = checked.size;

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">Contacts</h1>
        <div className="page-actions">
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.txt"
            style={{ display: 'none' }}
            onChange={handleFileChange}
          />
          <button
            className="btn btn-secondary"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
          >
            {uploading ? 'Loading…' : '📂 Load File'}
          </button>
          {allContacts.length > 0 && (
            <>
              <button className="btn btn-ghost" onClick={handleClear}>
                Clear
              </button>
              <button className="btn btn-primary" onClick={applySelection}>
                Use {checkedCount} contacts →
              </button>
            </>
          )}
        </div>
      </div>

      {/* Stats */}
      {(validCount > 0 || invalidCount > 0) && (
        <div className="contacts-stats">
          <span className="tag success">Valid: {validCount}</span>
          {invalidCount > 0 && (
            <span className="tag error">Invalid: {invalidCount}</span>
          )}
          <span className="tag">Selected: {checkedCount}</span>
        </div>
      )}

      {error && <div className="status-message error">{error}</div>}

      {allContacts.length > 0 && (
        <>
          {/* Search */}
          <div className="search-bar">
            <input
              className="form-input"
              type="text"
              placeholder="Search by phone or name…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          {/* Table */}
          <div className="contacts-table-wrap card">
            <table className="contacts-table">
              <thead>
                <tr>
                  <th>
                    <input
                      type="checkbox"
                      checked={allFilteredChecked}
                      onChange={handleCheckAll}
                    />
                  </th>
                  <th>#</th>
                  <th>Phone</th>
                  <th>Name</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((contact, fi) => {
                  const origIdx = allContacts.indexOf(contact);
                  return (
                    <tr key={origIdx} className={checked.has(origIdx) ? 'selected' : ''}>
                      <td>
                        <input
                          type="checkbox"
                          checked={checked.has(origIdx)}
                          onChange={(e) => handleCheck(origIdx, e.target.checked)}
                        />
                      </td>
                      <td className="row-num">{fi + 1}</td>
                      <td className="phone-cell">+{contact.phone}</td>
                      <td className="name-cell">{contact.name || '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {allContacts.length === 0 && !uploading && !error && (
        <div className="empty-state">
          <p>Load a CSV or TXT file to import contacts.</p>
          <p style={{ fontSize: '0.85rem', marginTop: '0.5rem', color: 'var(--text-secondary)' }}>
            CSV must have a <code>phone</code> column. TXT has one number per line.
          </p>
        </div>
      )}
    </div>
  );
}
