# Owned credential transport — 2026-11-19

Status: tested on `feat/shared-session-discovery`; not enabled on Edge and not
connected to the household's Apple account. No live credentials or exports were
used for this work.

## What the app now controls

`apple_transport.py` owns HTTPS requests, response parsing, destination validation,
TLS configuration and DNS resolution for the clients assembled by
`owned_protocol.py`. The prototype no longer uses the candidate's default
CloudKit/escrow client construction. Construction replaces unused SDK HTTP
objects before network access and closes all new clients on failure/cancellation.
Main account construction has the same transport installed before sign-in.
Discovery refuses accounts with an unprotected account HTTP transport.

| Purpose | Allowed destinations and operations |
| --- | --- |
| Account authentication | Explicit GSA/GSAS authentication paths and setup.icloud.com loginDelegates |
| Location reports | Explicit gateway.icloud.com Find My report paths |
| CloudKit reads | Explicit gateway.icloud.com init/database read/code-invoke paths; init allows only the Find My or Keychain container query |
| Keychain recovery | Numbered Apple escrowproxy hosts; only get_records, get_club_cert, srp_init and recover |
| Cuttlefish functions | Only fetchViableBottles, fetchChanges and fetchRecoverableTLKShares through the owned client |

No suffix-wide apple.com/icloud.com permission is granted. Server-provided gateway
URLs are checked before their tokens are used. Unknown destinations, userinfo,
nonstandard ports, encoded/ambiguous URLs, fragments, arbitrary query parameters,
record saves and escrow enroll/delete paths fail closed. Regional/changed Apple
endpoints require an explicit compatibility review rather than a wildcard.

Redirects are disabled and rejected, including same-origin redirects. Environment
proxies and cookies are disabled, and callers cannot override Host, proxy or TLS
settings. No automatic HTTP retry is made, especially for device-passcode calls.
Timeouts and decoded response sizes are bounded. Error codes/repr do not contain
URLs, credentials, headers or response bodies.

TLS verifies hostnames and certificates with a pinned-package certifi trust store,
plus Apple's public root. SSL_CERT_FILE/SSL_CERT_DIR cannot replace that store.
The public root is bundled, never fetched during authentication, and its DER
SHA-256 is checked before use:
`b0b1730ecbc7ff4505142c49f1295e6eda6bcaed7e2c68c5be91b5a11001f024`.
Source: https://www.apple.com/appleca/AppleIncRootCertificate.cer . This is a public
certificate, not a private key or account credential. Leaf certificates are not
pinned, so normal Apple certificate rotation does not require a code change.
DNS answers are checked for global addresses, including mixed public/private
responses, and the connector uses those answers without a separate app lookup.

## What this does not prove

A Python object wrapper is **not an isolation boundary against malicious Python
running in the same process**. Such code could read process memory or open a
separate socket instead of calling this transport. Pinned source/hashes and review
reduce supply-chain drift; they are not a proof that the initial dependency is
benign. OS-level egress restriction and credential/codec process isolation still
need a deployment design and testing. Do not describe these URL checks as that
sandbox or claim all dependencies are audited.

Anisette remains a separate boundary. Source inspection of anisette 1.2.4 found:

- its default library URL is a third-party download host; the SDK can reach it
  when a local library file is absent;
- provisioning uses a separate urllib3 client and server-provided Apple URL bag;
- the bundled alternative helper downloads its native libraries from Apple's
  app CDN, using its own networking implementation.

These paths are not routed through the new transport. This does not establish
that passwords were sent to them: the library download is an artifact fetch and
provisioning uses device/provisioning data. But a runtime executable download and
an additional network implementation must be addressed before the unified UI is
enabled. A deployment must fail if reviewed local artifacts are missing, enforce
artifact integrity, constrain provisioning destinations/redirects, and review the
helper's separate provenance/licensing. No new download, provisioning or Apple
account operation was run during this review.

Likewise, POST is used for both reads and writes in Apple's protocol. The owned
client restricts named operations and write paths, but this is not a complete
wire-level verification of every protobuf payload from a malicious dependency.

## Verification

The app regression suite now has 120 passing cases, including 17 transport/DNS/TLS
cases. Negative URL cases additionally cover deceptive domains, Unicode/userinfo,
encoded hosts/paths, local IPs, query injection and destination/profile mismatch.
Two real local HTTPS tests show that a 307 does not forward the synthetic body or
authentication, and that a server with an untrusted certificate receives no
credential-bearing HTTP. Local DNS/TLS overrides exist only inside fixtures;
production DNS rejection is independently tested.

The pinned candidate's 877 offline tests pass. Seven app/candidate integration tests
cover actual decryption, owned HTTP installation before authentication, constrained
client construction, disallowed operations, server-provided third-party gateway
rejection using real SDK request construction, and cancellation cleanup. Fifteen
controller cases pass, including refusal to request a token for an unprotected
account. No real Apple endpoint or production data is used by these tests.

References for the transport design:
- https://docs.aiohttp.org/en/stable/client_reference.html
- https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html

## Offline signing increment — 2026-11-19

The experimental account factory now requires an initialized app-owned offline
signer. Its adapter loads a local regular-file artifact only after an explicitly
supplied SHA-256 matches, requires existing provisioning state, and replaces the
library's implicit download and provisioning fallbacks with failures. OTP work
runs in a worker thread and is serialized; only the two required signing fields
are returned. Private state serialization is explicit, with no automatic file
write, and the legacy provider restore entry point is refused.

Nine synthetic signer tests cover artifact tampering/missing files/symlinks,
unprovisioned identities, lost provisioning, redacted failures, closure, worker
thread execution and disabled high-level download fallback. Candidate integration
also exercises the owned provider and rejects a default SDK provider before
account creation. All tests run without network or household credentials.

This is not yet a replacement for fresh provisioning or persistent account
restore. Those paths, UI handoff, private inventory storage, and process-level
egress isolation remain required before activation. Native work in a thread
cannot be forcibly interrupted by cancelling its await; no hard preemption or
memory zeroization is claimed. An explicitly supplied digest must ultimately come
from a reviewed release manifest, not from an untrusted downloaded artifact.
