# Release readiness and stable operation

Current assessment after the owner macOS provider test, 2026-11-21. Historical
reviews describe earlier stages; use this checklist with MAC_SIGNER_REVIEW.md.
There is no approved shared-runtime stable release yet. The workflow and renderer
intentionally reject that promotion until these gates are satisfied.

## Verified for the current Edge candidate

- Edge0.1.14-dev.1.6 runs protected on Home Assistant OS with the native worker
  restricted by AppArmor/seccomp; the original provider/identity remains intact.
- Owner macOS login, trusted-device verification, encrypted session save and
  discovery handoff completed. Apple Music still returns init/-22410.
- Latest observed poll completed12 selected items with0 failures and7 reports;
  8 items have saved locations, including earlier sightings. This does not prove
  continuous location availability or all-device sightings.
- 300 app regressions,877 pinned SDK cases,17 controller cases and16 discovery/Mac
  adapter cases passed. Real anonymous provisioning and three cold native signing
  and machine-restoration cycles passed in disposable containers.
- Shared image build, worker isolation and report-child smoke passed. Apple
  binaries and private state stay outside Git and published image contexts.

## Remaining gates for the first release

1. **Operational recovery on the installed app.** Observe unattended macOS polling,
   deliberately restart the app and verify session reuse without login, verify
   selected items and history remain intact, and finish expiry/reauthentication,
   network interruption/backoff and recovery checks. Synthetic encryption/native
   restoration is not proof of target-host Supervisor backup/restore. Sensitive
   interactions remain in protected ingress. Keep the existing working installation
   available throughout validation; do not delete it to prepare a release.
2. **Security, provenance and licensing closure for the actual shared runtime.**
   Finish the credential-path/transitive review and notices/source inventory for
   FindMy.py, the GPL Mac engine/emulator and the Apple native component. Current
   Apple component use is explicit private evaluation; separate local download
   is not an established public-release clearance. The absent Rust exporter does
   not block this runtime; it remains relevant only to legacy packaging. Fix any
   material findings and document the precise supported scope and remaining risks.
   Bound/clean retained encrypted machine generations safely and finish release
   supply-chain metadata/advisory checks. No independent-security-audit claim.
3. **Immutable stable delivery.** Package the shared runtime explicitly, choose a
   versioned released macOS provider default after validation, and add the reviewed
   stable workflow/renderer path with app/integration compatibility tests. Publish
   a matching companion integration release and immutable source/version metadata.
   Keep stable updates deliberate and Edge independent. Do not enable private
   evaluation by default or remove the current stable gate to bypass item2.
4. **Safe everyday/Edge coexistence and transition.** Stable and Edge repository
   URLs produce separate app/data/instance IDs. Validate separate entities and
   histories, one-time protected setup, a rollback procedure and the transition
   from Edge without losing existing history. Cross-volume secret migration is
   not implemented. A fresh stable installation has different entity identities;
   old Recorder history is not automatically reassigned. Prefer keeping the old
   entities/history intact until an explicit migration plan is verified.

## Companion integration boundary

Both app instances currently use one `custom_components/retrace` package in Core.
Separate app volumes do not isolate integration code versions. For everyday use,
pin that package to a compatible released version and test Edge app API changes
against it. Testing incompatible Edge integration code needs a separate HA test
instance or a separately designed domain; installing prerelease integration code
in the same Core can affect stable app entities too.

## Release acceptance and limitations

A first0.x release may disclose sparse reports, missing battery/street address,
Recorder retention behavior, amd64-only support and unofficial Apple compatibility.
It must not claim unresolved native-use rights or unperformed recovery checks are
cleared. A successful login is necessary evidence, not a complete release audit.

App installation/update remains through the repository UI. Public prebuilt images
remain gated by their component/distribution review. See CHANNELS.md for channel
mechanics and MAC_SIGNER_REVIEW.md for source/build/live evidence. No new household
restart, authentication, backup or migration was performed for this assessment.
