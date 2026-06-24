# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2026-06-24

Stronger media encryption, clearer verification, and better video.

### Security
- Separate audio key space: HKDF now derives six keys (chat, video, audio, each
  per direction) instead of sharing one media key for audio and video.
- Per-frame media IV is now a 4-byte random per-stream prefix plus an 8-byte
  counter, so an IV can never repeat within a stream.
- Per-frame encryption is negotiated bilaterally via an `fenc` advertisement in
  the key exchange; it is enabled only when both peers support Insertable
  Streams, and mixed-browser calls fall back cleanly to DTLS-SRTP. The in-call
  badge reflects the active mode (frames vs DTLS-SRTP).

### Changed
- Safety-number verification now shows named emoji (each labelled so the codes
  can be read aloud) alongside the hex, and the app prompts once to compare it.

### Performance
- Video capture requests 720p/30fps with echo cancellation, noise suppression,
  and auto gain; the video sender is tuned (content hint, ~2.5 Mbps cap,
  balanced degradation) for sharper motion.

## [1.2.0] - 2026-06-24

UI/UX pass: invite sharing, responsiveness, and a few security/performance
touches.

### Added
- Invite sharing on the waiting screen: an invite link plus a native share
  sheet and one-tap WhatsApp, Telegram, email, and SMS, with copy-link and
  copy-ID buttons. An invite (↗) button is also available in the call controls.
- Invite links carry the room in the URL fragment (`#room=ID`); opening one
  auto-joins the room. The fragment is never sent to the server.

### Changed
- Responsive layout reworked for phones and desktop: safe-area insets for
  notched devices, larger touch targets, a smaller picture-in-picture on small
  screens, and a wrapping header.

### Security
- Chat messages render via `textContent` / DOM nodes instead of HTML string
  interpolation, so message content can never inject markup.
- Room IDs entered to join (and parsed from invite links) are validated
  client-side before they are sent.

### Performance
- Shared `TextEncoder` / `TextDecoder` instances on the chat path.
- Chat history is capped in the DOM to bound memory on long sessions.

## [1.1.0] - 2026-06-24

The repository now tracks the single-file build that runs in production: the
client is embedded in `app.py` and all assets are self-hosted. This release
folds a security review of that build back into the repo.

### Added
- Safety-number (SAS) verification derived from the shared secret and both
  public keys, with an in-call emoji/hex comparison flow to detect a MITM.
- `GET /healthz` endpoint (status and active room count).
- Environment configuration: CORS allowlist, room cap and TTL, room-creation
  and message rate limits, and a per-field payload cap.

### Changed
- The client is embedded in `app.py` again; the standalone `index.html` was
  removed to avoid a drifting duplicate.
- socket.io and fonts are self-hosted under `static/`; the CDN script and
  Google Fonts (and the third-party origins they implied) were removed.
- Chat messages now carry a sequence number bound as AES-GCM AAD.

### Security
- Strict Content-Security-Policy limited to self-hosted origins, plus the full
  set of response security headers.
- Chat binds sequence number and timestamp as AAD for replay/reorder detection.
- Abuse limits: room-creation rate limit, global room cap, relay rate limiting,
  per-event payload validation, socket buffer cap, and a background sweeper.
- Fixed a per-client room leak when a client created multiple rooms.
- Container hardening: read-only root filesystem, `cap_drop: ALL`,
  `no-new-privileges`, and memory/PID limits.

### Known gaps
- Per-frame media encryption is not negotiated bilaterally, so a call should use
  the same browser family on both ends.
- No bundled TURN relay; only public STUN is configured.

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
