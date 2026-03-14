import os, uuid
from flask import Flask, request, Response
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(32).hex()
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

rooms:       dict[str, list[str]] = {}
sid_to_room: dict[str, str]       = {}

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Keywave - Privacy That Flows.</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;900&family=Share+Tech+Mono&display=swap" rel="stylesheet">
<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
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
   RESPONSIVE
══════════════════════════════════════════════════════════ */
@media (max-width: 700px) {
  #screen-session {
    grid-template-columns: 1fr;
    grid-template-rows: 48px 200px 1fr 52px;
    grid-template-areas:
      "header"
      "video"
      "chat"
      "controls";
  }
  #chat-panel { border-left: none; border-top: 1px solid var(--border); }
  .logo-title { font-size: 32px; letter-spacing: 6px; }
  .room-id-display { font-size: 26px; letter-spacing: 8px; }
}
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
    <div style="display:flex;align-items:center;gap:10px">
      <div class="pulse-indicator"></div>
      <button class="btn btn-secondary" id="copy-btn" onclick="UI.copyRoomId()">Copy ID</button>
    </div>
    <div class="wait-hint dim">
      Share the Room ID with your peer.<br>
      Connection is established peer-to-peer.<br>
      Server never sees your messages or keys.
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
      <button class="ctrl-end" title="End session" onclick="UI.hangup()">✕</button>
      <div class="crypto-info" id="crypto-info">
        <span>&#x1F512;</span> E2E ENCRYPTED
      </div>
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
      'raw', sharedBits, { name: 'HKDF' }, false, ['deriveKey']
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

    S.keysReady = true;
    Status.setKeys(true);
    Chat.enable();
    VideoE2E.applyPending();
    toast('Keys derived · AES-256-GCM active (chat + video)', 'ok');
    Chat.sysMsg('End-to-end keys established', 'ok');
  },

  async encryptMsg(text) {
    const iv  = crypto.getRandomValues(new Uint8Array(12));
    const ct  = await crypto.subtle.encrypt(
      { name: 'AES-GCM', iv },
      S.chatEncKey,
      new TextEncoder().encode(text)
    );
    const b64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)));
    return { ct: b64(ct), nonce: b64(iv) };
  },

  async decryptMsg(ctB64, nonceB64) {
    try {
      const from64 = b64 => Uint8Array.from(atob(b64), c => c.charCodeAt(0));
      const pt = await crypto.subtle.decrypt(
        { name: 'AES-GCM', iv: from64(nonceB64) },
        S.chatDecKey,
        from64(ctB64)
      );
      return new TextDecoder().decode(pt);
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
      const { ct, nonce } = await Crypto.encryptMsg(text);
      const ts = Date.now();
      S.socket.emit('msg', { ct, nonce, ts });
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
    const time   = new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    bubble.innerHTML = `
      <div class="msg-meta"><span>${who === 'local' ? 'ME' : 'PEER'}</span><span>${time}</span><span class="msg-lock">🔒</span></div>
      <div class="msg-body">${this._esc(text)}</div>`;
    area.appendChild(bubble);
    area.scrollTop = area.scrollHeight;
  },
  sysMsg(text, type = '') {
    const area = document.getElementById('messages-area');
    const el   = document.createElement('div');
    el.className = `sys-msg ${type}`;
    el.textContent = `⬡ ${text}`;
    area.appendChild(el);
    area.scrollTop = area.scrollHeight;
  },
  _esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); },
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

    S.socket.on('msg', async ({ ct, nonce, ts }) => {
      if (!S.keysReady) return;
      const text = await Crypto.decryptMsg(ct, nonce);
      Chat.appendMsg(text, 'remote', ts || Date.now());
    });

    S.socket.on('peer_left', () => {
      Status.setPeer('disconnected');
      toast('Peer disconnected', 'warn');
      Chat.sysMsg('Peer left the session', 'warn');
      Status.setVideo(false);
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
  joinRoom()    { const rid = document.getElementById('room-input').value.trim(); if (rid) S.socket.emit('join', { room_id: rid }); },
  copyRoomId()  { if (S.roomId) navigator.clipboard.writeText(S.roomId).then(() => toast('Room ID copied', 'ok')); },
  showWaiting(room_id) { show('screen-waiting'); document.getElementById('waiting-room-id').textContent = room_id; },
  showSession() { show('screen-session'); },
  goHome()      { show('screen-landing'); S.roomId = null; },
  hangup() {
    Media.stop();
    if (S.pc) { S.pc.close(); S.pc = null; }
    S.chatEncKey = null; S.chatDecKey = null;
    S.videoEncKey = null; S.videoDecKey = null;
    S.keysReady = false;
    S.pendingSends = []; S.pendingRecvs = [];
    S.roomId = null;
    show('screen-landing');
    toast('Session ended', 'warn');
  },
};

/* ══════════════════════════════════════════════════════════
   HELPERS
══════════════════════════════════════════════════════════ */
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
  } catch(e) {
    console.error('[Keywave boot error]', e);
    toast('Boot error: ' + e.message, 'error');
  }
})();
</script>
</body>"""

def peer_sid(room_id, my_sid):
    return next((s for s in rooms.get(room_id, []) if s != my_sid), None)

def relay(event, data):
    sid = request.sid
    room_id = sid_to_room.get(sid)
    if not room_id: return
    target = peer_sid(room_id, sid)
    if target: socketio.emit(event, data, to=target)

@app.route("/")
def index():
    return Response(INDEX_HTML, mimetype="text/html")

@socketio.on("create_room")
def on_create_room():
    sid = request.sid
    room_id = uuid.uuid4().hex[:10].upper()
    rooms[room_id] = [sid]          # creator is already peer 0
    sid_to_room[sid] = room_id
    join_room(room_id)
    emit("room_created", {"room_id": room_id})

@socketio.on("join")
def on_join(data):
    sid = request.sid
    room_id = str(data.get("room_id", "")).strip().upper()
    if room_id not in rooms:
        emit("error", {"msg": "Room not found."})
        return
    peers = rooms[room_id]
    if len(peers) >= 2:
        emit("error", {"msg": "Room is full (max 2 peers)."})
        return
    peers.append(sid)
    sid_to_room[sid] = room_id
    join_room(room_id)
    is_initiator = len(peers) == 2
    emit("joined", {"room_id": room_id, "initiator": is_initiator})
    if is_initiator:
        socketio.emit("peer_arrived", {}, to=peers[0])

@socketio.on("pubkey")
def on_pubkey(data): relay("pubkey", {"pubkey": data.get("pubkey")})

@socketio.on("offer")
def on_offer(data): relay("offer", {"sdp": data.get("sdp")})

@socketio.on("answer")
def on_answer(data): relay("answer", {"sdp": data.get("sdp")})

@socketio.on("ice")
def on_ice(data): relay("ice", {"candidate": data.get("candidate")})

@socketio.on("msg")
def on_msg(data): relay("msg", {"ct": data.get("ct"), "nonce": data.get("nonce"), "ts": data.get("ts")})

@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    room_id = sid_to_room.pop(sid, None)
    if not room_id: return
    peers = rooms.get(room_id, [])
    if sid in peers: peers.remove(sid)
    remaining = peer_sid(room_id, sid)
    if remaining: socketio.emit("peer_left", {}, to=remaining)
    if not peers: rooms.pop(room_id, None)

if __name__ == "__main__":
    print("[keywave] Running on http://0.0.0.0:5000", flush=True)
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)
