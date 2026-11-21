# Candidate macOS signer: source-only review

Reviewed 2026-11-21. Not installed, executed, or approved for runtime use.

## Evidence and pins

- OpenTagViewer wrapper: commit `05b5d7cb26c9a48925f5fa580f063da4c1bed3b0`,
  `python/exporter/macadi.py` and `python/pyproject.toml`.
- Engine: `parawanderer/os-findmy-e` commit
  `595d39810639d750715babc30b063d4ac8f2c437`,
  `tools/machoadi/mac_anisette.py`, its pyproject and repository license.
- Engine metadata declares GPL-2.0-only and depends on Unicorn and FindMy.
  Process separation alone does not settle distribution obligations. Review
  applicable source, notices and licensing before packaging; no upstream code
  has been incorporated into Retrace by this review.
- Wrapper pins the Apple CoreADI payload/library hashes. This is integrity
  evidence, not redistribution permission or evidence of successful sign-in.
  No Apple binary was downloaded during this review.
- Upstream's wrapper commit explicitly leaves real sign-in unverified.

Primary sources:
[wrapper commit](https://github.com/parawanderer/OpenTagViewer/commit/05b5d7cb26c9a48925f5fa580f063da4c1bed3b0),
[engine source](https://github.com/parawanderer/os-findmy-e/blob/595d39810639d750715babc30b063d4ac8f2c437/tools/machoadi/mac_anisette.py),
[engine metadata](https://github.com/parawanderer/os-findmy-e/blob/595d39810639d750715babc30b063d4ac8f2c437/tools/machoadi/pyproject.toml).

## Integration gaps observed directly in source

1. The wrapper's `EmulatedMac.open` downloads/verifies the library and implicitly
   provisions if no provisioned machine exists. Retrace requires explicit
   provisioning consent and fail-closed restoration, so it cannot call this
   unchanged at startup or during session restoration.
2. The engine's provisioning method calls its GSA transport directly. Retrace
   must broker the typed provisioning exchanges through its owned asynchronous
   transport; the native worker must remain unable to access the network.
3. The engine reads/writes machine state and identity files; OTP generation also
   saves state. Retrace must keep these behind its private atomic storage and
   narrow IPC boundary, without granting access to account secrets or host files.
4. The Mac provisioning device identifier is not a UUID; a separate host UUID is
   also present. Current Retrace account and signing stores validate UUID device
   identifiers. Introduce an explicit versioned backend/identity model; never
   reinterpret the saved Android identity as a Mac or overwrite it implicitly.
5. The wrapper uses blocking `subprocess.run`, inherits the parent environment,
   captures stdout/stderr and exposes a stderr line in errors. Retrace needs
   bounded asynchronous process ownership, minimal environment, cancellation and
   reaping, framed bounded output, and allowlisted error codes instead.
6. The candidate has runtime/emulator lifecycle constraints and mutable OTP
   state. Verify serialized signing, timeout recovery and cache expiration;
   neither concurrent state access nor replaying provisioning is acceptable.

## Work required before a live candidate

- Define backend-neutral typed identity/signing/provisioning IPC and synthetic
  fixtures. Test both existing UUID identity compatibility and the Mac identifier
  format, corrupt/partial state, and no implicit conversion or provisioning.
- Review the engine's transitive source, emulator dependencies, native artifact
  acquisition and license obligations. Pin reviewed source and dependency hashes.
- Adapt native calls behind the existing networkless worker policy; keep network
  exchange in the parent owned transport. Verify isolation and cancellation on
  Home Assistant OS as well as the development host.
- Test atomic state updates, interrupted writes, worker crashes, malformed output,
  output limits, secret-free diagnostics, and concurrent header requests using
  synthetic data before any household authentication.
- Offer a deliberate candidate identity transition with clear consequences and
  preservation of the existing identity/session. A successful real sign-in,
  restoration, recovery and polling cycle is required before claiming a fix.

Do not deploy the upstream CLI unchanged, add a remote signing service, weaken
worker isolation, or retry household authentication automatically. Existing Edge
and stable release gates remain in force.


## Feature-flag staging

`experimental_macos_signer` is a strictly boolean internal runtime option,
defaulting to false for both absent settings and existing installations. Current
implementation is a fail-closed gate only: true returns
`macos_signer_not_available` before artifact access or private-store operations.
It is deliberately not exposed in the Supervisor schema yet. It does not claim
that the Mac adapter exists or is deployable. Existing Android paths and identity
formats remain unchanged. When the adapter is ready, it must use distinct state
and explicit provisioning; never convert or replace the existing Android store.
