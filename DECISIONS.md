# Decisions

One entry per settled choice, with the reasoning. The point of this file is so a future
session (or a future Faisal) does not relitigate a question that already has an answer.

Format: **D-nnn — decision** · date · status · why · what would change it.

---

## D-001 — Google Places API (New) as the enrichment source
**2026-09-16 · settled**

Uses `POST https://places.googleapis.com/v1/places:searchText` with `X-Goog-Api-Key` and
`X-Goog-FieldMask` headers.

**Why:** the deciding factor was `businessStatus` (`OPERATIONAL` / `CLOSED_TEMPORARILY` /
`CLOSED_PERMANENTLY`). "Is this place still around?" is a stated requirement, and Google
answers it with a definitive field. Foursquare was evaluated first and started as the
choice, but its new API dropped the old `closed_bucket` field, which would have forced a
guesswork heuristic ("venue disappeared from search results since last run") with a real
false-positive rate.

Two further benefits fell out of it: the 21 already-enriched pins were originally
Google-sourced, so their 0–5 rating scale stays valid and needs no re-fetching (Foursquare
rates 0–10 — mixing scales in one field would have rendered broken stars); and the fields
we need sit in Google's Enterprise SKU with **1,000 free calls/month** against a first run
of ~650–700, so it should cost nothing.

**Cost of being wrong:** Google requires a billing account with a card even for the free
tier, and overage is $35/1,000 — pricier per call than Foursquare. Mitigated by a hard
quota cap in the Cloud console and by caching every result.

**What would change it:** poor coverage of small London independents. Guarded by D-009.

---

## D-002 — GitHub Pages on the personal account
**2026-09-16 · settled**

**Why:** geolocation is a hard requirement and iOS blocks it on `file://`, so the app must
be served over HTTPS — hosting is not optional. Pages is free, gives HTTPS, installs to the
home screen, and is where the Phase 2 automation runs (Actions) without adding a server.
`gh` is authorised as `Faisal-UX-Portfolio` with `repo` + `workflow` scopes.

**What would change it:** wanting a custom domain with private access control.

---

## D-003 — Split the single HTML file into separate assets
**2026-09-16 · settled · supersedes a handoff constraint**

The handoff `CLAUDE.md` deliberately required a single self-contained HTML file so it could
be opened anywhere with no setup. **That constraint is retired**, knowingly.

**Why:** it was written to serve "just open the file", but geolocation already forces
hosting (D-002), so the benefit it protected no longer exists. Against that, keeping pin
data as a JS literal inside the HTML means the Phase 2 automation would have to
string-edit a 518KB HTML file on every new venue — fragile, and a corrupted edit takes the
whole app down rather than one data file.

Splitting means automation only ever rewrites `pins.json`.

**Trade-off accepted:** `fetch()` fails on `file://` due to CORS, so local development now
needs `python3 -m http.server`. No build step, no npm, no dependency — the constraint that
actually mattered is intact.

---

## D-004 — Expand listicle reels into one pin per venue
**2026-09-16 · settled**

Roughly 40 of the 101 unmapped reels are "best 5 spots in X" captions naming several
venues. Each named venue becomes its own pin, all linking back to the same Reel.

**Why:** this is where the "over 400" comes from — it should take the map past 450 pins.
The alternative (one primary venue per reel) discards most of the recommendations.

**Cost:** more lookups, and a higher risk of bad matches — handled by D-007.

---

## D-005 — Closed venues are flagged, never deleted
**2026-09-16 · settled**

Permanently-closed venues stay in `pins.json` with a status flag, render greyed out, and
are hidden behind a filter toggle that is off by default.

**Why:** the pin is a memory of a Reel as well as a place to go. Deleting silently
discards something Faisal chose to save. Hiding by default keeps the map useful for
planning without destroying data.

---

## D-006 — Caption↔venue joins use explicit IDs, never list position
**2026-09-16 · settled · this one is load-bearing**

Every caption gets a short id derived from its Reel URL. Extraction subagents receive
`[ID: a1b2c3d4] CAPTION: ...` and must return one object per *input caption* keyed by that
id. The orchestrator asserts the returned id set is exactly the input id set with no
repeats; a failing batch is rejected and re-run whole — never partially trusted, never
patched by guessing. Reel URLs are recovered from the orchestrator's own id→url map, so
the model never handles a URL and cannot mangle one.

**Why:** the original build hit exactly this bug — batch results matched to the wrong
captions. Positional matching breaks the moment a model reorders, merges, splits or drops
an entry, which is precisely what listicle expansion does (1 input → 5 outputs). This makes
the failure structurally impossible rather than unlikely, and `scripts/selfcheck.py`
asserts byte-identical captions against the untouched raw file as a regression guard.

---

## D-007 — Venue matches are scored, and ambiguity goes to review rather than the map
**2026-09-16 · settled**

`0.7 × name similarity + 0.3 × distance score`. Auto-accept above 0.80. Anything
ambiguous, low-confidence, or hitting the **chain trap** (near-perfect name match more than
2km from known coordinates — the wrong Franco Manca branch) is written to
`data/needs-review.json` instead of `pins.json`.

**Why:** a wrong pin is worse than a missing pin. A missing venue is invisible; a wrong one
sends you across London to the wrong address and looks perfectly correct while doing it.

---

## D-008 — Dedupe on Google `place_id`, never on coordinates
**2026-09-16 · settled**

**Why:** `Nan Hotpot` and `RedBox Karaoke` share exact coordinates but are different
businesses (see CONTEXT.md). Where coordinates match but names do not clear a similarity
bar, both pins are kept *and* flagged for review rather than merged.

---

## D-009 — Stop and report after the first 50 enrichment lookups
**2026-09-16 · settled**

**Why:** if Google's coverage of small London independents turns out to be poor, that is
much better discovered at 50 calls than at 650 — both for the quota and for the decision
about whether to change approach.

---

## D-010 — Phase 2 capture uses `repository_dispatch`, not a queue file
**2026-09-16 · settled**

The iOS Shortcut POSTs to GitHub's `repository_dispatch` endpoint rather than appending to
an `inbox.json` via the Contents API.

**Why:** two shares in quick succession collide on the Contents API — the second write is
rejected on a stale sha and the entry is lost unless the phone retries, which is fiddly to
build reliably in the Shortcuts editor. Dispatch events simply queue as two workflow runs,
serialized by a `concurrency` group. It also sidesteps self-triggering for free: the
Action's own commit cannot satisfy a `repository_dispatch` trigger, so no `[skip ci]`
convention is needed.

---

## D-011 — The Shortcut asks for the venue name rather than scraping the caption
**2026-09-16 · settled**

**Why:** Instagram actively blocks caption scraping, and a capture pipeline that silently
fails on some reels is worse than one that costs five seconds of typing. Typing the name
also produces a better search query than a caption parse usually would — you know what the
place is called at the moment you save it.
