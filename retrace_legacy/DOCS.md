# Retrace

Open Web UI to set up the polling account, discover accessory keys and select
items. Newly discovered items are unselected. The integration is offered under
Settings → Devices & services when the companion custom integration is installed.

Recovery uses a separate Apple session. Explicitly consent before adding this
installation to the iCloud Keychain trust circle. Enter credentials only in the
app UI. The chosen trusted device's unlock passcode is not an Apple password or
an SMS code. No raw password/passcode is saved.

Overview shows the last reported positions, not live GPS. Original timestamps and
accuracy remain visible. Battery and street address data are not available from
this source. Core's native zones and Recorder supply integration history.
Polls run every 15 minutes, with backoff on failure; no laptop is needed.

Development installations are named Edge. This remains experimental. Keep the
working baseline while testing. Protect your HA account and encrypted backups.

## Identifying similar items

The chooser and item cards show a secondary line with the original Apple name
when it differs, a friendly model where known, the exported pairing date and a
short app-generated ID. Unknown models retain their model code. These details
are filled from saved private files during an upgrade; no Apple login is needed.
Hardware serials and key material are not exposed. Missing fields are omitted.
