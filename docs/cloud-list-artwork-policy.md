# Library artwork tiers

The App keeps its portrait, large-card and hero sizes. `scripts/list_artwork.py`
only upgrades undersized horizontal `entry.artwork` images used by the library,
categories and search. It never edits the hero, season images, titles, synopsis,
Douban packets, source bindings or source configuration.

The 2026-11-01 plan found 326 library images: 21 at 314×177, 3 at 334×188,
98 at 472×266, 117 at 628×354, 84 at 944×532, 2 at 980×552 and 1 at
1960×1104. Only the 122 images below 600px wide enter the initial upgrade queue.
The near-640 originals and larger images retain their original bytes.

## Source and output

Existing verified season images are preferred: the season number, season ID,
parent show ID, official image source and local content hash must all match the
depicted season. The matching official homepage season record may also supply
these bytes. Movies can reuse the same entry's officially sourced large hero.
Another season, another show's ID or an unverified pending season is rejected.
No network request is needed when these verified local wide bytes exist.

Otherwise the existing Apple PR inventory verifies the same official slug,
English title, film/series type and depicted season before an image descriptor
is used. One bounded request reads that work's actual official PR page. Real
wide key-art srcset URLs may use a modern header or older key-art directory;
they must belong to the same work, depicted season and key-art slot. Filenames
and directory layouts are not guessed from the thumbnail URL. Still images,
video posters and explicit 4:1/2:3 art are excluded rather than cropped. Only the
same `www.apple.com/tv-pr/shows-and-films/` work directory is accepted; redirects,
credentials, queries and path traversal are rejected. At most two actual
large_2x / large / medium_2x or unscaled key-art links are attempted.

An input must be a decodable landscape JPEG, PNG or WebP with at least 640×360
pixels, approximately 16:9, at most 8 MiB and at most 20 million pixels. Small
inputs are not upscaled. Cloud processing applies orientation, converts an
embedded colour profile to sRGB when present, resizes to 640×360 with Lanczos and
saves a normal RGB JPEG at quality 90. Source EXIF/comments are not copied, so
irrelevant JPEG metadata cannot change output bytes. There is no processing or
colour reduction on the television.

## Bounds and cache

The default command is an offline plan and does not alter the catalog or fetch
images. `--apply` is required for network access; `--publish` additionally calls
the existing immutable catalog publisher. A run permits 0–128 selected works,
at most 3 worker threads and a 30-second work budget including the PR page, with
bounded socket timeouts. The PR HTML response is capped at 2 MiB. The scheduled
sync step selects at most 12 due works, prioritizing untried works before retries
so failed early rows cannot starve the rest of the library.

`data/list-artwork-cache.json` keys accepted results by canonical official image
source, work, medium, depicted season and processor version. Updating Chinese
text or a metadata manifest does not invalidate image bytes. Unchanged accepted
tiers are reused for 7 days. Failures retain the previous image and wait 6 hours
before an ordinary retry. A later naturally larger original is never replaced
by a cached smaller tier. Up to four older module-generated references are
retained so a refreshed 640px tier can replace its previous generated image
without treating an unrelated native 640px original as replaceable. Publishing cached data performs no image network
requests and prevents a later medium-thumbnail collection from undoing an
accepted tier.

The catalog remains a complete snapshot if some upgrades fail: those works keep
their existing image, and `logs/list-artwork.json` records individual outcomes.
All image bytes and the complete immutable catalog are written and verified
before the manifest changes. Previous content-addressed images remain available
for older clients and history references.

The first bounded backfill accepted 87 of the 122 candidates: 8 official PR
wide images, 71 verified same-season local images, 1 same-movie hero and 7
same-movie official homepage/topic images. The 35 remaining works keep their
previous artwork because no acceptable wide asset with the required identity
and season proof was available through these sources and bounds. Explicit
4:1 artwork was not cropped, and 26–74 MiB press ZIP packages were not fetched.
The 87 generated files total 5,042,712 bytes (largest 103,959 bytes). All other
entry fields and the original 628px/larger artwork remained unchanged.

Commands:

```text
python scripts/list_artwork.py --limit 12
python scripts/list_artwork.py --apply --limit 12 --workers 3 --publish
python scripts/catalog.py --validate
python -m unittest discover -s tests -v
```

An initial explicitly requested backfill can raise `--limit` within 128 while
keeping the same 3-worker and per-image bounds. Actual download and television
comparison outcomes must be reported separately from these offline tests.
