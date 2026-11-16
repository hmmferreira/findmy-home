# Side-by-side installation and release gates

The live Dragon bridge and dashboard remain the baseline. This repository has no
deployment hook. Nothing is pushed to the homelab main branch.

## Local Supervisor trial (not yet completed)
Copy findmy_home to the local-app mount (/local_apps/findmy_home or /addons/findmy_home) on the HA host; reload the app store,
build and install it. Copy custom_components/findmy_home to the matching directory
under /config/custom_components, then restart Core. Use supported file/SSH access;
do not edit .storage. Open the app in ingress, complete setup, choose a small test
set, and confirm the discovered integration. Both installations have separate
sessions and IDs. Never copy credentials through Git, chat, options or logs.

Installing a custom integration executes code with Core permissions. Review the
artifact before installation/restart. The prototype has not passed this live trial.

## Comparison
Verify discovery, factor choice, recovery consent/passcodes, item rediscovery,
disabled items and stable IDs. Privately compare Apple timestamps, accuracy and
locations with the baseline. Test two successful polls, expiry -> Repairs -> login,
app/Core restarts, network loss/backoff, and Recorder history. Check phone and
desktop layouts. A missing report must keep its timestamp, not appear fresh.
Beta trackers must remain separate from existing MQTT entities/person bindings.

Rollback: stop/disable the beta app and integration. Keep private state until the
user chooses deletion. Review and back up before removing integration entities.

## Community release gates
No public repository or release exists. FindMy.py is MIT licensed. The pinned
findmy-export checkout has no obvious LICENSE or Cargo license field: resolve
redistribution rights before publishing its binary or sources. Review rustpush,
Apple-private API dependencies and anisette independently. Preserve required
notices and publish corresponding source where required. Apple compatibility is
unofficial and no endorsement is implied. Complete live testing, hassfest/native
integration checks, browser tests, AppArmor, SBOM, locks and signing first.
