# Retrace naming and compatibility

Retrace is the product name. The currently implemented tracking source is Apple
Find My; other ecosystems are a future direction, not an implemented feature.
Apple Find My, FindMy.py and their upstream authors retain their actual names,
licenses and attribution. This project is independent and is not endorsed by Apple.

## Source and installation names

The canonical repository is https://github.com/hmmferreira/retrace. App source is
`retrace/`, its Python package is `retrace/rootfs/app/retrace/`, and the synthetic
capability probe is `retrace_runtime_probe/`. Shared delivery uses the
`retrace_shared/` folder. Build/test workflows and import paths use these names.
The native isolation child profile is `retrace-native`; its restrictions remain
unchanged. The container account is retrace, retaining numeric UID/GID 1000.

## Compatibility anchors

Existing installations keep the app slugs `findmy_home`, `findmy_home_shared` and
`findmy_runtime_probe`, HA integration domain/folder `custom_components/findmy_home`,
discovery service `findmy_home`, private `/data/findmy_home` and optional
`FINDMY_HOME_DATA` setting. Entity/device/instance identifiers and cryptographic
format markers remain unchanged. These are deliberate upgrade compatibility
anchors, not stale product branding. Do not text-replace them or uninstall/re-add
an integration to change its name: doing so can lose session access and detach
Recorder history. User-selected integration titles remain preserved. The companion
update changes known default entry titles to Retrace when activated in Core.

The installed HA repository can retain its original `findmy-home#edge` registration
because GitHub redirects Git fetch/clone operations. This preserves Supervisor's
repository prefix, installed app identity and data. Do not remove/re-add it or
create a new GitHub repository at the old name, which disables that redirect.
New install links use `retrace#edge`; their Supervisor prefix differs. Never
hardcode either prefix. Verify store refresh and app update after the rename.
Local Git remotes use `git@github.com:hmmferreira/retrace.git`.

An app update does not replace custom integration files in Core. The companion
update remains a separate Marketplace action and its activation requires Core
restart. Shared stable promotion remains blocked by the documented release gates.
