# One-shot runtime capability probe

Install and start this diagnostic app once, then inspect its log. It exits after
printing one generic JSON result. `supported` means this app's effective container
profile allowed the production Landlock/seccomp restrictions and the synthetic
checks passed. `boundary_unavailable` means the required kernel/container controls
were unavailable. Other results are failures; do not weaken the runtime controls.

The app requests no Supervisor/Home Assistant/Docker API, ingress, network ports,
capabilities, privileged mode or host/config/data mounts. It runs as UID1000 and
creates only temporary synthetic files inside its own `/tmp`.

The restricted child uses the exact production `native_sandbox.py`. It attempts
private synthetic file access, a synthetic write, a parent `/proc` file open
(without reading its contents), metadata changes, socket creation without any
connection or address lookup, harmless `/bin/true`, signal-zero permission check,
and a dumpability change. No Apple request, account, credential, session export,
native artifact or device is used. No host secrets are read or logged.

This verifies a diagnostic container's effective profile, not successful Apple
login or native provisioning. It does not alter or restart an installed Edge app.
Remove the diagnostic app after checking its result. Never enable extra privileges
or disable its restrictions to turn a failing result into a passing one.
