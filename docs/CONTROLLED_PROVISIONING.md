# Controlled native provisioning and signing

Experimental shared-session branch only. Tests use synthetic state and a stand-in
native implementation: no household credentials, private artifact, live Apple
requests or real native provisioning were used. This is not deployed on Edge.

## Parent owns the handshake

`controlled_provisioning.py` implements asynchronous lookup/start/finish. It
requires explicit new-identity creation, verifies a supplied SHA-256 for a local
regular-file artifact before passing bytes to a worker, and returns private state
without writing files or replacing an existing identity. It never accepts an
Apple account password. Artifact I/O runs off the event loop; HTTP and worker IPC
are asynchronous. Failures produce generic codes and no stage is retried.

The owned provisioning transport permits exactly:

- GET `https://gsa.apple.com/grandslam/GsService2/lookup`
- POST `https://gsa.apple.com/grandslam/MidService/startMachineProvisioning`
- POST `https://gsa.apple.com/grandslam/MidService/finishMachineProvisioning`

Both returned URLs must match before any provisioning payload is sent. There are
no guessed fallbacks or suffix-wide permissions. Endpoint compatibility evidence:
[pinned ap source](https://github.com/hpidcock/ap/blob/e690795d1744/internal/anisette/provisioning/provisioning.go).
This is not an Apple API guarantee or live verification. The parent transport
also enforces TLS/DNS rules, response limits, no redirects/environment proxies and
no retries. `provision_new_identity` requires a supplied worker; production startup
supplies `IsolatedNativeWorker` only after the reviewed artifact policy permits it.

## Implemented worker boundary

`native_worker.py` launches a one-use Linux child with `-I -S -B`, a minimal
environment, closed inherited descriptors and a separate process group. Account
passwords, account sessions, credentials-directory paths and environment values
are not passed. Native stdout/stderr go to `/dev/null`; a separate inherited pipe
carries framed JSON, with bounded messages and strict bounded binary fields.
Startup cancellation acquires any late child handle before killing/reaping it;
spawn failures close both control descriptors. Repeated close never signals a
previously reaped PID.

Before third-party imports, artifact input or native code, the trusted child:

- Requires Linux x86_64/aarch64, Landlock ABI 3 or later and system libseccomp2.
- Sets no-new-privileges, non-dumpable status and CPU/address-space/open-file,
  file-size and core limits.
- Applies Landlock restrictions: read-only public app/interpreter/dependency
  directories and selected public runtime files only. No `/data`, parent `/proc`
  files or home directories are granted. File writes/removal/creation, executing
  files and all other handled filesystem accesses are denied. The app image must
  keep private data outside these public code/library directories.
- Installs a seccomp filter denying network/socket calls (including UNIX sockets),
  fork/clone/exec, tracing/other-process memory or descriptors, parent signalling,
  namespaces/mounts, io_uring, kernel-key/BPF/performance APIs, identity/capability
  changes and `prctl` changes. Metadata mutation calls (chmod/chown/timestamps/
  xattrs) and descriptor-control ioctl/fcntl calls are denied separately because
  Landlock does not mediate every metadata change. Missing critical syscall
  definitions fail closed.
  The worker cannot reverse non-dumpable status or the already-applied boundary.

It requires no additional capabilities, privileged mode, unshare or namespace
creation. If the target kernel/container denies a restriction, startup fails;
there is no permissive fallback. This is an explicit Linux policy, not a claim
that Python URL checks form a sandbox or that all kernel attack surface is gone.
Landlock limits content reads and directory enumeration, not every metadata query:
stat/readlink of a known path may still reveal public metadata or existence. The
policy must not be described as hiding all filesystem/process metadata.

After the boundary is active, the child loads only supplied in-memory artifact
bytes via the low-level anisette loader. Implicit download/provisioning fallbacks
fail. The child runs a strict prepare/begin/finish state machine, retaining native
session handles privately. On errors, cancellation or timeout the parent kills
and reaps the whole process; this avoids relying on anisette 1.2.4's unimplemented
`destroy_provisioning` API. Its native DEBUG messages contain sensitive values,
which is why neither normal stdout nor stderr is used for app logging or IPC.

## Process-backed offline signing

`ProcessOfflineSigner` satisfies the existing OfflineSigner/provider interface
but puts native loading/signing in the same restricted child. It accepts only
already-provisioned state, serializes IPC, and never silently provisions. Each
successful initialization/signing response includes a validated private snapshot.
The parent caches that snapshot for synchronous, nonblocking serialization and
refuses export while an operation is pending. Close revokes immediately, clears
cached state, terminates and reaps the process. Pending operations cannot publish
late usable results.

The original thread-backed OfflineSigner remains for isolated prototype tests;
it is not the selected process boundary for shared runtime startup/restore.
Its cancellation/close changes provide logical revocation, not native interruption
or zeroization.

## Evidence and remaining release gates

Synthetic tests exercise the real process boundary: denied private-file reads,
parent environment content, filesystem writes/metadata mutation, IPv4/IPv6/UNIX sockets, process
execution/signalling, and attempts to re-enable dumpability. They check native
output isolation, signing snapshot updates, cancellation/hang/error process
reaping, startup cancellation/descriptor cleanup, repeated close, bad frames and
unsupported boundaries. Parent orchestration tests cover endpoint substitution,
invalid fields, no automatic persistence/retry, redaction and timeout cleanup.
None substitutes for testing real native artifact compatibility or Apple's live
service.

A reviewed artifact release manifest is still required: exact digest, source and
version, guest architecture, distribution/license evidence and approval. A digest
computed from an arbitrary download does not establish trust. The committed
policy must reject incomplete review, missing files or mismatches; no artifact
is fabricated or auto-downloaded. Once policy is approved, target HA kernel
support and actual native compatibility must be checked before an explicit live
setup. The process boundary does not resolve library provenance or redistribution
rights, and tests with synthetic code do not resolve them either.

### Technical compatibility check

A production `Dockerfile.shared` image was built with the pinned Python backend
and libseccomp2. Its native-boundary smoke test passed as UID 1000, without added
capabilities, on a read-only filesystem and with container networking disabled.
A deterministic bundle from the inspected public vendor artifact, SHA-256
`1cc48641b9803e951eaf96439463e05790e5b14452155261dcc271cec53ad563`, also
completed the worker's local `prepare` operation inside those restrictions. The
check validated only the three returned identity-header field names; values were
not logged. It made no Apple requests, provisioning exchange or account operation.
This proves local loading/initialization compatibility for that image/host, not
redistribution approval, completed provisioning, target-HA support or live login.
The artifact policy remains pending review; the probe did not bypass it in the
production setup flow.

### One identity across provisioning and account authentication

Shared startup supplies a generated local user ID, device ID and client-info
string together to `IsolatedNativeWorker`. The child uses these in its native
device configuration: uppercase device ID and raw local user ID are retained.
The child base64-encodes the local user ID only when returning its provisioning
header, matching the native signer and later SDK headers; a separate random ADI
identifier is retained. All
three fields are required together and header-control characters are refused.
The parent handshake accepts the corresponding validated user-agent string.
Startup must persist and reuse both account IDs and the client description with
machine state; changing only one half would introduce a different installation.
Synthetic process tests verify the explicit identity reaches both native config
and provisioning headers. The local compatibility probe above preceded this
optional explicit-identity increment; it did not verify live Apple acceptance.
