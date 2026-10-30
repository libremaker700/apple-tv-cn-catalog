# Official homepage feed

`home_sync.py` reads the US Apple TV channel and the sci-fi room, using their structured shelf data. The five supported channel sections and five sci-fi sections keep the source page's relative order and each section's actual work order. Pagination controls are not works. This feed represents the returned sections, not an exhaustive inventory of the Apple TV service.

Schema 2 includes a work registry keyed by the official UMC identity. Works absent from the originals inventory are retained with independently fetched official US detail metadata. They receive no playback provider ID. Their mainland names and synopses go through the existing public Douban/Wikipedia identity checks, at most five missing works per run, with a daily retry queue. Access errors leave their English names pending; no AI-generated title is accepted as proof.

Hero images are native 1920×1080; shelf images are native 400×600; additional detail images are 960×540. Files use the SHA-256 of the actual JPEG bytes. Image URLs are checked on a six-hour positive-cache interval and detail metadata on a seven-day interval. Transport failure preserves the last published feed and already downloaded cache files. Catalog and images are validated before the manifest is replaced.

The existing six-hour GitHub workflow publishes this feed independently of the originals catalog. Apps validate identity, image hashes, dimensions and the 24 MiB current-image budget before atomically activating it. Version equality reuses the feed and local images. Schema 1 remains readable by the new app. The release bundles the latest complete snapshot for offline display.

Run `python scripts/home_sync.py`, `python scripts/home_sync.py --validate`, and `python -m unittest discover -s tests -v` from the repository root.
