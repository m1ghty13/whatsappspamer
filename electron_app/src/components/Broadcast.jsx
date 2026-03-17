import React, { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { useAppContext } from '../App';
import GptModal from './modals/GptModal';

export default function Broadcast() {
  const {
    selectedContacts,
    broadcastStatus,
    setBroadcastStatus,
    broadcastLogs,
    setBroadcastLogs,
    templateToUse,
    setTemplateToUse,
    openSettings,
  } = useAppContext();

  const [text, setText] = useState('');
  const [url, setUrl] = useState('');
  const [addButton, setAddButton] = useState(false);
  const [buttonText, setButtonText] = useState('');
  const [buttonUrl, setButtonUrl] = useState('');
  const [gptEnabled, setGptEnabled] = useState(false);
  const [showGptModal, setShowGptModal] = useState(false);
  const [sending, setSending] = useState(false);
  const [statusMsg, setStatusMsg] = useState('');

  const logRef = useRef(null);

  // Apply template
  useEffect(() => {
    if (templateToUse) {
      setText(templateToUse.text || '');
      setUrl(templateToUse.url || '');
      if (templateToUse.button_text) {
        setAddButton(true);
        setButtonText(templateToUse.button_text);
        setButtonUrl(templateToUse.button_url || '');
      }
      setTemplateToUse(null);
    }
  }, [templateToUse, setTemplateToUse]);

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [broadcastLogs]);

  // Sync sending state with broadcastStatus
  useEffect(() => {
    if (broadcastStatus) {
      if (broadcastStatus.status === 'done') {
        setSending(false);
        setStatusMsg(
          `Done! Sent: ${broadcastStatus.sent}, Errors: ${broadcastStatus.errors}`
        );
      } else if (broadcastStatus.status === 'stopped') {
        setSending(false);
        setStatusMsg(
          `Stopped. Sent: ${broadcastStatus.sent}, Errors: ${broadcastStatus.errors}`
        );
      }
    }
  }, [broadcastStatus]);

  async function handleStart() {
    if (!selectedContacts.length) {
      setStatusMsg('No contacts selected. Go to Contacts tab to load a file.');
      return;
    }
    if (!text.trim()) {
      setStatusMsg('Message text is required.');
      return;
    }

    setSending(true);
    setStatusMsg('');
    setBroadcastLogs([]);
    setBroadcastStatus({ status: 'running', done: 0, total: selectedContacts.length });

    try {
      await api.post('/api/broadcast/start', {
        contacts: selectedContacts,
        text,
        url,
        button_text: addButton ? buttonText : '',
        button_url: addButton ? buttonUrl : '',
        gpt_enabled: gptEnabled,
        gpt_proxies: null,
      });
    } catch (e) {
      setSending(false);
      setStatusMsg(`Error: ${e.message}`);
      setBroadcastStatus(null);
    }
  }

  async function handleStop() {
    try {
      await api.post('/api/broadcast/stop', {});
      setStatusMsg('Stop requested…');
    } catch (e) {
      setStatusMsg(`Stop error: ${e.message}`);
    }
  }

  const done = broadcastStatus?.done ?? 0;
  const total = broadcastStatus?.total ?? selectedContacts.length;
  const errors = broadcastStatus?.errors ?? 0;
  const progress = total > 0 ? Math.round((done / total) * 100) : 0;

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">Broadcast</h1>
      </div>

      <div className="broadcast-layout">
        <div className="broadcast-form card">
          {/* Message text */}
          <div className="form-group">
            <label className="form-label">
              Message
              <span className="char-count">{text.length}</span>
            </label>
            <textarea
              className="form-textarea"
              rows={6}
              placeholder="Enter your message…"
              value={text}
              onChange={(e) => setText(e.target.value)}
              disabled={sending}
            />
          </div>

          {/* URL */}
          <div className="form-group">
            <label className="form-label">Link URL (optional)</label>
            <input
              className="form-input"
              type="url"
              placeholder="https://example.com"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={sending}
            />
          </div>

          {/* Add button checkbox */}
          <div className="form-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={addButton}
                onChange={(e) => setAddButton(e.target.checked)}
                disabled={sending}
              />
              Add link button
            </label>
          </div>

          {addButton && (
            <div className="form-row">
              <div className="form-group flex-1">
                <label className="form-label">Button Text</label>
                <input
                  className="form-input"
                  placeholder="Open Website"
                  value={buttonText}
                  onChange={(e) => setButtonText(e.target.value)}
                  disabled={sending}
                />
              </div>
              <div className="form-group flex-1">
                <label className="form-label">Button URL</label>
                <input
                  className="form-input"
                  type="url"
                  placeholder="https://example.com"
                  value={buttonUrl}
                  onChange={(e) => setButtonUrl(e.target.value)}
                  disabled={sending}
                />
              </div>
            </div>
          )}

          {/* GPT */}
          <div className="form-group">
            <div className="gpt-row">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={gptEnabled}
                  onChange={(e) => setGptEnabled(e.target.checked)}
                  disabled={sending}
                />
                GPT text variations
              </label>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setShowGptModal(true)}
                title="GPT Settings"
              >
                ⚙ Settings
              </button>
            </div>
          </div>

          {/* Stats bar */}
          <div className="broadcast-stats">
            <span className="stat">
              <span className="stat-label">Selected</span>
              <span className="stat-value">{selectedContacts.length}</span>
            </span>
            <span className="stat">
              <span className="stat-label">Sent</span>
              <span className="stat-value success">{done}</span>
            </span>
            <span className="stat">
              <span className="stat-label">Errors</span>
              <span className="stat-value error">{errors}</span>
            </span>
            <span className="stat">
              <span className="stat-label">Remaining</span>
              <span className="stat-value">{Math.max(0, total - done)}</span>
            </span>
          </div>

          {/* Progress bar */}
          {(sending || done > 0) && (
            <div className="progress-bar-wrap">
              <div className="progress-bar">
                <div
                  className="progress-fill"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <span className="progress-label">{progress}%</span>
            </div>
          )}

          {statusMsg && (
            <div className={`status-message ${statusMsg.startsWith('Error') ? 'error' : 'info'}`}>
              {statusMsg}
            </div>
          )}

          {/* Action buttons */}
          <div className="broadcast-actions">
            {!sending ? (
              <button
                className="btn btn-primary btn-lg"
                onClick={handleStart}
                disabled={sending}
              >
                ▶ Start Broadcast
              </button>
            ) : (
              <button className="btn btn-danger btn-lg" onClick={handleStop}>
                ⏹ Stop
              </button>
            )}
          </div>
        </div>

        {/* Log panel */}
        <div className="log-panel card">
          <div className="log-header">
            <h3>Activity Log</h3>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setBroadcastLogs([])}
            >
              Clear
            </button>
          </div>
          <div className="log-content" ref={logRef}>
            {broadcastLogs.length === 0 ? (
              <span className="log-empty">No activity yet.</span>
            ) : (
              broadcastLogs.map((line, i) => (
                <div key={i} className="log-line">
                  {line}
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {showGptModal && <GptModal onClose={() => setShowGptModal(false)} />}
    </div>
  );
}
