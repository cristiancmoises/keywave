# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-06-24

First hardened release. Mobile support, link sharing, session verification, and
a production-oriented deployment.

### Added
- Responsive, mobile-friendly UI: tabbed video/chat layout on small screens,
  safe-area insets, larger touch targets, and front/back camera switching.
- Invite sharing: native share sheet plus WhatsApp, Telegram, email, SMS, and
  copy. Room ID is carried in the URL fragment and auto-joins on open.
- Safety-number (SAS) verification derived from the shared secret and both
  public keys, with an out-of-band comparison flow to detect a MITM.
- Per-frame audio/video encryption (AES-256-GCM via Insertable Streams),
  negotiated bilaterally with an honest in-call status badge.
- ICE restart and reconnection handling; connection-timeout hint.
- `GET /healthz` and `GET /config` (ICE/TURN) endpoints.
- Environment-based configuration: CORS allowlist, STUN/TURN, room caps and TTL,
  rate limits, and a self-signed TLS mode for the dev runner.
- `SECURITY.md` and this changelog.

### Changed
- Client is now a single source of truth (`index.html`) served by the app,
  replacing the previously duplicated, drifting embedded copy.
- Production runtime moved to gunicorn with a gevent-websocket worker.
- socket.io and fonts are self-hosted under `static/` instead of loaded from a
  CDN.
- README rewritten and trimmed; security detail moved to `SECURITY.md`.

### Security
- Strict Content-Security-Policy with a per-request nonce and no third-party
  origins; full set of response security headers.
- Chat messages bind sequence number and timestamp as AAD, giving replay and
  reorder detection.
- Separate key space per medium (chat, video, audio) and per direction.
- Abuse limits: room-creation rate limit, global room cap, relay rate limiting,
  per-event payload validation, socket buffer cap, and a background sweeper for
  abandoned rooms.
- Container hardening: non-root user, `cap_drop: ALL`, `no-new-privileges`,
  read-only root filesystem, memory/PID limits.

### Fixed
- Orphan-room memory leak when a client created multiple rooms.
- Disconnect handler crash that prevented peer-left notifications.
- Stale peer connection reused on rejoin; teardown is now shared between hangup
  and rejoin so no session state leaks between calls.
- In-call media badge previously could claim frame encryption that was not
  active.

### Performance
- Zero-copy frame decryption and a hoisted send IV buffer on the media hot path.
- Shared text encoder/decoder instances for chat.
- `requestAnimationFrame`-coalesced viewport handler; capped chat history.

## [0.1.0] - 2026-06-24

Initial prototype. ECDH P-256 key exchange and AES-256-GCM for chat and video
over a Flask + Socket.IO relay, delivered as a single embedded client.
