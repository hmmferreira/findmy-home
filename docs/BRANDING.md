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

The repository remains https://github.com/hmmferreira/findmy-home and installed
channel URLs stay unchanged. Changing that URL changes Supervisor's repository
identity and can strand the existing app/update path. A future repository/package
rename needs a separate migration plan; product branding does not require it.
Source package directories and Python modules keep their established names for
compatibility. Contributor instructions apply to Retrace under these paths.

The app update changes app/store/sidebar/web branding. Companion manifest,
translations and default entry-title changes require updating the custom
integration separately through its normal installation path and activating that
version in Home Assistant. An app update alone does not replace Core's files.
