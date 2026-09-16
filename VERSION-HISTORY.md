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
