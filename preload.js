// Beyond — preload bridge. Renderer <-> main (which relays to the Python backend).
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("beyond", {
  login: (token, remember) => ipcRenderer.send("login", { token, remember }),
  refresh: () => ipcRenderer.send("refresh"),
  config: (cfg) => ipcRenderer.send("config", cfg),
  rpc: (payload) => ipcRenderer.send("rpc", payload),
  rpcClear: () => ipcRenderer.send("rpcclear"),
  spotify: (opts) => ipcRenderer.send("spotify", opts || {}),
  logger: (payload) => ipcRenderer.send("logger", payload || {}),
  profile: (payload) => ipcRenderer.send("profile", payload || {}),
  logout: () => ipcRenderer.send("logout"),
  savedToken: () => ipcRenderer.invoke("saved-token"),
  win: (action) => ipcRenderer.send("win", action),
  openExternal: (url) => ipcRenderer.send("open-external", url),
  admin: (payload) => ipcRenderer.invoke("admin-request", payload),
  // live event stream from the Python/modifyself backend
  onEvent: (cb) => ipcRenderer.on("backend", (_e, data) => cb(data)),
});
