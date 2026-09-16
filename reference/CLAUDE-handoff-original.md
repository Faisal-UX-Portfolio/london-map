# Faisal's London Reels Map

A single-file HTML web app that plots Faisal's Instagram "London" saved-collection
(restaurants, bars, activities) onto an interactive map, styled after Apple Maps /
iOS 26 Liquid Glass. Built iteratively in a Claude.ai chat; handed off here because
the remaining work (enriching ~313 places with live data, one Google lookup at a
time) is too slow to do turn-by-turn in that chat.

## What's in this zip

```
CLAUDE.md                        <- this file
app/london-reels-map.html        <- the current working app (open it in a browser)
data/mapped-pins.json            <- 313 places already geocoded, ready to use
data/unmapped-reels.json         <- 101 reels not yet matched to a place
data/all-414-reels-raw.json      <- the full original set, for reference/redo
```

## Where this data came from

Faisal exported his Instagram data (Settings → Export Your Information), which
produced `saved_collections.json`. His "London" collection had 414 saved
Reels. Each Reel's caption was parsed to guess a venue name (from `@handles`,
`📍` pins, or "at X" phrasing), then that guess was run through a places-search
tool (Google Places, via `location_bias` centred on London: lat 51.5074,
lng -0.1278) to get a real name, address, and lat/lng.

**313 of 414 reels are geocoded** (`mapped-pins.json`). The other **101**
(`unmapped-reels.json`) are reels whose captions have no usable location
clue at all — recipe posts, "5 places to try" listicles naming several
venues at once, bare tags like "West London" — or where every Google Places
result Claude tried didn't confidently match the venue in question.

### Data quality notes (read before trusting the data blindly)
- Every entry in `mapped-pins.json` was matched by a human-reviewed search
  query against Google Places, not fuzzy-matched automatically. A handful of
  bad matches were caught and excluded during the build (e.g. a search for
  "Argentum" first returned an unrelated estate agency before a better query
  found the actual Notting Hill café). There could still be a few
  wrong matches that weren't caught — spot-check anything with a generic
  name.
- Duplicate venues are expected and correct: if Faisal saved two different
  Reels about the same restaurant, both appear as separate pins with
  identical coordinates but different `reel_url`/`caption`.
- One indexing bug happened mid-build (batch results got matched to the
  wrong original captions) and was caught and fixed before the data was
  finalised — flagging in case a similar bug is reintroduced during a
  rewrite; always double check `reel_url` actually points to the Reel
  described in `caption` for a given `place_name`.

## `mapped-pins.json` schema

```json
{
  "place_name": "Gordon's Wine Bar",
  "lat": 51.507944,
  "lng": -0.123314,
  "address": "47 Villiers St, London WC2N 6NE",
  "reel_url": "https://www.instagram.com/reel/...",
  "caption": "full original Instagram caption text",
  "owner": "creator's display name or @handle",
  "category": "restaurant/food | activity | other",
  "rating": 4.6,              // null if not yet enriched
  "rating_count": 6277,       // null if not yet enriched
  "price_level": 2,           // null if not yet enriched; Google's 0-4 scale
  "hours": ["Mon: 11:00 AM–11:00 PM", "Tue: ...", ... 7 entries, Mon->Sun]
           // null if not yet enriched
}
```

`category` was assigned by keyword-matching the caption text (a simple
heuristic, not verified per-venue) — it drives which colour pin and which
filter chip a place shows under in the app.

**Only ~21 of the 313 have `rating`/`rating_count`/`price_level`/`hours`
filled in** — this is the main unfinished piece of work, see below.

## `unmapped-reels.json` schema

```json
{
  "url": "https://www.instagram.com/reel/...",
  "caption": "full original caption",
  "owner": "creator handle/name"
}
```

## The app (`app/london-reels-map.html`)

Self-contained single HTML file — Leaflet.js and its CSS are inlined, no
build step, no dependencies, just open it in a browser. Pin data is a
JS literal (`const PINS = [...]`) near the bottom of the file, generated
from `mapped-pins.json`.

Design language: built to intentionally mimic Apple's **Liquid Glass**
material (iOS 26), not generic glassmorphism. Specific rules that were
followed and should be preserved if you touch the CSS:
- Never stack more than one translucent glass panel visually overlapping
  another — Apple's own guidance is that this looks muddy. The
  title/stat/search card is one continuous glass surface, not three.
- **Concentric corner radii**: a child element's border-radius = parent's
  radius minus the parent's padding, not an arbitrary number (see the
  `--r`/`--pad` CSS custom properties on `.header-pill`/`.search-row`).
- Glass surfaces get a **specular highlight**: a faint bright line along
  the top edge (`inset 0 1px 0 var(--glass-shine)` in the `.glass` and
  `.rail-btn` box-shadows) — real glass has a lensing highlight, plain
  blur alone reads as generic.
- The current-location button and the theme toggle are **separate floating
  circles**, not bundled inside the search card — this matches real Apple
  Maps, which keeps its compass/location control as its own floating
  element apart from the search bar.
- Colour palette: light-first (not dark-first), true iOS system colours —
  `systemRed` for food (`--food`), a teal for activities (`--activity`),
  `systemBlue` for all interactive/action elements (`--spark`: directions
  button, active filter chip, CTA). Orange was deliberately avoided for
  food because it clashed with the blue accent (see CSS `:root` block for
  exact hex values, light and dark).
- Typography is the **native system font stack**
  (`-apple-system, BlinkMacSystemFont, ...`) — this renders as real San
  Francisco on an iPhone automatically. Don't reintroduce a Google Font;
  that was tried and deliberately reverted.
- Markers are teardrop pins (`.map-pin`, Apple Maps style) with a thin-line
  SVG glyph per category (fork/knife for food, ticket for activity, generic
  pin for other) — not emoji, and not plain dots.
- Bottom sheet slides up from the bottom (single detent — fully open or
  fully closed, no drag-to-resize; that's a known simplification, true
  Apple sheets have peek/half/full states which weren't worth the
  engineering effort in a web page).
- The Directions button opens `maps.apple.com` with the venue's address —
  real functionality, not decorative.

## What's left to do

### 1. Enrich all 313 mapped pins with live data (the main task)
For each entry in `mapped-pins.json`, look up the venue (Google Places API,
or web search as a fallback) and fill in:
- `rating` / `rating_count` — current Google rating
- `price_level` — Google's 0–4 scale (nullable, not every place has one)
- `hours` — **and check the venue is still trading**. If a lookup shows
  the business permanently closed or the listing no longer exists, flag it
  rather than silently dropping it — Faisal should decide whether to pull
  it from the map or keep it as a memory of the Reel regardless.

The app already has the UI for this wired up (star rating badge + "Today:"
hours line in the bottom sheet, see `openSheet()` in the JS) — it just reads
`p.rating` / `p.hours` if present and renders nothing if they're `null`, so
partial data is fine to ship incrementally.

### 2. Attempt the 101 unmapped reels
Read each caption in `unmapped-reels.json` by hand (same approach that got
the mapped list from ~230 to 313) — many will be genuinely un-geocodable
(recipes, multi-venue listicles), but some will have a venue name buried in
less obvious phrasing than the regex-friendly ones already caught. Anything
found should be appended to `mapped-pins.json` in the same schema (with
`rating`/`hours`/etc. as `null` until enriched separately).

### 3. Nice-to-haves, not required
- Real Google Places `photo` references for a thumbnail per pin (the
  export tool doesn't currently pass these back, so it's a data gap, not
  a design decision).
- Drag-to-resize bottom sheet (peek/half/full), to better match native
  Apple Maps.
- A basic dedupe/merge view for pins with identical coordinates (i.e.
  multiple reels for the same venue) instead of showing them as separate
  pins on top of each other.

## Constraints to keep in mind

- Keep the app a **single self-contained HTML file** — no build step, no
  node_modules, no external requests except OpenStreetMap map tiles and
  Apple/Google Maps links the user taps. That's a deliberate choice so
  Faisal can just open the file, or drop it anywhere, without setup.
- Don't reintroduce Google Fonts, marker images, or a JS framework —
  see the design-language notes above for why.
