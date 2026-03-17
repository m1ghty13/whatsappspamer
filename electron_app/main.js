const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

// Keep userData relative to project root
app.setPath('userData', path.join(__dirname, '..'));

const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;
const BACKEND_PORT = 8765;
const BACKEND_URL = `http://localhost:${BACKEND_PORT}`;
const HEALTH_URL = `${BACKEND_URL}/health`;
const POLL_INTERVAL = 500;   // ms
const POLL_TIMEOUT = 60000;  // ms
const POLL_DELAY   = 500;    // ms — wait before first poll (Python startup time)

let mainWindow = null;
let pythonProcess = null;

// ── Launch Python backend ──────────────────────────────────────────────────────

function killPortSync(port) {
  try {
    const { execSync } = require('child_process');
    if (process.platform === 'win32') {
      const out = execSync(`netstat -ano | findstr :${port}`, { encoding: 'utf8', stdio: ['pipe','pipe','pipe'] });
      const match = out.match(/LISTENING\s+(\d+)/);
      if (match) {
        execSync(`taskkill /PID ${match[1]} /F /T`, { stdio: 'ignore' });
        console.log(`[Electron] Killed process on port ${port} (PID ${match[1]})`);
      }
    }
  } catch (_) { /* port was free */ }
}

function startPythonBackend() {
  killPortSync(BACKEND_PORT);

  const backendDir = path.join(__dirname, '..', 'backend');
  const backendScript = path.join(backendDir, 'main.py');

  console.log('[Electron] Spawning Python backend:', backendScript);

  // Use pythonw on Windows to avoid console window in prod
  const pythonBin = process.platform === 'win32'
    ? (isDev ? 'python' : 'pythonw')
    : 'python3';

  pythonProcess = spawn(pythonBin, [backendScript], {
    cwd: path.join(__dirname, '..'),
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env },
  });

  pythonProcess.stdout.on('data', (data) => {
    process.stdout.write(`[Python] ${data}`);
  });

  pythonProcess.stderr.on('data', (data) => {
    process.stderr.write(`[Python] ${data}`);
  });

  pythonProcess.on('exit', (code, signal) => {
    console.log(`[Electron] Python process exited: code=${code} signal=${signal}`);
    pythonProcess = null;
  });

  pythonProcess.on('error', (err) => {
    console.error('[Electron] Failed to start Python:', err.message);
    dialog.showErrorBox(
      'Backend Error',
      `Failed to start Python backend:\n${err.message}\n\nMake sure Python is installed and in PATH.`
    );
  });
}

// ── Poll backend health ────────────────────────────────────────────────────────

function waitForBackend() {
  return new Promise((resolve, reject) => {
    const start = Date.now();

    // Give Python a moment to initialize before first poll
    setTimeout(poll, POLL_DELAY);

    function poll() {
      const req = http.get(HEALTH_URL, (res) => {
        if (res.statusCode === 200) {
          console.log('[Electron] Backend is ready.');
          resolve();
        } else {
          scheduleNext();
        }
        res.resume();
      });

      req.on('error', () => scheduleNext());
      req.setTimeout(500, () => {
        req.destroy();
        scheduleNext();
      });
    }

    function scheduleNext() {
      if (Date.now() - start > POLL_TIMEOUT) {
        reject(new Error(`Backend did not start within ${POLL_TIMEOUT / 1000}s`));
        return;
      }
      setTimeout(poll, POLL_INTERVAL);
    }

    // poll() is now called via setTimeout above
  });
}

// ── Create browser window ──────────────────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#0d0d1a',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
    show: true,
  });

  mainWindow.webContents.on('did-fail-load', (event, code, desc, url) => {
    console.error(`[Electron] Page failed to load: ${desc} (${code}) — ${url}`);
  });

  mainWindow.webContents.on('render-process-gone', (event, details) => {
    console.error('[Electron] Renderer crashed:', details);
  });

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
  } else {
    // Load built dist
    mainWindow.loadFile(path.join(__dirname, 'dist', 'index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ── App lifecycle ──────────────────────────────────────────────────────────────

app.whenReady().then(async () => {
  startPythonBackend();
  createWindow();

  // Wait for backend in background — frontend will retry on its own
  waitForBackend()
    .then(() => console.log('[Electron] Backend is ready.'))
    .catch((err) => console.error('[Electron] Backend start timeout:', err.message));

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  if (pythonProcess) {
    console.log('[Electron] Killing Python backend...');
    try {
      const { execSync } = require('child_process');
      if (process.platform === 'win32') {
        execSync(`taskkill /pid ${pythonProcess.pid} /f /t`, { stdio: 'ignore' });
      } else {
        pythonProcess.kill('SIGTERM');
      }
    } catch (e) {
      console.error('[Electron] Error killing Python:', e);
    }
    pythonProcess = null;
  }
});

// ── IPC helpers ───────────────────────────────────────────────────────────────

ipcMain.handle('get-app-version', () => app.getVersion());
ipcMain.handle('get-backend-url', () => BACKEND_URL);
