# Side-by-side installation and release gates

The live Dragon bridge and dashboard remain the baseline. This repository has no
deployment hook. Nothing is pushed to the homelab main branch.

## Legacy local Supervisor trial
Copy findmy_home to the local-app mount (/local_apps/findmy_home or /addons/findmy_home) on the HA host; reload the app store,
build and install it. Copy custom_components/findmy_home to the matching directory
under /config/custom_components, then restart Core. Use supported file/SSH access;
do not edit .storage. Open the app in ingress, complete setup, choose a small test
set, and confirm the discovered integration. Both installations have separate
sessions and IDs. Never copy credentials through Git, chat, options or logs.

Installing a custom integration executes code with Core permissions. Review the
artifact before installation/restart. Repository Edge is now installed and has partial live validation; see below.

## Comparison
Verify discovery, factor choice, recovery consent/passcodes, item rediscovery,
disabled items and stable IDs. Privately compare Apple timestamps, accuracy and
locations with the baseline. Test two successful polls, expiry -> Repairs -> login,
app/Core restarts, network loss/backoff, and Recorder history. Check phone and
desktop layouts. A missing report must keep its timestamp, not appear fresh.
Edge trackers must remain separate from existing MQTT entities/person bindings.

Rollback: stop/disable the Edge app and integration. Keep private state until the
user chooses deletion. Review and back up before removing integration entities.

## Community release gates
Repository channel delivery is prepared; no stable release is approved. FindMy.py is MIT licensed. The pinned
findmy-export checkout has no obvious LICENSE or Cargo license field: resolve
redistribution rights before publishing its binary or sources. Review rustpush,
Apple-private API dependencies and anisette independently. Preserve required
notices and publish corresponding source where required. Apple compatibility is
unofficial and no endorsement is implied. Native tests against Home Assistant 2026.9.3 and hassfest now gate channel
publication. Python wheel locks are enforced. Live browser/restore checks,
AppArmor, SBOM, licensing and signing still remain. The evidence inventory is
[THIRD_PARTY_REVIEW.md](THIRD_PARTY_REVIEW.md).

## Repository channel delivery

See CHANNELS.md. Edge is automatically tested and published from main. Stable
requires explicit workflow promotion after the comparison checklist above.
For now builds happen in Supervisor on Install/Update; public prebuilt images
remain gated on dependency redistribution review. No manual package copying is
needed after the one-time repository app setup.

## Current live evidence — 2026-11-16

Two companion entries are loaded and Edge now receives real reports. Repeated
polls initially yielded reports for three of five selected items; two timed out.
The first bounded-search Edge poll completed all five without failures, with
three sightings and two continuing older-key searches. This is partial live
validation, not completion of the checklist. See
KNOWN_LIMITATIONS.md before deciding between an official preview and Stable.
The user asked what the limitations are; the release choice remains open.
No stable_verified assertion or Stable promotion has been made.
