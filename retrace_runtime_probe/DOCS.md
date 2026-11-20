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

## AppArmor alternative and staged failures

Version 0.1.2 adds a custom, enforced nested AppArmor profile for HAOS hosts whose
kernel does not provide Landlock. The child permanently changes from its app's
profile to `retrace-native`, verifies the exact enforced destination, then applies
the same no-new-privileges, resource limits and syscall filter. The child profile
allows public interpreter/library/code reads and private control-pipe traffic;
it grants no private data access, networking, executable launches or transition
back. No host policy is loaded by the app itself; Supervisor loads the app-owned
profile as part of its normal installation. Protection mode remains enabled and
no extra capabilities or host changes are requested.

Version 0.1.3 distinguishes failure stages in the trusted diagnostic parent using
fixed labels, whitelisted exception classes and numeric errno/exit values only.
This helps identify a missing parent runtime permission without printing paths,
exception messages, command arguments, environment values or process contents.
A supported result names the active boundary in `diagnostics.boundary`.

Primary implementation references:

- [Supervisor profile renaming](https://github.com/home-assistant/supervisor/blob/2026.11.0/supervisor/utils/apparmor.py)
- [OS Agent permits app-owned child profiles](https://github.com/home-assistant/os-agent/blob/main/apparmor/apparmor.go)
- [AppArmor permanent profile transition API](https://manpages.ubuntu.com/manpages/jammy/man2/aa_change_profile.2.html)

Actual HAOS verification on 2026-11-20: version0.1.4 reported `supported`, using
`apparmor-seccomp-v1`, UID1000 and all ten checks true, with protection enabled.
The host's Landlock version query returned ENOSYS38. Version0.1.4 gives only the
trusted synthetic parent normal Docker-equivalent file permissions, which fixes
interpreter/subprocess startup. Its nested restricted child remains unchanged
and identical to the shared-runtime child policy. This is a kernel/container
capability result, not a live Apple/native provisioning test.
