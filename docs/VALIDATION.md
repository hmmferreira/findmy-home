# Local validation — 2026-11-16

- 25 automated tests passed in an isolated, network-disabled container with no
  live runtime mounts: ingress/CSRF/read-only API, secrets, recovery ownership and
  full synthetic prompt journey, import normalization, polling/timestamps/expiry,
  and installer dry-run/integrity/no-overwrite.
- Built the complete amd64 app image on Dragon. Upstream patched Rust tests passed:
  endpoint lookup tests and session/identity/private escrow-password tests.
- Empty-state packaged startup check passed with uid 1000, read-only root,
  no added capabilities, no host ports, no-new-privileges and tmpfs data.
  Authenticated snapshot worked; direct management UI access was denied.
  Local helper returned HTTP 200; exporter help showed the cached-session flags.
- Python sources and integration JSON parsed. Supervisor YAML parsed with no
  published host port. Native integration/hassfest and browser rendering tests
  have not yet run. These focused tests do not prove end-to-end HA compatibility.
- No live Apple authentication was attempted in the new app. No original sessions,
  keys or item data were copied into it. The baseline bridge remains unchanged.
