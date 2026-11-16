# Release readiness and known limitations

Verified 2026-11-16 against the installed Edge app:

- Repeated polls of five selected items produce three reports; two item queries
  reach the 120-second limit. Their cause remains unresolved. Other items'
  completed reports are saved independently.
- Manual refresh retrieves Apple's stored report; it cannot make an AirTag
  broadcast or make nearby Apple devices relay a new sighting.
- Location polling and item discovery have separate initial authorizations.
  Valid sessions are reused; expiry needs sign-in and discovery may still need
  a trusted-device unlock passcode.
- Battery level and street address are unavailable. Recorder history starts
  with collected reports; historical backfill is not implemented.
- amd64 is the only supported app architecture. Supervisor builds from source.
  Public prebuilt container redistribution remains pending dependency licensing
  review, including the pinned exporter with no clear license declaration.
- Credential isolation, CSRF/read-only API and recovery ownership have automated
  tests. Independent security review, actual non-admin ingress authorization,
  full session-expiry recovery and backup/restore validation are incomplete.
- Edge, local and future Stable app installations have separate private data.
  Switching installation/channel currently needs one-time account setup.
  The companion integration uses one shared code package in Core; installing
  Edge integration code does not provide separate Core-code versions per app.
- Existing registry IDs are preserved during the Beta-to-Edge display-label
  migration. Renaming old entity IDs requires checking their consumers first.
  New entity IDs already contain their channel.
- Friendly model names cover a bounded catalog. Unknown models retain the raw
  model code. Pairing dates mean the exported pairing date, not purchase date.

Model facts are checked against DeviceKit's generated hardware catalog
(https://github.com/devicekit/DeviceKit/blob/master/Source/Device.generated.swift)
and Apple Support's MacBook Pro identification page
(https://support.apple.com/en-us/108052). No online model lookup is performed
during use, and hardware serials are not shown in descriptive labels.

A first official 0.x preview can disclose these limits. Production-Stable
promotion must not claim the outstanding validation has passed.
