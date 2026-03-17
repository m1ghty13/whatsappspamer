import React, {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  useCallback,
} from 'react';
import { createWebSocket } from './api';
import Accounts from './components/Accounts';
import Broadcast from './components/Broadcast';
import ContactsList from './components/ContactsList';
import Templates from './components/Templates';
import ProxyModal from './components/modals/ProxyModal';
import GptModal from './components/modals/GptModal';
import ProfileModal from './components/modals/ProfileModal';

// ── Context ────────────────────────────────────────────────────────────────────

export const AppContext = createContext(null);

export function useAppContext() {
  return useContext(AppContext);
}

// ── Nav items ──────────────────────────────────────────────────────────────────

const NAV_ITEMS = [
  { id: 'contacts',  label: 'Contacts',  icon: '👥' },
  { id: 'broadcast', label: 'Broadcast', icon: '📣' },
  { id: 'templates', label: 'Templates', icon: '📋' },
  { id: 'accounts',  label: 'Accounts',  icon: '📱' },
];

const API = 'http://localhost:8765';

// ── License helpers ────────────────────────────────────────────────────────────

/**
 * Poll /api/license/status until backend is ready (up to ~30 s).
 * Returns the status object or null on timeout.
 */
async function fetchLicenseStatus(retries = 40, delayMs = 800) {
  for (let i = 0; i < retries; i++) {
    try {
      const res = await fetch(`${API}/api/license/status`);
      if (res.ok) return await res.json();
    } catch (_) { /* backend not ready yet */ }
    await new Promise((r) => setTimeout(r, delayMs));
  }
  return null;
}

// ── License screens ────────────────────────────────────────────────────────────

function ActivationScreen({ onActivated }) {
  const [code, setCode]       = useState('');
  const [error, setError]     = useState('');
  const [loading, setLoading] = useState(false);

  async function handleActivate() {
    const trimmed = code.trim();
    if (!trimmed) { setError('Введите код доступа.'); return; }
    setLoading(true);
    setError('');
    try {
      const res  = await fetch(`${API}/api/license/activate`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ code: trimmed }),
      });
      const data = await res.json();
      if (data.status === 'active') {
        onActivated();
      } else {
        setError(data.message || 'Ошибка активации.');
      }
    } catch {
      setError('Не удалось подключиться к серверу. Попробуйте позже.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={styles.gateWrap}>
      <div style={styles.gateCard}>
        <div style={styles.gateIcon}>🔐</div>
        <h2 style={styles.gateTitle}>Активация</h2>
        <p style={styles.gateSubtitle}>
          Введите код доступа для активации приложения
        </p>
        <input
          style={styles.gateInput}
          type="text"
          placeholder="Код доступа"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleActivate()}
          disabled={loading}
          autoFocus
        />
        {error && <p style={styles.gateError}>{error}</p>}
        <button
          style={{ ...styles.gateBtn, opacity: loading ? 0.6 : 1 }}
          onClick={handleActivate}
          disabled={loading}
        >
          {loading ? 'Проверка...' : 'Активировать'}
        </button>
      </div>
    </div>
  );
}

function BlockedScreen() {
  return (
    <div style={styles.gateWrap}>
      <div style={styles.gateCard}>
        <div style={styles.gateIcon}>🚫</div>
        <h2 style={{ ...styles.gateTitle, color: '#e74c3c' }}>Доступ заблокирован</h2>
        <p style={styles.gateSubtitle}>
          Ваш код доступа был отозван или истёк.
          <br />Обратитесь к разработчику для получения нового кода.
        </p>
      </div>
    </div>
  );
}

function LoadingScreen() {
  return (
    <div style={styles.gateWrap}>
      <div style={styles.gateCard}>
        <div style={{ ...styles.gateIcon, animation: 'spin 1s linear infinite' }}>⏳</div>
        <p style={styles.gateSubtitle}>Инициализация...</p>
      </div>
    </div>
  );
}

// ── App ────────────────────────────────────────────────────────────────────────

export default function App() {
  // License gate: "loading" | "not_activated" | "active" | "blocked"
  const [licenseStatus, setLicenseStatus] = useState('loading');

  const [page, setPage] = useState('broadcast');
  const [wsEvents, setWsEvents] = useState([]);
  const [accountStatuses, setAccountStatuses] = useState({});
  const [accountQRs, setAccountQRs] = useState({});
  const [broadcastStatus, setBroadcastStatus] = useState(null);
  const [broadcastLogs, setBroadcastLogs] = useState([]);

  // Modal state
  const [showProxy,   setShowProxy]   = useState(false);
  const [showGpt,     setShowGpt]     = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [settingsTab, setSettingsTab] = useState('proxy');

  const [selectedContacts, setSelectedContacts] = useState([]);
  const [templateToUse, setTemplateToUse]       = useState(null);

  const wsRef = useRef(null);

  // ── License check on mount ─────────────────────────────────────────────────

  useEffect(() => {
    fetchLicenseStatus().then((data) => {
      if (!data) {
        // Backend never responded — show activation screen as fallback
        setLicenseStatus('not_activated');
        return;
      }
      setLicenseStatus(data.status);
    });
  }, []);

  // ── WebSocket (only when active) ───────────────────────────────────────────

  const handleWsEvent = useCallback((event) => {
    switch (event.type) {
      case 'account_status':
        setAccountStatuses((prev) => ({
          ...prev,
          [event.id]: { id: event.id, status: event.status, phone: event.phone },
        }));
        break;
      case 'account_qr':
        setAccountQRs((prev) => ({ ...prev, [event.id]: event.qr_b64 }));
        break;
      case 'broadcast_progress':
        setBroadcastStatus((prev) => ({
          ...(prev || {}),
          done: event.done,
          total: event.total,
          lastPhone: event.phone,
        }));
        break;
      case 'broadcast_log':
        setBroadcastLogs((prev) => [...prev.slice(-49), event.text]);
        break;
      case 'broadcast_done':
        setBroadcastStatus((prev) => ({
          ...(prev || {}),
          status: event.stopped ? 'stopped' : 'done',
          sent: event.sent,
          errors: event.errors,
        }));
        break;
      default:
        setWsEvents((prev) => [...prev.slice(-99), event]);
    }
  }, []);

  useEffect(() => {
    if (licenseStatus !== 'active') return;
    const handle = createWebSocket(handleWsEvent);
    wsRef.current = handle;
    return () => handle.close();
  }, [licenseStatus, handleWsEvent]);

  // ── License gate rendering ─────────────────────────────────────────────────

  if (licenseStatus === 'loading') return <LoadingScreen />;

  if (licenseStatus === 'not_activated') {
    return <ActivationScreen onActivated={() => setLicenseStatus('active')} />;
  }

  if (licenseStatus === 'blocked') {
    return <BlockedScreen />;
  }

  // ── Main UI (licenseStatus === 'active') ───────────────────────────────────

  function openSettings(tab = 'proxy') {
    setSettingsTab(tab);
    if (tab === 'proxy')   setShowProxy(true);
    else if (tab === 'gpt')     setShowGpt(true);
    else if (tab === 'profile') setShowProfile(true);
  }

  const ctx = {
    accountStatuses,
    accountQRs,
    setAccountQRs,
    wsEvents,
    broadcastStatus,
    setBroadcastStatus,
    broadcastLogs,
    setBroadcastLogs,
    selectedContacts,
    setSelectedContacts,
    templateToUse,
    setTemplateToUse,
    openSettings,
    setPage,
  };

  return (
    <AppContext.Provider value={ctx}>
      <div className="app-shell">
        {/* Sidebar */}
        <aside className="sidebar">
          <div className="sidebar-logo">
            <span className="logo-icon">💬</span>
            <span className="logo-text">Xivora</span>
          </div>

          <nav className="sidebar-nav">
            {NAV_ITEMS.map((item) => (
              <button
                key={item.id}
                className={`nav-item ${page === item.id ? 'active' : ''}`}
                onClick={() => setPage(item.id)}
                title={item.label}
              >
                <span className="nav-icon">{item.icon}</span>
                <span className="nav-label">{item.label}</span>
              </button>
            ))}
          </nav>

          <div className="sidebar-bottom">
            <button
              className="nav-item settings-btn"
              onClick={() => openSettings('proxy')}
              title="Settings"
            >
              <span className="nav-icon">⚙️</span>
              <span className="nav-label">Settings</span>
            </button>
          </div>
        </aside>

        {/* Main content */}
        <main className="content-area">
          {page === 'contacts'  && <ContactsList />}
          {page === 'broadcast' && <Broadcast />}
          {page === 'templates' && <Templates />}
          {page === 'accounts'  && <Accounts />}
        </main>
      </div>

      {showProxy   && <ProxyModal   onClose={() => setShowProxy(false)} />}
      {showGpt     && <GptModal     onClose={() => setShowGpt(false)} />}
      {showProfile && <ProfileModal onClose={() => setShowProfile(false)} />}
    </AppContext.Provider>
  );
}

// ── Inline styles for gate screens ─────────────────────────────────────────────
// (used only for activation / blocked / loading — before main CSS is relevant)

const styles = {
  gateWrap: {
    display:         'flex',
    alignItems:      'center',
    justifyContent:  'center',
    width:           '100%',
    height:          '100%',
    background:      '#0d0d1a',
  },
  gateCard: {
    background:   '#161628',
    border:       '1px solid #252540',
    borderRadius: '12px',
    padding:      '48px 40px',
    width:        '380px',
    textAlign:    'center',
    boxShadow:    '0 4px 40px rgba(0,0,0,0.5)',
  },
  gateIcon: {
    fontSize:     '48px',
    marginBottom: '16px',
    display:      'block',
  },
  gateTitle: {
    fontSize:     '22px',
    fontWeight:   '600',
    color:        '#e8e8f0',
    marginBottom: '8px',
  },
  gateSubtitle: {
    color:        '#8888a8',
    fontSize:     '14px',
    lineHeight:   '1.6',
    marginBottom: '24px',
  },
  gateInput: {
    width:           '100%',
    background:      '#1c1c30',
    border:          '1px solid #252540',
    borderRadius:    '8px',
    color:           '#e8e8f0',
    fontSize:        '15px',
    padding:         '10px 14px',
    outline:         'none',
    marginBottom:    '12px',
    letterSpacing:   '0.05em',
    boxSizing:       'border-box',
  },
  gateError: {
    color:        '#e74c3c',
    fontSize:     '13px',
    marginBottom: '12px',
  },
  gateBtn: {
    width:        '100%',
    background:   '#6c5dd3',
    color:        '#fff',
    border:       'none',
    borderRadius: '8px',
    padding:      '11px',
    fontSize:     '15px',
    fontWeight:   '600',
    cursor:       'pointer',
    transition:   '0.15s',
  },
};
