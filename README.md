# Apple TV public catalog and image files

`docs/` contains the actual content-addressed image files, Chinese presentation metadata, and immutable catalog releases. GitHub Pages is the public download endpoint. No playback IDs, routes, sessions, application code or private keys are published.

The Android app checks the manifest every six hours, downloads changed files, verifies SHA-256 and image decoding, and switches only after the complete version is ready. It keeps the previous valid version on errors.

The scheduled workflow checks daily and collects from Apple when seven days have elapsed since the previous successful collection. Manual `sync` forces collection; `publish` validates and deploys the existing snapshot. A failed collection never replaces the active catalog. A manifest marked `bundled-reviewed-snapshot` is the initial reviewed app snapshot, not a fresh network collection. Chinese storefront fetches can fail; retained Chinese data is preserved and pending items are explicitly marked.

The separate Chinese title workflow reuses verified names and resolves missing or unconfirmed names using public source APIs first (including TV/WEB animation identity), then Tavily search. It supports `TAVILY_API_KEY_1`, `TAVILY_API_KEY_2`, and the legacy `TAVILY_API_KEY` in Actions Secrets. Keys share one monthly program budget (default 100 request reservations, at most 12 unresolved works per run, maximum 20). Authentication or transport failure may use a backup key; rate limits stop requests instead of switching keys to bypass the limit. Search results only locate sources: matching original title, year and medium must be verified before a name is published. Evidence, pending states and reservations are saved in `data/title-cache.json`; verified titles are never searched again for the same identity. The title workflow checks daily with a seven-day timer; manual runs may force a check but retain budgets and retry cooldowns. Full catalog collection reapplies the verified cache.

The Android app downloads calibrated names/aliases with the catalog, then searches its own existing playback sources. Source availability is separate from finding a Chinese title; matching also checks year/type, cast and season. No playback credentials, source IDs, or search keys are published here.

`python scripts/catalog.py --validate` verifies every referenced image and catalog hash. `python scripts/catalog.py --force` performs a real collection.

GitHub Actions dependencies: requests, Pillow, opencc-python-reimplemented.

A matched playback source does not by itself verify a regional display title. The title workflow only retains that shortcut when the display title matches a known Chinese source alias; other regional names remain eligible for calibration. Source-reviewed title evidence is retained under data/title-reviews/ and reapplied from the verified identity cache during collection.
