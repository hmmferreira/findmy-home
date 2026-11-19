# Shared authentication and Python discovery prototype

Status: experimental feature branch; not deployed and not a completed extractor
rewrite. Edge remains on its working Rust-backed implementation. No production
Python dependency, Apple session, Keychain membership or item inventory changed.

## What is feasible

One app authentication flow can provide the account and identity used by both
location polling and key discovery. That means one email/password/2FA journey,
not one universal Apple token or one network request. Keychain escrow requires a
fresh password-equivalent token (PET), which the discovery candidate obtains by
an additional authentication exchange. It can use the transient credentials
already held during main sign-in. It cannot silently do this later from a
password-free saved session, and Apple can still demand another factor.

A trusted device's unlock passcode is a separate cryptographic approval. It is
not an unnecessary second Apple login and cannot be promised away. A native
recovery session also does not itself require enrolling another Keychain member;
this prototype calls recovery/read operations only and exposes no join, rename
or delete operation.

## Implemented in this branch

`shared_discovery.py` is app-owned orchestration over an injected Python protocol
client. It accepts an existing authenticated account, prepares a short-lived
in-memory token lease, clears the transient account password, lists recoverable
devices, accepts a device/passcode selection, and passes recovered Find My
accessories to a private sink. It does not spawn the Rust exporter or parse PTY
prompts. Starts/unlocks are background asyncio tasks with timeouts, expiry,
owner isolation, cancellation and generic errors. Public state contains opaque
choices and labels, never tokens, passcodes, hardware serials or item keys.

This is **not yet connected to AppleWorker's sign-in completion or the HTTP UI**.
The handoff must occur before the existing worker closes its authenticated
account. The caller retains account ownership until discovery finishes; the
controller closes its discovery client, not the caller's account. The private
sink must atomically validate/merge accessory keys, preserve selections and
coordinate with poll children. It must not persist the broader recovered
Keychain peer/view keys. These are integration requirements, not completed work.

## Protocol backend and licensing boundary

Released FindMy 0.10.2 has no `findmy.icloud` discovery API. It fails the prototype
capability check rather than starting a different sign-in or falling back to
Rust. A separate Python fork declares MIT and implements the protocol:

- repository: https://github.com/parawanderer/FindMy.py
- reviewed test revision: `8ecfae6cb34b29caf0bd8176ee73155ca81415a8`
- protocol discussion: https://github.com/malmeloo/FindMy.py/issues/278
- protocol documentation: https://github.com/parawanderer/OpenTagViewer/tree/main/docs/findmy-export

The experimental runner uses that clean, pinned checkout in a disposable image;
its source is not vendored or made a production dependency. The declared license
and claimed independent implementation still need provenance/compatibility
review before adoption. Translating the existing Rust source is not the approach
used here. We have already inspected that source historically and do not label
our work a clean-room cryptographic reimplementation. No license blocker is
claimed resolved merely by creating an adapter or changing languages.

## Test evidence

- Existing app regressions, 15 controller cases and 17 transport cases: 111 tests.
- Candidate backend suite: 877 tests passed in a read-only container, with no
  network, no Apple account and no production mounts.
- Six integration tests include running our controller over the candidate's real
  key-share/zone/record decryption code and synthetic account fixtures, producing
  an accessory that derives rolling advertising keys.
- Ownership, no duplicate account input, secret redaction, invalid choices,
  passcode validation, no automatic retries, token expiry/revocation, timeout,
  cancellation, inventory sink failures and resource closing are covered.

These tests prove local composition and failure handling, not Apple's live
protocol or a successful import from the household account. The app-owned client construction now closes its resources when initial open
is cancelled, with explicit coverage. Anisette provisioning and OS-level egress
isolation still require review before UI integration. See CREDENTIAL_BOUNDARY.md. Its own documentation distinguishes synthetic success from
live account verification.

Developer-only reproduction (the backend checkout must match backend.json and
have no local changes):

```sh
python3 tools/review-shared-discovery.py /path/to/reviewed/FindMy.py
```

The runner uses the existing private Portainer configuration. Builds download
public test dependencies; the test container itself has network disabled and no
host/runtime mounts. It packages allowlisted source/tests only. Never substitute
production session files, keys, account exports or a real passcode for fixtures.

## Before replacing the existing extractor

1. Review/pin the Python backend and its dependencies, including provenance, provisioning and
   process/network isolation. Retain notices; audit changed SDK behavior.
2. Wire main sign-in completion to the owned discovery session and expose one
   unified UI flow. Later discovery requiring a fresh PET must request main-flow
   reauthentication explicitly, without retaining a password.
3. Implement the atomic Find My-only private inventory sink and preservation of
   stable IDs, selections, alignment and existing polling.
4. Run an explicit live comparison using the app's protected UI for the device
   passcode. Do not collect a passcode through chat or test logs. Verify no trust
   join/write calls and compare actual recovered accessories/sightings.
5. Only then remove the Rust binary/build patches from a tested image. The helper
   image's separate licensing/provenance review does not disappear with Rust.


## Owned transport increment — 2026-11-19

Account, CloudKit and escrow HTTP for the prototype now go through the app-owned
transport with explicit Apple destinations, strict TLS, private-DNS rejection and
no redirects/environment proxies. Discovery refuses an unprotected account.
Candidate clients are composed explicitly, without changing shared module globals
or the production SDK. The public Apple root is bundled and hash-checked.
See [credential boundaries and tests](CREDENTIAL_BOUNDARY.md), including the
separate Anisette network paths and why an in-process wrapper is not a malicious
code sandbox. UI activation remains gated; Edge and its dependency lock have not
changed.

## Offline signer increment — 2026-11-19

The prototype refuses the SDK's default downloading/remote signer. It accepts an
app-owned offline signer with a verified local artifact and existing provisioning
only. Signing leaves the asyncio event loop, implicit provisioning/downloads stop
with redacted errors, and transient prepared headers are cleared after use.
Validation: 120 app cases, 877 candidate cases and seven composition cases pass;
the 15 controller cases also pass in the candidate environment. Fresh provisioning,
owned restore, UI wiring and process isolation remain open; no Edge deployment.
