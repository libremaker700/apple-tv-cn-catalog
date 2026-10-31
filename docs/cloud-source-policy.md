# Source verification is performed in GitHub

The Android client does not run background catalog-wide or visible-item source scans. It downloads the catalog and homepage metadata, displays the published source status and obtains actual routes on demand in a work's detail page.

The mainland title workflow first verifies Chinese names using the existing Douban and public-source policy. That same source check now publishes `zh.sourceCheck`; a separate bounded pass checks up to three already named works whose source status is missing or due for refresh. Positive results are reused for seven days and pending results for one day. Future releases remain name-only. Animation keeps the verified Douban display name.

The public result contains only schema, original English name, medium, season, year, found flag, route count and check time. It contains no provider content IDs, tokens, headers or playback URLs. The client accepts a positive status only for the matching work, medium, year and displayed season. A first-season result does not certify a second season. Missing or unsuccessful verification remains pending in the client; opening the app does not start a replacement scan.

A single scheduled source pass stops submitting requests after three minutes. Actual playback/decoder availability is not claimed by a catalog search result.
