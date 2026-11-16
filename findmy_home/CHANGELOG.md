# 0.1.7 — Bounded item searches with private checkpoints

- Check recent keys first, then at most one older key window per item refresh.
- Resume successful empty searches on later polls instead of repeatedly scanning
  from the beginning until timeout. Preserve checkpoints across restarts.
- Show incomplete searches explicitly; keep saved sightings and existing Apple
  pacing, global rate-limit pauses, worker limits and hard timeouts.

# 0.1.6 — Administrator access enforced in the app

- Require the exact administrator group from trusted Supervisor ingress, as
  well as the trusted peer and user identity; reject missing group headers.
- Preserve CSRF protection and the separate read-only integration API.
- Requires Supervisor 2026.11.0 or newer for forwarded group information.

# 0.1.5 — Diagnose slow item lookups

- Persist allowlisted query phase, elapsed time and aggregate counts.
- Surface timeout diagnostics without names, identifiers, keys or locations.
- Keep asynchronous queries, limits and credentials unchanged.

# 0.1.4 — Descriptive item labels and consistent Edge naming

- Add secondary labels with Apple-provided name, known model name, pairing date
  and a short app ID; omit unavailable information.
- Backfill existing items from saved files without a login or key rewrite.
- Give same-name exports unique hashed filenames instead of overwriting them.
- Use Edge consistently for development labels, including legacy integration
  titles; retain existing entity IDs, unique IDs and user title overrides.
- Remove the obsolete hardcoded diagnostics version.

# 0.1.3 — Setup, feedback, Edge names and manual refresh

- Explain separate location-access and item-key discovery sessions.
- Reuse the saved discovery session; fresh login is an explicit choice.
- Submit discovery email and password together through private stdin handling.
- Preserve typed recovery responses while refreshing background status.
- Confirm the exact number of saved tracked items; retain edits after errors.
- Add per-item asynchronous refresh with one-minute spacing, shared worker
  limits, duplicate suppression and the shared Apple rate-limit pause.
- Show per-item refresh progress and check time separately from sighting time.
- Publish channel metadata; new Edge entities have explicit Edge names/IDs.
  Existing stable unique IDs and existing registry IDs are retained.
- Make the app map an optional preview; link native HA devices and map views.
- Add locked DOM regression tests; these are not bundled in the runtime app.

# 0.1.2 — Concurrent incremental item queries

- Save and display each item result immediately.
- Hard-limit each item query to 120 seconds, including synchronous key derivation.
- Continue after a timed-out item and expose per-item progress counts.
- Keep old sightings intact and never pass Apple credentials on child argv.
- Two asynchronous workers, shared request pacing, and no shared-session writes.
- Stop queued work on authentication-required or rate-limit responses.
- Share a 30-minute HTTP 429 cooldown across both workers.
- Prepare Edge/stable repository delivery instead of repeated archive installs.

# 0.1.1 — Polling visibility

- Distinguish no location reports from successful tracking.
- Surface report counts and last/next poll times without secrets.
- Treat repeated empty Apple responses as a protocol failure, not no sightings.
- Wake polling after account connection/selection; preserve query cooldown.
- Emit only allowlisted count/status diagnostics in the app log.

# 0.1.0 — Local experimental prototype

- Guided ingress account verification and separate key-recovery flow.
- Selected-item polling, local helper and owner-only token/key storage.
- Native companion integration, Beta trackers, last sightings and Repairs.
- Map overview and item selection; no battery/address fabrication.
