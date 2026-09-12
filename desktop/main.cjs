const { app, BrowserWindow, ipcMain, screen } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const PROJECT_ROOT = path.resolve(__dirname, "..");
const API_PORT = Number(process.env.CONTEXTCLIP_API_PORT || "8765");
const API_BASE = `http://127.0.0.1:${API_PORT}`;
const WS_URL = `ws://127.0.0.1:${API_PORT}/events`;
const DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL || "http://127.0.0.1:5173";
const APP_ICON = path.join(PROJECT_ROOT, "assets", "logo");

let backendProcess = null;
let mainWindow = null;
let bubbleWindow = null;

function findPython() {
  const requested = process.env.CONTEXTCLIP_PYTHON;
  if (requested && fs.existsSync(requested)) {
    return requested;
  }

  const candidates = [
    path.join(PROJECT_ROOT, "venv", "Scripts", "python.exe"),
    path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe"),
  ];
  const found = candidates.find((candidate) => fs.existsSync(candidate));
  return found || "python";
}

function startBackend() {
  if (backendProcess) {
    return;
  }

  backendProcess = spawn(findPython(), ["main.py", "--agent-api"], {
    cwd: PROJECT_ROOT,
    env: {
      ...process.env,
      CONTEXTCLIP_API_PORT: String(API_PORT),
      PYTHONUTF8: "1",
    },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });

  backendProcess.stdout.on("data", (data) => {
    process.stdout.write(`[ContextClip API] ${data}`);
  });
  backendProcess.stderr.on("data", (data) => {
    process.stderr.write(`[ContextClip API] ${data}`);
  });
  backendProcess.on("exit", (code) => {
    console.log(`[ContextClip API] exited with code ${code}`);
    backendProcess = null;
  });
}

async function waitForBackend() {
  const started = Date.now();
  while (Date.now() - started < 15000) {
    try {
      const response = await fetch(`${API_BASE}/health`);
      if (response.ok) {
        return;
      }
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 350));
    }
  }
  throw new Error("ContextClip API did not become ready within 15 seconds.");
}

function appUrl(route = "") {
  if (!app.isPackaged) {
    return `${DEV_SERVER_URL}${route}`;
  }
  return `file://${path.join(PROJECT_ROOT, "dist", "index.html")}${route}`;
}

function createWindows() {
  mainWindow = new BrowserWindow({
    width: 1180,
    height: 760,
    minWidth: 960,
    minHeight: 640,
    backgroundColor: "#10172a",
    title: "ContextClip",
    icon: APP_ICON,
    titleBarStyle: "hidden",
    trafficLightPosition: { x: 18, y: 18 },
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow.loadURL(appUrl(""));

  bubbleWindow = new BrowserWindow({
    width: 392,
    height: 218,
    show: false,
    frame: false,
    transparent: true,
    resizable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    hasShadow: false,
    backgroundColor: "#00000000",
    icon: APP_ICON,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  bubbleWindow.setAlwaysOnTop(true, "floating");
  bubbleWindow.loadURL(appUrl("#/bubble"));
}

function bubbleBounds(anchor) {
  const width = 392;
  const height = 218;
  const point = {
    x: Number(anchor?.x || 0),
    y: Number(anchor?.y || 0),
  };
  const display = anchor ? screen.getDisplayNearestPoint(point) : screen.getPrimaryDisplay();
  const area = display.workArea;
  const gap = 18;

  let x = anchor ? point.x + gap : area.x + area.width - width - gap;
  let y = anchor ? point.y + gap : area.y + 86;

  if (x + width > area.x + area.width - gap) {
    x = point.x - width - gap;
  }
  if (y + height > area.y + area.height - gap) {
    y = point.y - height - gap;
  }

  x = Math.max(area.x + gap, Math.min(x, area.x + area.width - width - gap));
  y = Math.max(area.y + gap, Math.min(y, area.y + area.height - height - gap));
  return { x: Math.round(x), y: Math.round(y), width, height };
}

ipcMain.handle("contextclip:get-config", () => ({
  apiBase: API_BASE,
  wsUrl: WS_URL,
}));

ipcMain.on("contextclip:bubble-show", (_event, payload) => {
  if (!bubbleWindow) {
    return;
  }
  bubbleWindow.setBounds(bubbleBounds(payload?.anchor));
  bubbleWindow.showInactive();
});

ipcMain.on("contextclip:bubble-hide", () => {
  if (bubbleWindow) {
    bubbleWindow.hide();
  }
});

app.whenReady().then(async () => {
  if (process.platform === "win32") {
    app.setAppUserModelId("ContextClip");
  }
  startBackend();
  await waitForBackend();
  createWindows();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindows();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
});
