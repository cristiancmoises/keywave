import os, uuid, time, threading, mimetypes
from flask import Flask, request, Response, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room

# ── Configuration (all optional, via environment) ───────────────────────────
def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default

# CORS: lock this to your real origin(s) in production, e.g.
#   KEYWAVE_ALLOWED_ORIGINS=https://keywave.example.com
_origins = os.environ.get("KEYWAVE_ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = _origins if _origins == "*" else [o.strip() for o in _origins.split(",") if o.strip()]

PORT          = _env_int("KEYWAVE_PORT", 5000)
MAX_ROOMS     = _env_int("KEYWAVE_MAX_ROOMS", 5000)     # global room cap (DoS bound)
ROOM_TTL      = _env_int("KEYWAVE_ROOM_TTL", 7200)      # seconds a half-open room survives
CREATE_WINDOW = _env_int("KEYWAVE_CREATE_WINDOW", 60)
CREATE_MAX    = _env_int("KEYWAVE_CREATE_MAX", 10)      # max create_room / window / client
MSG_WINDOW    = _env_int("KEYWAVE_MSG_WINDOW", 10)
MSG_MAX       = _env_int("KEYWAVE_MSG_MAX", 120)        # max relayed msgs / window / client
MAX_PAYLOAD   = _env_int("KEYWAVE_MAX_PAYLOAD", 256 * 1024)  # bytes per relayed field
ROOM_ID_LEN   = 10

mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("text/javascript", ".js")

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["SECRET_KEY"] = os.urandom(32).hex()
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024
socketio = SocketIO(
    app,
    cors_allowed_origins=ALLOWED_ORIGINS,
    async_mode="threading",
    max_http_buffer_size=MAX_PAYLOAD * 2,
    ping_timeout=30,
    ping_interval=25,
)

# room_id -> {"peers": [sid, ...], "created": float}
rooms       = {}
sid_to_room = {}
_create_log = {}   # sid -> [timestamps]   (create_room rate limiting)
_msg_log    = {}   # sid -> [timestamps]   (msg relay rate limiting)
_lock       = threading.Lock()

ROOM_ALPHABET = set("0123456789ABCDEF")

def _valid_room_id(rid):
    return isinstance(rid, str) and len(rid) == ROOM_ID_LEN and all(c in ROOM_ALPHABET for c in rid)

def _too_big(*vals):
    total = 0
    for v in vals:
        total += len(v) if isinstance(v, str) else len(str(v))
    return total > MAX_PAYLOAD

def _rate_ok(log, sid, window, limit):
    now = time.time()
    with _lock:
        hits = [t for t in log.get(sid, []) if now - t < window]
        if len(hits) >= limit:
            log[sid] = hits
            return False
        hits.append(now)
        log[sid] = hits
        return True

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Keywave - Privacy That Flows.</title>
<link href="/static/fonts.css" rel="stylesheet">
<script src="/static/socket.io.min.js"></script>
<style>
/* ══════════════════════════════════════════════════════════
   ROOT & RESET
══════════════════════════════════════════════════════════ */
:root {
  --bg:          #03040a;
  --panel:       #080b14;
  --panel2:      #0d1120;
  --border:      #1a2540;
  --border-hi:   #2a3f6a;
  --neon:        #00ff9f;
  --neon-dim:    #00995f;
  --neon-glow:   rgba(0,255,159,0.18);
  --blue:        #00cfff;
  --blue-dim:    #0088aa;
  --warn:        #ffbb00;
  --danger:      #ff2d55;
  --text:        #8899b0;
  --text-hi:     #ccdaee;
  --text-lo:     #2a3545;
  --font-ui:     'Orbitron', monospace;
  --font-mono:   'Share Tech Mono', monospace;
  --radius:      4px;
  --transition:  0.18s ease;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body {
  height: 100%;
  background: var(--bg);
  color: var(--text-hi);
  font-family: var(--font-mono);
  font-size: 14px;
  line-height: 1.5;
  overflow: hidden;
  cursor: default;
}

/* Scanline overlay */
body::before {
  content: '';
  position: fixed; inset: 0; z-index: 9999;
  background: repeating-linear-gradient(
    0deg,
    transparent,
    transparent 2px,
    rgba(0,0,0,0.06) 2px,
    rgba(0,0,0,0.06) 4px
  );
  pointer-events: none;
}

/* ══════════════════════════════════════════════════════════
   UTILITIES
══════════════════════════════════════════════════════════ */
.hidden { display: none !important; }

.neon { color: var(--neon); }
.blue { color: var(--blue); }
.warn { color: var(--warn); }
.danger { color: var(--danger); }
.dim { color: var(--text); }

.glow {
  text-shadow: 0 0 12px var(--neon), 0 0 30px rgba(0,255,159,0.3);
}

/* ══════════════════════════════════════════════════════════
   SCREENS WRAPPER
══════════════════════════════════════════════════════════ */
#app {
  width: 100vw;
  height: 100vh;
  display: flex;
  flex-direction: column;
}

/* ══════════════════════════════════════════════════════════
   LANDING SCREEN
══════════════════════════════════════════════════════════ */
#screen-landing {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0;
  padding: 40px 20px;
}

.logo-block {
  text-align: center;
  margin-bottom: 60px;
}

.logo-title {
  font-family: var(--font-ui);
  font-size: 52px;
  font-weight: 900;
  letter-spacing: 12px;
  color: var(--neon);
  text-shadow: 0 0 20px var(--neon), 0 0 60px rgba(0,255,159,0.25);
  line-height: 1;
}

.logo-sub {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 5px;
  color: var(--text);
  margin-top: 12px;
  text-transform: uppercase;
}

.cipher-badges {
  display: flex;
  gap: 12px;
  justify-content: center;
  margin-top: 20px;
  flex-wrap: wrap;
}

.badge {
  font-size: 10px;
  letter-spacing: 2px;
  padding: 4px 10px;
  border: 1px solid var(--border-hi);
  color: var(--blue);
  border-radius: 2px;
  background: rgba(0,207,255,0.05);
  text-transform: uppercase;
}

.landing-card {
  width: 100%;
  max-width: 440px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.card-section {
  padding: 28px 32px;
}

.card-section + .card-section {
  border-top: 1px solid var(--border);
}

.card-label {
  font-family: var(--font-ui);
  font-size: 10px;
  letter-spacing: 3px;
  color: var(--text);
  text-transform: uppercase;
  margin-bottom: 16px;
}

.btn {
  font-family: var(--font-ui);
  font-size: 11px;
  letter-spacing: 3px;
  padding: 12px 24px;
  border: 1px solid;
  border-radius: var(--radius);
  cursor: pointer;
  text-transform: uppercase;
  transition: var(--transition);
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: transparent;
}

.btn-primary {
  border-color: var(--neon);
  color: var(--neon);
}
.btn-primary:hover {
  background: var(--neon-glow);
  box-shadow: 0 0 16px rgba(0,255,159,0.3);
}

.btn-secondary {
  border-color: var(--blue);
  color: var(--blue);
}
.btn-secondary:hover {
  background: rgba(0,207,255,0.08);
  box-shadow: 0 0 16px rgba(0,207,255,0.2);
}

.btn-danger {
  border-color: var(--danger);
  color: var(--danger);
}
.btn-danger:hover {
  background: rgba(255,45,85,0.1);
}

.btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.input-row {
  display: flex;
  gap: 8px;
}

.inp {
  flex: 1;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-hi);
  font-family: var(--font-mono);
  font-size: 16px;
  padding: 10px 14px;
  letter-spacing: 3px;
  text-transform: uppercase;
  outline: none;
  transition: var(--transition);
}

.inp:focus {
  border-color: var(--blue);
  box-shadow: 0 0 0 2px rgba(0,207,255,0.1);
}

.inp::placeholder {
  color: var(--text-lo);
  letter-spacing: 2px;
  text-transform: uppercase;
}

/* ══════════════════════════════════════════════════════════
   WAITING SCREEN
══════════════════════════════════════════════════════════ */
#screen-waiting {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 32px;
  padding: 40px;
}

.wait-label {
  font-family: var(--font-ui);
  font-size: 10px;
  letter-spacing: 4px;
  color: var(--text);
  text-transform: uppercase;
}

.room-id-display {
  font-family: var(--font-ui);
  font-size: 40px;
  font-weight: 900;
  letter-spacing: 16px;
  color: var(--neon);
  text-shadow: 0 0 20px var(--neon), 0 0 50px rgba(0,255,159,0.2);
  text-align: center;
  padding: 24px 36px;
  border: 1px solid var(--neon-dim);
  background: rgba(0,255,159,0.03);
  border-radius: var(--radius);
}

.pulse-indicator {
  width: 10px; height: 10px;
  border-radius: 50%;
  background: var(--warn);
  box-shadow: 0 0 12px var(--warn);
  animation: pulse 1.4s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(0.7); }
}

.wait-hint {
  font-size: 12px;
  color: var(--text);
  letter-spacing: 1px;
  text-align: center;
  max-width: 320px;
}

/* ══════════════════════════════════════════════════════════
   SESSION SCREEN
══════════════════════════════════════════════════════════ */
#screen-session {
  flex: 1;
  display: grid;
  grid-template-rows: 48px 1fr 52px;
  grid-template-columns: 1fr 360px;
  grid-template-areas:
    "header  header"
    "video   chat"
    "controls controls";
  min-height: 0;
}

/* ── Header ── */
#session-header {
  grid-area: header;
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 0 20px;
  border-bottom: 1px solid var(--border);
  background: var(--panel);
}

.header-logo {
  font-family: var(--font-ui);
  font-size: 14px;
  font-weight: 900;
  letter-spacing: 6px;
  color: var(--neon);
  text-shadow: 0 0 10px rgba(0,255,159,0.5);
}

.header-sep { color: var(--text-lo); }

.header-room {
  font-size: 12px;
  letter-spacing: 3px;
  color: var(--blue);
}

.header-status {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 16px;
}

.status-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  letter-spacing: 1px;
  color: var(--text);
}

.dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--text-lo);
  flex-shrink: 0;
  transition: var(--transition);
}
.dot.active { background: var(--neon); box-shadow: 0 0 8px var(--neon); }
.dot.warn   { background: var(--warn); box-shadow: 0 0 8px var(--warn); animation: pulse 1.4s infinite; }
.dot.error  { background: var(--danger); box-shadow: 0 0 8px var(--danger); }

/* ── Video Panel ── */
#video-panel {
  grid-area: video;
  position: relative;
  background: #000;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

#remote-video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  background: #000;
}

#local-video {
  position: absolute;
  bottom: 16px;
  right: 16px;
  width: 140px;
  height: 90px;
  object-fit: cover;
  border: 1px solid var(--border-hi);
  border-radius: var(--radius);
  background: #000;
  z-index: 10;
}

.video-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: rgba(3,4,10,0.85);
  z-index: 5;
  transition: opacity 0.3s;
}
.video-overlay.hidden { display: none; }

.overlay-icon {
  font-size: 36px;
  opacity: 0.4;
}

.overlay-text {
  font-size: 12px;
  letter-spacing: 2px;
  color: var(--text);
}

.e2e-badge {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  letter-spacing: 2px;
  padding: 4px 10px;
  border: 1px solid rgba(0,255,159,0.3);
  border-radius: 2px;
  background: rgba(0,0,0,0.6);
  color: var(--neon-dim);
  backdrop-filter: blur(4px);
  text-transform: uppercase;
}
.e2e-badge.active { color: var(--neon); border-color: rgba(0,255,159,0.6); }

/* ── Chat Panel ── */
#chat-panel {
  grid-area: chat;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--border);
  background: var(--panel);
  min-height: 0;
}

#messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
}

#messages-area::-webkit-scrollbar { width: 4px; }
#messages-area::-webkit-scrollbar-track { background: transparent; }
#messages-area::-webkit-scrollbar-thumb { background: var(--border-hi); border-radius: 2px; }

.msg-bubble {
  max-width: 90%;
  animation: msgIn 0.15s ease;
}

@keyframes msgIn {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}

.msg-bubble.local { align-self: flex-end; }
.msg-bubble.remote { align-self: flex-start; }

.msg-meta {
  font-size: 10px;
  letter-spacing: 1px;
  color: var(--text-lo);
  margin-bottom: 4px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.msg-bubble.local .msg-meta { justify-content: flex-end; }

.msg-body {
  padding: 8px 12px;
  border-radius: var(--radius);
  font-size: 13px;
  line-height: 1.5;
  word-break: break-word;
}

.msg-bubble.local .msg-body {
  background: rgba(0,207,255,0.1);
  border: 1px solid rgba(0,207,255,0.2);
  color: var(--text-hi);
}

.msg-bubble.remote .msg-body {
  background: var(--panel2);
  border: 1px solid var(--border);
  color: var(--text-hi);
}

.msg-lock {
  font-size: 9px;
  opacity: 0.5;
}

#chat-input-area {
  display: flex;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid var(--border);
}

#msg-input {
  flex: 1;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-hi);
  font-family: var(--font-mono);
  font-size: 13px;
  padding: 8px 12px;
  outline: none;
  transition: var(--transition);
}
#msg-input:focus {
  border-color: var(--border-hi);
}
#msg-input:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
#msg-input::placeholder { color: var(--text-lo); }

#send-btn {
  font-family: var(--font-ui);
  font-size: 9px;
  letter-spacing: 2px;
  padding: 8px 14px;
  border: 1px solid var(--blue-dim);
  border-radius: var(--radius);
  color: var(--blue);
  background: transparent;
  cursor: pointer;
  text-transform: uppercase;
  transition: var(--transition);
}
#send-btn:hover {
  background: rgba(0,207,255,0.08);
  border-color: var(--blue);
}
#send-btn:disabled { opacity: 0.3; cursor: not-allowed; }

/* System messages in chat */
.sys-msg {
  text-align: center;
  font-size: 10px;
  letter-spacing: 2px;
  color: var(--text-lo);
  padding: 4px 0;
  text-transform: uppercase;
}
.sys-msg.ok { color: var(--neon-dim); }
.sys-msg.warn { color: var(--warn); opacity: 0.7; }

/* ── Controls Bar ── */
#controls-bar {
  grid-area: controls;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 0 20px;
  border-top: 1px solid var(--border);
  background: var(--panel);
}

.ctrl-btn {
  width: 40px; height: 40px;
  border-radius: 50%;
  border: 1px solid var(--border-hi);
  background: var(--panel2);
  color: var(--text-hi);
  font-size: 16px;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: var(--transition);
  flex-shrink: 0;
}
.ctrl-btn:hover { border-color: var(--text); }
.ctrl-btn.active {
  border-color: var(--neon);
  color: var(--neon);
  box-shadow: 0 0 10px rgba(0,255,159,0.2);
}
.ctrl-btn.muted {
  border-color: var(--danger);
  color: var(--danger);
  background: rgba(255,45,85,0.08);
}

.ctrl-end {
  width: 48px; height: 40px;
  border-radius: 20px;
  border: 1px solid var(--danger);
  background: rgba(255,45,85,0.12);
  color: var(--danger);
  font-size: 18px;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: var(--transition);
}
.ctrl-end:hover {
  background: rgba(255,45,85,0.25);
  box-shadow: 0 0 12px rgba(255,45,85,0.3);
}

.crypto-info {
  margin-left: auto;
  font-size: 10px;
  letter-spacing: 1.5px;
  color: var(--text-lo);
  display: flex;
  align-items: center;
  gap: 6px;
  text-transform: uppercase;
}
.crypto-info.ready { color: var(--neon-dim); }

/* ══════════════════════════════════════════════════════════
   TOAST / LOG
══════════════════════════════════════════════════════════ */
#toast-area {
  position: fixed;
  bottom: 70px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
}

.toast {
  font-size: 11px;
  letter-spacing: 1.5px;
  padding: 8px 18px;
  border-radius: var(--radius);
  border: 1px solid var(--border-hi);
  background: var(--panel);
  color: var(--text);
  animation: toastIn 0.2s ease, toastOut 0.3s ease 2.8s forwards;
  text-transform: uppercase;
  white-space: nowrap;
  backdrop-filter: blur(4px);
}
.toast.ok    { border-color: var(--neon-dim); color: var(--neon); }
.toast.error { border-color: var(--danger); color: var(--danger); }
.toast.warn  { border-color: var(--warn); color: var(--warn); }

@keyframes toastIn  { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
@keyframes toastOut { from { opacity: 1; } to { opacity: 0; transform: translateY(-6px); } }

/* ══════════════════════════════════════════════════════════
   INVITE / SHARE
══════════════════════════════════════════════════════════ */
.invite-card {
  width: 100%; max-width: 440px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
}
.share-link-row { display: flex; gap: 8px; margin-bottom: 14px; }
.share-link-row .inp {
  font-size: 13px; letter-spacing: 1px; text-transform: none;
  padding: 10px 12px;
}
.share-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
.share-btn {
  font-family: var(--font-ui);
  font-size: 10px; letter-spacing: 1px;
  padding: 12px 6px; min-height: 46px;
  border: 1px solid var(--border-hi);
  background: var(--panel2); color: var(--text-hi);
  border-radius: var(--radius);
  cursor: pointer; text-transform: uppercase;
  transition: var(--transition);
}
.share-btn:hover    { border-color: var(--blue);  color: var(--blue); }
.share-btn.wa:hover { border-color: #25d366; color: #25d366; }
.share-btn.tg:hover { border-color: #29a9eb; color: #29a9eb; }
.share-btn.go:hover { border-color: var(--neon); color: var(--neon); }
.share-hint { font-size: 10px; margin-top: 12px; line-height: 1.5; text-align: center; }

/* ══════════════════════════════════════════════════════════
   RESPONSIVE  (desktop + phones, safe-area aware)
══════════════════════════════════════════════════════════ */
#session-header { padding-top: env(safe-area-inset-top); }
#controls-bar   { padding-bottom: env(safe-area-inset-bottom); }
#screen-landing, #screen-waiting {
  padding-left:  max(20px, env(safe-area-inset-left));
  padding-right: max(20px, env(safe-area-inset-right));
}

@media (max-width: 760px) {
  #screen-session {
    grid-template-columns: 1fr;
    grid-template-rows: auto minmax(180px, 36vh) 1fr auto;
    grid-template-areas:
      "header"
      "video"
      "chat"
      "controls";
  }
  #session-header { height: auto; min-height: 48px; flex-wrap: wrap; gap: 8px 14px; padding: 8px 14px; }
  .header-status { gap: 10px; flex-wrap: wrap; }
  #controls-bar { min-height: 56px; padding: 8px 14px; }
  #chat-panel { border-left: none; border-top: 1px solid var(--border); }
  #local-video { width: 96px; height: 64px; bottom: 12px; right: 12px; }
  .logo-title { font-size: 32px; letter-spacing: 6px; }
  .room-id-display { font-size: 26px; letter-spacing: 8px; padding: 18px 20px; }
  .ctrl-btn { width: 44px; height: 44px; }      /* comfortable touch targets */
  .ctrl-end { width: 52px; height: 44px; }
  .crypto-info { display: none; }                /* free up width on small bars */
}

@media (max-width: 360px) {
  .share-grid { grid-template-columns: repeat(2, 1fr); }
  .logo-title { font-size: 26px; letter-spacing: 4px; }
}

/* ══════════════════════════════════════════════════════════
   VERIFICATION MODAL (safety number / SAS)
══════════════════════════════════════════════════════════ */
.modal-overlay {
  position: fixed; inset: 0; z-index: 2000;
  background: rgba(3,4,10,0.88);
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
  backdrop-filter: blur(4px);
}
.modal-overlay.hidden { display: none; }
.modal-box {
  width: 100%; max-width: 440px;
  background: var(--panel);
  border: 1px solid var(--border-hi);
  border-radius: var(--radius);
  padding: 28px 32px;
}
.modal-title {
  font-family: var(--font-ui);
  font-size: 12px; letter-spacing: 3px;
  color: var(--neon); text-transform: uppercase;
  margin-bottom: 14px;
}
.modal-desc { font-size: 12px; color: var(--text); line-height: 1.6; margin-bottom: 20px; }
.sas-emoji { font-size: 34px; letter-spacing: 8px; text-align: center; margin-bottom: 14px; }
.sas-hex {
  font-family: var(--font-mono);
  font-size: 16px; letter-spacing: 3px; color: var(--blue);
  text-align: center; padding: 12px;
  background: var(--bg); border: 1px solid var(--border);
  border-radius: var(--radius); margin-bottom: 22px;
  word-break: break-all;
}
.modal-actions { display: flex; gap: 10px; justify-content: flex-end; }
#verify-btn:disabled { opacity: 0.3; cursor: not-allowed; }
.dot.active { background: var(--neon); box-shadow: 0 0 8px var(--neon); }
</style>
</head>
<body>
<div id="app">

  <!-- ── LANDING ────────────────────────────────────── -->
  <div id="screen-landing">
    <div class="logo-block">
      <div class="logo-title glow">Keywave</div>
      <div class="logo-sub">End-to-End Encrypted · Chat &amp; Video</div>
      <div class="cipher-badges">
        <span class="badge">ECDH P-256</span>
        <span class="badge">HKDF-SHA-256</span>
        <span class="badge">AES-256-GCM</span>
        <span class="badge">WebRTC P2P</span>
      </div>
    </div>

    <div class="landing-card">
      <div class="card-section">
        <div class="card-label">// New Session</div>
        <button class="btn btn-primary" id="create-btn" onclick="UI.createRoom()" style="width:100%;justify-content:center;">
          &#x2295; Create Encrypted Room
        </button>
      </div>
      <div class="card-section">
        <div class="card-label">// Join Existing Room</div>
        <div class="input-row">
          <input class="inp" id="room-input" type="text"
            placeholder="ROOM ID"
            maxlength="10"
            autocomplete="off"
            spellcheck="false"
            onkeydown="if(event.key==='Enter')UI.joinRoom()">
          <button class="btn btn-secondary" onclick="UI.joinRoom()">Join</button>
        </div>
      </div>
    </div>
  </div>

  <!-- ── WAITING ────────────────────────────────────── -->
  <div id="screen-waiting" class="hidden">
    <div class="wait-label">// Secure Room Created</div>
    <div class="room-id-display" id="waiting-room-id">——————</div>
    <div style="display:flex;align-items:center;gap:10px;justify-content:center">
      <div class="pulse-indicator"></div>
      <span class="wait-label" style="letter-spacing:2px">Waiting for peer to join…</span>
    </div>

    <div class="invite-card">
      <div class="card-label">// Invite link &nbsp;·&nbsp; auto-joins on open</div>
      <div class="share-link-row">
        <input id="share-link" class="inp" readonly value="" onfocus="this.select()" aria-label="Invite link">
        <button class="btn btn-secondary" onclick="Share.copyLink()">Copy</button>
      </div>
      <div class="share-grid">
        <button class="share-btn go" id="share-native-btn" onclick="Share.native()">↗ Share…</button>
        <button class="share-btn wa" onclick="Share.wa()">WhatsApp</button>
        <button class="share-btn tg" onclick="Share.tg()">Telegram</button>
        <button class="share-btn" onclick="Share.email()">Email</button>
        <button class="share-btn" onclick="Share.sms()">SMS</button>
        <button class="share-btn" onclick="UI.copyRoomId()">Copy ID</button>
      </div>
      <div class="share-hint dim">Use “Share…” for Signal, Session, Tox, Element and anything else installed. Peer-to-peer; the server never sees your messages or keys.</div>
    </div>

    <button class="btn" style="border-color:var(--text-lo);color:var(--text)" onclick="UI.goHome()">Cancel</button>
  </div>

  <!-- ── SESSION ────────────────────────────────────── -->
  <div id="screen-session" class="hidden">

    <!-- Header -->
    <div id="session-header">
      <span class="header-logo">KEYWAVE</span>
      <span class="header-sep">|</span>
      <span class="header-room" id="header-room-id">——</span>
      <div class="header-status">
        <div class="status-pill">
          <div class="dot warn" id="dot-peer"></div>
          <span id="lbl-peer">Waiting</span>
        </div>
        <div class="status-pill">
          <div class="dot" id="dot-keys"></div>
          <span id="lbl-keys">Keys</span>
        </div>
        <div class="status-pill">
          <div class="dot" id="dot-video"></div>
          <span id="lbl-video">Video</span>
        </div>
        <div class="status-pill">
          <div class="dot" id="dot-verify"></div>
          <span id="lbl-verify">Unverified</span>
        </div>
        <button class="btn btn-secondary" id="verify-btn" onclick="Verify.open()" disabled
          style="padding:6px 12px;font-size:9px;letter-spacing:2px;">Safety #</button>
      </div>
    </div>

    <!-- Video -->
    <div id="video-panel">
      <video id="remote-video" autoplay playsinline></video>
      <video id="local-video" autoplay playsinline muted></video>
      <div class="video-overlay" id="video-overlay">
        <div class="overlay-icon">◈</div>
        <div class="overlay-text">Awaiting encrypted stream…</div>
      </div>
      <div class="e2e-badge" id="e2e-badge">
        <span id="e2e-dot" style="width:6px;height:6px;border-radius:50%;background:var(--neon-dim);display:inline-block;"></span>
        AES-256-GCM
      </div>
    </div>

    <!-- Chat -->
    <div id="chat-panel">
      <div id="messages-area"></div>
      <div id="chat-input-area">
        <input id="msg-input" type="text"
          placeholder="Waiting for peer to join…"
          autocomplete="off"
          spellcheck="false"
          disabled
          onkeydown="if(event.key==='Enter')Chat.send()">
        <button id="send-btn" disabled onclick="Chat.send()">Send</button>
      </div>
    </div>

    <!-- Controls -->
    <div id="controls-bar">
      <button class="ctrl-btn active" id="btn-mic" title="Toggle microphone" onclick="Media.toggleMic()">🎤</button>
      <button class="ctrl-btn active" id="btn-cam" title="Toggle camera" onclick="Media.toggleCam()">📷</button>
      <button class="ctrl-btn" id="btn-invite" title="Invite / share link" onclick="Share.quick()">↗</button>
      <button class="ctrl-end" title="End session" onclick="UI.hangup()">✕</button>
      <div class="crypto-info" id="crypto-info">
        <span>&#x1F512;</span> E2E ENCRYPTED
      </div>
    </div>

  </div>
</div>

<!-- ── SAFETY-NUMBER VERIFICATION MODAL ───────────────── -->
<div id="verify-modal" class="modal-overlay hidden" role="dialog" aria-modal="true" aria-label="Safety number verification">
  <div class="modal-box">
    <div class="modal-title">// Safety Number</div>
    <p class="modal-desc">
      Read these out to your peer over the live call. If they match on both
      screens, no one is intercepting your keys. If they differ, end the call.
    </p>
    <div id="sas-emoji" class="sas-emoji">· · · · · ·</div>
    <div id="sas-hex" class="sas-hex">——</div>
    <div class="modal-actions">
      <button class="btn" style="border-color:var(--text-lo);color:var(--text)" onclick="Verify.close()">Close</button>
      <button class="btn btn-primary" onclick="Verify.confirm()">They Match</button>
    </div>
  </div>
</div>

<!-- Toast container -->
<div id="toast-area"></div>

<!-- ═══════════════════════════════════════════════════════
     JAVASCRIPT
═══════════════════════════════════════════════════════ -->
<script>
'use strict';

const TE = new TextEncoder();
const TD = new TextDecoder();

/* ══════════════════════════════════════════════════════════
   STATE
══════════════════════════════════════════════════════════ */
const S = {
  socket:        null,
  pc:            null,
  localStream:   null,
  roomId:        null,
  isInitiator:   false,
  ecdhKey:       null,   // CryptoKeyPair (ECDH P-256)
  ecdhPubRaw:    null,   // ArrayBuffer — our public key to send
  chatEncKey:    null,   // CryptoKey AES-256-GCM — encrypt outgoing chat
  chatDecKey:    null,   // CryptoKey AES-256-GCM — decrypt incoming chat
  videoEncKey:   null,
  videoDecKey:   null,
  keysReady:     false,
  pendingSends:  [],
  pendingRecvs:  [],
  audioMuted:    false,
  videoOff:      false,
  insertableStreams: false,
  sas:           null,   // Uint8Array — safety number (MITM check)
  verified:      false,
  txSeq:         0,      // outgoing chat sequence (replay/reorder defense)
  rxSeq:         0,      // highest accepted incoming sequence
};

/* ══════════════════════════════════════════════════════════
   CRYPTO  (pure SubtleCrypto — zero CDN dependency)
══════════════════════════════════════════════════════════ */
const Crypto = {

  async init() {
    // Generate ephemeral ECDH P-256 keypair
    S.ecdhKey = await crypto.subtle.generateKey(
      { name: 'ECDH', namedCurve: 'P-256' },
      false,
      ['deriveKey', 'deriveBits']
    );
    // Export public key as raw bytes for sending over signaling
    S.ecdhPubRaw = await crypto.subtle.exportKey('raw', S.ecdhKey.publicKey);

    S.insertableStreams = (typeof RTCRtpSender !== 'undefined' &&
      typeof RTCRtpSender.prototype.createEncodedStreams === 'function');

    toast('Crypto ready · ECDH P-256 keypair generated', 'ok');
  },

  async deriveKeys(peerPubB64) {
    // Import peer's public key
    const peerPubRaw = Uint8Array.from(atob(peerPubB64), c => c.charCodeAt(0)).buffer;
    const peerPub = await crypto.subtle.importKey(
      'raw', peerPubRaw,
      { name: 'ECDH', namedCurve: 'P-256' },
      false, []
    );

    // Derive 64 raw bytes from ECDH shared secret via HKDF
    const sharedBits = await crypto.subtle.deriveBits(
      { name: 'ECDH', public: peerPub },
      S.ecdhKey.privateKey,
      256
    );

    // Import as HKDF key
    const hkdfKey = await crypto.subtle.importKey(
      'raw', sharedBits, { name: 'HKDF' }, false, ['deriveKey', 'deriveBits']
    );

    // Deterministically assign tx/rx so both peers get opposite directions
    // Lexicographic comparison of public keys decides who is "A"
    const myB64  = btoa(String.fromCharCode(...new Uint8Array(S.ecdhPubRaw)));
    const isA    = myB64 < peerPubB64;
    const txInfo = isA ? 'A->B' : 'B->A';
    const rxInfo = isA ? 'B->A' : 'A->B';
    const enc    = new TextEncoder();

    S.chatEncKey = await crypto.subtle.deriveKey(
      { name: 'HKDF', hash: 'SHA-256', salt: new Uint8Array(32), info: enc.encode('chat:' + txInfo) },
      hkdfKey, { name: 'AES-GCM', length: 256 }, false, ['encrypt']
    );
    S.chatDecKey = await crypto.subtle.deriveKey(
      { name: 'HKDF', hash: 'SHA-256', salt: new Uint8Array(32), info: enc.encode('chat:' + rxInfo) },
      hkdfKey, { name: 'AES-GCM', length: 256 }, false, ['decrypt']
    );
    S.videoEncKey = await crypto.subtle.deriveKey(
      { name: 'HKDF', hash: 'SHA-256', salt: new Uint8Array(32), info: enc.encode('video:' + txInfo) },
      hkdfKey, { name: 'AES-GCM', length: 256 }, false, ['encrypt']
    );
    S.videoDecKey = await crypto.subtle.deriveKey(
      { name: 'HKDF', hash: 'SHA-256', salt: new Uint8Array(32), info: enc.encode('video:' + rxInfo) },
      hkdfKey, { name: 'AES-GCM', length: 256 }, false, ['decrypt']
    );

    // Safety number (SAS): HKDF over the shared secret bound to BOTH public
    // keys in sorted order, independent of direction. A relay that swaps keys
    // to MITM the session cannot reproduce this value on both sides.
    const lo = myB64 < peerPubB64 ? myB64 : peerPubB64;
    const hi = myB64 < peerPubB64 ? peerPubB64 : myB64;
    const sasBits = await crypto.subtle.deriveBits(
      { name: 'HKDF', hash: 'SHA-256', salt: new Uint8Array(32),
        info: enc.encode('keywave:sas:' + lo + ':' + hi) },
      hkdfKey, 64
    );
    S.sas = new Uint8Array(sasBits);

    // Fresh session: reset chat sequence counters and verification state.
    S.txSeq = 0; S.rxSeq = 0; S.verified = false;

    S.keysReady = true;
    Status.setKeys(true);
    Chat.enable();
    VideoE2E.applyPending();
    Verify.ready();
    toast('Keys derived · AES-256-GCM active (chat + video)', 'ok');
    Chat.sysMsg('End-to-end keys established — verify the safety number', 'ok');
  },

  async encryptMsg(text, seq, ts) {
    const iv  = crypto.getRandomValues(new Uint8Array(12));
    const aad = TE.encode(seq + ':' + ts);
    const ct  = await crypto.subtle.encrypt(
      { name: 'AES-GCM', iv, additionalData: aad },
      S.chatEncKey,
      TE.encode(text)
    );
    const b64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)));
    return { ct: b64(ct), nonce: b64(iv) };
  },

  async decryptMsg(ctB64, nonceB64, seq, ts) {
    try {
      const from64 = b64 => Uint8Array.from(atob(b64), c => c.charCodeAt(0));
      const aad = TE.encode(seq + ':' + ts);
      const pt = await crypto.subtle.decrypt(
        { name: 'AES-GCM', iv: from64(nonceB64), additionalData: aad },
        S.chatDecKey,
        from64(ctB64)
      );
      return TD.decode(pt);
    } catch {
      return '[⚠ AUTHENTICATION FAILED]';
    }
  },
};

/* ══════════════════════════════════════════════════════════
   VIDEO FRAME ENCRYPTION (Insertable Streams / AES-256-GCM)
══════════════════════════════════════════════════════════ */
const VideoE2E = {
  wrapSender(sender) {
    if (!sender.createEncodedStreams) return;
    const { readable, writable } = sender.createEncodedStreams();
    if (S.keysReady) this._pipeSend(readable, writable);
    else S.pendingSends.push({ readable, writable });
  },
  wrapReceiver(receiver) {
    if (!receiver.createEncodedStreams) return;
    const { readable, writable } = receiver.createEncodedStreams();
    if (S.keysReady) this._pipeRecv(readable, writable);
    else S.pendingRecvs.push({ readable, writable });
  },
  applyPending() {
    while (S.pendingSends.length) { const { readable, writable } = S.pendingSends.pop(); this._pipeSend(readable, writable); }
    while (S.pendingRecvs.length) { const { readable, writable } = S.pendingRecvs.pop(); this._pipeRecv(readable, writable); }
    const badge = document.getElementById('e2e-badge');
    const dot   = document.getElementById('e2e-dot');
    if (badge) badge.classList.add('active');
    if (dot)   dot.style.background = 'var(--neon)';
    document.getElementById('crypto-info')?.classList.add('ready');
  },
  _pipeSend(readable, writable) {
    const key = S.videoEncKey;
    readable.pipeThrough(new TransformStream({
      async transform(frame, ctrl) {
        try {
          const iv  = crypto.getRandomValues(new Uint8Array(12));
          const enc = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, frame.data);
          const out = new Uint8Array(12 + enc.byteLength);
          out.set(iv); out.set(new Uint8Array(enc), 12);
          frame.data = out.buffer;
          ctrl.enqueue(frame);
        } catch {}
      }
    })).pipeTo(writable);
  },
  _pipeRecv(readable, writable) {
    const key = S.videoDecKey;
    readable.pipeThrough(new TransformStream({
      async transform(frame, ctrl) {
        try {
          const d = new Uint8Array(frame.data);
          if (d.length < 13) return;
          const dec = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: d.slice(0,12) }, key, d.slice(12));
          frame.data = dec;
          ctrl.enqueue(frame);
        } catch {}
      }
    })).pipeTo(writable);
  },
};

/* ══════════════════════════════════════════════════════════
   WEBRTC
══════════════════════════════════════════════════════════ */
const WebRTC = {
  createPC() {
    const cfg = {
      iceServers: [
        { urls: 'stun:stun.l.google.com:19302' },
        { urls: 'stun:stun1.l.google.com:19302' },
      ],
      ...(S.insertableStreams ? { encodedInsertableStreams: true } : {}),
    };
    S.pc = new RTCPeerConnection(cfg);
    S.localStream.getTracks().forEach(track => {
      const sender = S.pc.addTrack(track, S.localStream);
      if (S.insertableStreams) VideoE2E.wrapSender(sender);
    });
    S.pc.ontrack = (e) => {
      const rv = document.getElementById('remote-video');
      if (rv.srcObject !== e.streams[0]) {
        rv.srcObject = e.streams[0];
        document.getElementById('video-overlay').classList.add('hidden');
        Status.setVideo(true);
      }
      if (S.insertableStreams) VideoE2E.wrapReceiver(e.receiver);
    };
    S.pc.onicecandidate = (e) => { if (e.candidate) S.socket.emit('ice', { candidate: e.candidate }); };
    S.pc.onconnectionstatechange = () => {
      const state = S.pc.connectionState;
      Status.setPeer(state);
      if (state === 'connected') { Chat.sysMsg('Peer-to-peer connection established', 'ok'); toast('P2P connected', 'ok'); }
      else if (state === 'disconnected' || state === 'failed') { Status.setVideo(false); Chat.sysMsg('Peer disconnected', 'warn'); }
    };
  },
  async makeOffer() {
    this.createPC();
    const offer = await S.pc.createOffer();
    await S.pc.setLocalDescription(offer);
    S.socket.emit('offer', { sdp: offer });
  },
  async handleOffer(sdp) {
    this.createPC();
    await S.pc.setRemoteDescription(new RTCSessionDescription(sdp));
    const answer = await S.pc.createAnswer();
    await S.pc.setLocalDescription(answer);
    S.socket.emit('answer', { sdp: answer });
  },
  async handleAnswer(sdp) { await S.pc.setRemoteDescription(new RTCSessionDescription(sdp)); },
  async handleIce(c) { try { await S.pc.addIceCandidate(new RTCIceCandidate(c)); } catch {} },
};

/* ══════════════════════════════════════════════════════════
   MEDIA
══════════════════════════════════════════════════════════ */
const Media = {
  async start() {
    try {
      S.localStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      document.getElementById('local-video').srcObject = S.localStream;
      return true;
    } catch {
      try {
        S.localStream = await navigator.mediaDevices.getUserMedia({ video: false, audio: true });
        document.getElementById('local-video').srcObject = S.localStream;
        toast('Camera unavailable — audio only', 'warn');
        return true;
      } catch { toast('Media access denied', 'error'); return false; }
    }
  },
  toggleMic() {
    if (!S.localStream) return;
    const track = S.localStream.getAudioTracks()[0];
    if (!track) return;
    S.audioMuted = !S.audioMuted;
    track.enabled = !S.audioMuted;
    const btn = document.getElementById('btn-mic');
    btn.classList.toggle('active', !S.audioMuted);
    btn.classList.toggle('muted', S.audioMuted);
    btn.textContent = S.audioMuted ? '🔇' : '🎤';
  },
  toggleCam() {
    if (!S.localStream) return;
    const track = S.localStream.getVideoTracks()[0];
    if (!track) return;
    S.videoOff = !S.videoOff;
    track.enabled = !S.videoOff;
    const btn = document.getElementById('btn-cam');
    btn.classList.toggle('active', !S.videoOff);
    btn.classList.toggle('muted', S.videoOff);
    btn.textContent = S.videoOff ? '🚫' : '📷';
  },
  stop() { if (S.localStream) { S.localStream.getTracks().forEach(t => t.stop()); S.localStream = null; } },
};

/* ══════════════════════════════════════════════════════════
   CHAT
══════════════════════════════════════════════════════════ */
const Chat = {
  enable() {
    const inp = document.getElementById('msg-input');
    const btn = document.getElementById('send-btn');
    inp.disabled = false;
    inp.placeholder = 'Encrypted message…';
    btn.disabled = false;
    inp.focus();
  },
  async send() {
    try {
      const input = document.getElementById('msg-input');
      const text  = input.value.trim();
      if (!text || !S.keysReady) return;
      if (text.length > 4000) { toast('Message too long (max 4000)', 'warn'); return; }
      const ts  = Date.now();
      const seq = ++S.txSeq;
      const { ct, nonce } = await Crypto.encryptMsg(text, seq, ts);
      S.socket.emit('msg', { ct, nonce, ts, seq });
      this.appendMsg(text, 'local', ts);
      input.value = '';
    } catch(e) {
      console.error('[Chat.send]', e);
      toast('Send error: ' + e.message, 'error');
    }
  },
  appendMsg(text, who, ts) {
    const area   = document.getElementById('messages-area');
    const bubble = document.createElement('div');
    bubble.className = `msg-bubble ${who}`;
    const meta = document.createElement('div');
    meta.className = 'msg-meta';
    const whoEl = document.createElement('span');
    whoEl.textContent = who === 'local' ? 'ME' : 'PEER';
    const timeEl = document.createElement('span');
    timeEl.textContent = new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const lock = document.createElement('span');
    lock.className = 'msg-lock'; lock.textContent = '🔒';
    meta.append(whoEl, timeEl, lock);
    const body = document.createElement('div');
    body.className = 'msg-body';
    body.textContent = text;   // textContent => message content can never inject markup
    bubble.append(meta, body);
    this._push(area, bubble);
  },
  sysMsg(text, type = '') {
    const area = document.getElementById('messages-area');
    const el   = document.createElement('div');
    el.className = `sys-msg ${type}`;
    el.textContent = `⬡ ${text}`;
    this._push(area, el);
  },
  _push(area, node) {
    area.appendChild(node);
    while (area.children.length > 250) area.removeChild(area.firstChild);  // bound DOM growth
    area.scrollTop = area.scrollHeight;
  },
};

/* ══════════════════════════════════════════════════════════
   STATUS
══════════════════════════════════════════════════════════ */
const Status = {
  setPeer(state) {
    const dot = document.getElementById('dot-peer');
    const lbl = document.getElementById('lbl-peer');
    dot.className = 'dot';
    if (state === 'connected')    { dot.classList.add('active'); lbl.textContent = 'Connected'; }
    else if (state === 'connecting') { dot.classList.add('warn');  lbl.textContent = 'Connecting'; }
    else if (state === 'disconnected' || state === 'failed') { dot.classList.add('error'); lbl.textContent = 'Disconnected'; }
    else { dot.classList.add('warn'); lbl.textContent = 'Waiting'; }
  },
  setKeys(ok) {
    document.getElementById('dot-keys').className = 'dot' + (ok ? ' active' : ' warn');
    document.getElementById('lbl-keys').textContent = ok ? 'Keys OK' : 'Keying…';
  },
  setVideo(ok) {
    document.getElementById('dot-video').className = 'dot' + (ok ? ' active' : '');
    document.getElementById('lbl-video').textContent = ok ? 'Video E2E' : 'No Video';
  },
};

/* ══════════════════════════════════════════════════════════
   SAFETY-NUMBER VERIFICATION (MITM defense)
══════════════════════════════════════════════════════════ */
const SAS_EMOJI = ['🐶','🐱','🦊','🐻','🐼','🐨','🦁','🐯','🐮','🐷','🐸','🐵','🐔','🐧','🦉','🦄','🐝','🦋','🐢','🐙','🐠','🐬','🐳','🌵','🌲','🍀','🍎','🍊','🍋','🍇','🍓','🍒','🍑','🥝','🌽','🥕','🍄','🌰','🍔','🍕','🌮','🍿','🍩','🍪','🎂','🍫','☕','🍵','⚽','🏀','🎲','🎸','🎺','🎨','🚀','🛸','⭐','🌙','☀️','🔥','💧','❄️','🔑','🔒'];

const Verify = {
  ready() {
    const b = document.getElementById('verify-btn');
    if (b) b.disabled = false;
    this.setState(false);
  },
  setState(ok) {
    const dot = document.getElementById('dot-verify');
    const lbl = document.getElementById('lbl-verify');
    if (!dot) return;
    dot.className = 'dot' + (ok ? ' active' : ' warn');
    lbl.textContent = ok ? 'Verified' : 'Unverified';
  },
  _render() {
    if (!S.sas) return null;
    const em = [], hex = [];
    S.sas.forEach((byte, i) => {
      if (i < 6) em.push(SAS_EMOJI[byte & 63]);
      hex.push(byte.toString(16).padStart(2, '0'));
    });
    return { emoji: em.join('  '), hex: hex.join(' ').toUpperCase() };
  },
  open() {
    const r = this._render();
    if (!r) { toast('Keys not ready yet', 'warn'); return; }
    document.getElementById('sas-emoji').textContent = r.emoji;
    document.getElementById('sas-hex').textContent = r.hex;
    document.getElementById('verify-modal').classList.remove('hidden');
  },
  close() { document.getElementById('verify-modal').classList.add('hidden'); },
  confirm() {
    S.verified = true;
    this.setState(true);
    this.close();
    toast('Session marked verified', 'ok');
    Chat.sysMsg('Safety number confirmed — channel verified', 'ok');
  },
};

/* ══════════════════════════════════════════════════════════
   SIGNALING
══════════════════════════════════════════════════════════ */
const Signaling = {
  connect() {
    S.socket = io();

    S.socket.on('room_created', ({ room_id }) => { S.roomId = room_id; UI.showWaiting(room_id); });

    S.socket.on('joined', async ({ room_id, initiator }) => {
      S.roomId = room_id;
      S.isInitiator = initiator;
      if (initiator) await this._startSession();
    });

    S.socket.on('peer_arrived', async () => { await this._startSession(); });

    S.socket.on('pubkey', async ({ pubkey }) => {
      try {
        await Crypto.deriveKeys(pubkey);
        if (S.isInitiator) await WebRTC.makeOffer();
      } catch(e) {
        console.error('[pubkey/deriveKeys]', e);
        toast('Key exchange failed: ' + e.message, 'error');
      }
    });

    S.socket.on('offer',  async ({ sdp })       => { await WebRTC.handleOffer(sdp); });
    S.socket.on('answer', async ({ sdp })       => { await WebRTC.handleAnswer(sdp); });
    S.socket.on('ice',    async ({ candidate }) => { await WebRTC.handleIce(candidate); });

    S.socket.on('msg', async ({ ct, nonce, ts, seq }) => {
      if (!S.keysReady) return;
      // Reject replays and reordering: sequence must strictly increase.
      if (typeof seq !== 'number' || seq <= S.rxSeq) return;
      S.rxSeq = seq;
      const text = await Crypto.decryptMsg(ct, nonce, seq, ts);
      Chat.appendMsg(text, 'remote', ts || Date.now());
    });

    S.socket.on('peer_left', () => {
      Status.setPeer('disconnected');
      toast('Peer disconnected', 'warn');
      Chat.sysMsg('Peer left the session', 'warn');
      Status.setVideo(false);
      S.verified = false;
      Verify.setState(false);
    });

    S.socket.on('error', ({ msg }) => toast(msg, 'error'));
    S.socket.on('disconnect', () => toast('Disconnected from server', 'error'));
  },

  async _startSession() {
    UI.showSession();
    document.getElementById('header-room-id').textContent = S.roomId;
    await Media.start();
    Status.setPeer('connecting');
    Chat.sysMsg('Room: ' + S.roomId + ' · Share this ID with your peer');
    Chat.sysMsg('Secure channel establishing…');
    // Send our ECDH public key (raw, base64-encoded)
    const b64 = btoa(String.fromCharCode(...new Uint8Array(S.ecdhPubRaw)));
    S.socket.emit('pubkey', { pubkey: b64 });
  },
};

/* ══════════════════════════════════════════════════════════
   UI
══════════════════════════════════════════════════════════ */
const UI = {
  createRoom()  { S.socket.emit('create_room'); },
  joinRoom() {
    const rid = (document.getElementById('room-input').value || '').trim().toUpperCase();
    if (!validRoomId(rid)) { toast('Enter a valid 10-character room ID', 'warn'); return; }
    S.socket.emit('join', { room_id: rid });
  },
  copyRoomId()  { if (S.roomId) navigator.clipboard.writeText(S.roomId).then(() => toast('Room ID copied', 'ok')); },
  showWaiting(room_id) {
    show('screen-waiting');
    document.getElementById('waiting-room-id').textContent = room_id;
    const link = document.getElementById('share-link');
    if (link) link.value = Share.link();
    const nb = document.getElementById('share-native-btn');
    if (nb) nb.style.display = (typeof navigator.share === 'function') ? '' : 'none';
  },
  showSession() { show('screen-session'); },
  goHome()      { show('screen-landing'); S.roomId = null; },
  hangup() {
    Media.stop();
    if (S.pc) { S.pc.close(); S.pc = null; }
    S.chatEncKey = null; S.chatDecKey = null;
    S.videoEncKey = null; S.videoDecKey = null;
    S.keysReady = false;
    S.pendingSends = []; S.pendingRecvs = [];
    S.sas = null; S.verified = false;
    S.txSeq = 0; S.rxSeq = 0;
    S.roomId = null;
    const vb = document.getElementById('verify-btn');
    if (vb) vb.disabled = true;
    Verify.setState(false);
    show('screen-landing');
    toast('Session ended', 'warn');
  },
};

/* ══════════════════════════════════════════════════════════
   SHARE / INVITE
══════════════════════════════════════════════════════════ */
const Share = {
  link() {
    const base = location.origin + location.pathname;
    return base + '#room=' + encodeURIComponent(S.roomId || '');
  },
  blurb() { return 'Join my end-to-end encrypted Keywave room: '; },
  message() { return this.blurb() + this.link(); },
  _open(url) { window.open(url, '_blank', 'noopener,noreferrer'); },
  async native() {
    if (typeof navigator.share !== 'function') { this.copyLink(); return; }
    try { await navigator.share({ title: 'Keywave invite', text: this.blurb(), url: this.link() }); }
    catch (e) { /* user dismissed the share sheet */ }
  },
  quick() { if (typeof navigator.share === 'function') this.native(); else this.copyLink(); },
  wa()    { this._open('https://wa.me/?text=' + encodeURIComponent(this.message())); },
  tg()    { this._open('https://t.me/share/url?url=' + encodeURIComponent(this.link()) + '&text=' + encodeURIComponent(this.blurb())); },
  email() { this._open('mailto:?subject=' + encodeURIComponent('Keywave invite') + '&body=' + encodeURIComponent(this.message())); },
  sms()   { location.href = 'sms:?&body=' + encodeURIComponent(this.message()); },
  copyLink() {
    if (!S.roomId) { toast('No active room', 'warn'); return; }
    navigator.clipboard.writeText(this.link()).then(() => toast('Invite link copied', 'ok'),
                                                    () => toast('Copy failed', 'error'));
  },
};

/* ══════════════════════════════════════════════════════════
   HELPERS
══════════════════════════════════════════════════════════ */
function validRoomId(r) { return /^[0-9A-F]{10}$/.test(r); }

function show(id) {
  ['screen-landing','screen-waiting','screen-session'].forEach(s =>
    document.getElementById(s).classList.toggle('hidden', s !== id));
}
function toast(msg, type = '') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg.toUpperCase();
  document.getElementById('toast-area').appendChild(el);
  setTimeout(() => el.remove(), 3300);
}

/* ══════════════════════════════════════════════════════════
   BOOTSTRAP
══════════════════════════════════════════════════════════ */
(async () => {
  try {
    await Crypto.init();
    Signaling.connect();
    // Auto-join from an invite link (#room=ID). The fragment is never sent to
    // the server; socket.io buffers this emit until the connection is ready.
    const hm = (location.hash || '').match(/room=([0-9A-Fa-f]{10})/);
    if (hm) {
      const rid = hm[1].toUpperCase();
      const inp = document.getElementById('room-input');
      if (inp) inp.value = rid;
      toast('Joining room from invite…', 'ok');
      S.socket.emit('join', { room_id: rid });
    }
  } catch(e) {
    console.error('[Keywave boot error]', e);
    toast('Boot error: ' + e.message, 'error');
  }
})();
</script>
</body>"""

def peer_sid(room_id, my_sid):
    r = rooms.get(room_id)
    if not r:
        return None
    return next((s for s in r["peers"] if s != my_sid), None)

def relay(event, data):
    sid = request.sid
    room_id = sid_to_room.get(sid)
    if not room_id:
        return
    target = peer_sid(room_id, sid)
    if target:
        socketio.emit(event, data, to=target)

# ── HTTP ─────────────────────────────────────────────────────────────────────
@app.after_request
def _secure_headers(resp):
    resp.headers["X-Content-Type-Options"]    = "nosniff"
    resp.headers["X-Frame-Options"]           = "DENY"
    resp.headers["Referrer-Policy"]           = "no-referrer"
    resp.headers["Permissions-Policy"]        = "camera=(self), microphone=(self), geolocation=()"
    resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    # Self-hosted assets only — no third-party origins. 'unsafe-inline' is
    # required by the inline event handlers and <script>/<style> blocks.
    resp.headers["Content-Security-Policy"] = (
        "default-src 'none'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self'; media-src 'self' blob:; "
        "connect-src 'self' ws: wss:; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
    )
    return resp

@app.route("/")
def index():
    return Response(INDEX_HTML, mimetype="text/html")

@app.route("/healthz")
def healthz():
    with _lock:
        n = len(rooms)
    return jsonify(status="ok", rooms=n)

# ── Signaling ─────────────────────────────────────────────────────────────────
@socketio.on("create_room")
def on_create_room():
    sid = request.sid
    if not _rate_ok(_create_log, sid, CREATE_WINDOW, CREATE_MAX):
        emit("error", {"msg": "Slow down — too many rooms created."})
        return
    with _lock:
        # One room per client: release any previous room this sid still holds,
        # so repeated create_room calls cannot leak rooms.
        prev = sid_to_room.get(sid)
        if prev and prev in rooms:
            pr = rooms[prev]
            if sid in pr["peers"]:
                pr["peers"].remove(sid)
            if not pr["peers"]:
                rooms.pop(prev, None)
        if len(rooms) >= MAX_ROOMS:
            emit("error", {"msg": "Server is at capacity. Try again later."})
            return
        room_id = uuid.uuid4().hex[:ROOM_ID_LEN].upper()
        while room_id in rooms:
            room_id = uuid.uuid4().hex[:ROOM_ID_LEN].upper()
        rooms[room_id] = {"peers": [sid], "created": time.time()}
        sid_to_room[sid] = room_id
    join_room(room_id)
    emit("room_created", {"room_id": room_id})

@socketio.on("join")
def on_join(data):
    sid = request.sid
    room_id = str((data or {}).get("room_id", "")).strip().upper()
    if not _valid_room_id(room_id):
        emit("error", {"msg": "Invalid room ID."})
        return
    with _lock:
        r = rooms.get(room_id)
        if not r:
            emit("error", {"msg": "Room not found."})
            return
        if sid in r["peers"]:
            return
        if len(r["peers"]) >= 2:
            emit("error", {"msg": "Room is full (max 2 peers)."})
            return
        r["peers"].append(sid)
        sid_to_room[sid] = room_id
        peer0 = r["peers"][0]
        is_initiator = len(r["peers"]) == 2
    join_room(room_id)
    emit("joined", {"room_id": room_id, "initiator": is_initiator})
    if is_initiator:
        socketio.emit("peer_arrived", {}, to=peer0)

@socketio.on("pubkey")
def on_pubkey(data):
    pk = (data or {}).get("pubkey")
    if not isinstance(pk, str) or _too_big(pk):
        return
    relay("pubkey", {"pubkey": pk})

@socketio.on("offer")
def on_offer(data):
    sdp = (data or {}).get("sdp")
    if sdp is None or _too_big(sdp):
        return
    relay("offer", {"sdp": sdp})

@socketio.on("answer")
def on_answer(data):
    sdp = (data or {}).get("sdp")
    if sdp is None or _too_big(sdp):
        return
    relay("answer", {"sdp": sdp})

@socketio.on("ice")
def on_ice(data):
    cand = (data or {}).get("candidate")
    if cand is None or _too_big(cand):
        return
    relay("ice", {"candidate": cand})

@socketio.on("msg")
def on_msg(data):
    sid = request.sid
    data = data or {}
    ct, nonce = data.get("ct"), data.get("nonce")
    if not isinstance(ct, str) or not isinstance(nonce, str):
        return
    if _too_big(ct, nonce):
        return
    if not _rate_ok(_msg_log, sid, MSG_WINDOW, MSG_MAX):
        return
    relay("msg", {"ct": ct, "nonce": nonce, "ts": data.get("ts"), "seq": data.get("seq")})

@socketio.on("disconnect")
def on_disconnect(reason=None):
    sid = request.sid
    with _lock:
        _create_log.pop(sid, None)
        _msg_log.pop(sid, None)
        room_id = sid_to_room.pop(sid, None)
        if not room_id:
            return
        r = rooms.get(room_id)
        if not r:
            return
        if sid in r["peers"]:
            r["peers"].remove(sid)
        remaining = r["peers"][0] if r["peers"] else None
        if not r["peers"]:
            rooms.pop(room_id, None)
    if remaining:
        socketio.emit("peer_left", {}, to=remaining)

def _sweeper():
    """Reap abandoned half-open rooms so the maps cannot grow without bound."""
    while True:
        socketio.sleep(60)
        now = time.time()
        with _lock:
            stale = [rid for rid, r in rooms.items()
                     if len(r["peers"]) < 2 and now - r["created"] > ROOM_TTL]
            for rid in stale:
                for s in rooms[rid]["peers"]:
                    sid_to_room.pop(s, None)
                rooms.pop(rid, None)

if __name__ == "__main__":
    socketio.start_background_task(_sweeper)
    print(f"[keywave] Running on http://0.0.0.0:{PORT}", flush=True)
    # NOTE: this uses the Werkzeug dev server (allow_unsafe_werkzeug). It is fine
    # behind a TLS-terminating reverse proxy (Nginx Proxy Manager). For a heavier
    # deployment, run under gunicorn with a gevent-websocket worker instead.
    socketio.run(app, host="0.0.0.0", port=PORT, debug=False, allow_unsafe_werkzeug=True)
