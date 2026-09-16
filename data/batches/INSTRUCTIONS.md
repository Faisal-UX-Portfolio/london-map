# Venue extraction instructions

You are given a batch file of Instagram reel captions. Extract the real, specific, named
**London** venues each caption recommends.

Input rows: `{"id": "...", "caption": "...", "owner": "..."}` where `owner` is the account
that posted the reel.

## What counts as a venue

A specific named place you could walk into: restaurant, cafe, bar, pub, shop, museum,
park, market, attraction, club. It must have a name.

**Not venues:** neighbourhoods or areas ("Soho", "West London"), generic categories
("Japanese restaurants"), topic hashtags (#londonfood), platform/tourism-board accounts
(`@deliveroo`, `@chinatownlondon`, `@discoverhongkong`), venues outside London.

## The owner rule — read this carefully

`owner` is usually a **content creator** reviewing places. A creator is not a venue, and
their self-promo sign-off ("Follow @abdunoureats for more!") must be ignored.

**But venues also post about themselves**, and those absolutely count. If the owner is
clearly a business — a restaurant, cafe, bar, shop — and the caption is that business
talking about its own food, menu, opening hours or customers ("our new tasting menu",
"open everyday from 12:00", "drop a 🍣 if you're visiting us"), then **the owner IS the
venue**. Extract it, with `source_signal: "owner_is_venue"`.

Tells that the owner is a business, not a creator: a trading name ("Ayllu Restaurant",
"The Knot Churros", "Noodle Inn"), first-person plural about a menu or premises ("our",
"we serve", "visiting us"), stated opening hours, or a location pin for itself.

Tells that the owner is a creator: a personal name, a handle describing a persona
("fashionable foodie", "Food & Travel Content Creator"), reviewing places in the third
person, asking followers for suggestions.

If genuinely ambiguous, extract it — a wrong candidate gets filtered later by the
confidence scoring, whereas a missed venue is gone for good.

## Listicles are the point

A caption like "5 best hot chocolates: 1. @x 📍Soho 2. @y 📍Shoreditch..." must return
**all five** venues as five entries in that row's `venues` array. Never pick just one.
These captions are the main reason this task exists.

## Handles

`@handles` are very often the venue itself. Convert to a readable name:
`@noodleandbeerltd` → "Noodle and Beer", `@hinaga_kakigori` → "Hinaga Kakigori". Strip
suffixes like `ltd`, `_london`, `_uk`, `.uk`, `official`, trailing digits.

## No venue

If a caption names no identifiable venue — a cooking recipe, a vibe post, "London's
dessert game is world class", recommendations deferred to a link in bio — set
`"no_venue": true` with a short `reason`, and leave `venues` empty.

## Fields

- `name` — readable venue name
- `area_hint` — the London area stated for that venue ("Soho", "Hammersmith"), else null
- `source_signal` — one of `handle`, `pin_emoji`, `at_phrase`, `numbered_list`, `hashtag`,
  `owner_is_venue`, `other`

## Output contract (strict)

- **Exactly one object per input row** — same count as input, no more, no fewer.
- Each object carries the `id` **copied verbatim** from its input row. That id is the only
  thing linking your answer back to the right reel. A wrong id silently attaches a venue to
  someone else's reel, which is the worst failure available here.
- Multiple venues from one caption go in that row's `venues` array — never as extra
  top-level objects.
- Do not reorder-and-renumber, invent, or drop rows.

```json
[
  {"id": "a1b2c3d4e5f6", "no_venue": false, "reason": null,
   "venues": [{"name": "Noodle and Beer", "area_hint": "Chinatown", "source_signal": "handle"}]},
  {"id": "f6e5d4c3b2a1", "no_venue": true, "reason": "recipe", "venues": []}
]
```

Write the JSON array and nothing else — no markdown fences, no commentary.

Before finishing, re-read your output file and the input file and confirm the id sets match
exactly with no duplicates.
