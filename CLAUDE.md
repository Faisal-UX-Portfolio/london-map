# Faisal's London Reels Map

A static map of London venues — restaurants, bars, activities — sourced from Instagram
Reels saved to a private collection. Each pin links back to the Reel that recommended it.

**Read `CONTEXT.md` first** for what this is and where the data came from, and
`DECISIONS.md` before changing any settled choice.

## Architecture

No server, no build step, no framework, no npm. Static files served by GitHub Pages.

```
index.html   style.css   app.js   pins.json   manifest.json   sw.js
vendor/      Leaflet 1.9.4 (vendored, not from a CDN)
data/        source data + pipeline output
scripts/     extract → enrich → dedupe → selfcheck
reference/   the original inherited app, split up, for design reference
```

`pins.json` is the **only** file the Phase 2 automation rewrites. Nothing else is
generated. Keep it that way — it is the reason the app was split out of a single HTML file
(D-003).

## Local development

`fetch()` fails on `file://`, so do not open `index.html` directly:

```bash
python3 -m http.server 8000
```

Then open `http://localhost:8000`. That is the whole toolchain.

## Design language

The app intentionally mimics Apple's **Liquid Glass** material, not generic
glassmorphism. These rules came from the original build and are worth preserving —
several of them were arrived at by trying the alternative first and reverting it.

- **Never stack translucent glass panels over one another.** Apple's own guidance is that
  it reads muddy. The title/stat/search card is one continuous glass surface, not three.
- **Concentric corner radii**: a child's border-radius = parent's radius minus the parent's
  padding, not an arbitrary number. See the `--r`/`--pad` custom properties.
- **Specular highlight**: a faint bright line along the top edge
  (`inset 0 1px 0 var(--glass-shine)`). Real glass lenses light; plain blur alone reads as
  generic.
- **Floating controls stay separate.** The location button and theme toggle are their own
  floating circles, not bundled into the search card — this is what real Apple Maps does.
- **Colour**: light-first, true iOS system colours. `systemRed` for food, teal for
  activities, `systemBlue` for every interactive element. Orange was deliberately rejected
  for food — it clashed with the blue accent.
- **Typography**: the native system font stack (`-apple-system, BlinkMacSystemFont, ...`),
  which renders as real San Francisco on an iPhone. A Google Font was tried and reverted;
  do not reintroduce one.
- **Markers** are teardrop pins with thin-line SVG glyphs per category — not emoji, not
  plain dots.
- Marker labels are gated to zoom ≥ 15. The original showed them at every zoom, which was
  the main source of both clutter and paint cost.

## Data integrity rules

These are not style preferences. Breaking one produces a map that looks right and is
wrong.

1. **Never join captions to venues by list position.** Use the explicit ID scheme (D-006).
   A pin linking to the wrong Reel is the worst failure available here because it is
   invisible.
2. **Never dedupe venues by coordinates alone** (D-008). Two different businesses can share
   a building centroid — this exists in the real data.
3. **A low-confidence match goes to `data/needs-review.json`, not to the map** (D-007). A
   missing pin is invisible; a wrong pin sends you to the wrong address looking correct.
4. **Never delete a venue because it closed** (D-005). Flag it.
5. Run `python3 scripts/selfcheck.py` after any change to the data pipeline. It asserts
   every caption is byte-identical to the untouched raw export.

## Working agreements

- Opus orchestrates; Sonnet subagents do volume work (caption extraction, repetitive edits).
- A QA subagent checks each step; a UX subagent reviews each UI iteration.
- Update `VERSION-HISTORY.md` as work lands, and add to `DECISIONS.md` whenever a choice
  is settled — including the reasoning and what would change it.
