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
loaded; the socket.io client and fonts are self-hosted.

### Key agreement

Each peer generates an ephemeral, non-extractable **ECDH P-256** keypair per
session and sends the raw public key through the relay. ECDH yields a 256-bit
shared secret.

### Key derivation

HKDF-SHA-256 expands the shared secret into four independent AES-256-GCM keys:
a send and receive key for chat, and a send and receive key for media. The
`info` strings are `chat:A->B` / `chat:B->A` and `video:A->B` / `video:B->A`.
Send/receive direction is assigned by a lexicographic comparison of the two
base64 public keys, so the two peers derive mirror-image key sets. Audio and
video frames share the media key for their direction.

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
Streams. A fresh random 96-bit IV is generated for each frame and prepended to
the ciphertext.

Insertable Streams is a Chromium feature. This build enables per-frame
encryption whenever the local browser supports it and does not negotiate it
bilaterally, so **both peers should use a Chromium-based browser** for a call.
Where Insertable Streams is unavailable on both ends, media is still protected
by WebRTC's transport encryption (DTLS-SRTP); because calls are peer-to-peer,
that remains end-to-end at the transport layer. Per-frame encryption is defense
in depth for paths that traverse a middlebox (for example a TURN relay).

### Session verification (safety number)

Public keys travel through the untrusted relay, so a malicious relay could
attempt a man-in-the-middle by substituting its own keys. Keywave derives a
**safety number** with HKDF over the shared secret and both exchanged public
keys (sorted), independent of direction. Honest peers compute the same value; an
attacker sitting in the middle necessarily produces a different value on each
side.

The safety number is shown as six emoji for a quick visual check, with the full
64-bit value in hex in the verification dialog. Compare it with your peer over
the live call. If the codes match, no one is intercepting the keys. Until you
confirm, the session is shown as unverified.

## Verifying a session

1. Connect to a peer.
2. Open the **Safety #** control in the call header.
3. Read the emoji (or hex) aloud and confirm they match on both screens.
4. If they match, mark the session verified. If they differ, end the call.

This step is what makes it safe to share a room ID over a messaging app: even
if the ID is intercepted, an attacker who joins cannot reproduce your safety
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
- **Per-frame media E2E is Chromium-only** and is not negotiated bilaterally in
  this build, so a call should use the same browser family on both ends; mixed
  Chromium/non-Chromium calls are not supported. Other cases fall back to
  DTLS-SRTP.
- **No metadata protection** (IPs, timing, who-talks-to-whom).
- **No in-session ratchet.** Keys are ephemeral per session and discarded on
  hangup, which gives forward secrecy across sessions; there is no key rotation
  within a single session (sessions are short-lived).
- **No bundled TURN.** Only public STUN is used, so calls across symmetric NAT
  or carrier-grade NAT may fail until you add a TURN relay.

## Server hardening

- A strict Content-Security-Policy limited to self-hosted origins with no
  third-party sources. Inline event handlers in the client require
  `'unsafe-inline'` for scripts; everything else is `'self'`.
- Response headers: `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `Permissions-Policy`, and `Cross-Origin-Opener-Policy`.
- Abuse limits: room-creation rate limit, global room cap, relay rate limiting,
  per-event payload size validation, a socket buffer cap, and a background
  sweeper that reaps abandoned rooms. One room per client prevents room leaks.
- No persistence: rooms and sessions live only in memory.
- Container runs as a non-root user with `cap_drop: ALL`, `no-new-privileges`, a
  read-only root filesystem, and memory/PID limits.

## Supported browsers

- Chrome / Edge / Chromium 86+: full chat and per-frame media encryption.
- Firefox / Safari: full chat encryption; media uses DTLS-SRTP (use the same
  browser family on both ends).
- A secure context is required (`https://` or `http://localhost`); camera access
  and Web Crypto are unavailable on plain-HTTP origins.

## Reporting a vulnerability

Please report security issues privately to the maintainer rather than opening a
public issue. Include a description, affected version or commit, and steps to
reproduce. Keywave is provided without warranty; see `LICENSE`.
