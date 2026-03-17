import React, { useEffect, useState, useCallback, useRef } from 'react';
import { api } from '../api';
import { useAppContext } from '../App';
import ProfileModal from './modals/ProfileModal';

const QR_TTL = 55; // seconds before QR expires (~60s for WhatsApp)

const STATUS_COLOR = {
  connected:    'var(--success)',
  connecting:   'var(--warning)',
  disconnected: 'var(--text-secondary)',
  error:        'var(--error)',
};

export default function Accounts() {
  const { accountStatuses, accountQRs, setAccountQRs } = useAppContext();
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [qrModal, setQrModal] = useState(null);    // { accountId, qr_b64 }
  const [qrSecondsLeft, setQrSecondsLeft] = useState(QR_TTL);
  const qrTimerRef = useRef(null);
  const dismissedQRRef = useRef(new Set()); // accounts where user closed QR modal
  const [profileOpen, setProfileOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(null);

  const fetchAccounts = useCallback(async () => {
    try {
      const data = await api.get('/api/accounts/');
      setAccounts(data);
    } catch (e) {
      console.error('Failed to fetch accounts:', e);
    }
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchAccounts();
  }, [fetchAccounts]);

  // Poll every 3 seconds
  useEffect(() => {
    const timer = setInterval(fetchAccounts, 3000);
    return () => clearInterval(timer);
  }, [fetchAccounts]);

  // Handle new QR — only update if modal is already open for that account OR a new entry appeared
  const prevQRsRef = useRef({});
  useEffect(() => {
    const prev = prevQRsRef.current;
    for (const [accountId, qr_b64] of Object.entries(accountQRs)) {
      if (prev[accountId] !== qr_b64) {
        // New or updated QR for this account
        setQrModal((current) => {
          // Don't reopen if user explicitly dismissed this account's QR
          if (dismissedQRRef.current.has(accountId)) return current;
          // Auto-open only if modal already open for this account, or nothing open
          if (!current || current.accountId === accountId) {
            return { accountId, qr_b64 };
          }
          return current;
        });
        setQrSecondsLeft(QR_TTL);
        if (qrTimerRef.current) clearInterval(qrTimerRef.current);
        qrTimerRef.current = setInterval(() => {
          setQrSecondsLeft((s) => {
            if (s <= 1) { clearInterval(qrTimerRef.current); return 0; }
            return s - 1;
          });
        }, 1000);
      }
    }
    prevQRsRef.current = { ...accountQRs };
  }, [accountQRs]);

  // When QR expires — poll /qr endpoint every 3s until a new QR arrives
  const qrPollRef = useRef(null);
  useEffect(() => {
    if (qrSecondsLeft === 0 && qrModal) {
      qrPollRef.current = setInterval(async () => {
        try {
          const data = await api.get(`/api/accounts/${qrModal.accountId}/qr`);
          if (data.qr_b64 && data.qr_b64 !== qrModal.qr_b64) {
            setQrModal((prev) => ({ ...prev, qr_b64: data.qr_b64 }));
            setQrSecondsLeft(QR_TTL);
            clearInterval(qrPollRef.current);
            if (qrTimerRef.current) clearInterval(qrTimerRef.current);
            qrTimerRef.current = setInterval(() => {
              setQrSecondsLeft((s) => {
                if (s <= 1) { clearInterval(qrTimerRef.current); return 0; }
                return s - 1;
              });
            }, 1000);
          }
        } catch (_) {}
      }, 3000);
    } else {
      if (qrPollRef.current) { clearInterval(qrPollRef.current); qrPollRef.current = null; }
    }
    return () => { if (qrPollRef.current) clearInterval(qrPollRef.current); };
  }, [qrSecondsLeft, qrModal]);

  // Auto-close QR modal when account connects
  useEffect(() => {
    if (qrModal && accountStatuses[qrModal.accountId]?.status === 'connected') {
      dismissedQRRef.current.add(qrModal.accountId);
      setQrModal(null);
      if (qrTimerRef.current) clearInterval(qrTimerRef.current);
      if (qrPollRef.current) clearInterval(qrPollRef.current);
      setAccountQRs((prev) => { const n = { ...prev }; delete n[qrModal.accountId]; return n; });
    }
  }, [accountStatuses, qrModal]);

  // Cleanup timers on unmount
  useEffect(() => () => {
    if (qrTimerRef.current) clearInterval(qrTimerRef.current);
    if (qrPollRef.current) clearInterval(qrPollRef.current);
  }, []);

  // Merge WS status updates into accounts list
  const mergedAccounts = accounts.map((acc) => {
    const ws = accountStatuses[acc.id];
    if (ws) {
      return {
        ...acc,
        status: ws.status,
        phone: ws.phone || acc.phone,
      };
    }
    return acc;
  });

  function closeQrModal() {
    if (qrModal) dismissedQRRef.current.add(qrModal.accountId);
    setQrModal(null);
    if (qrTimerRef.current) clearInterval(qrTimerRef.current);
    if (qrPollRef.current) clearInterval(qrPollRef.current);
  }

  async function addAccount() {
    setLoading(true);
    try {
      const result = await api.post('/api/accounts/', {});
      dismissedQRRef.current.clear(); // allow QR to show for new account
      await fetchAccounts();
    } catch (e) {
      alert(`Failed to add account: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function deleteAccount(id) {
    try {
      await api.del(`/api/accounts/${id}`);
      setAccounts((prev) => prev.filter((a) => a.id !== id));
      setAccountQRs((prev) => { const n = { ...prev }; delete n[id]; return n; });
      dismissedQRRef.current.add(id);
      if (qrModal?.accountId === id) {
        setQrModal(null);
        if (qrTimerRef.current) clearInterval(qrTimerRef.current);
        if (qrPollRef.current) clearInterval(qrPollRef.current);
      }
    } catch (e) {
      alert(`Failed to delete account: ${e.message}`);
    }
    setDeleteConfirm(null);
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">Accounts</h1>
        <div className="page-actions">
          <button
            className="btn btn-secondary"
            onClick={() => setProfileOpen(true)}
          >
            Auto Profile
          </button>
          <button className="btn btn-primary" onClick={addAccount} disabled={loading}>
            {loading ? 'Adding…' : '+ Add Account'}
          </button>
        </div>
      </div>

      {mergedAccounts.length === 0 ? (
        <div className="empty-state">
          <p>No accounts yet. Click "Add Account" to scan a QR code.</p>
        </div>
      ) : (
        <div className="accounts-list">
          {mergedAccounts.map((acc) => (
            <div key={acc.id} className="account-card">
              <div className="account-info">
                <span
                  className="status-dot"
                  style={{ background: STATUS_COLOR[acc.status] || 'var(--text-secondary)' }}
                  title={acc.status}
                />
                <div className="account-details">
                  <span className="account-id">{acc.id}</span>
                  {acc.phone && (
                    <span className="account-phone">+{acc.phone}</span>
                  )}
                  <span className="account-status-text">{acc.status}</span>
                </div>
              </div>
              <div className="account-stats">
                <span className="stat-item sent" title="Sent">
                  ✓ {acc.sent_count ?? 0}
                </span>
                <span className="stat-item error" title="Errors">
                  ✗ {acc.error_count ?? 0}
                </span>
              </div>
              <div className="account-actions">
                <button
                  className="btn btn-sm btn-ghost"
                  onClick={() => setDeleteConfirm(acc.id)}
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* QR Modal */}
      {qrModal && (
        <div className="modal-overlay" onClick={closeQrModal}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Scan QR Code</h2>
              <button className="modal-close" onClick={closeQrModal}>✕</button>
            </div>
            <div className="modal-body" style={{ textAlign: 'center' }}>
              <p style={{ marginBottom: '1rem', color: 'var(--text-secondary)' }}>
                Account: <strong>{qrModal.accountId}</strong>
              </p>
              <p style={{ marginBottom: '1rem', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                Open WhatsApp on your phone → Linked Devices → Link a Device
              </p>
              <div style={{ position: 'relative', display: 'inline-block' }}>
                <img
                  src={`data:image/png;base64,${qrModal.qr_b64}`}
                  alt="QR Code"
                  style={{
                    width: 260,
                    height: 260,
                    borderRadius: 8,
                    background: '#fff',
                    padding: 8,
                    opacity: qrSecondsLeft === 0 ? 0.3 : 1,
                    transition: 'opacity 0.3s',
                    display: 'block',
                  }}
                />
                {qrSecondsLeft === 0 && (
                  <div style={{
                    position: 'absolute', inset: 0,
                    display: 'flex', flexDirection: 'column',
                    alignItems: 'center', justifyContent: 'center',
                    gap: 6, pointerEvents: 'none',
                  }}>
                    <span style={{ fontSize: '2rem' }}>⏳</span>
                    <span style={{ color: 'var(--text-primary)', fontWeight: 600, fontSize: '0.95rem' }}>QR expired</span>
                  </div>
                )}
              </div>
              <div style={{ marginTop: 10, fontSize: '0.85rem', color: qrSecondsLeft === 0 ? 'var(--text-secondary)' : qrSecondsLeft <= 10 ? 'var(--error)' : 'var(--text-secondary)', fontWeight: 500 }}>
                {qrSecondsLeft === 0
                  ? 'Waiting for new QR…'
                  : `QR expires in ${qrSecondsLeft}s`}
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={closeQrModal}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirm Modal */}
      {deleteConfirm && (
        <div className="modal-overlay" onClick={() => setDeleteConfirm(null)}>
          <div className="modal-box modal-sm" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Confirm Delete</h2>
              <button className="modal-close" onClick={() => setDeleteConfirm(null)}>✕</button>
            </div>
            <div className="modal-body">
              <p>Delete account <strong>{deleteConfirm}</strong>? This cannot be undone.</p>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setDeleteConfirm(null)}>
                Cancel
              </button>
              <button className="btn btn-danger" onClick={() => deleteAccount(deleteConfirm)}>
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {profileOpen && <ProfileModal onClose={() => setProfileOpen(false)} />}
    </div>
  );
}
