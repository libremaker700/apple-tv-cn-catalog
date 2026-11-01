# Apple TV mainland metadata and official artwork

The active catalog uses metadataPolicy mainland-v1. Apple US supplies the official inventory, English identity and artwork. Chinese presentation metadata comes only from the reviewed mainland catalog and independently verified mainland title sources. The collector does not request regional Apple storefronts and does not fall back to them.

Chinese name verification uses Douban, Baidu Baike and Bangumi identity records. Wikipedia is accepted only when the same original title/year/type exposes an explicit mainland-name field; its article heading is never used as a mainland alias. Regional Apple search results and metadata endpoints are rejected before requests or verification. Unknown mainland names stay pending and keep the English original title.

The title workflow supports TAVILY_API_KEY_1, TAVILY_API_KEY_2 and the legacy TAVILY_API_KEY in GitHub Actions Secrets. The existing shared monthly budget (default 100 reservations) and per-run limit (default 12, maximum 20) remain in force. Rate limits stop the run; a second key is not used to bypass limits. Search results locate identity sources, and snippets alone never approve a title.

The reviewed mainland baseline is data/mainland-catalog.json. Verified corrections and evidence remain in data/title-cache.json and data/title-reviews/. Collection reapplies only mainland-policy records. An available playback source does not automatically prove an unverified display name.

The scheduled inventory workflow collects daily (20-hour guard tolerates scheduler jitter); manual sync forces collection. The separate name workflow also checks daily with its existing timer. Unverified regional data is rejected by catalog validation, the Android native cache and JavaScript merge boundaries. Migrated application caches remove old presentation metadata while keeping image files, playback bindings, favorites and progress.

Season discovery reads the real season list from each Apple US show page and verifies every season ID, parent show ID, release date and artwork through the website's season metadata. Anonymous website session parameters are used only in memory and never saved or published. If a season API omits artwork, the official PR image is accepted only when its season number and release year match. The public catalog includes all validated season images, not just the latest show poster. Mainland Chinese summaries are reused only for the matching season and year; missing summaries stay pending.

data/season-cache.json retains the last complete season set. Newest-season metadata is checked daily; older-season metadata and unchanged image bytes are reused for up to seven days. Every run still discovers the actual season list. Failures preserve accepted data and appear in docs/season-sync-report.json for retry on the next run. An officially announced future season can appear without a playback ID. artworkSeasonNumber records the season depicted by the PR poster, which can be earlier than the latest announced seasonNumber. Android keeps those roles separate when labeling cards and opening details. The app checks the published version on launch after its six-hour cache interval, or immediately from its update button.

The docs directory contains real content-addressed images and immutable active releases. Images and catalog are written before version.json. Android verifies hashes and decodes every changed image before activating a snapshot. Invalid updates keep the last accepted mainland snapshot or bundled mainland metadata. No playback IDs, source configuration, session data, signing keys or search keys are published.

Commands:

Display-name selection runs in GitHub, never in the Android playback page. The name workflow compares all bounded public CMS checks, counts each distinct library address once per confirmed title, and prefers the verified current name on equal counts. Multiple records or play lines in one library cannot inflate its vote. Only a matching independently verified subject ID, or matching director and at least two main cast names together with title/year/type/season checks, can supply a vote. Web/share lines and extras are excluded. Animation follows this same server-side selection policy; the Douban name remains an alias and identity reference. Future releases still receive names only, with no source probing before release.

`nameSelection` publishes title/count totals and incomplete-coverage status without provider IDs, URLs or playback credentials. A partial check does not claim global coverage and is retried after a shorter interval. The counts mean identity-checked API records with direct-media entries, not player decoder acceptance. The public registry contains the 29 standard CMS libraries; private shared-library sessions and the three dedicated protocol adapters are not treated as CMS endpoints. Collection retains the existing per-run limits, bounds the provider workers and each work's time budget, and preserves the last usable metadata on network failure.

- python -m unittest discover -s tests -v
- python scripts/catalog.py --validate
- python scripts/catalog.py --force
- python scripts/title_lookup.py --force

Dependencies: requests, Pillow, opencc-python-reimplemented.
