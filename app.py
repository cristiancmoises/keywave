"""
Keywave — end-to-end encrypted P2P chat + video signaling server.

The server is a *blind relay*: it sees only ephemeral ECDH public keys,
opaque AES-GCM ciphertext, and WebRTC SDP/ICE. It never holds plaintext or
session keys. All confidentiality lives in the browser (see index.html).

Configuration (environment variables):
  KEYWAVE_HOST              bind host (default 0.0.0.0)
  KEYWAVE_PORT              bind port (default 5000)
  KEYWAVE_ASYNC             gevent | threading        (default gevent)
  KEYWAVE_SECRET_KEY        Flask secret (default: random per boot)
  KEYWAVE_ALLOWED_ORIGINS   CORS allowlist, comma-separated, or *  (default *)
  KEYWAVE_MAX_ROOMS         global room cap            (default 5000)
  KEYWAVE_ROOM_TTL          seconds a half-open room lives (default 7200)
  KEYWAVE_CREATE_PER_MIN    room creations per sid/min (default 12)
  KEYWAVE_MSG_PER_SEC       relayed events per sid/sec (default 40)
  STUN_URLS                 comma-separated stun: urls (default Google STUN)
  TURN_URLS                 comma-separated turn(s): urls
  TURN_USERNAME/TURN_CREDENTIAL   static long-term TURN creds
  TURN_STATIC_SECRET        coturn REST shared secret (ephemeral creds)
  TURN_TTL                  ephemeral cred lifetime sec (default 86400)
  KEYWAVE_TLS_CERT/KEYWAVE_TLS_KEY   enable HTTPS in the dev runner
"""
import os

# gevent monkey-patching must happen before importing the stdlib it patches.
ASYNC_MODE = os.environ.get("KEYWAVE_ASYNC", "gevent").strip().lower()
if ASYNC_MODE == "gevent":
    try:
        from gevent import monkey
        monkey.patch_all()
    except Exception:  # pragma: no cover - gevent missing → degrade gracefully
        ASYNC_MODE = "threading"

import base64
import hashlib
import hmac
import mimetypes
import secrets
import threading
import time
from collections import deque

mimetypes.add_type("font/woff2", ".woff2")  # slim images often lack this mapping

from flask import Flask, request, Response, jsonify, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Config ────────────────────────────────────────────────────────────────
HOST            = os.environ.get("KEYWAVE_HOST", "0.0.0.0")
PORT            = int(os.environ.get("KEYWAVE_PORT", "5000"))
MAX_ROOMS       = int(os.environ.get("KEYWAVE_MAX_ROOMS", "5000"))
ROOM_TTL        = int(os.environ.get("KEYWAVE_ROOM_TTL", "7200"))
CREATE_PER_MIN  = int(os.environ.get("KEYWAVE_CREATE_PER_MIN", "12"))
MSG_PER_SEC     = int(os.environ.get("KEYWAVE_MSG_PER_SEC", "40"))
_origins_env    = os.environ.get("KEYWAVE_ALLOWED_ORIGINS", "*").strip()
ALLOWED_ORIGINS = "*" if _origins_env == "*" else [o.strip() for o in _origins_env.split(",") if o.strip()]

# Per-event payload caps (bytes/chars) — defence in depth on top of buffer cap.
LIMITS = {"pubkey": 512, "ct": 16384, "nonce": 64, "sdp": 32768, "candidate": 4096}

ROOM_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no ambiguous chars

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["SECRET_KEY"] = os.environ.get("KEYWAVE_SECRET_KEY") or secrets.token_hex(32)

socketio = SocketIO(
    app,
    cors_allowed_origins=ALLOWED_ORIGINS,
    async_mode=ASYNC_MODE,
    max_http_buffer_size=131072,
    ping_timeout=30,
    ping_interval=25,
)

# ── In-memory state (single worker; ephemeral, never persisted) ─────────────
_lock = threading.RLock()
rooms: dict[str, dict] = {}          # room_id -> {"peers": [sid,...], "created": ts}
sid_to_room: dict[str, str] = {}     # sid -> room_id
_create_log: dict[str, deque] = {}   # sid -> recent create timestamps
_msg_log: dict[str, deque] = {}      # sid -> recent relay timestamps

# ── Load client once at startup; nonce is injected per request ──────────────
with open(os.path.join(BASE_DIR, "index.html"), "r", encoding="utf-8") as _f:
    INDEX_TEMPLATE = _f.read()


# ── ICE / TURN config ───────────────────────────────────────────────────────
def build_ice_servers() -> list[dict]:
    servers: list[dict] = []
    stun = os.environ.get("STUN_URLS", "stun:stun.l.google.com:19302,stun:stun1.l.google.com:19302")
    for u in [s.strip() for s in stun.split(",") if s.strip()]:
        servers.append({"urls": u})

    turn_urls = [u.strip() for u in os.environ.get("TURN_URLS", "").split(",") if u.strip()]
    if turn_urls:
        secret = os.environ.get("TURN_STATIC_SECRET")
        if secret:  # coturn REST: time-limited HMAC credential
            ttl = int(os.environ.get("TURN_TTL", "86400"))
            username = str(int(time.time()) + ttl)
            cred = base64.b64encode(
                hmac.new(secret.encode(), username.encode(), hashlib.sha1).digest()
            ).decode()
            servers.append({"urls": turn_urls, "username": username, "credential": cred})
        else:
            user = os.environ.get("TURN_USERNAME")
            cred = os.environ.get("TURN_CREDENTIAL")
            entry = {"urls": turn_urls}
            if user and cred:
                entry["username"] = user
                entry["credential"] = cred
            servers.append(entry)
    return servers


# ── Security headers on every response ──────────────────────────────────────
@app.after_request
def secure_headers(resp: Response) -> Response:
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault(
        "Permissions-Policy",
        "camera=(self), microphone=(self), display-capture=(self), "
        "fullscreen=(self), geolocation=(), payment=(), usb=()",
    )
    resp.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'none'; base-uri 'none'; frame-ancestors 'none'",
    )
    fwd_proto = request.headers.get("X-Forwarded-Proto", "")
    if request.is_secure or fwd_proto == "https":
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return resp


# ── Routes ──────────────────────────────────────────────────────────────────
@app.route("/")
def index() -> Response:
    nonce = secrets.token_urlsafe(16)
    html = INDEX_TEMPLATE.replace("__CSP_NONCE__", nonce)
    resp = Response(html, mimetype="text/html")
    resp.headers["Content-Security-Policy"] = (
        "default-src 'none'; "
        f"script-src 'self' 'nonce-{nonce}'; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self'; "
        "img-src 'self' data: blob:; "
        "media-src 'self' blob:; "
        "connect-src 'self'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
    )
    return resp


@app.route("/healthz")
def healthz() -> Response:
    with _lock:
        return jsonify(status="ok", rooms=len(rooms), async_mode=ASYNC_MODE)


@app.route("/config")
def config() -> Response:
    resp = jsonify(iceServers=build_ice_servers())
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/favicon.ico")
def favicon() -> Response:
    return Response(status=204)


# ── Helpers ───────────────────────────────────────────────────────────────
def gen_room_id() -> str:
    return "".join(secrets.choice(ROOM_ALPHABET) for _ in range(8))


def peer_sid(room_id: str, my_sid: str):
    room = rooms.get(room_id)
    if not room:
        return None
    return next((s for s in room["peers"] if s != my_sid), None)


def _rate_ok(log: dict, sid: str, limit: int, window: float) -> bool:
    now = time.monotonic()
    dq = log.setdefault(sid, deque())
    while dq and now - dq[0] > window:
        dq.popleft()
    if len(dq) >= limit:
        return False
    dq.append(now)
    return True


def _valid_str(v, max_len: int) -> bool:
    return isinstance(v, str) and 0 < len(v) <= max_len


def relay(event: str, data: dict) -> None:
    sid = request.sid
    if not _rate_ok(_msg_log, sid, MSG_PER_SEC, 1.0):
        return
    with _lock:
        room_id = sid_to_room.get(sid)
        target = peer_sid(room_id, sid) if room_id else None
    if target:
        socketio.emit(event, data, to=target)


def _cleanup_sid(sid: str) -> None:
    """Remove a sid from its room; notify peer; drop empty rooms. Caller holds _lock."""
    room_id = sid_to_room.pop(sid, None)
    if not room_id:
        return
    room = rooms.get(room_id)
    if not room:
        return
    if sid in room["peers"]:
        room["peers"].remove(sid)
    remaining = room["peers"][0] if room["peers"] else None
    if remaining:
        socketio.emit("peer_left", {}, to=remaining)
    else:
        rooms.pop(room_id, None)
    # NOTE: do NOT reap _create_log / _msg_log here — create_room calls this to
    # drop an abandoned room, and wiping the deque would reset the rate limiter.
    # Those logs are reaped on real disconnect (see on_disconnect).


# ── Background sweeper: reap stale half-open / empty rooms ───────────────────
def _sweeper() -> None:
    while True:
        socketio.sleep(60)
        now = time.time()
        with _lock:
            for rid in list(rooms.keys()):
                room = rooms.get(rid)
                if not room:
                    continue
                if not room["peers"] or (len(room["peers"]) < 2 and now - room["created"] > ROOM_TTL):
                    for s in list(room["peers"]):
                        sid_to_room.pop(s, None)
                    rooms.pop(rid, None)


# ── Socket.IO events ────────────────────────────────────────────────────────
@socketio.on("create_room")
def on_create_room():
    sid = request.sid
    with _lock:
        if not _rate_ok(_create_log, sid, CREATE_PER_MIN, 60.0):
            emit("error_msg", {"msg": "Too many rooms — slow down."})
            return
        if len(rooms) >= MAX_ROOMS:
            emit("error_msg", {"msg": "Server is at capacity. Try again later."})
            return
        # Drop any abandoned room this sid already owns (prevents orphan leak).
        _cleanup_sid(sid)
        # Generate a unique id.
        room_id = gen_room_id()
        while room_id in rooms:
            room_id = gen_room_id()
        rooms[room_id] = {"peers": [sid], "created": time.time()}
        sid_to_room[sid] = room_id
    join_room(room_id)
    emit("room_created", {"room_id": room_id})


@socketio.on("join")
def on_join(data):
    sid = request.sid
    if not isinstance(data, dict):
        emit("error_msg", {"msg": "Bad request."})
        return
    room_id = str(data.get("room_id", "")).strip().upper()
    if not room_id or len(room_id) > 16:
        emit("error_msg", {"msg": "Invalid room ID."})
        return
    with _lock:
        room = rooms.get(room_id)
        if not room:
            emit("error_msg", {"msg": "Room not found."})
            return
        if sid in room["peers"]:
            return
        if len(room["peers"]) >= 2:
            emit("error_msg", {"msg": "Room is full (max 2 peers)."})
            return
        _cleanup_sid(sid)  # leave any prior room first
        room = rooms.get(room_id)
        if not room or len(room["peers"]) >= 2:
            emit("error_msg", {"msg": "Room not available."})
            return
        room["peers"].append(sid)
        sid_to_room[sid] = room_id
        first_peer = room["peers"][0]
    join_room(room_id)
    emit("joined", {"room_id": room_id, "initiator": True})
    socketio.emit("peer_arrived", {}, to=first_peer)


@socketio.on("leave")
def on_leave(data):
    sid = request.sid
    rid = None
    with _lock:
        rid = sid_to_room.get(sid)
        _cleanup_sid(sid)
    if rid:
        leave_room(rid)


@socketio.on("pubkey")
def on_pubkey(data):
    if not isinstance(data, dict):
        return
    pk = data.get("pubkey")
    if not _valid_str(pk, LIMITS["pubkey"]):
        return
    relay("pubkey", {"pubkey": pk, "fenc": bool(data.get("fenc"))})


@socketio.on("offer")
def on_offer(data):
    if not isinstance(data, dict) or not isinstance(data.get("sdp"), dict):
        return
    if len(str(data["sdp"].get("sdp", ""))) > LIMITS["sdp"]:
        return
    relay("offer", {"sdp": data.get("sdp")})


@socketio.on("answer")
def on_answer(data):
    if not isinstance(data, dict) or not isinstance(data.get("sdp"), dict):
        return
    if len(str(data["sdp"].get("sdp", ""))) > LIMITS["sdp"]:
        return
    relay("answer", {"sdp": data.get("sdp")})


@socketio.on("ice")
def on_ice(data):
    if not isinstance(data, dict) or not isinstance(data.get("candidate"), dict):
        return
    if len(str(data["candidate"].get("candidate", ""))) > LIMITS["candidate"]:
        return
    relay("ice", {"candidate": data.get("candidate")})


@socketio.on("msg")
def on_msg(data):
    if not isinstance(data, dict):
        return
    ct, nonce = data.get("ct"), data.get("nonce")
    if not _valid_str(ct, LIMITS["ct"]) or not _valid_str(nonce, LIMITS["nonce"]):
        return
    relay("msg", {
        "ct": ct,
        "nonce": nonce,
        "ts": int(data.get("ts") or 0),
        "seq": int(data.get("seq") or 0),
    })


@socketio.on("disconnect")
def on_disconnect(reason=None):
    sid = request.sid
    rid = None
    with _lock:
        rid = sid_to_room.get(sid)
        _cleanup_sid(sid)
        _create_log.pop(sid, None)
        _msg_log.pop(sid, None)
    if rid:
        try:
            leave_room(rid)
        except Exception:
            pass


@socketio.on_error_default
def on_error(e):  # pragma: no cover
    print(f"[keywave] socket error: {e}", flush=True)


# ── Entrypoint (dev runner; production uses gunicorn — see Dockerfile) ───────
socketio.start_background_task(_sweeper)

if __name__ == "__main__":
    ssl_args = {}
    cert, key = os.environ.get("KEYWAVE_TLS_CERT"), os.environ.get("KEYWAVE_TLS_KEY")
    if cert and key and os.path.exists(cert) and os.path.exists(key):
        ssl_args = {"certfile": cert, "keyfile": key}
        print(f"[keywave] TLS enabled ({cert})", flush=True)

    print(f"[keywave] async={ASYNC_MODE} on {HOST}:{PORT}", flush=True)
    socketio.run(app, host=HOST, port=PORT, debug=False,
                 allow_unsafe_werkzeug=(ASYNC_MODE == "threading"), **ssl_args)
