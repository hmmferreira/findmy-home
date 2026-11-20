# Initial Apple sign-in refusal

## Observed boundary — 2026-11-20

Retrace's typed diagnostics recorded `apple_step=init`, `apple_code=-22410`.
At this stage the pinned SDK has sent the username, initial SRP value and client
metadata; it has not calculated/submitted the password proof. This is not evidence
of a wrong password. The code alone does not establish an account ban, a temporary
rate limit, a specific identity defect, or a universal recovery procedure.

A separate Linux collector reported the same initial error before 2FA on
2026-11-19/20: https://github.com/parawanderer/OpenTagViewer/issues/288 . That
report also describes an affected account completing Apple's web sign-in. These
are observations from that reporter, not a diagnosis of this household account.

Upstream main was inspected at 37d5ca0; changes after our pinned 8ecfae6 concern
hsc=409 second-factor detection after the SRP exchange. They are not an established
fix for this initial refusal, so the runtime pin has not been changed.

## Offline identity consistency check

Startup checks an existing signing identity without provisioning or signing in.
The restricted native worker compares its saved device ID, local-user ID and
client-info string against the saved account metadata. Only three booleans and a
fixed status/error label are logged as `Retrace identity check`. No IDs, serials,
OTP headers, tokens, passwords or native-state bytes enter diagnostics. No header
is generated, no account/client network request is made, and no saved files are
replaced. A missing identity is reported as not_saved and never created by this
check. Cancellation closes/reaps the worker.

`consistent` rules out those three mismatches; it does not prove Apple's acceptance
of the machine/client or establish why -22410 was returned. `mismatch` is diagnostic,
not permission to silently change/reprovision the identity. Preserve saved state
and investigate before any explicit recovery action.

Do not repeatedly replay sign-in, reset the account password based on this code,
substitute somebody else's hardware identifiers, or add an unreviewed remote
signing provider. Direct sign-in on Apple's own website is a separate human check
for account-level problems. It must not put credentials or verification codes in
chat, logs, fixtures or Git. No upstream maintainer message has been sent.

## Verified household check

Edge0.1.14-dev.1.5 completed the offline check on Home Assistant: device ID,
local-user ID and client-info comparisons all returned true (`consistent`).
This eliminates those saved-native-vs-account mismatches as an explanation for
this installation's observed refusal. It does not establish the server's reason
or validate the account through Apple's web flow; that human check is pending.
Private signing identity and account session were retained without another login.
Validation: 280 app regressions, 877 upstream cases, 17 controller cases and
15 discovery cases passed, along with the isolated worker/report-child smoke.
