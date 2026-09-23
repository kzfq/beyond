
(function () {
  "use strict";

  var basePath = location.pathname.replace(/\/+$/, "");
  var VIEWER_WS =
    (location.protocol === "https:" ? "wss://" : "ws://") +
    location.host + basePath + "/ws";

  var ws = null;
  var connected = false;
  var backoff = 1000;
  var listeners = [];
  var outbox = [];
  var agentOnline = true;
  var offlineTimer = null;

  function emitLocal(evt) {
    for (var i = 0; i < listeners.length; i++) {
      try { listeners[i](evt); } catch (_) {}
    }
  }

  var overlay = null, overlayMsg = null;
  function ensureOverlay() {
    if (overlay) return;
    overlay = document.createElement("div");
    overlay.id = "beyondConnOverlay";
    overlay.style.cssText =
      "position:fixed;inset:0;z-index:99999;display:none;align-items:center;" +
      "justify-content:center;background:rgba(6,10,20,0.82);backdrop-filter:blur(4px);" +
      "font-family:inherit;color:#eaf0fb;text-align:center;";
    var box = document.createElement("div");
    box.style.cssText =
      "max-width:340px;padding:26px 30px;border-radius:16px;" +
      "background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.12);";
    var dot = document.createElement("div");
    dot.style.cssText =
      "width:12px;height:12px;border-radius:50%;background:#f0b23a;margin:0 auto 14px;" +
      "box-shadow:0 0 0 6px rgba(240,178,58,0.15);animation:beyondPulse 1.2s ease-in-out infinite;";
    overlayMsg = document.createElement("div");
    overlayMsg.style.cssText = "font-size:15px;line-height:1.5;";
    box.appendChild(dot);
    box.appendChild(overlayMsg);
    overlay.appendChild(box);
    var style = document.createElement("style");
    style.textContent =
      "@keyframes beyondPulse{0%,100%{opacity:.4}50%{opacity:1}}";
    document.head.appendChild(style);
    (document.body || document.documentElement).appendChild(overlay);
  }
  function showOverlay(msg) {
    ensureOverlay();
    overlayMsg.textContent = msg;
    overlay.style.display = "flex";
  }
  function hideOverlay() {
    if (overlay) overlay.style.display = "none";
  }

  function markOnline() {
    agentOnline = true;
    if (offlineTimer) { clearTimeout(offlineTimer); offlineTimer = null; }
    if (connected) hideOverlay();
  }
  function markOffline() {

    if (offlineTimer) return;
    offlineTimer = setTimeout(function () {
      offlineTimer = null;
      agentOnline = false;
      showOverlay("Your PC is offline. Start Beyond on your PC to control it here.");
    }, 2500);
  }

  function connect() {
    try { ws = new WebSocket(VIEWER_WS); }
    catch (e) { scheduleReconnect(); return; }

    ws.onopen = function () {
      connected = true;
      backoff = 1000;
      if (agentOnline) hideOverlay();
      while (outbox.length && ws.readyState === 1) ws.send(outbox.shift());
    };
    ws.onmessage = function (e) {
      var msg;
      try { msg = JSON.parse(e.data); } catch (_) { return; }
      if (msg.t === "event") {

        markOnline();
        emitLocal(msg.data || {});
      } else if (msg.t === "agent_status") {
        if (msg.online) markOnline();
        else markOffline();
      }
    };
    ws.onclose = function () {
      connected = false;
      showOverlay("Reconnecting to your session…");
      scheduleReconnect();
    };
    ws.onerror = function () { try { ws.close(); } catch (_) {} };
  }
  function scheduleReconnect() {
    setTimeout(connect, backoff);
    backoff = Math.min(backoff * 2, 15000);
  }

  function sendCmd(data) {
    var frame = JSON.stringify({ t: "cmd", data: data });
    if (connected && ws && ws.readyState === 1) ws.send(frame);
    else outbox.push(frame);
  }

  async function adminFetch(payload) {
    payload = payload || {};
    var baseUrl = payload.baseUrl, key = payload.key,
        path = payload.path || "", query = payload.query || "";
    try {
      if (!baseUrl || !key)
        return { ok: false, status: 0, error: "Set the Base URL and Admin key first." };
      var base = String(baseUrl).replace(/\/+$/, "");
      var res = await fetch(base + path + query, {
        headers: { "X-API-Key": key, Accept: "application/json" },
      });
      var text = await res.text();
      var data;
      try { data = JSON.parse(text); } catch (_) { data = text; }
      return { ok: res.ok, status: res.status, data: data };
    } catch (e) {
      return { ok: false, status: 0, error: String(e && e.message ? e.message : e) };
    }
  }

  window.beyond = {
    login: function (token, remember) { sendCmd({ cmd: "login", token: token }); },
    refresh: function () { sendCmd({ cmd: "refresh" }); },
    config: function (cfg) { sendCmd(Object.assign({ cmd: "config" }, cfg || {})); },
    rpc: function (payload) { sendCmd(Object.assign({ cmd: "rpc" }, payload || {})); },
    rpcClear: function () { sendCmd({ cmd: "rpcclear" }); },
    spotify: function (opts) { sendCmd(Object.assign({ cmd: "spotify" }, opts || {})); },
    logger: function (payload) { sendCmd(Object.assign({ cmd: "logger" }, payload || {})); },
    profile: function (payload) { sendCmd(Object.assign({ cmd: "profile" }, payload || {})); },
    logout: function () { sendCmd({ cmd: "logout" }); },

    savedToken: function () { return Promise.resolve(null); },

    win: function () {},
    openExternal: function (url) { try { window.open(url, "_blank", "noopener"); } catch (_) {} },
    admin: adminFetch,
    onEvent: function (cb) { if (typeof cb === "function") listeners.push(cb); },
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", connect);
  } else {
    connect();
  }
})();
