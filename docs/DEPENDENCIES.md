# Python dependency updates

`findmy_home/requirements.txt` records direct dependency intent.
`findmy_home/requirements.lock` records the complete tested CPython 3.12 Linux
runtime set. Production Docker builds, the test image and GitHub CI install this
lock with `--require-hashes --only-binary=:all:` and run `pip check`.

The initial lock preserves the 30 installed versions of the tested 0.1.8 amd64
image, excluding pip itself. SHA-256 hashes were obtained from the corresponding
non-yanked PyPI wheel metadata and committed for subsequent install verification.
This follows [pip's secure-install guidance](https://pip.pypa.io/en/stable/topics/secure-installs/).
No running app credentials or private state were used to create it.

For an update, resolve the direct requirements in a clean CPython 3.12 Linux
sandbox, review transitive version changes and licensing/advisories, and record
exact versions plus permitted wheel hashes in the lock. Do not regenerate during
app startup or Docker builds. Build the image from the updated lock, run the
synthetic tests and startup smoke check, then deploy Edge and verify real polling.
Promote only after the remaining release checks pass. A missing wheel must fail
the build; do not silently fall back to an unreviewed source distribution.

The hashes detect artifact changes after this reviewed lock; they do not prove
that a package is safe or that PyPI was uncompromised when the hashes were
selected. Rust uses its pinned checkout and Cargo lock separately. Base images,
Debian packages, SBOM/provenance and public image signatures need separate work;
this Python lock does not make the complete container bit-for-bit reproducible.
