# Prompt for the selfbot.fyi relay (VPS) Claude session

Paste everything in the fenced block below into the VPS session.

```
Rebuild the Beyond relay on this VPS as a MULTI-TENANT service. Today it is
single-tenant (one password at /session). Replace that with per-user tenants:
every Beyond app install gets its OWN unguessable link and its OWN password,
fully isolated from every other tenant. Security is the priority — treat this
as handling account-takeover-grade secrets.

## Roles
- viewer = a browser. Opens https://selfbot.fyi/p/<slug> , logs in with the
  tenant's password.
- agent  = a user's PC app. Connects OUTBOUND and is the only thing that talks
  to Discord. Identified by (slug, agent_secret).
- relay  = THIS VPS. Serves each tenant's UI, checks passwords, and shuttles
  JSON between a viewer and the agent of the SAME slug. Never touches Discord.

## Two hostnames (already set up)
- agent.selfbot.fyi  = DNS-only / grey-cloud (NO Cloudflare challenge). Use it
  for all AGENT traffic (enroll + agent websocket), because the agent is a
  non-browser client that cannot solve a Cloudflare JS challenge.
- selfbot.fyi        = Cloudflare-proxied. Use it for all VIEWER traffic
  (the page, login, viewer websocket). Browsers solve the challenge fine.
Both terminate TLS at nginx and proxy to this app on 127.0.0.1:8787.

## Secrets (environment only; never hardcode, never log)
- BEYOND_ENROLL_KEY : a single shared key the app must present to register a new
  tenant. Generate a long random value; it gates enrollment (a speed bump
  against mass registration, NOT the main defense). Report it back.
- DB path for tenant storage (sqlite is fine).

## Storage (sqlite)
tenants(slug TEXT PRIMARY KEY,
        agent_secret_hash TEXT,   -- Argon2id/scrypt hash of the agent_secret
        password_hash TEXT,       -- Argon2id/scrypt hash of the viewer password
        created_at, last_seen)
sessions(sid TEXT PRIMARY KEY, slug TEXT, expires_at)   -- viewer cookies
Also keep, in memory: for each connected agent, its slug -> (ws, ui_bundle),
and the set of viewer websockets per slug.

## Hashing (REQUIRED)
- Hash BOTH the viewer password AND the agent_secret with Argon2id
  (argon2-cffi). If you truly cannot install it, use hashlib.scrypt
  (n=2**15, r=8, p=1) with a fresh 16-byte per-record salt. Store only the
  hash (+salt/params). Verify with a constant-time compare. Never store or log
  plaintext.
- Compare BEYOND_ENROLL_KEY with hmac.compare_digest.

## Endpoints — AGENT side (on agent.selfbot.fyi)
POST /enroll
    body: {"enroll_key","agent_secret","password"}
    - constant-time check enroll_key; if wrong -> 403.
    - generate slug = secrets.token_urlsafe(16) (~128 bits); ensure unique;
      validate ^[A-Za-z0-9_-]{16,64}$.
    - store tenant with argon2 hashes of agent_secret and password.
    - respond {"slug": "<slug>"}.
    - RATE LIMIT: per-IP (e.g. 5/hour) and cap tenants/IP; 429 on exceed.

GET /agent/ws   (websocket)
    - headers: X-Beyond-Slug: <slug>, Authorization: Bearer <agent_secret>.
    - look up tenant by slug; verify agent_secret against agent_secret_hash
      (constant-time). Wrong/missing -> 401/403, close.
    - one agent per slug: if another connects for the same slug, close the old.
    - bind this socket to slug. Update last_seen.
    - messages FROM agent: {"t":"ui_bundle","files":{"index.html":...}} (cache
      in memory for this slug; reject if >2 MB), {"t":"event","data":{...}}
      (broadcast to THIS slug's viewers only), {"t":"pong"},
      {"t":"set_password","password":...} (re-hash + update this tenant's
      password_hash — supports rotation).
    - messages TO agent: {"t":"cmd","data":{...}} (a viewer command for this
      slug), {"t":"ping"} every 20s; drop agent if no pong within 60s.

## Endpoints — VIEWER side (on selfbot.fyi)
GET /p/<slug>
    - validate slug format; unknown slug -> 404.
    - if no valid session cookie for this slug -> serve a minimal password login
      page (POSTs to /p/<slug>/login).
    - if cookie valid but that slug's agent is NOT connected (no cached bundle)
      -> 503 with a small "PC offline" page.
    - if cookie valid AND agent connected -> serve that slug's cached
      index.html bundle (Content-Type text/html). Keep x-content-type-options:
      nosniff.

POST /p/<slug>/login
    - body {"password":...}. Verify against this slug's password_hash
      (constant-time argon2 verify). Generic error on failure.
    - on success: sid = secrets.token_urlsafe(32); store sessions(sid, slug,
      expires_at=now+7d); set cookie (name generic, e.g. "bsid"):
      HttpOnly; Secure; SameSite=Lax; Path=/p/<slug>; Max-Age=7d.
      The cookie holds ONLY the sid (opaque). Redirect to /p/<slug>.
    - RATE LIMIT: per (slug, IP) ~10 tries / 10 min then temporary lockout with
      backoff; also a global per-IP cap. 429 on exceed.

GET /p/<slug>/ws   (websocket)
    - require a valid session cookie whose stored slug == this slug. Else close.
    - messages FROM viewer: {"t":"cmd","data":{...}} -> forward to the agent
      bound to THIS slug as {"t":"cmd","data":{...}}. If no agent connected,
      reply {"t":"event","data":{"type":"login_error","msg":"PC offline"}}.
    - messages TO viewer: {"t":"event","data":{...}} (this slug's agent events),
      {"t":"agent_status","online":true|false}.
    - on viewer connect: send {"t":"agent_status","online":<bool>} immediately;
      if online, send the agent {"t":"cmd","data":{"cmd":"refresh"}} so the new
      panel re-hydrates. On agent connect/drop: broadcast agent_status to that
      slug's viewers.
    - message rate cap per connection.

## Isolation (CRITICAL)
A viewer session bound to slug X may ONLY open /p/X/ws and only ever reaches
X's agent. Never route a command or event across slugs. Route strictly by slug
on every message.

## General hardening
- Validate slug format on every route; reject bad input early.
- JSON parse in try/except; cap message + bundle sizes; cap connections/slug.
- Never log secrets (password, agent_secret, enroll_key) or full slugs (log a
  short prefix). 
- Keep the existing security headers. Ensure Cloudflare "WebSockets" is ON for
  the viewer path.
- Run under systemd (auto-restart). Remove/disable the old single-tenant
  /session, /session/ws, /agent/ws-with-shared-token routes.

## REPORT BACK
1. BEYOND_ENROLL_KEY value (the user pastes it into the app's agent_config.json).
2. Confirm URLs: POST https://agent.selfbot.fyi/enroll ,
   wss://agent.selfbot.fyi/agent/ws , https://selfbot.fyi/p/<slug> ,
   https://selfbot.fyi/p/<slug>/login , wss://selfbot.fyi/p/<slug>/ws .
3. Hash algorithm used (Argon2id or scrypt).
4. Cookie attributes actually set.
5. Rate-limit values chosen for /enroll and /login.
6. Any change to the message envelope or field names above.
7. Confirm agent.selfbot.fyi is still grey-cloud (DNS-only).
```
