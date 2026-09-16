# Context

## What this is

An interactive map of London places — restaurants, bars, activities — sourced entirely
from Instagram Reels Faisal saved to a private "London" collection. Each pin links back
to the Reel that recommended it.

It is a static site: no server, no build step, no framework. It is hosted on GitHub Pages
so it can be installed to an iPhone home screen and use geolocation (iOS blocks
geolocation on `file://`, which is why hosting is mandatory rather than optional).

## Where the data came from

Faisal exported his Instagram data (Settings → Export Your Information), producing
`saved_collections.json`. The "London" collection held **414 saved Reels**. A previous
Claude.ai session parsed each caption to guess a venue name (from `@handles`, `📍` pins,
or "at X" phrasing), then resolved those guesses against Google Places to get real names,
addresses and coordinates.

That session got **313 of 414** geocoded and built a working single-file HTML app. It
stopped short of finishing, which is why this repo exists.

## State inherited from that session

Verified by reading the data directly rather than trusting the handoff notes:

| Fact | Detail |
|---|---|
| Reels accounted for | 414 = 313 mapped + 101 unmapped — zero gaps, zero overlap |
| Enriched | **21 of 313** have rating/hours/price; the rest are `null` |
| Categories | 191 restaurant/food, 115 activity, 7 other |
| Coordinate duplicate groups | 35 (same venue saved from multiple Reels) |
| Original app | 518KB single HTML file, Leaflet 1.9.4 inlined, pins as a JS literal |

## Two data traps found on inspection

**1. Identical coordinates do not mean identical venue.**
`Nan Hotpot` and `RedBox Karaoke` sit at *exactly* the same lat/lng but are different
businesses — both geocoded to a single building centroid. Any dedupe keyed on coordinates
alone would silently fuse two unrelated venues into one pin. Dedupe must key on venue
identity (Google `place_id`), never position.

**2. A caption↔venue misalignment bug has happened before.**
The handoff notes record that during the original build, batch results were once matched
back to the wrong original captions. It was caught and fixed, but it is the single most
damaging failure mode available here — a pin that looks perfectly plausible while linking
to the wrong Reel. It is designed out structurally (see DECISIONS.md D-006) and guarded by
`scripts/selfcheck.py`.

## Repo layout

```
index.html              the app shell
style.css               app styling (Liquid Glass)
app.js                  app logic
pins.json               the served pin data — the ONLY file automation rewrites
manifest.json           PWA manifest
sw.js                   service worker (offline shell + last-known pins)
icons/                  home screen icons
vendor/                 Leaflet 1.9.4, extracted from the original monolith
data/                   source data (raw reels, mapped pins, cache, needs-review)
scripts/                pipeline: extract → enrich → dedupe → selfcheck
reference/              the original app, split up, kept for design reference
```

## Ownership

Built on a work machine but personal property. Everything must transfer cleanly to
Faisal's personal GitHub (`Faisal-UX-Portfolio`) and personal Claude account. Nothing in
the runtime depends on Claude — once built, the site and its automation run on their own.
