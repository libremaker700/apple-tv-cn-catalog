# Apple TV mainland metadata and official artwork

The active catalog uses metadataPolicy mainland-v1. Apple US supplies the official inventory, English identity and artwork. Chinese presentation metadata comes only from the reviewed mainland catalog and independently verified mainland title sources. The collector does not request regional Apple storefronts and does not fall back to them.

Chinese name verification uses Douban, Baidu Baike and Bangumi identity records. Wikipedia is accepted only when the same original title/year/type exposes an explicit mainland-name field; its article heading is never used as a mainland alias. Regional Apple search results and metadata endpoints are rejected before requests or verification. Unknown mainland names stay pending and keep the English original title.

The title workflow supports TAVILY_API_KEY_1, TAVILY_API_KEY_2 and the legacy TAVILY_API_KEY in GitHub Actions Secrets. The existing shared monthly budget (default 100 reservations) and per-run limit (default 12, maximum 20) remain in force. Rate limits stop the run; a second key is not used to bypass limits. Search results locate identity sources, and snippets alone never approve a title.

The reviewed mainland baseline is data/mainland-catalog.json. Verified corrections and evidence remain in data/title-cache.json and data/title-reviews/. Collection reapplies only mainland-policy records. An available playback source does not automatically prove an unverified display name.

The scheduled inventory workflow checks daily and collects after seven days; manual sync forces collection. The separate name workflow also checks daily with its existing timer. Unverified regional data is rejected by catalog validation, the Android native cache and JavaScript merge boundaries. Migrated application caches remove old presentation metadata while keeping image files, playback bindings, favorites and progress.

The docs directory contains real content-addressed images and immutable active releases. Images and catalog are written before version.json. Android verifies hashes and decodes every changed image before activating a snapshot. Invalid updates keep the last accepted mainland snapshot or bundled mainland metadata. No playback IDs, source configuration, session data, signing keys or search keys are published.

Commands:

- python -m unittest discover -s tests -v
- python scripts/catalog.py --validate
- python scripts/catalog.py --force
- python scripts/title_lookup.py --force

Dependencies: requests, Pillow, opencc-python-reimplemented.