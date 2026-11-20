# One-shot runtime capability probe

Install and start this diagnostic app once, then inspect its log. It exits after
printing one generic JSON result. `supported` means this app's effective container
profile allowed the production Landlock/seccomp restrictions and the synthetic
checks passed. `boundary_unavailable` means the required kernel/container controls
were unavailable. `unexpected_uid` means the process did not run as UID1000.
Other results are failures; do not weaken the runtime controls.

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

## Safe diagnostics in 0.1.1

The result now includes a fixed reason code and numeric diagnostics (no paths,
exception text, environment, hostname or credentials). `landlock_abi` is the
kernel's version-query result, `landlock_errno` records query failure, and
`boundary_errno` records the last restriction failure. Platform is a fixed
architecture label and UID is numeric.

Interpretation must consider container policy as well as kernel configuration:
ENOSYS (38) generally means unavailable/compiled out, EOPNOTSUPP (95) indicates
Landlock disabled at boot, and EPERM (1) can indicate a syscall or policy denial.
These are diagnostic clues, not permission to weaken protection or change the OS.
The [kernel documentation](https://www.kernel.org/doc/html/v6.12/userspace-api/landlock.html)
explains build/boot requirements. The
[HAOS 17.1 kernel fragment](https://github.com/home-assistant/operating-system/blob/17.1/buildroot-external/kernel/v6.12.y/hassos.config)
selects AppArmor in CONFIG_LSM; an app-specific AppArmor allow rule cannot enable a
kernel security module that is absent or disabled at boot.
