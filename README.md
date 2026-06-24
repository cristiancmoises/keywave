# Keywave

End-to-end encrypted, peer-to-peer chat and video. One small service, no
accounts, no persistence. The server only relays the handshake; it never sees
message or call content.

![Keywave](./images/keywave.png)
![Screenshot](./images/2.png)
![Screenshot](./images/3.png)

## Features

- 1:1 text chat and video/audio calls, encrypted in the browser.
- Works on desktop and mobile, with a responsive layout and camera switching.
- Invite by link: native share sheet plus WhatsApp, Telegram, email, SMS, and
  copy. Opening an invite link auto-joins the room.
- Safety-number verification to detect a man-in-the-middle.
- Single static client, no build step. Self-hosted assets, no CDN.

## Quick start

```bash
docker compose up -d --build
```

Open <http://localhost:5128>. To try it on one machine, open it in two browser
windows: create a room in the first and use the invite link in the second.
`localhost` is a secure context, so the camera and Web Crypto work without TLS.

Endpoints: `GET /healthz` (status), `GET /config` (ICE/TURN servers).

## Sharing an invite

After creating a room, the invite panel offers a native share sheet (covering
Signal, Session, Tox, Element, and anything else installed) plus one-tap
WhatsApp, Telegram, email, SMS, and copy. The room ID travels in the URL
fragment (`#room=ID`), which browsers never send to the server, and the link
auto-joins on open.

A room ID is a one-time key: anyone who has it can take one of the two slots.
After connecting, verify the safety number (see [SECURITY.md](./SECURITY.md)).

## Running on a phone or over a network

Phones can't use `localhost`, so they need a secure context over the network.
Options:

1. **Reverse proxy with a real certificate** (recommended). Put Keywave behind
   Nginx Proxy Manager, Caddy, or Traefik with a domain and a Let's Encrypt
   certificate. See the notes at the bottom of `docker-compose.yml`.
2. **Self-signed certificate on the LAN** (quick test). The certificate must
   include the machine's LAN IP as a Subject Alternative Name:

   ```bash
   openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
     -keyout key.pem -out cert.pem \
     -subj "/CN=192.168.1.50" -addext "subjectAltName=IP:192.168.1.50"

   KEYWAVE_ASYNC=threading KEYWAVE_TLS_CERT=cert.pem KEYWAVE_TLS_KEY=key.pem python app.py
   ```

   Open `https://192.168.1.50:5000` and accept the warning.
3. **A tunnel** (cloudflared, ngrok, tailscale-funnel) that terminates HTTPS.

For calls between two mobile networks or behind carrier-grade NAT, STUN alone is
usually not enough; configure a TURN relay (see Configuration). A TURN relay
only forwards encrypted media.

## Configuration

Everything is optional and set via environment variables. The full list is in
the header comment of `app.py`; the most useful:

| Variable | Purpose | Default |
| --- | --- | --- |
| `KEYWAVE_PORT` | Bind port | `5000` |
| `KEYWAVE_ALLOWED_ORIGINS` | CORS allowlist (`*` or comma-separated) | `*` |
| `STUN_URLS` | STUN servers (comma-separated) | Google STUN |
| `TURN_URLS` | TURN servers | none |
| `TURN_USERNAME` / `TURN_CREDENTIAL` | Static TURN credentials | none |
| `TURN_STATIC_SECRET` | coturn REST shared secret (time-limited creds) | none |
| `KEYWAVE_MAX_ROOMS` | Global room cap | `5000` |
| `KEYWAVE_ROOM_TTL` | Seconds a half-open room lives | `7200` |
| `KEYWAVE_TLS_CERT` / `KEYWAVE_TLS_KEY` | Enable HTTPS in the dev runner | none |

## How it works

Peers exchange ephemeral ECDH P-256 public keys through the relay, derive
AES-256-GCM keys with HKDF, and encrypt chat messages and media frames in the
browser. A safety number derived from the shared secret and both public keys
lets the two users confirm there is no man-in-the-middle. Full details,
including the threat model and known limitations, are in
[SECURITY.md](./SECURITY.md).

## Project layout

```
app.py             Flask + Socket.IO relay server
index.html         Single-page client (HTML, CSS, JS; no build step)
static/            Self-hosted socket.io client and fonts
Dockerfile         gunicorn + gevent-websocket
docker-compose.yml
```

## Links

- Security model and reporting: [SECURITY.md](./SECURITY.md)
- Release notes: [CHANGELOG.md](./CHANGELOG.md)
- License: [LICENSE](./LICENSE)
