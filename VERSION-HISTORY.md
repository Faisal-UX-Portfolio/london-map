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
