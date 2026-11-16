# Find My Home — experimental app + integration

A separate prototype for friendly Apple Find My item setup in Home Assistant.
The working Dragon MQTT bridge and Item Tracking dashboard are not modified.

## User journey
1. Open the app through Home Assistant ingress.
2. Connect the polling account and choose SMS or trusted-device 2FA.
3. Discover items through guided key recovery. Accept the Keychain trust
   explanation, authenticate, choose a trusted device, and enter its unlock passcode.
4. Select items with checkboxes. New items start disabled; rediscovery keeps choices.
5. Approve the discovered native integration. It creates separate Beta devices,
   GPS trackers and last-sighting sensors. HA zones and Recorder handle history.
6. Open Overview for the map. Add items later from Account & items.

Apple polling and key recovery use separate sessions. The wizard exposes
both; it does not promise one universal login. No Mac needs to stay running.

## Status and limits
This is development source, not a published or security-audited release.
Transport/recovery tests use synthetic credentials without Apple network access.
A real Supervisor ingress/discovery install and real-account UI journey must still
be tested before this can replace the working bridge. Only amd64 is targeted.
Battery status and street addresses are not available from this report source.
History follows the user's Recorder configuration; no retention period or backfill
is promised. Sparse sightings are not a continuous GPS track.

## Packaging
- findmy_home/: Supervisor app, ingress UI, local helper, patched exporter,
  selected-item polling, owner-only runtime state.
- custom_components/findmy_home/: native integration, config/reauth flows,
  coordinator, trackers, timestamps, Repairs and sanitized diagnostics.
- tests/: isolated transport, security, recovery and polling tests.
- docs/SECURITY.md: trust boundaries, storage and remaining review.
- docs/RELEASE.md: install/compare checklist and community-release gates.

Manifest URLs are the intended project location. No GitHub repository or public
release has been created. The source is kept in a separate local Git repo.

## Development
Build from the findmy_home directory using its Dockerfile. It compiles the pinned
exporter with the known protocol/session fixes and bundles the anisette helper
locally; no public anisette service is used. Leaflet 1.9.4 is vendored with license
and hashes; scripts do not load from a CDN. Maps fetch OpenStreetMap tiles.

The local Portainer helper runs python tools/docker-check.py test or build.
Set PORTAINER_DOCKER_API and PORTAINER_KEY_FILE for another environment.
It is developer tooling, not part of the app. Tests have no network or live
runtime mounts. Do not copy production sessions into test fixtures.
