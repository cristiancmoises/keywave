# Security

This document describes Keywave's threat model, cryptographic design, known
limitations, and how to report a vulnerability.

## Threat model

Keywave is a two-party, end-to-end encrypted chat and video tool. The signaling
server is treated as **untrusted**: it relays the handshake but is assumed to be
curious or hostile. Encryption happens entirely in the browser.

What the server (and anyone on the network path) can see:

- IP addresses of both peers and the timing of a session.
- That two parties joined the same room and exchanged data.
- Ephemeral public keys, opaque ciphertext, and WebRTC SDP/ICE during signaling.

What it cannot see:

- Message plaintext or call audio/video.
- The session keys (they are derived in the browser and never sent).

Keywave does not try to hide metadata (who talks to whom, when, from where). If
that is part of your threat model, run it over a network layer that does.

## Cryptography

All primitives use the browser's Web Crypto API. No third-party crypto code is
loaded.

### Key agreement

Each peer generates an ephemeral, non-extractable **ECDH P-256** keypair per
session and sends the raw public key through the relay. ECDH yields a 256-bit
shared secret.

### Key derivation

HKDF-SHA-256 expands the shared secret into six independent AES-256-GCM keys:
chat, video, and audio, each split into a send and receive key. The `info`
string is `keywave:{chat|video|audio}:{A->B|B->A}`. Send/receive direction is
assigned by a lexicographic comparison of the two base64 public keys, so the two
peers derive mirror-image key sets. Each medium has its own key space, so frame
nonces from different streams can never collide.

The HKDF salt is a fixed zero block. This is intentional and safe: the input key
material is a high-entropy ephemeral ECDH secret, and the `info` strings provide
domain separation between keys.

### Chat

Each message is encrypted with AES-256-GCM using a fresh random 96-bit IV. The
message sequence number and timestamp are bound as additional authenticated data
(AAD), so they cannot be altered without failing authentication. The receiver
rejects any message whose sequence number is not strictly increasing, which
gives replay and reorder detection.

### Audio and video

Media is encrypted per encoded frame with AES-256-GCM using WebRTC Insertable
Streams. The IV is a 4-byte random per-stream prefix plus an 8-byte big-endian
counter, so an IV is never reused within a stream.

Frame encryption is negotiated bilaterally: each peer advertises support, and it
is enabled only if both peers support it. Insertable Streams is currently a
Chromium feature, so a call involving Firefox or Safari falls back to WebRTC's
transport encryption (DTLS-SRTP). The in-call badge reflects which mode is
active rather than claiming frame encryption that is not running.

Because calls are peer-to-peer (optionally via a TURN relay that only forwards
encrypted packets), media is end-to-end encrypted at the transport layer even
when per-frame encryption is unavailable. Per-frame encryption is defense in
depth for paths that traverse a middlebox.

### Session verification (safety number)

Public keys travel through the untrusted relay, so a malicious relay could
attempt a man-in-the-middle by substituting its own keys. Keywave derives a
**safety number** with HKDF over the shared secret and both exchanged public
keys (sorted), independent of direction. Honest peers compute the same value; an
attacker sitting in the middle necessarily produces a different value on each
side.

The safety number is shown as five emoji for a quick visual check, with the full
64-bit value in hex in the verification dialog. Compare it with your peer over
the live call. If the codes match, no one is intercepting the keys. Until you
confirm, the session is shown as unverified.

## Verifying a session

1. Connect to a peer.
2. Open the **Safety** control in the call header.
3. Read the emoji (or hex) aloud and confirm they match on both screens.
4. If they match, mark the session verified. If they differ, end the call.

This step is what makes it safe to share a room link over a messaging app: even
if the link is intercepted, an attacker who joins cannot reproduce your safety
number.

## Known limitations

- **Trust in the origin.** As with any web-delivered E2E app, the server ships
  the client code. A compromised origin could serve a backdoored client.
  Self-hosted assets and a strict CSP reduce supply-chain exposure, but you
  ultimately trust whoever operates the origin.
- **Room IDs are bearer capabilities.** Anyone who has a room ID can take one of
  the two slots. The safety number defeats a racing attacker (their code will
  not match), and rooms hold at most two peers.
- **Verification is manual.** If users skip the safety-number comparison, a
  relay-level MITM is not automatically detected. The app surfaces an unverified
  state but does not block media, because the call itself is needed to compare.
- **Per-frame media E2E is Chromium-only** today; other browsers use DTLS-SRTP.
- **No metadata protection** (IPs, timing, who-talks-to-whom).
- **No in-session ratchet.** Keys are ephemeral per session and discarded on
  hangup, which gives forward secrecy across sessions; there is no key rotation
  within a single session (sessions are short-lived).

## Server hardening

- Per-request CSP nonce and a strict policy with no third-party origins
  (socket.io and fonts are self-hosted).
- Response headers: `X-Content-Type-Options`, `Referrer-Policy`,
  `X-Frame-Options`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`, and
  HSTS over HTTPS.
- Abuse limits: room-creation rate limit, global room cap, relay rate limiting,
  per-event payload validation, a socket buffer cap, and a background sweeper
  that reaps abandoned rooms.
- No persistence: rooms and sessions live only in memory.
- Container runs as a non-root user with `cap_drop: ALL`, `no-new-privileges`, a
  read-only root filesystem, and memory/PID limits.

## Supported browsers

- Chrome / Edge / Chromium 86+: full chat and per-frame media encryption.
- Firefox / Safari: full chat encryption; media uses DTLS-SRTP.
- A secure context is required (`https://` or `http://localhost`); camera access
  and Web Crypto are unavailable on plain-HTTP origins.

## Reporting a vulnerability

Please report security issues privately to the maintainer rather than opening a
public issue. Include a description, affected version or commit, and steps to
reproduce. Keywave is provided without warranty; see `LICENSE`.
