# Handing this to your personal Claude

Nothing in the running system depends on Claude. Once set up, the site and its automation
run on their own — Claude is only involved when you want to *change* something.

## What to say

> Take over the project at https://github.com/Faisal-UX-Portfolio/london-map — clone it and
> read `CONTEXT.md`, `DECISIONS.md` and `CLAUDE.md` before changing anything.

That's it. Everything needed to continue is in the repo.

## Checklist if anything moves accounts

- [ ] **The repo** is already on the personal account (`Faisal-UX-Portfolio`). Nothing to move.
- [ ] **The Shortcut token** is a fine-grained PAT you created yourself. If you ever
      regenerate it, update the Text action inside the Shortcut (docs/SHORTCUT.md).
- [ ] **No API keys exist.** Nominatim and OpenStreetMap need none. There is nothing to
      re-key and no billing anywhere.
- [ ] **No scheduled jobs, no connectors, no MCP servers.** The only automation is one
      GitHub Action, triggered by your phone.

## The state of things

| | |
|---|---|
| Places on the map | **339** |
| Reels mapped | **351** of 414 |
| Ratings / opening hours | none — see DECISIONS.md D-014, D-015 |
| Needing a human look | 44 in `data/needs-review.json` |

## The obvious next moves

1. **Add ratings and hours.** The Google Places pipeline is written, tested and unused —
   `scripts/enrich.py` plus `scripts/places.py`. It needs a Google Cloud key with billing
   attached; the ~385 lookups should sit inside the free tier. Foursquare needs no card and
   the provider interface is one function. See D-014 for the measured comparison.
2. **Clear `data/needs-review.json`.** 29 venues Nominatim couldn't find and 13 it wasn't
   confident about. Most are judgement calls a human makes in seconds.
3. **The 44 reels with no venue** (`data/no-venue-reels.json`) are mostly genuinely
   unmappable — recipes, and "link in bio" posts that never name anywhere.
4. **7 pins are still named after a street.** Their captions usually name the venue; the
   fix is to read the caption and rename by hand.

## Rules worth not breaking

They're in `CLAUDE.md`, but the two that matter most:

- **Never join captions to venues by list position.** A pin linking to the wrong reel is
  invisible — it looks completely plausible. `scripts/selfcheck.py` guards this by
  comparing every caption byte-for-byte against the untouched export. Run it after any
  data change.
- **Never dedupe venues by coordinates alone.** Two different businesses share a building
  centroid in this very dataset.
