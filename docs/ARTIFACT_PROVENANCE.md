# Native artifact and candidate provenance review — 2026-11-19

Status: source integrity, APK signature/vendor association, and current Dragon
worker initialization verified; native-use/distribution approval is still pending. This document records observations, not a legal opinion or an
upstream guarantee. No household artifact, session, password or passcode was read.
The source/bundle inspection below did not execute native code. A subsequent
parent-run compatibility probe initialized the verified vendor bundle inside the
production shared image's IsolatedNativeWorker on Dragon: UID/GID1000, all
capabilities dropped, read-only root, no container network, and worker Landlock/
seccomp restrictions. It made no Apple/provisioning exchange and used no account.
This establishes initialization on the current Dragon host, not Home Assistant
host compatibility, successful provisioning, independent native code safety or
permission to use/distribute the binaries.

## Public native source inspected

Downloaded the public vendor APK over HTTPS from:
https://apps.mzstatic.com/content/android-apple-music-apk/applemusic.apk

The response was HTTP 200 with no redirect. It reported version `4.9.6.1447`,
142,139,820 bytes, and Last-Modified `2025-04-15T18:26:03Z`. Independent parsing of
AndroidManifest.xml found package `com.apple.android.music`, versionName `4.9.6`,
versionCode `1447`. The exact downloaded APK SHA-256 is:

`9aab4e3bfd44b509dd657b030d46df536c5592512c256fc59012cce47a2e9c9c`

Only these archive members were selected, hashed and inspected as data:

| Member | Bytes | SHA-256 |
| --- | ---: | --- |
| lib/arm64-v8a/libCoreADI.so | 1,792,592 | 9d5b557cf3faf88c34c394ab2cd7fc1a3b4acf3aed51f28cd0bc093858107c22 |
| lib/arm64-v8a/libstoreservicescore.so | 2,388,480 | bd335e6963ba5ae2f5babca613435ad56d2660a9aee37df35f876c458d105ce4 |

Both have ELF64 little-endian headers with machine 183 (AArch64). This establishes
which bytes/guest architecture were inspected; it is not a native code audit.
Official Android Build Tools 35.0.0 `apksigner verify --verbose --print-certs`
verified APK Signature Scheme v2, with one signer, exit 0. Other signing schemes
and SourceStamp were absent. The certificate SHA-256 is:

`88ba590ec2e1ea33c4458daf59489faee2cef297a9b4071e18cf82ef531100aa`

The same certificate fingerprint is published for `com.apple.android.music` by
Apple's HTTPS association document:
https://music.apple.com/.well-known/assetlinks.json . This association, rather
than a self-asserted certificate subject name, anchors the signer to the vendor's
published Android app identity. The certificate uses a 1024-bit RSA key; successful
verification records the vendor's existing signing configuration and is not an
endorsement of its key strength or a permission grant.

The verifier ran in a disposable `eclipse-temurin:17-jre` container as UID1000,
network disabled, root filesystem read-only, all capabilities dropped, no new
privileges, with only the public temporary review directory mounted read-only.
The APK was parsed as data, not installed/executed. Container was removed afterward.
Runtime image ID:
`sha256:f3e2aa42fcb2fe28a3d414b585505dc3b59a2cba154ebb259f288ff73caf1191`.

Verifier provenance: official Google repository metadata
https://dl.google.com/android/repository/repository2-1.xml selected
https://dl.google.com/android/repository/build-tools_r35_linux.zip , size61,958,799.
Its published SHA-1 `2cfaa0bbb2336e9ec18ed3ecea84fa2e2af607bc` matched; separately
recorded ZIP SHA-256:
`bd3a4966912eb8b30ed0d00b0cda6b6543b949d5ffe00bea54c04c81e1561d88`.
Extracted apksigner.jar SHA-256:
`00ef9948f843fe395d2440ae3ef41405b8040a6d5d46493bd1902ac0ee6deae7`.
Tool usage reference: https://developer.android.com/tools/apksigner .

`tools/review-native-artifact.py` independently builds a deterministic uncompressed
USTAR with sorted, fixed-name ELF files and a compact `fs.json` index compatible
with Anisette's FSCollection format. UID/GID and timestamps are zero; no source
paths, signatures, unrelated APK files, sessions or account state are copied.
Two repeated builds produced 4,188,160 identical bytes with SHA-256:

`1cc48641b9803e951eaf96439463e05790e5b14452155261dcc271cec53ad563`

The APK and bundle stay outside Git in a temporary review directory. They are not
included in the app image, release package or test fixtures. The tool performs no
download, execution or approval, and refuses a source/member/bundle hash mismatch.
The vendor URL is mutable: a future download must match the pinned bytes or fail;
its location alone never approves a changed version.

## Wrapper and native licensing are separate

The pinned Anisette 1.2.4 Python wheel is identified by PyPI SHA-256:
`f61e620aa736f0cac0ca102dd44a02cc2caea1a072eab0f1ef7f2d8b534e03dc`.
This matches the existing app dependency lock. Its packaged license is MIT with
2025 Anisette.py contributor attribution. The wrapper source/documentation
identifies Apple Music APK libraries and a third-party default library download;
the new path never uses that download fallback.

Primary references:
- https://pypi.org/pypi/anisette/1.2.4/json
- https://github.com/malmeloo/Anisette.py/blob/main/LICENSE
- https://github.com/malmeloo/Anisette.py/blob/main/anisette/_library.py
- https://github.com/Dadoum/anisette-v3-server/blob/main/source/app.d

The wrapper's MIT notice does not establish permission to redistribute Apple's
native binaries or authorize this particular use. No such permission was located
or inferred in this review. Native-use/license review remains pending; bundling
or downloading executable libraries at app runtime is therefore not enabled.
A future local-use-only policy, if reviewed/approved, must still keep binaries out
of community images; it is a separate decision from permission to redistribute.

## Fixed release policy

`artifact_policy.py` reads only bundled `trusted_artifacts.json`. It has no runtime
manifest path, environment override, user-provided approval flag, arbitrary source
URL or download fallback. An approved entry must bind the source APK version/hash,
wrapper wheel/version, guest and tested host architectures, exact bundle/member
hashes, review ID/date/evidence and native-use/redistribution review result.

The committed entry records the technical pins above but remains `pending`, with
no release host architecture approved and native rights unresolved. Current
Dragon worker initialization is recorded above; HA-host compatibility and a
release approval decision have not been established. Selection fails with
`artifact_review_required`. An owned-session private manifest cannot turn a raw
digest into execution approval. Tests inject clearly synthetic approved manifests;
no real release approval is asserted by those fixtures.

This policy is part of the reviewed app image, not an independently signed vendor
attestation or a sandbox against malicious code in the same process. A malicious
replacement app image can replace its policy too. Native worker isolation and
release supply-chain review remain separate controls.

## Python discovery candidate evidence

Reviewed clean checkout:
https://github.com/parawanderer/FindMy.py/tree/8ecfae6cb34b29caf0bd8176ee73155ca81415a8

- Root `LICENSE.md` declares MIT, attributed to FindMy.py Contributors (2023).
  Its SHA-256 is `51396fd82204e1d844bbff2019054d8c3712e53c3ed8485c9f19dd73990eb46e`.
  `pyproject.toml` includes this license file. The license history traces to initial
  commit `a47a3c45a526769bc44f2c575160ed562d03cc53`; no extra NOTICE/license files
  appear in the pinned repository tree.
- CloudKit implementation entered in commit
  `6b0fa3b9a7f1e250b9a5b5c2f16627831d77d72c`; Keychain recovery entered in
  `edd02f70d180064d520b6caab524b2e6d6e68f2c`. Commit metadata identifies the author
  and an AI coauthor. That records contribution history; it does not establish
  independent authorship or provenance of every line.
- The pinned `cloudkit.proto`/`cuttlefish.proto` headers claim authorship from a
  protocol specification rather than an existing implementation and cite
  https://github.com/parawanderer/OpenTagViewer/tree/main/docs/findmy-export .
  This is an upstream claim, not a clean-room certification by this app.
- Generated protobuf files identify protoc version 5.28.1. The candidate has
  write/join/delete capabilities beyond our recovery use. App-owned composition
  restricts its exposed operations; inclusion of those capabilities is still
  relevant to the code/isolation review.

The declared MIT terms and traceable commits are concrete positive evidence;
they do not resolve possible third-party derivation/specification obligations,
complete dependency notices, malicious-code analysis or the separate native
binary rights question. The candidate remains test-only and pinned. Retain its
notice if a reviewed release adopts it; do not describe a full provenance audit
or clean-room cryptographic rewrite as completed.
