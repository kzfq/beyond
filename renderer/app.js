
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const RING_C = 2 * Math.PI * 52;

$$("[data-win]").forEach((b) => b.addEventListener("click", () => window.beyond.win(b.dataset.win)));

const BADGES = [
  [1 << 0, "Discord Staff", "5e74e9b61934fc1f67c65515d1f7e60d"],
  [1 << 1, "Partnered Server Owner", "3f9748e53446a137a052f3454e2de41e"],
  [1 << 2, "HypeSquad Events", "bf01d1073931f921909045f3a39fd264"],
  [1 << 6, "HypeSquad Bravery", "8a88d63823d8a71cd5e390baa45efa02"],
  [1 << 7, "HypeSquad Brilliance", "011940fd013da3f7fb926e4a1cd2e618"],
  [1 << 8, "HypeSquad Balance", "3aa41de486fa12454c3761e8e223442e"],
  [1 << 9, "Early Supporter", "7060786766c9c840eb3019e725d2b358"],
  [1 << 3, "Bug Hunter", "2717692c7dca7289b35297368a940dd0"],
  [1 << 14, "Bug Hunter Gold", "848f79194d4be5ff5f81505cbd0ce1e6"],
  [1 << 17, "Early Verified Bot Developer", "6df5892e0f35b051f8b61eace34f4967"],
  [1 << 18, "Moderator Programs Alumni", "fee1624003e2fee35cb398e125dc479b"],
  [1 << 22, "Active Developer", "6bdc42827a38498929a4920da12695d9"],
];
const NITRO_BADGE = "2ba85e8026a8614b640c2837bcdfe21b";

function renderBadges(flags, nitroActive) {
  const el = $("#badges");
  const items = BADGES.filter(([bit]) => flags & bit).map(
    ([, name, hash]) =>
      `<img class="badge" title="${name}" alt="${name}" src="https://cdn.discordapp.com/badge-icons/${hash}.png" />`
  );
  if (nitroActive)
    items.push(`<img class="badge" title="Nitro" alt="Nitro" src="https://cdn.discordapp.com/badge-icons/${NITRO_BADGE}.png" />`);
  el.innerHTML = items.join("") || `<span class="badge-none">No badges</span>`;
}

const NICO = {
  info: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M12 11v5M12 8h.01" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>',
  ok: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M8 12.5l2.5 2.5 5-5.5" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  err: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M9 9l6 6M15 9l-6 6" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>',
  warn: '<svg viewBox="0 0 24 24"><path d="M12 3l9 16H3z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M12 10v4M12 17h.01" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>',
};
const notifList = $("#notifList");
const notifs = [];
function timeAgo(ts) {
  const s = Math.floor((Date.now() - ts) / 1000);
  if (s < 60) return `${s} second${s === 1 ? "" : "s"} ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} minute${m === 1 ? "" : "s"} ago`;
  const h = Math.floor(m / 60);
  return `${h} hour${h === 1 ? "" : "s"} ago`;
}
function esc(s) { return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }
function renderNotifs() {
  if (!notifs.length) { notifList.innerHTML = `<div class="notif-empty">No notifications yet.</div>`; return; }
  notifList.innerHTML = notifs.map((n) => `
    <div class="n">
      <div class="n-ico ${n.kind}">${NICO[n.kind] || NICO.info}</div>
      <div class="n-body"><div class="n-msg">${n.msg}</div><div class="n-meta" data-ts="${n.ts}">${timeAgo(n.ts)}</div></div>
    </div>`).join("");
}
function updateTimes() {
  $$(".n-meta[data-ts]").forEach((el) => { el.textContent = timeAgo(Number(el.dataset.ts)); });
}
function notify(kind, msg) {
  notifs.unshift({ kind, msg, ts: Date.now() });
  if (notifs.length > 25) notifs.pop();
  renderNotifs();
}
$("#clearNotif").addEventListener("click", () => { notifs.length = 0; renderNotifs(); });
setInterval(updateTimes, 15000);
renderNotifs();

function setRing(el, value, max) { el.style.strokeDashoffset = String(RING_C * (1 - Math.max(0, Math.min(1, value / max)))); }
function countUp(el, to) {
  const t0 = performance.now();
  (function step(t) {
    const k = Math.min(1, (t - t0) / 900);
    el.textContent = Math.round(to * (1 - Math.pow(1 - k, 3)));
    if (k < 1) requestAnimationFrame(step);
  })(t0);
}
let uptimeStart = null;
const pad = (n) => String(n).padStart(2, "0");
setInterval(() => {
  if (!uptimeStart) return;
  let s = Math.floor((Date.now() - uptimeStart) / 1000);
  const dd = Math.floor(s / 86400); s -= dd * 86400;
  const hh = Math.floor(s / 3600); s -= hh * 3600;
  const mm = Math.floor(s / 60); s -= mm * 60;
  $("#upDD").textContent = pad(dd); $("#upHH").textContent = pad(hh);
  $("#upMM").textContent = pad(mm); $("#upSS").textContent = pad(s);
}, 500);

let cmdCount = 0;
function renderStats(s) {
  $("#greetName").textContent = s.globalName;
  $("#username").textContent = s.globalName;
  $("#handle").textContent = s.discriminator ? `${s.username}#${s.discriminator}` : `@${s.username}`;
  $("#avatar").src = s.avatarUrl;
  $("#userId").textContent = s.id;
  $("#nitro").textContent = s.nitro;
  renderBadges(s.publicFlags || 0, s.nitroActive);
  countUp($("#serversVal"), s.servers);
  countUp($("#friendsVal"), s.friends);
  setRing($("#ringServers"), s.servers, 100);
  setRing($("#ringFriends"), s.friends, 1000);

  const h = s.discriminator ? `${s.username}#${s.discriminator}` : `@${s.username}`;
  if ($("#avatar2")) $("#avatar2").src = s.avatarUrl;
  if ($("#username2")) $("#username2").textContent = s.globalName;
  if ($("#handle2")) $("#handle2").textContent = h;
  if ($("#userId2")) $("#userId2").textContent = s.id;
}

$$(".rail-btn[data-tab]").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".rail-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const tab = btn.dataset.tab;
    $$(".page").forEach((p) => p.classList.toggle("hidden", p.dataset.page !== tab));
  });
});

const loginEl = $("#login"), appEl = $("#app"), tokenInput = $("#token"), errEl = $("#loginError");
let pending = false;
$("#reveal").addEventListener("click", () => { tokenInput.type = tokenInput.type === "password" ? "text" : "password"; });
function setBtn(state) { const b = $("#loginBtn"); b.disabled = state; b.textContent = state ? "Connecting…" : "Login"; }
function doLogin(token, remember, silent) {
  errEl.textContent = "";
  pending = !silent;
  if (!silent) setBtn(true);
  window.beyond.login(token, remember);
}
$("#loginBtn").addEventListener("click", () => {
  const t = tokenInput.value.trim();
  if (!t) { errEl.textContent = "Enter a token first."; return; }
  if (addMode) {
    addMode = false;
    const b = $("#loginBtn"); if (b) b.textContent = "Login";
    window.beyond.account({ action: "add", token: t });
    loginEl.classList.add("hidden"); appEl.classList.remove("hidden");
    tokenInput.value = ""; errEl.textContent = "";
    return;
  }
  doLogin(t, $("#remember").checked, false);
});
tokenInput.addEventListener("keydown", (e) => { if (e.key === "Enter") $("#loginBtn").click(); });

// ---- token helper bookmarklet ----
(function () {
  const BKM = 'javascript:(function(){var t="";try{t=(localStorage.token||"").replace(/"/g,"");}catch(e){}if(!t){try{var f=document.createElement("iframe");document.head.appendChild(f);t=(f.contentWindow.localStorage.token||"").replace(/"/g,"");document.head.removeChild(f);}catch(e){}}if(!t){alert("Token not found — make sure you are on discord.com and logged in.");return;}navigator.clipboard.writeText(t).then(function(){alert("✓ Token copied! Paste it in Beyond.");},function(){prompt("Your token:",t);});})();';
  const modal = $("#tokenModal");
  const bkmLink = $("#tokenBkm");
  if (bkmLink) bkmLink.href = BKM;
  function openModal() { modal.classList.remove("hidden"); }
  function closeModal() { modal.classList.add("hidden"); }
  const helper = $("#tokenHelper");
  if (helper) helper.addEventListener("click", openModal);
  const closeBtn = $("#tokenModalClose");
  if (closeBtn) closeBtn.addEventListener("click", closeModal);
  modal.addEventListener("click", (e) => { if (e.target === modal) closeModal(); });
  const copyBtn = $("#copyBkm");
  if (copyBtn) copyBtn.addEventListener("click", () => {
    navigator.clipboard.writeText(BKM).then(
      () => { copyBtn.textContent = "Copied!"; setTimeout(() => { copyBtn.textContent = "Copy bookmarklet URL"; }, 2200); },
      () => {}
    );
  });
})();

// ---- accounts (multi-account switcher) ----
let accounts = [];
let activeId = null;
let addMode = false;
const acctSwitcher = $("#acctSwitcher");
const acctList = $("#acctList");

function renderSwitcher() {
  if (!acctList) return;
  if (!accounts.length) {
    acctList.innerHTML = `<div class="acct-empty">No saved accounts yet.</div>`;
    return;
  }
  acctList.innerHTML = accounts.map((a) => {
    const name = esc(a.globalName || a.username || "account");
    const handle = a.username ? esc("@" + a.username) : "";
    const av = a.avatarUrl
      ? `<img class="acct-av" src="${esc(a.avatarUrl)}" alt="">`
      : `<div class="acct-av acct-av-ph">${esc((name[0] || "?").toUpperCase())}</div>`;
    const isActive = a.id === activeId;
    return `<div class="acct-row${isActive ? " active" : ""}" data-id="${esc(a.id)}">
      ${av}
      <div class="acct-row-main"><div class="acct-row-name">${name}</div>
        <div class="acct-row-handle">${handle}</div></div>
      ${isActive ? '<span class="acct-check">✓</span>' : ""}
      <button class="acct-x" data-id="${esc(a.id)}" title="Remove">×</button>
    </div>`;
  }).join("");
}

function toggleSwitcher(force) {
  if (!acctSwitcher) return;
  const show = force !== undefined ? force : acctSwitcher.classList.contains("hidden");
  acctSwitcher.classList.toggle("hidden", !show);
  if (show) renderSwitcher();
}

function startAddAccount() {
  addMode = true;
  toggleSwitcher(false);
  tokenInput.value = "";
  errEl.textContent = "Adding another account — paste its token.";
  appEl.classList.add("hidden");
  loginEl.classList.remove("hidden");
  const b = $("#loginBtn"); if (b) b.textContent = "Add account";
}

$("#switchBtn").addEventListener("click", () => toggleSwitcher());
$("#addBtn").addEventListener("click", startAddAccount);
if ($("#switchBtn2")) $("#switchBtn2").addEventListener("click", () => toggleSwitcher());
if ($("#acctAddInline")) $("#acctAddInline").addEventListener("click", startAddAccount);

if (acctList) {
  acctList.addEventListener("click", (e) => {
    const x = e.target.closest(".acct-x");
    if (x) { e.stopPropagation(); window.beyond.account({ action: "remove", id: x.dataset.id }); return; }
    const row = e.target.closest(".acct-row");
    if (row) {
      const id = row.dataset.id;
      if (id !== activeId) { window.beyond.account({ action: "switch", id }); notify("info", "Switching account…"); }
      toggleSwitcher(false);
    }
  });
}
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  toggleSwitcher(false);
  if (addMode) {
    addMode = false;
    const b = $("#loginBtn"); if (b) b.textContent = "Login";
    errEl.textContent = "";
    if (accounts.length) { loginEl.classList.add("hidden"); appEl.classList.remove("hidden"); }
  }
});
if ($("#refreshBtn")) $("#refreshBtn").addEventListener("click", () => window.beyond.refresh());

const tglPrivate = $("#tglPrivate"), tglDisc = $("#tglDiscoverable");
const tglPrivate2 = $("#tglPrivate2"), tglDisc2 = $("#tglDiscoverable2");
function loadToggles() {
  try {
    const c = JSON.parse(localStorage.getItem("beyond.cfg") || "{}");
    if ("private" in c) { tglPrivate.checked = c.private; if (tglPrivate2) tglPrivate2.checked = c.private; }
    if ("discoverable" in c) { tglDisc.checked = c.discoverable; if (tglDisc2) tglDisc2.checked = c.discoverable; }
  } catch (_) {}
}
function sendConfig(includeBot, openInvite) {
  const cfg = { private: tglPrivate.checked, discoverable: tglDisc.checked };
  try { localStorage.setItem("beyond.cfg", JSON.stringify(cfg)); } catch (_) {}
  if (includeBot) {
    cfg.botToken = botToken.value.trim();
    cfg.botAppId = botApp.value.trim();
    cfg.botGuild = botGuild.value.trim();
    if (openInvite) cfg.openInvite = true;
  }
  window.beyond.config(cfg);
}
function botAuthorized() {
  try { return localStorage.getItem("beyond.bot.authorized") === "1"; } catch (_) { return false; }
}
function syncToggles(priv, disc) {
  tglPrivate.checked = priv; if (tglPrivate2) tglPrivate2.checked = priv;
  tglDisc.checked = disc; if (tglDisc2) tglDisc2.checked = disc;
}
tglPrivate.addEventListener("change", () => { syncToggles(tglPrivate.checked, tglDisc.checked); sendConfig(); notify("info", `Private mode <b>${tglPrivate.checked ? "on" : "off"}</b>`); });
tglDisc.addEventListener("change", () => { syncToggles(tglPrivate.checked, tglDisc.checked); sendConfig(); });
if (tglPrivate2) tglPrivate2.addEventListener("change", () => { syncToggles(tglPrivate2.checked, tglDisc.checked); sendConfig(); notify("info", `Private mode <b>${tglPrivate2.checked ? "on" : "off"}</b>`); });
if (tglDisc2) tglDisc2.addEventListener("change", () => { syncToggles(tglPrivate.checked, tglDisc2.checked); sendConfig(); });
loadToggles();

const botToken = $("#botToken"), botApp = $("#botApp"), botConnect = $("#botConnect"),
      botStatus = $("#botStatus"), botDot = $("#botDot"), botGuild = $("#botGuild");
let lastInvite = null;
function loadBotCreds() {
  try {
    const b = JSON.parse(localStorage.getItem("beyond.bot") || "{}");
    if (b.appId) botApp.value = b.appId;
    if (b.token) botToken.value = b.token;
    if (b.guild) botGuild.value = b.guild;
  } catch (_) {}
}
botConnect.addEventListener("click", () => {
  const t = botToken.value.trim(), a = botApp.value.trim(), g = botGuild.value.trim();
  if (!t || !a) { botStatus.textContent = "Enter both the Application ID and Bot token."; return; }
  try { localStorage.setItem("beyond.bot", JSON.stringify({ appId: a, token: t, guild: g })); } catch (_) {}
  botConnect.disabled = true; botConnect.textContent = "Connecting…";
  botStatus.textContent = "Starting real bot…";

  sendConfig(true, !botAuthorized());
});
loadBotCreds();

const RPC = {
  type: $("#rpcType"), name: $("#rpcName"), text: $("#rpcText"),
  details: $("#rpcDetails"), state: $("#rpcState"),
  largeImg: $("#rpcLargeImg"), largeTxt: $("#rpcLargeTxt"),
  smallImg: $("#rpcSmallImg"), smallTxt: $("#rpcSmallTxt"),
  elapsed: $("#rpcElapsed"), total: $("#rpcTotal"),
  stream: $("#rpcStream"), btn1: $("#rpcBtn1"), btn1u: $("#rpcBtn1Url"),
  btn2: $("#rpcBtn2"), btn2u: $("#rpcBtn2Url"), emoji: $("#rpcEmoji"),
};
const KIND_LABEL = {
  playing: "PLAYING A GAME", listening: "LISTENING TO", watching: "WATCHING",
  streaming: "LIVE ON TWITCH", competing: "COMPETING IN", spotify: "LISTENING TO SPOTIFY",
  youtube: "WATCHING YOUTUBE", crunchyroll: "WATCHING CRUNCHYROLL",
  xbox: "PLAYING ON XBOX", playstation: "PLAYING ON PLAYSTATION",
  vrchat: "PLAYING VRCHAT", custom: "PLAYING", custom_status: "CUSTOM STATUS",
};
let rpcStatus = "online";
let rpcElapsedStart = null;

function applyTypeVisibility() {
  const t = RPC.type.value;
  $$("#app [data-hide]").forEach((el) => {
    el.classList.toggle("hidden", el.dataset.hide.split(",").includes(t));
  });
  $$("#app [data-only]").forEach((el) => {
    el.classList.toggle("hidden", !el.dataset.only.split(",").includes(t));
  });
}

function setPv(el, val, ph) {
  if (el === document.activeElement) return;
  el.textContent = val || "";
  el.classList.toggle("pv-empty", !val);
  if (ph) el.setAttribute("data-ph", ph);
}
function fmtMin(m) {
  const total = Math.round(m * 60);
  const mm = Math.floor(total / 60), ss = total % 60;
  return `${pad(mm)}:${pad(ss)}`;
}
function updatePreview() {
  const t = RPC.type.value;
  const custom = t === "custom_status";
  $("#pvKind").textContent = KIND_LABEL[t] || t.toUpperCase();

  if (custom) {
    setPv($("#pvName"), (RPC.emoji.value ? RPC.emoji.value + " " : "") + (RPC.text.value || ""), "Status text");
    $("#pvDetail").style.display = "none"; $("#pvState").style.display = "none";
    $("#pvTime").textContent = "";
    $("#pvLarge").classList.add("hidden");
    $("#pvLargePlaceholder").classList.add("hidden");
    $("#pvSmall").classList.add("hidden");
    $("#pvButtons").innerHTML = "";
    return;
  }
  $("#pvDetail").style.display = ""; $("#pvState").style.display = "";
  setPv($("#pvName"), RPC.name.value, "Name");
  setPv($("#pvDetail"), RPC.details.value, "Details (line 1)");
  setPv($("#pvState"), RPC.state.value, "State (line 2)");

  const li = RPC.largeImg.value.trim();
  if (li) { $("#pvLarge").src = li; $("#pvLarge").classList.remove("hidden"); $("#pvLargePlaceholder").classList.add("hidden"); }
  else { $("#pvLarge").classList.add("hidden"); $("#pvLargePlaceholder").classList.remove("hidden"); }
  const si = RPC.smallImg.value.trim();
  if (si) { $("#pvSmall").src = si; $("#pvSmall").classList.remove("hidden"); }
  else $("#pvSmall").classList.add("hidden");

  const el = parseFloat(RPC.elapsed.value || "0");
  const tot = parseFloat(RPC.total.value || "0");
  $("#pvTime").textContent = tot > 0 ? `${fmtMin(el)} / ${fmtMin(tot)}` : `${fmtMin(el)} elapsed`;

  const btns = [];
  if (RPC.btn1.value) btns.push([RPC.btn1.value, "rpcBtn1"]);
  if (RPC.btn2.value) btns.push([RPC.btn2.value, "rpcBtn2"]);
  $("#pvButtons").innerHTML = btns.map(([b, f]) => `<div class="pvbtn" data-focus="${f}">${esc(b)}</div>`).join("");
}

Object.values(RPC).forEach((el) => el && el.addEventListener("input", updatePreview));
RPC.type.addEventListener("change", () => { applyTypeVisibility(); updatePreview(); });

$$(".pv-edit").forEach((elm) => {
  elm.addEventListener("input", () => {
    const field = elm.dataset.field;
    const val = elm.textContent;
    if (RPC.type.value === "custom_status" && field === "name") {
      RPC.text.value = val;
    } else {
      const map = { name: RPC.name, details: RPC.details, state: RPC.state };
      if (map[field]) map[field].value = val;
    }
  });
  elm.addEventListener("blur", updatePreview);
  elm.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); elm.blur(); } });
});

$("#rpcCard").addEventListener("click", (e) => {
  const hit = e.target.closest("[data-focus]");
  if (!hit) return;
  const input = document.getElementById(hit.dataset.focus);
  if (!input) return;
  input.focus();
  input.classList.add("flash");
  setTimeout(() => input.classList.remove("flash"), 800);
});

function collectActivity() {
  const t = RPC.type.value;
  const a = { rpc_type: t };
  if (t === "custom_status") {
    a.text = RPC.text.value; if (RPC.emoji.value) a.emoji = RPC.emoji.value;
    return a;
  }
  if (RPC.name.value) a.name = RPC.name.value;
  if (RPC.details.value) a.details = RPC.details.value;
  if (RPC.state.value) a.state = RPC.state.value;
  if (RPC.largeImg.value) a.large_image = RPC.largeImg.value.trim();
  if (RPC.largeTxt.value) a.large_text = RPC.largeTxt.value;
  if (RPC.smallImg.value) a.small_image = RPC.smallImg.value.trim();
  if (RPC.smallTxt.value) a.small_text = RPC.smallTxt.value;
  if (RPC.elapsed.value) a.elapsed_minutes = RPC.elapsed.value;
  if (RPC.total.value) a.total_minutes = RPC.total.value;
  if (t === "streaming" && RPC.stream.value) a.stream_url = RPC.stream.value;
  if (RPC.btn1.value && RPC.btn1u.value) { a.button1 = RPC.btn1.value; a.button1_url = RPC.btn1u.value; }
  if (RPC.btn2.value && RPC.btn2u.value) { a.button2 = RPC.btn2.value; a.button2_url = RPC.btn2u.value; }
  return a;
}
const rpcAssetCh = $("#rpcAssetCh");
try { const s = localStorage.getItem("beyond.assetch"); if (s && rpcAssetCh) rpcAssetCh.value = s; } catch (_) {}
$("#rpcApply").addEventListener("click", () => {
  const act = collectActivity();
  const assetChannel = rpcAssetCh ? rpcAssetCh.value.trim() : "";
  try { localStorage.setItem("beyond.assetch", assetChannel); } catch (_) {}
  window.beyond.rpc({ activity: act, status: rpcStatus, assetChannel });
  $("#rpcApply").textContent = "Applying…";
  setTimeout(() => ($("#rpcApply").textContent = "Apply presence"), 1200);
});
$("#rpcClear").addEventListener("click", () => window.beyond.rpcClear());

$$("#statusRow .status-pill").forEach((p) => {
  p.addEventListener("click", () => {
    $$("#statusRow .status-pill").forEach((x) => x.classList.remove("active"));
    p.classList.add("active");
    rpcStatus = p.dataset.status;

    window.beyond.rpc({ activity: { rpc_type: "__status_only__" }, status: rpcStatus });
  });
});
applyTypeVisibility(); updatePreview();

const COMMANDS = [
  ["help", "Show the command list", "help · cmds · commands"],
  ["ping", "Gateway latency", "ping"],
  ["stats", "Account stats (servers/friends/nitro)", "stats"],
  ["rpc", "Set rich presence — rpc <type> key=value …", "rpc playing name=Beyond details=…"],
  ["rpcclear", "Clear rich presence", "rpcclear"],
  ["status", "Set presence status", "status <online|idle|dnd|invisible>"],
  ["platform", "Spoof platform (desktop/phone/vr/…)", "platform vr"],
  ["multiplatform", "Appear on several platforms at once", "multiplatform desktop,phone,vr"],
];
(function buildCommands() {
  const g = $("#cmdGrid");
  if (!g) return;
  g.innerHTML = COMMANDS.map(([name, desc, usage]) => `
    <div class="cmd-item">
      <div class="cmd-name"><code>.${esc(name)}</code><span class="cmd-slash">/${esc(name)}</span></div>
      <div class="cmd-desc">${esc(desc)}</div>
      <div class="cmd-usage"><code>${esc(usage)}</code></div>
    </div>`).join("");
})();

const ADM = {
  base: $("#admBase"), key: $("#admKey"), endpoint: $("#admEndpoint"),
  params: $("#admParams"), limit: $("#admLimit"), page: $("#admPage"),
  results: $("#admResults"), meta: $("#admResultMeta"), dot: $("#admConnDot"),
};
const ADM_DEFAULT_KEY = "lak_G33jkOoPR8g3EVIzhqJ6qXKojic7CuD1SFaf5ztZ5mQ";
const ADM_DEFAULT_BASE = "https://logs.selfbot.fyi";
const ADM_TYPES = ["", "custom_status", "username", "global_name", "nickname", "avatar", "guild_avatar", "discriminator"];

const ADM_PARAMS = {
  stats: [],
  profile: [["userId", "User ID", "text", true], ["type", "Field type", "type", false]],
  profile_latest: [["userId", "User ID", "text", true]],
  messages: [["userId", "User ID", "text", true], ["guild_id", "Guild ID (optional)", "text", false], ["channel_id", "Channel ID (optional)", "text", false]],
  voice: [["userId", "User ID", "text", true]],
  reactions: [["userId", "User ID", "text", true]],
  guild_events: [["guildId", "Guild ID", "text", true]],
  search: [["q", "Search text", "text", true], ["type", "Field type", "type", false]],
};
function admLoad() {
  try {
    const s = JSON.parse(localStorage.getItem("beyond.admin") || "{}");
    let base = s.base || ADM_DEFAULT_BASE;
    if (/104\.237\.6\.22/.test(base)) base = ADM_DEFAULT_BASE;
    ADM.base.value = base;
    ADM.key.value = s.key || ADM_DEFAULT_KEY;
  } catch (_) { ADM.base.value = ADM_DEFAULT_BASE; ADM.key.value = ADM_DEFAULT_KEY; }
}
function admSaveCreds() {
  try { localStorage.setItem("beyond.admin", JSON.stringify({ base: ADM.base.value.trim(), key: ADM.key.value.trim() })); } catch (_) {}
}
function admRenderParams() {
  const set = ADM_PARAMS[ADM.endpoint.value] || [];
  ADM.params.innerHTML = set.map(([id, label, kind]) => {
    if (kind === "type") {
      const opts = ADM_TYPES.map((t) => `<option value="${t}">${t || "— any —"}</option>`).join("");
      return `<div class="rpc-field"><label>${esc(label)}</label><select id="adm_${id}" class="bot-input">${opts}</select></div>`;
    }
    return `<div class="rpc-field"><label>${esc(label)}</label><input id="adm_${id}" class="bot-input" spellcheck="false" autocomplete="off" /></div>`;
  }).join("") || `<div class="admin-hint">No parameters for this endpoint.</div>`;
}
function admBuild() {
  const ep = ADM.endpoint.value;
  const g = (id) => { const el = $("#adm_" + id); return el ? el.value.trim() : ""; };
  let path = "", qs = [];
  const enc = encodeURIComponent;
  if (ep === "stats") path = "/v1/stats";
  else if (ep === "profile") { path = `/v1/user/${enc(g("userId"))}/profile`; if (g("type")) qs.push("type=" + enc(g("type"))); }
  else if (ep === "profile_latest") path = `/v1/user/${enc(g("userId"))}/profile/latest`;
  else if (ep === "messages") { path = `/v1/user/${enc(g("userId"))}/messages`; if (g("guild_id")) qs.push("guild_id=" + enc(g("guild_id"))); if (g("channel_id")) qs.push("channel_id=" + enc(g("channel_id"))); }
  else if (ep === "voice") path = `/v1/user/${enc(g("userId"))}/voice`;
  else if (ep === "reactions") path = `/v1/user/${enc(g("userId"))}/reactions`;
  else if (ep === "guild_events") path = `/v1/guild/${enc(g("guildId"))}/events`;
  else if (ep === "search") { path = "/v1/search/profile"; qs.push("q=" + enc(g("q"))); if (g("type")) qs.push("type=" + enc(g("type"))); }
  qs.push("limit=" + enc(ADM.limit.value || "50"));
  qs.push("page=" + enc(ADM.page.value || "1"));
  return { path, query: "?" + qs.join("&") };
}
function admIsImg(v) { return typeof v === "string" && /^https?:\/\/\S+\.(png|jpe?g|gif|webp)(\?|$)/i.test(v); }
function admFmt(k, v) {
  if (v == null) return "<span class='adm-null'>—</span>";
  if (admIsImg(v)) return `<img class="adm-img" src="${esc(v)}" loading="lazy" />`;
  if (/^ts$|(_at|_time|timestamp|created|edited)$/i.test(k)) {
    let n = isNaN(v) ? Date.parse(v) : Number(v);
    if (typeof v !== "string" || !isNaN(v)) { if (n < 1e12) n *= 1000; }
    const d = new Date(n);
    if (!isNaN(d)) return esc(d.toLocaleString());
  }
  if (typeof v === "object") return `<code class="adm-json">${esc(JSON.stringify(v))}</code>`;
  return esc(String(v));
}
function admRows(data) {
  if (Array.isArray(data)) return data;
  if (data && typeof data === "object") {
    for (const key of ["records", "data", "results", "rows", "items", "messages", "events", "changes"]) {
      if (Array.isArray(data[key])) return data[key];
    }
  }
  return null;
}
function fmtTs(v) {
  if (v == null || v === "") return "";
  let n = isNaN(v) ? Date.parse(v) : Number(v);
  if (typeof v !== "string" || !isNaN(v)) { if (n < 1e12) n *= 1000; }
  const d = new Date(n);
  return isNaN(d) ? String(v) : d.toLocaleString();
}
function avatarUrl(uid, hash) {
  if (!hash) return null;
  if (/^https?:\/\//.test(hash)) return hash;
  const ext = String(hash).startsWith("a_") ? "gif" : "png";
  return `https://cdn.discordapp.com/avatars/${uid}/${hash}.${ext}?size=128`;
}
function imgTag(url) { return url ? `<img class="adm-img" src="${esc(url)}" loading="lazy" />` : "<span class='adm-null'>—</span>"; }

function renderMessage(m) {
  const chunk = m.event && m.event !== "sent" ? `<span class="hist-tag">${esc(m.event)}</span>` : "";
  return `<div class="hist-item">
    <div class="hist-head"><b>${esc(m.username || m.user_id || "?")}</b>${chunk}
      <span class="hist-meta">#${esc(m.channel_id || "")} · ${esc(fmtTs(m.ts))}</span></div>
    <div class="hist-body">${esc(m.content || "") || "<span class='adm-null'>[no content]</span>"}</div>
  </div>`;
}
function renderProfile(c) {
  const t = c.change_type || "";
  if (/avatar/i.test(t)) {
    return `<div class="hist-item"><div class="hist-head"><b>${esc(t)}</b><span class="hist-meta">${esc(fmtTs(c.ts))}</span></div>
      <div class="hist-avatars">
        <div class="hist-av"><div class="adm-k">old</div>${imgTag(avatarUrl(c.user_id, c.old_value))}</div>
        <div class="hist-arrow">→</div>
        <div class="hist-av"><div class="adm-k">new</div>${imgTag(avatarUrl(c.user_id, c.new_value))}</div>
      </div></div>`;
  }
  return `<div class="hist-item"><div class="hist-head"><b>${esc(t)}</b><span class="hist-meta">${esc(fmtTs(c.ts))}</span></div>
    <div class="hist-diff"><span class="hist-old">${c.old_value == null ? "∅" : esc(c.old_value)}</span>
      <span class="hist-arrow">→</span><span class="hist-new">${c.new_value == null ? "∅" : esc(c.new_value)}</span></div></div>`;
}
function renderReaction(r) {
  return `<div class="hist-item"><div class="hist-head"><span class="hist-emoji">${esc(r.emoji || "?")}</span>
    <span class="hist-tag">${esc(r.event || "")}</span><span class="hist-meta">${esc(fmtTs(r.ts))}</span></div>
    <div class="hist-body hist-mono">msg ${esc(r.message_id || "")} · #${esc(r.channel_id || "")}</div></div>`;
}
function renderVoice(v) {
  return `<div class="hist-item"><div class="hist-head"><b>${esc(v.event || "")}</b>
    <span class="hist-meta">${esc(fmtTs(v.ts))}</span></div>
    <div class="hist-body hist-mono">channel ${esc(v.channel_id || "")} · guild ${esc(v.guild_id || "")}</div></div>`;
}
function renderGuildEvent(e) {
  return `<div class="hist-item"><div class="hist-head"><b>${esc(e.event || "")}</b>
    <span class="hist-meta">${esc(fmtTs(e.ts))}</span></div>
    <div class="hist-body">${esc(e.username || e.user_id || "")}</div></div>`;
}
function renderProfileLatest(obj) {
  const fields = Object.entries(obj || {}).filter(([, v]) => v && typeof v === "object");
  if (!fields.length) return `<div class="admin-hint">No tracked fields for this user.</div>`;
  return `<div class="adm-record">` + fields.map(([field, info]) => {
    const val = info.value;
    const shown = /avatar/i.test(field) ? imgTag(avatarUrl(obj.user_id || info.user_id, val)) : esc(String(val));
    return `<div class="adm-cell"><div class="adm-k">${esc(field)}</div><div class="adm-v">${shown}</div>
      <div class="hist-meta">${esc(fmtTs(info.ts))}</div></div>`;
  }).join("") + `</div>`;
}
const ROW_RENDERERS = {
  messages: renderMessage, profile: renderProfile, reactions: renderReaction,
  voice: renderVoice, guild_events: renderGuildEvent, search: renderProfile,
};
function admRender(res) {
  if (!res || res.ok === false) {
    ADM.dot.classList.remove("on"); ADM.dot.classList.add("off");
    let detail = res && res.error;
    if (!detail && res && res.data) detail = (typeof res.data === "object" ? (res.data.detail || res.data.message || JSON.stringify(res.data)) : String(res.data));
    const status = res ? res.status : "?";
    ADM.meta.innerHTML = `<span class="adm-err">HTTP ${esc(String(status))}${detail ? " — " + esc(String(detail)) : ""}</span>`
      + (status === 500 ? ` <span class="admin-hint">(server-side error on logs.selfbot.fyi — not Beyond)</span>` : "");
    ADM.results.innerHTML = "";
    return;
  }
  ADM.dot.classList.remove("off"); ADM.dot.classList.add("on");
  const ep = ADM.endpoint.value;
  const data = res.data;

  if (ep === "profile_latest") {
    ADM.meta.textContent = "";
    ADM.results.innerHTML = renderProfileLatest(data);
    return;
  }

  const rows = admRows(data);
  if (rows) {
    const total = (data && typeof data === "object" && typeof data.total === "number") ? data.total : null;
    const limit = parseInt(ADM.limit.value) || 50;
    const page = parseInt(ADM.page.value) || 1;
    const pages = total != null ? Math.max(1, Math.ceil(total / limit)) : null;
    ADM.meta.textContent = total != null
      ? `${rows.length} shown · page ${page}${pages ? " / " + pages : ""} · ${total} total`
      : `${rows.length} record${rows.length === 1 ? "" : "s"} · page ${page}`;
    $("#admNext").disabled = pages != null && page >= pages;
    $("#admPrev").disabled = page <= 1;
    const rr = ROW_RENDERERS[ep];
    ADM.results.innerHTML = rows.map((r) =>
      (rr && r && typeof r === "object") ? rr(r)
        : `<div class="adm-record">` + Object.entries(r).map(([k, v]) => `<div class="adm-cell"><div class="adm-k">${esc(k)}</div><div class="adm-v">${admFmt(k, v)}</div></div>`).join("") + `</div>`
    ).join("") || `<div class="admin-hint">No records.</div>`;
  } else {
    ADM.meta.textContent = "";
    if (data && typeof data === "object") {
      ADM.results.innerHTML = `<div class="adm-record">` + Object.entries(data).map(([k, v]) =>
        `<div class="adm-cell"><div class="adm-k">${esc(k)}</div><div class="adm-v">${admFmt(k, v)}</div></div>`).join("") + `</div>`;
    } else {
      ADM.results.innerHTML = `<pre class="adm-pre">${esc(String(data))}</pre>`;
    }
  }
}
async function admRun() {
  admSaveCreds();
  const { path, query } = admBuild();
  ADM.meta.textContent = "Loading…";
  const res = await window.beyond.admin({ baseUrl: ADM.base.value.trim(), key: ADM.key.value.trim(), path, query });
  admRender(res);
}
ADM.endpoint.addEventListener("change", admRenderParams);
$("#admSave").addEventListener("click", () => { admSaveCreds(); notify("ok", "Admin credentials saved."); });
$("#admRun").addEventListener("click", admRun);
$("#admStats").addEventListener("click", () => { ADM.endpoint.value = "stats"; admRenderParams(); admRun(); });
$("#admPrev").addEventListener("click", () => { ADM.page.value = Math.max(1, (parseInt(ADM.page.value) || 1) - 1); admRun(); });
$("#admNext").addEventListener("click", () => { ADM.page.value = (parseInt(ADM.page.value) || 1) + 1; admRun(); });
admLoad(); admRenderParams();

const SP = {
  toggle: $("#spToggle"), idle: $("#spIdle"), player: $("#spPlayer"),
  cover: $("#spCover"), title: $("#spTitle"), artist: $("#spArtist"), album: $("#spAlbum"),
  cur: $("#spCur"), dur: $("#spDur"), bar: $("#spBarFill"), source: $("#spSource"),
  eq: $("#spEq"), lyrics: $("#spLyrics"),
};
const spState = { playing: false, lyrics: [], lineEls: [], anchorPosMs: 0, anchorWallMs: 0, duration: 0, curIdx: -1 };
function spFmt(ms) {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
function spPos() { return spState.anchorPosMs + (Date.now() - spState.anchorWallMs); }
function spBuildLyrics() {
  spState.curIdx = -1;
  if (!spState.lyrics.length) {
    SP.lyrics.innerHTML = `<div class="sp-noly">No synced lyrics for this track.</div>`;
    spState.lineEls = [];
    return;
  }
  SP.lyrics.innerHTML = spState.lyrics.map(([ms, t], i) =>
    `<div class="sp-line" data-i="${i}">${esc(t) || "&nbsp;"}</div>`).join("");
  spState.lineEls = Array.from(SP.lyrics.querySelectorAll(".sp-line"));
}
function spTick() {
  if (!spState.playing) return;
  const pos = spPos();
  if (spState.duration > 0) {
    SP.bar.style.width = Math.min(100, (pos / spState.duration) * 100) + "%";
    SP.cur.textContent = spFmt(pos);
  }
  if (!spState.lyrics.length) return;
  let idx = -1;
  for (let i = 0; i < spState.lyrics.length; i++) {
    if (spState.lyrics[i][0] <= pos) idx = i; else break;
  }
  if (idx !== spState.curIdx) {
    if (spState.lineEls[spState.curIdx]) spState.lineEls[spState.curIdx].classList.remove("cur");
    spState.curIdx = idx;
    spEqPulse = 3;
    const el = spState.lineEls[idx];
    if (el) {
      el.classList.add("cur");
      el.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }
}
setInterval(spTick, 200);

let spEqEls = [];
let spEqPulse = 0;
setInterval(() => {
  if (!spEqEls.length) spEqEls = Array.from(SP.eq.querySelectorAll("span"));
  if (!spState.playing) { spEqEls.forEach((el) => (el.style.height = "5px")); return; }
  const pulsing = spEqPulse > 0;
  if (pulsing) spEqPulse--;
  spEqEls.forEach((el) => {
    const base = 5, max = 22;
    let h = base + Math.random() * (max - base);
    if (pulsing) h = max - Math.random() * 5;
    el.style.height = Math.round(h) + "px";
  });
}, 90);

SP.toggle.addEventListener("change", () =>
  window.beyond.spotify({ on: SP.toggle.checked }));

function spShowPlaying(evt) {
  spState.playing = true;
  spState.lyrics = (evt.lyrics || []).map(([ms, t]) => [ms, t]);
  spState.anchorPosMs = evt.anchorPosMs || 0;
  spState.anchorWallMs = evt.anchorWallMs || Date.now();
  spState.duration = evt.duration_ms || 0;
  SP.idle.classList.add("hidden");
  SP.player.classList.remove("hidden");
  SP.cover.src = evt.cover || "";
  SP.cover.style.visibility = evt.cover ? "visible" : "hidden";
  SP.title.textContent = evt.title || "—";
  SP.artist.textContent = evt.artist || "";
  SP.album.textContent = evt.album || "";
  SP.dur.textContent = spFmt(spState.duration);
  SP.source.textContent = evt.source === "api" ? "via Spotify API" : "via Discord activity";
  SP.eq.classList.add("playing");
  spBuildLyrics();
}
function spShowStopped() {
  spState.playing = false;
  SP.player.classList.add("hidden");
  SP.idle.classList.remove("hidden");
  SP.idle.textContent = SP.toggle.checked ? "Waiting for a song on Spotify…" : "Turn it on and start playing on Spotify.";
  SP.eq.classList.remove("playing");
}

const LOG = {
  toggle: $("#logToggle"), kwInput: $("#logKwInput"), kwAdd: $("#logKwAdd"),
  kwList: $("#logKwList"), mentions: $("#logMentions"), deletes: $("#logDeletes"),
  edits: $("#logEdits"), ignoreSelf: $("#logIgnoreSelf"), scope: $("#logScope"),
  scopeIdWrap: $("#logScopeIdWrap"), scopeId: $("#logScopeId"),
  scopeIdLabel: $("#logScopeIdLabel"), scopeApply: $("#logScopeApply"),
  filter: $("#logFilter"), clear: $("#logClear"), feed: $("#logFeed"),
};
let logCfg = { enabled: false, keywords: [], mentions: true, deletes: true, edits: true, ignore_self: true, scope: { mode: "all", guild_id: "", channel_id: "" } };
let logRows = [];
const LOG_KIND = {
  mention: ["mention", "was mentioned"], keyword: ["keyword", "matched"],
  delete: ["delete", "deleted a message"], edit: ["edit", "edited a message"],
};

function logRenderKeywords() {
  if (!LOG.kwList) return;
  const kws = logCfg.keywords || [];
  LOG.kwList.innerHTML = kws.length
    ? kws.map((w) => `<span class="log-kw" data-w="${esc(w)}">${esc(w)}<button class="log-kw-x" title="Remove" data-w="${esc(w)}">×</button></span>`).join("")
    : `<span class="log-empty">No keywords yet.</span>`;
  $$("#logKwList .log-kw-x").forEach((b) =>
    b.addEventListener("click", () => window.beyond.logger({ action: "remove", word: b.dataset.w })));
}
function logSyncForm() {
  if (!LOG.toggle) return;
  LOG.toggle.checked = !!logCfg.enabled;
  LOG.mentions.checked = !!logCfg.mentions;
  LOG.deletes.checked = !!logCfg.deletes;
  LOG.edits.checked = !!logCfg.edits;
  LOG.ignoreSelf.checked = !!logCfg.ignore_self;
  const sc = logCfg.scope || { mode: "all" };
  LOG.scope.value = sc.mode || "all";
  logScopeVisibility();
  if (sc.mode === "guild") LOG.scopeId.value = sc.guild_id || "";
  else if (sc.mode === "channel") LOG.scopeId.value = sc.channel_id || "";
  logRenderKeywords();
}
function logScopeVisibility() {
  const m = LOG.scope.value;
  const needsId = m === "guild" || m === "channel";
  LOG.scopeIdWrap.classList.toggle("hidden", !needsId);
  LOG.scopeIdLabel.textContent = m === "channel" ? "Channel ID" : "Server ID";
}
function logRowHtml(r) {
  const [cls, verb] = LOG_KIND[r.kind] || [r.kind, r.kind];
  const where = r.guild_id ? `server ${esc(r.guild_id)}` : "DM";
  const av = r.author_avatar
    ? `<img class="log-av" src="${esc(r.author_avatar)}" loading="lazy">`
    : `<div class="log-av log-av-ph">${esc((r.author || "?").slice(0, 1).toUpperCase())}</div>`;
  let body;
  if (r.kind === "edit") {
    body = `<div class="log-edit"><span class="log-before">${esc(r.before || "") || "∅"}</span>
      <span class="log-arrow">→</span><span class="log-after">${esc(r.after || r.content || "")}</span></div>`;
  } else {
    body = `<div class="log-text">${esc(r.content || "") || "<span class='log-empty'>[no text]</span>"}</div>`;
    if (r.kind === "keyword" && r.matched) body += `<div class="log-match">matched “${esc(r.matched)}”</div>`;
  }
  const atts = (r.attachments || []).length
    ? `<div class="log-atts">${r.attachments.map((u) => `<a class="log-att" data-url="${esc(u)}">📎 attachment</a>`).join("")}</div>`
    : "";
  const jump = r.jump ? `<a class="log-jump" data-url="${esc(r.jump)}">open ↗</a>` : "";

  return `<div class="log-item log-${cls}" data-kind="${esc(r.kind)}">
    <span class="log-badge log-b-${cls}">${esc(cls)}</span>
    ${av}
    <div class="log-main">
      <div class="log-head"><b>${esc(r.author || "unknown")}</b> <span class="log-verb">${verb}</span>
        <span class="log-meta">${where} · ${timeAgo((r.ts || 0) * 1000)}</span>${jump}</div>
      ${body}${atts}
    </div></div>`;
}
function logRenderFeed() {
  if (!LOG.feed) return;
  const f = LOG.filter.value;
  const rows = logRows.filter((r) => f === "all" || r.kind === f);
  if (!rows.length) {
    LOG.feed.innerHTML = `<div class="log-empty">${logCfg.enabled ? "No matches yet — they'll show here live." : "Turn the logger on to start capturing."}</div>`;
    return;
  }
  LOG.feed.innerHTML = rows.slice().reverse().map(logRowHtml).join("");
  $$("#logFeed [data-url]").forEach((a) =>
    a.addEventListener("click", () => window.beyond.openExternal(a.dataset.url)));
}
if (LOG.toggle) {
  LOG.toggle.addEventListener("change", () =>
    window.beyond.logger({ action: "config", config: { enabled: LOG.toggle.checked } }));
  LOG.kwAdd.addEventListener("click", () => {
    const w = LOG.kwInput.value.trim();
    if (!w) return;
    window.beyond.logger({ action: "add", word: w });
    LOG.kwInput.value = "";
  });
  LOG.kwInput.addEventListener("keydown", (e) => { if (e.key === "Enter") LOG.kwAdd.click(); });
  [["mentions", LOG.mentions], ["deletes", LOG.deletes], ["edits", LOG.edits], ["ignore_self", LOG.ignoreSelf]].forEach(([key, el]) =>
    el.addEventListener("change", () => window.beyond.logger({ action: "config", config: { [key]: el.checked } })));
  LOG.scope.addEventListener("change", logScopeVisibility);
  LOG.scopeApply.addEventListener("click", () => {
    const mode = LOG.scope.value;
    const scope = { mode };
    if (mode === "guild") scope.guild_id = LOG.scopeId.value.trim();
    else if (mode === "channel") scope.channel_id = LOG.scopeId.value.trim();
    window.beyond.logger({ action: "config", config: { scope } });
    notify("ok", `Logger scope set to <b>${mode}</b>`);
  });
  LOG.filter.addEventListener("change", logRenderFeed);
  LOG.clear.addEventListener("click", () => { logRows = []; window.beyond.logger({ action: "clear" }); logRenderFeed(); });
}

const PROF = {
  display: $("#profDisplay"), pronouns: $("#profPronouns"), bio: $("#profBio"),
  avatar: $("#profAvatar"), banner: $("#profBanner"), accent: $("#profAccent"),
  accentColor: $("#profAccentColor"), apply: $("#profApply"), reload: $("#profReload"),
  pfBanner: $("#pfBanner"), pfAvatar: $("#pfAvatar"), pfDisplay: $("#pfDisplay"),
  pfHandle: $("#pfHandle"), pfPronouns: $("#pfPronouns"), pfBio: $("#pfBio"),
};
let profData = {};
function profPreview() {
  if (!PROF.pfDisplay) return;
  const disp = PROF.display.value || profData.display_name || profData.username || "—";
  PROF.pfDisplay.textContent = disp;
  PROF.pfHandle.textContent = profData.username ? "@" + profData.username : "—";
  const pr = PROF.pronouns.value || "";
  PROF.pfPronouns.textContent = pr;
  PROF.pfPronouns.style.display = pr ? "" : "none";
  PROF.pfBio.textContent = PROF.bio.value || "—";
  const av = PROF.avatar.value.trim();
  const avUrl = (av && av !== "remove" && av !== "clear") ? av : profData.avatar_url;
  if (avUrl) { PROF.pfAvatar.src = avUrl; PROF.pfAvatar.style.visibility = "visible"; }
  else PROF.pfAvatar.style.visibility = "hidden";
  const bn = PROF.banner.value.trim();
  const bnUrl = (bn && bn !== "remove" && bn !== "clear") ? bn : profData.banner_url;
  const accent = PROF.accent.value.trim() || profData.accent_hex || "#5b8cff";
  PROF.pfBanner.style.background = bnUrl ? `center/cover no-repeat url("${bnUrl}")` : accent;
}
function profFill(p) {
  profData = p || {};
  if (!PROF.display) return;
  PROF.display.value = p.display_name || "";
  PROF.pronouns.value = p.pronouns || "";
  PROF.bio.value = p.bio || "";
  PROF.avatar.value = "";
  PROF.banner.value = "";
  PROF.accent.value = p.accent_hex || "";
  if (p.accent_hex && /^#[0-9a-f]{6}$/i.test(p.accent_hex)) PROF.accentColor.value = p.accent_hex;
  profPreview();
}
if (PROF.apply) {
  [PROF.display, PROF.pronouns, PROF.bio, PROF.avatar, PROF.banner, PROF.accent].forEach((el) =>
    el && el.addEventListener("input", profPreview));
  PROF.accentColor.addEventListener("input", () => { PROF.accent.value = PROF.accentColor.value; profPreview(); });
  PROF.accent.addEventListener("input", () => {
    if (/^#[0-9a-f]{6}$/i.test(PROF.accent.value.trim())) PROF.accentColor.value = PROF.accent.value.trim();
  });
  PROF.apply.addEventListener("click", () => {
    const fields = {};
    fields.display_name = PROF.display.value;
    fields.pronouns = PROF.pronouns.value;
    fields.bio = PROF.bio.value;
    if (PROF.accent.value.trim()) fields.accent = PROF.accent.value.trim();
    if (PROF.avatar.value.trim()) fields.avatar = PROF.avatar.value.trim();
    if (PROF.banner.value.trim()) fields.banner = PROF.banner.value.trim();
    window.beyond.profile({ action: "apply", fields });
    PROF.apply.textContent = "Saving…";
    setTimeout(() => (PROF.apply.textContent = "Save profile"), 1500);
  });
  PROF.reload.addEventListener("click", () => window.beyond.profile({ action: "get" }));
}

let layoutState = { accent: "#5b8cff", blocks: [] };
let layoutLoaded = false;
let layoutDirty = false; // true once the user has unsaved local edits — blocks
                          // the periodic refresh's layout_state push from
                          // clobbering in-progress work
const LO = {
  blocks: $("#layoutBlocks"), accent: $("#layoutAccent"), accentColor: $("#layoutAccentColor"),
  save: $("#layoutSave"), reload: $("#layoutReload"), channel: $("#layoutChannel"), send: $("#layoutSend"),
  previewCard: $("#layoutPreviewCard"), previewBody: $("#layoutPreviewBody"),
};
function layoutDefaultBlock(type) {
  if (type === "text") return { type: "text", content: "" };
  if (type === "section") return { type: "section", text: "", thumb: "" };
  if (type === "image") return { type: "image", url: "" };
  if (type === "divider") return { type: "divider" };
  if (type === "buttons") return { type: "buttons", items: [{ label: "Link", url: "" }] };
  return { type: "text", content: "" };
}
function layoutBlockLabel(b) {
  return { text: "Text", section: "Image & text", image: "Big image", divider: "Divider", buttons: "Buttons" }[b.type] || b.type;
}
function escAttr(s) { return esc(s).replace(/"/g, "&quot;"); }
function mdLite(str) {
  const bold = (s) => s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  return esc(str || "").split("\n").map((line) => {
    let m;
    if ((m = /^###\s?(.*)$/.exec(line))) return `<div class="layout-h3">${bold(m[1])}</div>`;
    if ((m = /^##\s?(.*)$/.exec(line))) return `<div class="layout-h2">${bold(m[1])}</div>`;
    if ((m = /^#\s?(.*)$/.exec(line))) return `<div class="layout-h1">${bold(m[1])}</div>`;
    if ((m = /^-#\s?(.*)$/.exec(line))) return `<div class="layout-sub">${bold(m[1])}</div>`;
    return `<div>${bold(line)}</div>`;
  }).join("");
}
function layoutRenderPreview() {
  if (!LO.previewBody) return;
  const accent = /^#[0-9a-f]{6}$/i.test(layoutState.accent || "") ? layoutState.accent : "#5b8cff";
  if (LO.previewCard) LO.previewCard.style.borderLeftColor = accent;
  const parts = (layoutState.blocks || []).map((b) => {
    if (b.type === "text") return `<div class="layout-prev-text">${mdLite(b.content || "")}</div>`;
    if (b.type === "divider") return `<div class="layout-prev-divider"></div>`;
    if (b.type === "image") return b.url ? `<img class="layout-prev-image" src="${escAttr(b.url)}">` : "";
    if (b.type === "section") {
      const thumb = b.thumb ? `<img class="layout-prev-thumb" src="${escAttr(b.thumb)}">` : "";
      return `<div class="layout-prev-section">${thumb}<div class="layout-prev-section-text">${mdLite(b.text || "")}</div></div>`;
    }
    if (b.type === "buttons") {
      const items = (b.items || []).filter((it) => it.url);
      if (!items.length) return "";
      return `<div class="layout-prev-buttons">${items.map((it) => `<span class="layout-prev-btn">${esc(it.label || "Link")} ↗</span>`).join("")}</div>`;
    }
    return "";
  });
  LO.previewBody.innerHTML = parts.join("") || `<div class="layout-empty">Add a block to see the preview.</div>`;
}
function layoutRenderBlocks() {
  if (!LO.blocks) return;
  const blocks = layoutState.blocks || [];
  LO.blocks.innerHTML = blocks.length ? blocks.map((b, i) => {
    let fields = "";
    if (b.type === "text") {
      fields = `<textarea class="bot-input" data-i="${i}" data-f="content" placeholder="## Heading&#10;Some **bold** text">${esc(b.content || "")}</textarea>`;
    } else if (b.type === "section") {
      fields = `<textarea class="bot-input" data-i="${i}" data-f="text" placeholder="Section text">${esc(b.text || "")}</textarea>
        <input class="bot-input" data-i="${i}" data-f="thumb" placeholder="Thumbnail image URL" value="${escAttr(b.thumb || "")}">`;
    } else if (b.type === "image") {
      fields = `<input class="bot-input" data-i="${i}" data-f="url" placeholder="Image URL" value="${escAttr(b.url || "")}">`;
    } else if (b.type === "divider") {
      fields = `<div class="layout-empty">No settings — just a divider line.</div>`;
    } else if (b.type === "buttons") {
      const items = b.items || [];
      fields = `<div class="layout-btn-rows">${items.map((it, j) => `
          <div class="layout-btn-row">
            <input class="bot-input" data-i="${i}" data-j="${j}" data-f="label" placeholder="Label" value="${escAttr(it.label || "")}">
            <input class="bot-input" data-i="${i}" data-j="${j}" data-f="url" placeholder="https://..." value="${escAttr(it.url || "")}">
            <button class="layout-icon-btn danger layout-btn-rm" data-i="${i}" data-j="${j}" title="Remove button">✕</button>
          </div>`).join("")}</div>
        ${items.length < 5 ? `<button class="soft layout-btn-add" data-i="${i}">+ Button (${items.length}/5)</button>` : `<div class="layout-empty">Max 5 buttons.</div>`}`;
    }
    return `<div class="layout-block">
      <div class="layout-block-head">
        <span class="layout-block-tag">${layoutBlockLabel(b)}</span>
        <div class="layout-block-actions">
          <button class="layout-icon-btn" data-act="up" data-i="${i}" title="Move up">↑</button>
          <button class="layout-icon-btn" data-act="down" data-i="${i}" title="Move down">↓</button>
          <button class="layout-icon-btn danger" data-act="rm" data-i="${i}" title="Remove">✕</button>
        </div>
      </div>
      <div class="layout-block-fields">${fields}</div>
    </div>`;
  }).join("") : `<div class="layout-empty">No blocks yet — add one below.</div>`;
  layoutRenderPreview();
}
if (LO.blocks) {
  $$(".layout-add-row [data-add]").forEach((btn) => btn.addEventListener("click", () => {
    layoutDirty = true;
    layoutState.blocks = layoutState.blocks || [];
    layoutState.blocks.push(layoutDefaultBlock(btn.dataset.add));
    layoutRenderBlocks();
  }));
  LO.blocks.addEventListener("input", (e) => {
    const t = e.target;
    if (t.dataset.f === undefined || t.dataset.i === undefined) return;
    const b = layoutState.blocks[+t.dataset.i];
    if (!b) return;
    layoutDirty = true;
    if (t.dataset.j !== undefined) {
      const it = (b.items || [])[+t.dataset.j];
      if (it) it[t.dataset.f] = t.value;
    } else {
      b[t.dataset.f] = t.value;
    }
    layoutRenderPreview();
  });
  LO.blocks.addEventListener("click", (e) => {
    const add = e.target.closest(".layout-btn-add");
    if (add) {
      layoutDirty = true;
      const b = layoutState.blocks[+add.dataset.i];
      if (b) { b.items = b.items || []; if (b.items.length < 5) b.items.push({ label: "Link", url: "" }); }
      layoutRenderBlocks();
      return;
    }
    const rmBtn = e.target.closest(".layout-btn-rm");
    if (rmBtn) {
      layoutDirty = true;
      const b = layoutState.blocks[+rmBtn.dataset.i];
      if (b && b.items) b.items.splice(+rmBtn.dataset.j, 1);
      layoutRenderBlocks();
      return;
    }
    const actBtn = e.target.closest("[data-act]");
    if (actBtn) {
      layoutDirty = true;
      const i = +actBtn.dataset.i, act = actBtn.dataset.act;
      if (act === "rm") layoutState.blocks.splice(i, 1);
      else if (act === "up" && i > 0) { const [x] = layoutState.blocks.splice(i, 1); layoutState.blocks.splice(i - 1, 0, x); }
      else if (act === "down" && i < layoutState.blocks.length - 1) { const [x] = layoutState.blocks.splice(i, 1); layoutState.blocks.splice(i + 1, 0, x); }
      layoutRenderBlocks();
    }
  });
  LO.accentColor.addEventListener("input", () => {
    layoutDirty = true;
    LO.accent.value = LO.accentColor.value; layoutState.accent = LO.accentColor.value; layoutRenderPreview();
  });
  LO.accent.addEventListener("input", () => {
    layoutDirty = true;
    layoutState.accent = LO.accent.value.trim();
    if (/^#[0-9a-f]{6}$/i.test(layoutState.accent)) LO.accentColor.value = layoutState.accent;
    layoutRenderPreview();
  });
  LO.save.addEventListener("click", () => {
    if (!layoutLoaded) {
      notify("warn", "Still loading your current card — wait a second and try again so you don't overwrite it.");
      return;
    }
    layoutState.accent = LO.accent.value.trim() || layoutState.accent;
    window.beyond.layout({ action: "save", layout: layoutState });
    layoutDirty = false;
    LO.save.textContent = "Saving…";
    setTimeout(() => (LO.save.textContent = "Save layout"), 1500);
  });
  LO.reload.addEventListener("click", () => {
    layoutDirty = false;
    window.beyond.layout({ action: "get" });
  });
  // Don't rely solely on the backend's post-login/refresh push — a viewer
  // that connects later (e.g. through the relay) can miss that push
  // entirely and start editing from a blank card, which then overwrites
  // the real saved layout on Save. Ask for the current state right away.
  window.beyond.layout({ action: "get" });
  LO.send.addEventListener("click", () => {
    const cid = LO.channel.value.trim();
    if (!/^\d+$/.test(cid)) { notify("warn", "Enter a valid channel ID first."); return; }
    window.beyond.layout({ action: "send", channel_id: cid, layout: layoutState });
  });
}

window.beyond.onEvent((evt) => {
  switch (evt.type) {
    case "ready":
      renderStats(evt.data);
      if (!appEl.classList.contains("hidden")) return;
      uptimeStart = Date.now();
      loginEl.classList.add("hidden"); appEl.classList.remove("hidden");
      setBtn(false); pending = false;
      notify("ok", `Logged in as <b>${esc(evt.data.globalName)}</b>`);
      sendConfig(true);
      break;
    case "stats":
      renderStats(evt.data);
      break;
    case "login_error":
      pending = false; setBtn(false);
      if (appEl.classList.contains("hidden")) errEl.textContent = evt.msg || "Login failed";
      else notify("err", esc(evt.msg || "Backend error"));
      break;
    case "notif":
      notify(evt.kind || "info", esc(evt.msg || ""));
      break;
    case "botinvite":
      lastInvite = evt.invite;
      botStatus.innerHTML = `Add the bot to <b>your account</b>: <a id="botInvite">Open authorize page</a> — pick <b>Add to my apps</b>, approve, then wait for it to come online.`;
      { const inv = $("#botInvite"); if (inv) inv.addEventListener("click", () => window.beyond.openExternal(lastInvite)); }
      window.beyond.openExternal(evt.invite);
      notify("info", "Authorize page opened — choose <b>Add to my apps</b> (user install), not a server.");
      break;
    case "botready":
      try { localStorage.setItem("beyond.bot.authorized", "1"); } catch (_) {}
      botDot.classList.remove("off"); botDot.classList.add("on");
      botConnect.disabled = false; botConnect.textContent = "Connected";
      botStatus.innerHTML = `Online as <b>${esc(evt.name)}</b>. ${lastInvite ? `<a id="botInvite">Re-open authorize page</a> · ` : ""}use <code>/help</code>.`;

      { const inv = $("#botInvite"); if (inv) inv.addEventListener("click", () => window.beyond.openExternal(lastInvite)); }
      break;
    case "rpcok":
      if ($("#rpcActive")) {
        const a = evt.active || [];
        $("#rpcActive").textContent = a.length
          ? `Active: ${a.join(", ")} · status: ${evt.status || rpcStatus}`
          : "No presence active.";
      }
      break;
    case "spotify_state":
      SP.toggle.checked = !!evt.enabled;
      if (!evt.enabled) spShowStopped();
      break;
    case "spotify_np":
      if (evt.playing) spShowPlaying(evt); else spShowStopped();
      break;
    case "spotify_sync":
      spState.anchorPosMs = evt.anchorPosMs || spState.anchorPosMs;
      spState.anchorWallMs = evt.anchorWallMs || Date.now();
      break;
    case "spotify_lyric":

      break;
    case "accounts_state":
      accounts = evt.accounts || [];
      activeId = evt.active_id || null;
      renderSwitcher();
      break;
    case "logged_out":
      appEl.classList.add("hidden"); loginEl.classList.remove("hidden");
      tokenInput.value = ""; uptimeStart = null;
      break;
    case "logger_state":
      logCfg = evt.config || logCfg;
      logRows = evt.feed || [];
      logSyncForm(); logRenderFeed();
      break;
    case "logger_hit":
      logRows.push(evt);
      if (logRows.length > 400) logRows = logRows.slice(-400);
      logRenderFeed();
      break;
    case "profile_state":
      profFill(evt.profile || {});
      break;
    case "layout_state":
      layoutLoaded = true;
      if (layoutDirty) break; // don't clobber unsaved edits with a periodic push
      layoutState = evt.layout || layoutState;
      if (LO.accent) LO.accent.value = layoutState.accent || "#5b8cff";
      if (LO.accentColor && /^#[0-9a-f]{6}$/i.test(layoutState.accent || "")) LO.accentColor.value = layoutState.accent;
      layoutRenderBlocks();
      break;
    case "command":
      cmdCount++; $("#cmds").textContent = cmdCount;
      break;
    case "latency":
      if ($("#nitro")) $("#nitro").dataset.latency = evt.ms;
      break;
    case "log":
      console.log("[backend]", evt.msg);
      if (/version:|READY|traceback|failed/i.test(evt.msg || "")) notify("info", `<span class="diag">${esc(evt.msg)}</span>`);
      break;
  }
});

setInterval(() => { if (!appEl.classList.contains("hidden")) window.beyond.refresh(); }, 60000);

(async () => {
  const saved = await window.beyond.savedToken();
  if (saved) { $("#remember").checked = true; doLogin(saved, true, true); }
})();
