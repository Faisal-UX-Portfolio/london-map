# Faisal's London

A map of London places — restaurants, bars, activities — saved from Instagram Reels.
Every pin links back to the reel that recommended it.

**Live:** https://faisal-ux-portfolio.github.io/london-map/

Add it to your iPhone home screen: open the link in Safari → Share → **Add to Home Screen**.
It then runs full-screen with its own icon, and "Near me" works.

## Docs

| File | What's in it |
|---|---|
| `CONTEXT.md` | What this is, where the data came from, known data traps |
| `DECISIONS.md` | Every settled choice and why — read before changing one |
| `VERSION-HISTORY.md` | What changed, when |
| `CLAUDE.md` | Design language and data-integrity rules |

## Running it locally

`fetch()` does not work from `file://`, so don't open `index.html` directly:

```bash
python3 -m http.server 8000
```

Then <http://localhost:8000>. That's the whole toolchain — no npm, no build step.
The service worker is deliberately not registered on localhost, so you never debug
cached code.

## Data pipeline

```bash
python3 scripts/extract_venues.py prepare   # batch unmapped captions for extraction
python3 scripts/extract_venues.py collect   # validate + merge extraction output
python3 scripts/build_pins.py               # mapped-pins.json -> pins.json
python3 scripts/enrich.py --dry-run         # show what would be looked up
python3 scripts/enrich.py --limit 50        # enrich, capped
python3 scripts/selfcheck.py                # integrity check - run after any change
```

`scripts/selfcheck.py` asserts every caption on every pin is byte-identical to the
original Instagram export. That guards against the one failure mode that matters here: a
pin that looks completely plausible while linking to the wrong reel.
