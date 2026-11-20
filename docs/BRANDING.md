# Retrace naming and compatibility

Retrace is the project and product name, replacing Find My Home. Its purpose is
location history and latest reported locations for belongings in Home Assistant.
The currently implemented source is **Apple Find My**. Other ecosystems are a
future direction, not an advertised working feature. Use compatibility wording
rather than suggesting Apple certification, endorsement or partnership.

User-facing names: Retrace (stable), Retrace Edge (development), and Retrace
Shared Edge (the separate shared-auth evaluation app). Experimental status and
release gates are unchanged by the rename. Upstream copyright/license notices
remain intact; do not rename FindMy.py, Apple services or upstream authors.

## Preserve existing installations

This is an in-place branding update, not an identity or storage migration.
Keep existing app slugs `findmy_home`/`findmy_home_shared`, integration domain
`findmy_home`, discovery service, API schema, private storage paths, instance IDs,
device identifiers and entity unique IDs. Existing registry entity IDs remain
unchanged so dashboards, Recorder history and automations continue to work.
Do not uninstall/re-add an integration just to rename it. User-chosen entry names
are preserved; known default legacy entry titles adopt Retrace at integration
setup after the companion update. Existing entity names/IDs can retain the old
technical prefix intentionally.

The canonical repository is https://github.com/hmmferreira/retrace after the
owner completes the GitHub rename. Public install links use the new name.
Existing installations can keep their original `findmy-home#edge` registration:
GitHub redirects Git fetch/clone operations, and retaining that registration
preserves Supervisor's installed repository/app identity and private data.
Verify a store refresh and normal update after the rename. Do not remove/re-add
that repository or create a new GitHub repository named `findmy-home`, which
would remove the redirect. New installations use `retrace#edge` and therefore
have a different Supervisor repository prefix. Never hardcode that prefix.

Update local Git remotes to `git@github.com:hmmferreira/retrace.git` after
verifying the renamed repository. Existing source package directories and Python
modules keep their established names for compatibility. Contributor instructions
apply to Retrace under these paths.

The app update changes app/store/sidebar/web branding. Companion manifest,
translations and default entry-title changes require updating the custom
integration separately through its normal installation path and activating that
version in Home Assistant. An app update alone does not replace Core's files.
