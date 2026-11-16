# 0.1.2 — Concurrent incremental item queries

- Save and display each item result immediately.
- Hard-limit each item query to 120 seconds, including synchronous key derivation.
- Continue after a timed-out item and expose per-item progress counts.
- Keep old sightings intact and never pass Apple credentials on child argv.
- Two asynchronous workers, shared request pacing, and no shared-session writes.
- Stop queued work on authentication-required or rate-limit responses.
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
