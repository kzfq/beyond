

const { app, BrowserWindow, ipcMain, shell } = require("electron");
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");

const CONFIG_PATH = path.join(app.getPath("userData"), "beyond.config.json");

let win = null;
let backend = null;

function loadConfig() { try { return JSON.parse(fs.readFileSync(CONFIG_PATH, "utf8")); } catch (_) { return {}; } }
function saveConfig(cfg) { try { fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2), { mode: 0o600 }); } catch (_) {} }

function send(evt) { if (win && !win.isDestroyed()) win.webContents.send("backend", evt); }

function toBackend(obj) {
  if (!backend || !backend.stdin.writable) return false;
  try { backend.stdin.write(JSON.stringify(obj) + "\n"); return true; } catch (_) { return false; }
}

function startBackend() {
  if (backend) return;
  const script = path.join(__dirname, "backend", "beyond_backend.py");
  if (!fs.existsSync(script)) { send({ type: "login_error", msg: "backend/beyond_backend.py missing" }); return; }
  const candidates = process.platform === "win32" ? ["python", "py"] : ["python3", "python"];
  for (const py of candidates) {
    try {
      backend = spawn(py, ["-u", script], { cwd: __dirname, env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" }, stdio: ["pipe", "pipe", "pipe"] });
      break;
    } catch (_) { backend = null; }
  }
  if (!backend) { send({ type: "login_error", msg: "Python not found — install Python 3.10+ and modifyself" }); return; }

  let buf = "";
  backend.stdout.on("data", (d) => {
    buf += d.toString();
    let i;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (line) { try { send(JSON.parse(line)); } catch (_) {} }
    }
  });
  backend.stderr.on("data", (d) => send({ type: "log", msg: d.toString().trim() }));
  backend.on("exit", (code) => {
    backend = null;
    if (code) send({ type: "login_error", msg: `Backend crashed (code ${code})` });
  });
  backend.on("error", () => { backend = null; send({ type: "login_error", msg: "Failed to launch Python backend" }); });
}

function stopBackend() { if (backend) { try { backend.kill(); } catch (_) {} backend = null; } }

ipcMain.on("login", (_e, { token, remember }) => {
  const cfg = loadConfig();
  if (remember) cfg.token = token; else delete cfg.token;
  saveConfig(cfg);
  startBackend();
  toBackend({ cmd: "login", token });
});
ipcMain.on("refresh", () => toBackend({ cmd: "refresh" }));
ipcMain.on("config", (_e, cfg) => toBackend({ cmd: "config", ...cfg }));
ipcMain.on("rpc", (_e, payload) => toBackend({ cmd: "rpc", ...payload }));
ipcMain.on("rpcclear", () => toBackend({ cmd: "rpcclear" }));
ipcMain.on("spotify", (_e, payload) => toBackend({ cmd: "spotify", ...payload }));
ipcMain.on("logger", (_e, payload) => toBackend({ cmd: "logger", ...payload }));
ipcMain.on("profile", (_e, payload) => toBackend({ cmd: "profile", ...payload }));
ipcMain.on("account", (_e, payload) => toBackend({ cmd: "account", ...payload }));
ipcMain.on("layout", (_e, payload) => toBackend({ cmd: "layout", ...payload }));
ipcMain.on("logout", () => {
  const cfg = loadConfig(); delete cfg.token; saveConfig(cfg);
  toBackend({ cmd: "logout" });
  stopBackend();
});
ipcMain.handle("saved-token", async () => loadConfig().token || null);
ipcMain.on("win", (_e, action) => {
  if (!win) return;
  if (action === "min") win.minimize();
  else if (action === "max") win.isMaximized() ? win.unmaximize() : win.maximize();
  else if (action === "close") win.close();
});
ipcMain.on("open-external", (_e, url) => shell.openExternal(url));

ipcMain.handle("admin-request", async (_e, { baseUrl, key, path, query }) => {
  try {
    if (!baseUrl || !key) return { ok: false, status: 0, error: "Set the Base URL and Admin key first." };
    const base = String(baseUrl).replace(/\/+$/, "");
    const url = base + path + (query || "");
    const res = await fetch(url, { headers: { "X-API-Key": key, Accept: "application/json" } });
    const text = await res.text();
    let data;
    try { data = JSON.parse(text); } catch (_) { data = text; }
    return { ok: res.ok, status: res.status, data };
  } catch (e) {
    return { ok: false, status: 0, error: String(e && e.message ? e.message : e) };
  }
});

function createWindow() {
  const iconPath = path.join(
    __dirname, "assets",
    process.platform === "win32" ? "beyond.ico" : "logo.png"
  );
  win = new BrowserWindow({
    width: 1180, height: 760, minWidth: 980, minHeight: 640,
    frame: false, backgroundColor: "#0a0e1a", show: false,
    icon: fs.existsSync(iconPath) ? iconPath : undefined,
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, nodeIntegration: false },
  });
  win.loadFile(path.join(__dirname, "renderer", "index.html"));
  win.once("ready-to-show", () => win.show());
}

if (process.platform === "win32") app.setAppUserModelId("com.nox.beyond");
app.whenReady().then(createWindow);
app.on("before-quit", stopBackend);
app.on("window-all-closed", () => { stopBackend(); app.quit(); });
