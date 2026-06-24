# Keywave

End-to-end encrypted, peer-to-peer chat and video. One small service, no
accounts, no persistence. The server only relays the handshake; it never sees
message or call content.

![Keywave](./images/keywave.png)
![Screenshot](./images/2.png)
![Screenshot](./images/3.png)

## Features

- 1:1 text chat and video/audio calls, encrypted in the browser.
- Works on desktop and mobile with a responsive, touch-friendly layout.
- Invite by link: a share sheet plus one-tap WhatsApp, Telegram, email, and SMS,
  or copy the link / room ID. Opening an invite link auto-joins the room.
- Safety-number verification to detect a man-in-the-middle.
- Per-frame media encryption on Chromium browsers (Insertable Streams).
- Single self-contained service: the client is embedded in `app.py` and all
  assets (socket.io, fonts) are self-hosted. No CDN, no third-party origins.

## Quick start

```bash
docker compose up -d --build
```

Open <http://localhost:5128>. To try it on one machine, open it in two browser
windows: create a room in the first, copy the room ID, and join with it in the
second. `localhost` is a secure context, so the camera and Web Crypto work
without TLS.

Endpoints: `GET /healthz` (status + active room count).

## Connecting a peer

Create a room. The waiting screen shows an invite link and quick share buttons:
a native share sheet (covering Signal, Session, Tox, Element, and anything else
installed) plus one-tap WhatsApp, Telegram, email, and SMS, with "Copy" for the
link and "Copy ID" for the room ID alone. The room ID travels in the URL
fragment (`#room=ID`), which browsers never send to the server, and opening the
link auto-joins the room. There is also an invite button (↗) in the call
controls.

A room holds at most two peers and is one-time use: anyone who has the link can
take the second slot, so after connecting, verify the safety number (see
[SECURITY.md](./SECURITY.md)) to confirm no one is in the middle.

## Running on a phone or over a network

Phones can't use `localhost`, so they need a secure context (HTTPS) over the
network. Two practical options:

1. **Reverse proxy with a real certificate** (recommended). Put Keywave behind
   Nginx Proxy Manager, Caddy, or Traefik with a domain and a Let's Encrypt
   certificate, pointed at `http://keywave:5000` with WebSocket upgrade headers
   enabled. See the notes at the bottom of `docker-compose.yml`.
2. **A tunnel** (cloudflared, ngrok, tailscale-funnel) that terminates HTTPS.

Calls connect peer-to-peer using public STUN. Between two mobile networks or
behind carrier-grade NAT this can fail; this build does not ship a configurable
TURN relay, so deploy one and adjust the ICE configuration if you need that.

## Configuration

Everything is optional and set via environment variables.

| Variable | Purpose | Default |
| --- | --- | --- |
| `KEYWAVE_PORT` | Bind port inside the container | `5000` |
| `KEYWAVE_ALLOWED_ORIGINS` | CORS allowlist (`*` or comma-separated) | `*` |
| `KEYWAVE_MAX_ROOMS` | Global room cap | `5000` |
| `KEYWAVE_ROOM_TTL` | Seconds a half-open room lives before reaping | `7200` |
| `KEYWAVE_CREATE_MAX` / `KEYWAVE_CREATE_WINDOW` | Room-creation rate limit (count / seconds) | `10` / `60` |
| `KEYWAVE_MSG_MAX` / `KEYWAVE_MSG_WINDOW` | Relayed-message rate limit (count / seconds) | `120` / `10` |
| `KEYWAVE_MAX_PAYLOAD` | Max bytes per relayed field | `262144` |

Lock `KEYWAVE_ALLOWED_ORIGINS` to your real origin in production.

## How it works

Peers exchange ephemeral ECDH P-256 public keys through the relay, derive
AES-256-GCM keys with HKDF, and encrypt chat messages and media frames in the
browser. A safety number derived from the shared secret and both public keys
lets the two users confirm there is no man-in-the-middle. Full details,
including the threat model and known limitations, are in
[SECURITY.md](./SECURITY.md).

## Project layout

```
app.py             Flask + Socket.IO relay, with the client embedded as HTML
static/            Self-hosted socket.io client and fonts (no CDN)
Dockerfile         python:3.12-slim, runs app.py behind your reverse proxy
docker-compose.yml
```

## Links

- Security model and reporting: [SECURITY.md](./SECURITY.md)
- Release notes: [CHANGELOG.md](./CHANGELOG.md)
- License: [LICENSE](./LICENSE)
