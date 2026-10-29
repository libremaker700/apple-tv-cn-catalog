# Apple TV public catalog and image files

`docs/` contains the actual content-addressed image files, Chinese presentation metadata, and immutable catalog releases. GitHub Pages is the public download endpoint. No playback IDs, routes, sessions, application code or private keys are published.

The Android app checks the manifest every six hours, downloads changed files, verifies SHA-256 and image decoding, and switches only after the complete version is ready. It keeps the previous valid version on errors.

The scheduled workflow checks daily and collects from Apple when seven days have elapsed since the previous successful collection. Manual `sync` forces collection; `publish` validates and deploys the existing snapshot. A failed collection never replaces the active catalog. A manifest marked `bundled-reviewed-snapshot` is the initial reviewed app snapshot, not a fresh network collection. Chinese storefront fetches can fail; retained Chinese data is preserved and pending items are explicitly marked. No AI or Tavily integration is claimed.

`python scripts/catalog.py --validate` verifies every referenced image and catalog hash. `python scripts/catalog.py --force` performs a real collection.

GitHub Actions dependencies: requests, Pillow, opencc-python-reimplemented.
