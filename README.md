# Apple TV mainland metadata and official artwork

The active catalog uses metadataPolicy mainland-v1. Apple US supplies the official inventory, English identity and artwork. Chinese presentation metadata comes only from the reviewed mainland catalog and independently verified mainland title sources. The collector does not request regional Apple storefronts and does not fall back to them.

Chinese name verification uses Douban, Baidu Baike and Bangumi identity records. Wikipedia is accepted only when the same original title/year/type exposes an explicit mainland-name field; its article heading is never used as a mainland alias. Regional Apple search results and metadata endpoints are rejected before requests or verification. Unknown mainland names stay pending and keep the English original title.

The title workflow supports numbered YDC, Tavily and Gemini account pools in Actions Secrets, including legacy key names. Explicit balance/quota errors switch to the next configured account and search provider. Empty results do not rotate accounts; rate, authentication and transport failures are recorded separately. The request budget remains bounded (200 paid search reservations per month, at most five works per title run). Search/model suggestions never approve a title without independent identity checks.

The reviewed mainland baseline is data/mainland-catalog.json. Verified corrections and evidence remain in data/title-cache.json and data/title-reviews/. Collection reapplies only mainland-policy records. An available playback source does not automatically prove an unverified display name.

Inventory, name verification and released-work source checks run every three calendar days anchored at 2026-11-01, staggered at 08:37, 11:47 and 14:17 Asia/Shanghai. Daily scheduler wakeups perform only the date gate on intervening days. Manual runs remain available. Source runs examine 12 due works by default, maximum 24; failed and missing records rotate automatically. Push publication validates existing data without paid synopsis/hero translation. See docs/automatic-verification.md. Unverified regional data is rejected by catalog validation, the Android native cache and JavaScript merge boundaries. Migrated application caches remove old presentation metadata while keeping image files, playback bindings, favorites and progress.

Season discovery reads the real season list from each Apple US show page and verifies every season ID, parent show ID, release date and artwork through the website's season metadata. Anonymous website session parameters are used only in memory and never saved or published. If a season API omits artwork, the official PR image is accepted only when its season number and release year match. The public catalog includes all validated season images, not just the latest show poster. Mainland Chinese summaries are reused only for the matching season and year; missing summaries stay pending.

data/season-cache.json retains the last complete season set. Newest-season metadata is checked daily; older-season metadata and unchanged image bytes are reused for up to seven days. Every run still discovers the actual season list. Failures preserve accepted data and appear in docs/season-sync-report.json for retry on the next run. An officially announced future season can appear without a playback ID. artworkSeasonNumber records the season depicted by the PR poster, which can be earlier than the latest announced seasonNumber. Android keeps those roles separate when labeling cards and opening details. The app checks the published version on launch after its six-hour cache interval, or immediately from its update button.

The docs directory contains real content-addressed images and immutable active releases. Images and catalog are written before version.json. Android verifies hashes and decodes every changed image before activating a snapshot. Invalid updates keep the last accepted mainland snapshot or bundled mainland metadata. No playback IDs, source configuration, session data, signing keys or search keys are published.

Detail presentation uses atomic `zh.detailMetadata` / `zh.detailSeasons` packets. One independently verified Douban subject response supplies the Chinese title, synopsis and score together. Rating counts are neither published nor required for a score; absent scores are `NO_RATING`, not a CMS score. Movie packets use season 0, TV packets require an exact season. An unnumbered TV subject is accepted only for season 1. One subject cannot be relabeled for multiple seasons. Cached packets are published with the catalog and home snapshot; the App never fetches these fields separately when opening a work. Existing Chinese names with missing packets stay in the bounded metadata queue, and missing synopses are retried. Current names selected by verified source counts retain their display priority; a packet keeps its original Douban title and subject as evidence.

Official homepage hero copy continues through the existing Gemini `home_copy.py` pipeline. Its text and the legacy shared official synopsis cache are independent of the Douban detail packets, so a later official translation cannot overwrite the detail synopsis or score. See `docs/metadata-pipeline.md` for the packet contract and actual coverage.

Commands:

Display-name selection runs in GitHub, never in the Android playback page. The name workflow compares all bounded public CMS checks, counts each distinct library address once per confirmed title, and prefers the verified current name on equal counts. Multiple records or play lines in one library cannot inflate its vote. Only a matching independently verified subject ID, or matching director and at least two main cast names together with title/year/type/season checks, can supply a vote. Web/share lines and extras are excluded. Animation follows this same server-side selection policy; the Douban name remains an alias and identity reference. Future releases still receive names only, with no source probing before release.

`nameSelection` publishes title/count totals and incomplete-coverage status without provider IDs, URLs or playback credentials. Source recall is separate: an already verified alias can retrieve direct-media entries by exact normalized name, year, season and compatible type, without mandatory cast fields. Known subject conflicts still reject a record. This weaker recall cannot rename a work, invent title evidence or supply name-selection votes; year-suffix normalization still needs strong identity evidence. A source check reports API-level media entries, never player decoder acceptance. A partial check does not claim global coverage and is retried after a shorter interval. The registry matches all 33 App libraries: 29 CMS libraries plus shared library, Ikanbot, shenhua and bblue dedicated adapters. The latter two use separate Juzi line selectors, never fake CMS URLs. Shared sessions and Juzi protocol configuration come only from optional encrypted Actions Secrets `APPLETV_SHARED_SESSION_JSON` / `APPLETV_JUZI_PROTOCOL_JSON`. Missing configuration, limited access, transport failures and unresolved identity stay pending; they never prove absence. Changed source scope invalidates old negative checks. Queue attempts rotate, have a one-hour incomplete retry interval, use four provider workers, at most 20 seconds per provider and 90 seconds per work. Released works have priority in the independent title queue. No App startup bulk probing is added. See `docs/source-coverage.md` for validation boundaries.

- python -m unittest discover -s tests -v
- python scripts/catalog.py --validate
- python scripts/catalog.py --force
- python scripts/title_lookup.py --force

Undersized horizontal library artwork is handled separately by
`scripts/list_artwork.py`. Its default command is an offline plan; explicit
`--apply` requests a bounded cloud upgrade to 640×360 while preserving 628px and
larger originals. Cached tier bytes are reapplied during publication, with
failure retaining the existing image. The scheduled sync processes at most 12
due works with 3 workers. See `docs/cloud-list-artwork-policy.md` for source,
season, size, cache and rollback rules. This does not change portrait or hero
specifications or the Gemini/Douban metadata pipelines.

Dependencies: requests, Pillow, opencc-python-reimplemented, cryptography.
