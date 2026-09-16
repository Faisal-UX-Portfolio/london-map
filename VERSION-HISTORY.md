# Version History

Newest first. One entry per meaningful change.

---

## 2026-09-16 — Step 1: repo scaffold

Unpacked `london-reels-map-handoff.zip` into a git repo and split the inherited 518KB
single-file app into its parts.

- `vendor/leaflet-1.9.4.{js,css}` extracted from the monolith (verified: parses clean)
- `reference/` keeps the original app whole plus its CSS, body markup and JS split out,
  for design reference
- `data/` holds the inherited source data: `raw-reels.json` (all 414),
  `mapped-pins.json` (313), `unmapped-reels.json` (101)
- Docs created: `CONTEXT.md`, `DECISIONS.md`, `VERSION-HISTORY.md`, `CLAUDE.md`

Verified on the inherited data before trusting it: 414 reels account for exactly
313 mapped + 101 unmapped with no gaps or overlap; 21 of 313 pins are enriched.

Two data traps recorded in CONTEXT.md — coordinate-identical but distinct venues
(`Nan Hotpot` / `RedBox Karaoke`), and the prior caption↔venue misalignment bug.

---

## Before this repo — inherited state

Built in a Claude.ai chat, delivered as `london-reels-map-handoff.zip`.

- 414 Reels exported from an Instagram "London" saved collection
- 313 geocoded against Google Places; 101 left unmapped
- 21 of 313 enriched with rating / review count / price level / opening hours
- Single-file HTML app with Leaflet inlined, Apple Maps–style Liquid Glass styling,
  category filter chips, search, geolocate, theme toggle and a bottom sheet with a
  working Apple Maps directions link

---

## 2026-09-16 — Step 2: mined the 101 unmapped reels

**111 venue candidates recovered from 57 reels** (44 reels have no usable venue).
54 of those came from listicle expansion — reels naming several venues at once, the
biggest yielding 11.

- `scripts/extract_venues.py` — `prepare` writes ID-keyed batches, `collect` validates
  subagent output and merges. The id-set assert (D-006) passed on every batch.
- Five Sonnet subagents processed ~20 captions each against
  `data/batches/INSTRUCTIONS.md`.
- Output: `data/extracted-venues.json`, `data/no-venue-reels.json`.

**Two recall bugs found and fixed mid-step**, both of which silently discarded real venues:

1. The recipe prefilter fired on the bare word "ingredients", binning three venue posts
   that used it in review prose (D-012). Prefilter now bins 5 instead of 9.
2. The extraction rules told subagents the owner is never a venue, which discarded six
   restaurants posting about their own menus (D-013).

Both were caught by reading the subagents' own reasoning rather than just their output
counts. Re-running all five batches after the fixes took the yield from 102 venues across
49 reels to **111 across 57**.

Agents correctly excluded out-of-London content: Manchester, Portsmouth, Edinburgh, Los
Angeles and Tempe AZ.

---

## 2026-09-16 — QA and UX review fixes

Two review subagents ran against the live app. Their findings, applied:

**Blocking bug (QA):** the scrim covered the header, filter chips and side rail, so on any
phone-width screen you could not search, change a filter or toggle the theme while a place
card was open — the tap closed the card instead. Header and bottom bar now sit above the
scrim and sheet (z-index 60), verified with `elementFromPoint`.

**Search and filters moved to the bottom of the screen (UX).** Apple's guidance puts search
at the bottom when there is no bottom toolbar, and this app is used one-handed on the
street — the two most-touched controls were the only ones out of thumb reach. The sheet now
opens *above* the bottom bar (`--chrome-h`, measured at runtime) so the controls are never
covered. The wordmark became a small non-interactive top pill.

**Clustering below zoom 15.** 150+ overlapping unlabelled teardrops was the first thing you
saw. Pins now cluster into count bubbles below the zoom where labels appear — above it, the
custom teardrop pins render exactly as before, so the pin design is untouched at every zoom
where it was ever legible. A 66px pixel grid, no library.

**Light-mode contrast.** `--muted` measured 3.44:1 and `--muted-2` 2.23:1 over a light
backing, under the 4.5:1 and 3:1 minimums. Raised to 5.00:1 and 3.63:1 (verified by
computation, not by eye). Dark mode already passed and was left alone.

Also: swipe-to-dismiss on the sheet (the grabber previously promised a gesture that did not
exist), `safeUrl()` scheme allowlist on every href (`esc()` escapes text but does nothing to
`javascript:`), visible keyboard focus rings, honest `aria-modal` plus focus restore, a
28px clear button (was 20px, under the tap-target minimum), panel-aware map panning on wide
screens, the reel caption surfaced above the fold as the reason a place is on the map, and
a stale detail card now swaps to results when a search excludes it.

**The service worker is no longer registered on localhost.** It served stale JavaScript
twice during development and cost real debugging time.

---

## 2026-09-16 — Step 4: live on GitHub Pages

Repo: https://github.com/Faisal-UX-Portfolio/london-map (public, `main`)
Live: https://faisal-ux-portfolio.github.io/london-map/

Verified the deployed site over HTTPS at iPhone viewport — map, clustering, filters and
bottom chrome all render correctly. HTTPS is what makes geolocation possible at all; iOS
blocks it on `file://`, which is why hosting was never optional.

Added `docs/PHONE-SETUP.md` for home-screen install and location permissions.

---

## 2026-09-16 — Geocoding and Phase 2 automation

**Enrichment dropped, mapping kept.** After OSM measured at 15% hours coverage (D-014), the
owner chose to ship without ratings or hours (D-015). Nominatim was still used for
geocoding, because putting the listicle venues on the map was a separate requirement:

| | Before | After |
|---|---|---|
| Places | 274 | **339** |
| Reels mapped | 313 | **351** of 414 |
| Pins named after a street | 16 | 7 |

10 pins gained real names — `10 Wakley St` → `Tanakatsu`, `81 Great Eastern St` →
`Hoxton Grill`, `332 Portobello Rd` → `Layla bakery`.

**Four matching bugs fixed**, each silently rejecting correct venues: accents were mangled
(`Gökyüzü` vs `Gokyuzu` scored 0.58), length differences were punished (`JOIA` vs
`JOIA Restaurant, Bar & Rooftop` scored 0.33), chain branches were treated as ambiguity
(every `Kricket` in London), and distance diluted scores for candidates that had no
coordinates to measure. Plus D-016: Nominatim returns nothing for `Dishoom Shoreditch,
London` but five results for `Dishoom, London`, so lookups now walk a ladder of
progressively looser queries — that alone recovered 21 pins.

**Phase 2 shipped and tested end to end.** Share sheet → Shortcut → `repository_dispatch` →
GitHub Action geocodes and commits → Pages rebuilds. Verified by a real workflow run.

The end-to-end test earned its keep: `selfcheck.py` required every reel to exist in the
original export, so it would have **failed on every genuinely new venue** — blocking the
entire automation. Post-export reels are now validated as Instagram links instead, while
the byte-identical caption check still applies to everything from the export.

---

## 2026-09-16 — Street-named pins resolved, and PLACES.md

Read the captions behind all seven pins still named after a street. **Four were genuine
errors, three were not** — `1947 London`, `64 Old Compton Street` and `221B Baker Street`
are the businesses' real names, and `113 Korean Kitchen & Karaoke` is too once renamed.

| Was | Now | Evidence |
|---|---|---|
| 10A Gee's Court | **Cup+Lid** | Caption credits `@cuppluslid`; OSM confirms it 3m away |
| 11-15 Minories | **Lindt** | Caption is the Lindt flagship at W1D 7EA — the pin was in EC3N, the wrong end of London |
| 113 KTV | **113 Korean Kitchen & Karaoke** | Caption names it outright |
| 278 Uxbridge Rd | **Chipsy** | Caption credits `@chipsy_uk` |

Recorded in `data/manual-corrections.json` with the reasoning, applied by
`scripts/apply_corrections.py` (idempotent) — see D-017.

Added **`PLACES.md`**: all 339 places grouped by category, A–Z, with address, postcode area
and reel links. Regenerate with `python3 scripts/build_list.py`.
