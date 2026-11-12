const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

// Use ANGLE D3D11 backend - more stable on Windows while keeping WebGL working
// This fixes "GPU state invalid after WaitForGetOffsetInRange" error
app.commandLine.appendSwitch('use-angle', 'd3d11');
app.commandLine.appendSwitch('enable-features', 'Vulkan');
app.commandLine.appendSwitch('ignore-gpu-blocklist');

const BACKEND_PORT = 8001;
let mainWindow;
let pythonProcess;

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1920,
        height: 1080,
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false, // For simple IPC/Socket.IO usage
        },
        backgroundColor: '#000000',
        frame: false, // Frameless for custom UI
        titleBarStyle: 'hidden',
        show: false, // Don't show until ready
    });

    // In dev, load Vite server. In prod, load index.html
    const isDev = process.env.NODE_ENV !== 'production';

    const loadFrontend = (retries = 3) => {
        const url = isDev ? 'http://localhost:5173' : null;
        const loadPromise = isDev
            ? mainWindow.loadURL(url)
            : mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));

        loadPromise
            .then(() => {
                console.log('Frontend loaded successfully!');
                windowWasShown = true;
                mainWindow.show();
                if (isDev) {
                    mainWindow.webContents.openDevTools();
                }
            })
            .catch((err) => {
                console.error(`Failed to load frontend: ${err.message}`);
                if (retries > 0) {
                    console.log(`Retrying in 1 second... (${retries} retries left)`);
                    setTimeout(() => loadFrontend(retries - 1), 1000);
                } else {
                    console.error('Failed to load frontend after all retries. Keeping window open.');
                    windowWasShown = true;
                    mainWindow.show(); // Show anyway so user sees something
                }
            });
    };

    loadFrontend();

    mainWindow.on('closed', () => {
        mainWindow = null;
    });
}

function startPythonBackend() {
    const projectRoot = path.resolve(__dirname, '..');
    const scriptPath = path.join(projectRoot, 'backend', 'server.py');
    const localPython = process.platform === 'win32'
        ? path.join(projectRoot, '.venv', 'Scripts', 'python.exe')
        : path.join(projectRoot, '.venv', 'bin', 'python');
    const pythonExecutable = process.env.ADA_PYTHON || (
        require('fs').existsSync(localPython) ? localPython : 'python'
    );

    if (pythonExecutable === 'python') {
        console.warn('[A.D.A] Project-local .venv was not found. Run scripts\\setup_local.ps1; using PATH python as a temporary fallback.');
    }
    console.log(`Starting Python backend: ${scriptPath}`);
    console.log(`Python interpreter: ${pythonExecutable}`);

    const localDataRoot = path.join(projectRoot, '.ada');
    const cacheRoot = path.join(localDataRoot, 'cache');
    const localEnv = {
        ...process.env,
        ADA_PROJECT_ROOT: projectRoot,
        PYTHONUNBUFFERED: '1',
        PYTHONPYCACHEPREFIX: path.join(cacheRoot, 'pycache'),
        PIP_CACHE_DIR: path.join(cacheRoot, 'pip'),
        HF_HOME: path.join(cacheRoot, 'huggingface'),
        HUGGINGFACE_HUB_CACHE: path.join(cacheRoot, 'huggingface', 'hub'),
        XDG_CACHE_HOME: path.join(cacheRoot, 'xdg'),
        TORCH_HOME: path.join(cacheRoot, 'torch'),
        PLAYWRIGHT_BROWSERS_PATH: path.join(localDataRoot, 'browsers'),
        TEMP: path.join(cacheRoot, 'tmp'),
        TMP: path.join(cacheRoot, 'tmp'),
    };
    for (const directory of [
        localEnv.PYTHONPYCACHEPREFIX, localEnv.PIP_CACHE_DIR, localEnv.HF_HOME,
        localEnv.XDG_CACHE_HOME, localEnv.TORCH_HOME, localEnv.PLAYWRIGHT_BROWSERS_PATH,
        localEnv.TEMP,
    ]) {
        require('fs').mkdirSync(directory, { recursive: true });
    }

    pythonProcess = spawn(pythonExecutable, [scriptPath], {
        cwd: projectRoot,
        env: localEnv,
    });

    pythonProcess.stdout.on('data', (data) => {
        console.log(`[Python]: ${data}`);
    });

    pythonProcess.stderr.on('data', (data) => {
        console.error(`[Python Error]: ${data}`);
    });
}

app.whenReady().then(() => {
    ipcMain.on('window-minimize', () => {
        if (mainWindow) mainWindow.minimize();
    });

    ipcMain.on('window-maximize', () => {
        if (mainWindow) {
            if (mainWindow.isMaximized()) {
                mainWindow.unmaximize();
            } else {
                mainWindow.maximize();
            }
        }
    });

    ipcMain.on('window-close', () => {
        if (mainWindow) mainWindow.close();
    });

    ipcMain.handle('select-path', async (_event, options = {}) => {
        const properties = options.directory ? ['openDirectory'] : ['openFile'];
        const result = await dialog.showOpenDialog(mainWindow, {
            properties,
            filters: options.filters || [],
            title: options.title || 'Select a file',
        });
        if (result.canceled || !result.filePaths.length) return null;
        return result.filePaths[0];
    });

    checkBackendPort(BACKEND_PORT).then((isTaken) => {
        if (isTaken) {
            console.log('A.D.A backend port is already in use. Checking its health endpoint.');
            waitForBackend().then(createWindow);
        } else {
            startPythonBackend();
            // Give it a moment to start, then wait for health check
            setTimeout(() => {
                waitForBackend().then(createWindow);
            }, 1000);
        }
    });

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
});

function checkBackendPort(port) {
    return new Promise((resolve) => {
        const net = require('net');
        const server = net.createServer();
        server.once('error', (err) => {
            if (err.code === 'EADDRINUSE') {
                resolve(true);
            } else {
                resolve(false);
            }
        });
        server.once('listening', () => {
            server.close();
            resolve(false);
        });
        server.listen(port);
    });
}

function waitForBackend() {
    return new Promise((resolve) => {
        const check = () => {
            const http = require('http');
            http.get(`http://127.0.0.1:${BACKEND_PORT}/status`, (res) => {
                if (res.statusCode === 200) {
                    console.log('Backend is ready!');
                    resolve();
                } else {
                    console.log('Backend not ready, retrying...');
                    setTimeout(check, 1000);
                }
            }).on('error', (err) => {
                console.log('Waiting for backend...');
                setTimeout(check, 1000);
            });
        };
        check();
    });
}

let windowWasShown = false;

app.on('window-all-closed', () => {
    // Only quit if the window was actually shown at least once
    // This prevents quitting during startup if window creation fails
    if (process.platform !== 'darwin' && windowWasShown) {
        app.quit();
    } else if (!windowWasShown) {
        console.log('Window was never shown - keeping app alive to allow retries');
    }
});

app.on('will-quit', () => {
    console.log('App closing... Killing Python backend.');
    if (pythonProcess) {
        if (process.platform === 'win32') {
            // Windows: Force kill the process tree synchronously
            try {
                const { execSync } = require('child_process');
                execSync(`taskkill /pid ${pythonProcess.pid} /f /t`);
            } catch (e) {
                console.error('Failed to kill python process:', e.message);
            }
        } else {
            // Unix: SIGKILL
            pythonProcess.kill('SIGKILL');
        }
        pythonProcess = null;
    }
});
