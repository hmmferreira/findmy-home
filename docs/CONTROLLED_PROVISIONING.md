# Controlled provisioning groundwork

Experimental shared-session branch only. No household credentials, live Apple
requests or native provisioning were used. This is not activated in Edge or UI.

`controlled_provisioning.py` owns the asynchronous lookup/start/finish handshake.
It requires explicit creation of a new identity, verifies a supplied SHA-256 for
a local regular-file artifact before giving its bytes to a worker, and returns
private state bytes without writing files or replacing an existing identity.
It never accepts an Apple account password. Artifact reading runs off the event
loop and worker methods are asynchronous. An HTTP or worker failure stops the
flow with a generic code; no stage is retried automatically.

Its separate owned transport profile permits exactly three method/route pairs:

- GET `https://gsa.apple.com/grandslam/GsService2/lookup`
- POST `https://gsa.apple.com/grandslam/MidService/startMachineProvisioning`
- POST `https://gsa.apple.com/grandslam/MidService/finishMachineProvisioning`

Both server-supplied provisioning URLs must exactly match the reviewed routes
before the first provisioning payload is sent. There are no guessed endpoint
fallbacks or suffix-wide allowances. These route values are documented by the
[pinned ap implementation](https://github.com/hpidcock/ap/blob/e690795d1744/internal/anisette/provisioning/provisioning.go).
This is compatibility evidence, not Apple's official API guarantee or a claim of
live verification. The existing app-owned transport enforces TLS/DNS bounds,
response size limits, no redirects, no environment proxies and no HTTP retries.

## Explicit activation gate

There is deliberately no default native worker: the public entry point fails
with `isolated_provisioning_worker_required` until one is explicitly supplied.
The worker protocol is an interface, not a process sandbox. Production needs a
reviewed isolated implementation with no networking, redacted/disabled native
logs, bounded messages/resources, and reliable process termination on failure.
Its prepare/begin/finish methods must keep native session handles private and
its close method must reap the process. Awaitable cleanup has a five-second
bound; this does not promise that arbitrary native threads can be interrupted.

Review of the pinned installed anisette 1.2.4 source found that its native ADI
methods log intermediate bytes, persistent tokens and trust keys at DEBUG, and
`destroy_provisioning` raises NotImplementedError. Therefore this increment does
not call its existing provisioning helper, install a global logging workaround,
or expose that helper behind a production UI. A future worker must address those
facts before activation. Artifact provenance, distribution rights, trusted digest
manifest, device identity/client description compatibility, private state store
handoff and deliberate live verification remain open.

Synthetic tests cover successful composition, no automatic persistence, bad or
missing artifacts, symlinks/directories, missing explicit setup/worker, malicious
or swapped URL bags, unexpected identity/credential headers, secret redaction,
redirect refusal, no retries, invalid response fields, cancellation/timeout cleanup,
owned transport enforcement and event-loop-safe artifact I/O. They use an injected
fake worker and fake owned transport: they prove orchestration, not real native
or Apple protocol success.

## Integration review: remaining concrete worker requirements

The current app image has no reviewed worker launcher or release manifest for the
native artifact. Supplying a new Python subprocess alone does not solve this:
a process using the app's UID/filesystem/network could still read `/data`, inspect
its parent's environment or open its own sockets. The current protocol is only
an injection point for testing; it must not be labelled isolation in the UI.

Before enabling first-time provisioning, implement and test these restrictions
on the Home Assistant deployment target:

1. A reviewed release manifest binds the artifact digest to its source, version,
   architecture and distribution/license evidence. Do not compute a digest from
   an arbitrary download and then call that download trusted. No artifact or
   fresh household identity was manufactured during these tests.
2. Launch a one-use worker with a minimal environment and no account credentials,
   session-store files, inherited descriptors or host-secret mounts. Restrict its
   filesystem and process visibility so it cannot read the parent or `/data`.
3. Deny networking in the worker using an OS boundary, not a replacement Python
   HTTP object. Only the parent performs the reviewed three-request exchange.
   Apply no-new-privileges/resource bounds and prevent further process execution
   or tracing after startup. Check the actual target kernel's support; do not
   silently downgrade when a restriction cannot be applied.
4. Use bounded private IPC for artifact bytes, three identity headers, SPIM/CPIM,
   PTM/TK and final provisioning state. Native stdout/stderr must never flow into
   app logs. Separate framed control output from native logging; reject unknown
   messages and malformed/oversized fields.
5. On failure, cancellation or timeout, terminate and reap the whole worker;
   process termination provides a cleanup path despite the SDK's unimplemented
   native destroy API. Save final state atomically only after successful parent
   validation and worker cleanup. Never expose intermediate values in status.

Until this exists and is exercised with synthetic OS-boundary tests, the concrete
activation blocker is `isolated_provisioning_worker_required`. There is no hidden
fallback to the library's network client, Rust helper or remote signer.

The offline signer also remains a thread-backed experimental adapter, not the
restricted worker described above. Cancellation and close now revoke it
immediately, prevent late initialization from becoming usable, and reject late
signing results. Native calls already executing can still finish privately; close
does not claim native destruction, hard interruption or zeroization. That is why
both provisioning and signing need the eventual process boundary before an
untrusted-artifact/supply-chain threat model is considered satisfied.
