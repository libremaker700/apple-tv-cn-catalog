# Official homepage and topic feed

`home_sync.py` reads the public US page API advertised in Apple's own channel bootstrap configuration. It follows both canvas and shelf pagination to completion, rejecting repeated tokens, changed identities and excessive page counts. It retains display metadata only. Playback assets, account fields, sessions and API bootstrap parameters are not published.

Schema 3 includes a shared UMC work registry, seven homepage rows and independently ordered destination pages. The homepage order is Top 10 TV Shows, Top 10 Movies, New Releases, Dark Destinations, Browse All Apple Originals, Must-See Hits, and Coming to Apple TV. The free-premiere row is omitted. The upcoming destination is moved out of the browse-entry row to the homepage bottom. Other browse entries open their real topic pages. A source can contain more works than its first twenty-item batch.

Known UMC identities preserve existing originals and playback bindings. A unique exact English name, type and verified year can also reuse an original that lacks a UMC identity. A different known UMC identity or a conflicting year blocks that fallback. Additional works receive no playback provider ID. Mainland name checks reuse the existing bounded public-source workflow; unavailable names remain pending.

Hero images are native 1920×1080, portrait rows 400×600, landscape rows 640×360, and additional detail art 960×540. Files use the SHA-256 of the actual JPEG bytes. Page metadata and unchanged image URLs have a six-hour positive cache. Transport failure keeps the last published snapshot and downloaded images. All files are validated before the manifest is replaced.

The existing six-hour workflow publishes independently of the originals catalog. Apps validate destination references, US source paths, work identities, hashes and dimensions before atomic activation. The entire home and topic snapshot is bounded to 96 MiB of unique images, 40 destination pages and 1,000 works. Unchanged versions reuse local images. The release bundles the complete snapshot for offline browsing. Old schemas remain readable, and a schema-3 snapshot cannot be replaced by an older schema.

Run `python scripts/home_sync.py`, `python scripts/home_sync.py --validate`, and `python -m unittest discover -s tests -v` from the repository root.
