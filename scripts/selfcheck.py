#!/usr/bin/env python3
"""Assert-based integrity check. Run after any change to the data pipeline.

The load-bearing check is caption equality against the untouched raw export. The original
build hit a bug where batch results were matched back to the wrong captions, producing
pins that looked entirely plausible while linking to someone else's reel. Byte-for-byte
comparison against data/raw-reels.json is the regression guard for that.
"""
import json, sys, pathlib, collections

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def load(p, default=None):
    path = ROOT / p
    if not path.exists():
        if default is None:
            sys.exit(f"missing required file: {p}")
        return default
    return json.loads(path.read_text())


def check():
    raw = {r["url"]: r for r in load("data/raw-reels.json")}
    pins = load("pins.json")
    extracted = load("data/extracted-venues.json", [])
    no_venue = load("data/no-venue-reels.json", [])
    failures = []

    def want(cond, msg):
        if not cond:
            failures.append(msg)

    # 1. Every reel on a pin is real, and its caption is untouched.
    seen = collections.Counter()
    for p in pins:
        want(p.get("name"), f"pin {p.get('id')} has no name")
        want(isinstance(p.get("lat"), (int, float)) and isinstance(p.get("lng"), (int, float)),
             f"pin {p.get('name')} has non-numeric coordinates")
        want(51.2 < p["lat"] < 51.75 and -0.55 < p["lng"] < 0.35,
             f"pin {p.get('name')} at {p.get('lat')},{p.get('lng')} is outside Greater London")
        want(p.get("reels"), f"pin {p.get('name')} has no reels")
        for reel in p.get("reels", []):
            url = reel["url"]
            seen[url] += 1
            if url not in raw:
                failures.append(f"pin {p['name']} references unknown reel {url}")
                continue
            # THE check.
            if reel.get("caption") != raw[url]["caption"]:
                failures.append(f"CAPTION MISMATCH on {url} (pin {p['name']}) - "
                                "a reel is attached to the wrong venue")

    # A reel may legitimately sit on several pins - that is listicle expansion, one reel
    # naming five restaurants. What must NOT happen is a reel appearing on more pins than
    # extraction ever found venues in it, which would mean a duplicate crept in.
    extracted_per_reel = collections.Counter(v["reel_url"] for v in extracted)
    for url, n in seen.items():
        if n > 1:
            want(n <= extracted_per_reel.get(url, 1),
                 f"reel {url} is on {n} pins but extraction found only "
                 f"{extracted_per_reel.get(url, 1)} venue(s) in it - duplicate pin")

    # 2. Extracted candidates carry untouched captions too.
    for v in extracted:
        url = v["reel_url"]
        if url not in raw:
            failures.append(f"extracted venue {v['candidate_name']} references unknown reel {url}")
        elif v.get("caption") != raw[url]["caption"]:
            failures.append(f"CAPTION MISMATCH on extracted {v['candidate_name']} ({url})")

    # 3. Nothing silently vanished.
    accounted = set(seen) | {v["reel_url"] for v in extracted} | {r["reel_url"] for r in no_venue}
    missing = set(raw) - accounted
    want(not missing, f"{len(missing)} reels unaccounted for, e.g. {sorted(missing)[:3]}")

    # 4. Schema sanity on enriched fields.
    for p in pins:
        want(p.get("status") in ("open", "closed", "unknown"),
             f"pin {p.get('name')} has bad status {p.get('status')!r}")
        r = p.get("rating")
        want(r is None or (isinstance(r, (int, float)) and 0 <= r <= 5),
             f"pin {p.get('name')} rating {r!r} is not on Google's 0-5 scale")
        pl = p.get("price_level")
        want(pl is None or (isinstance(pl, int) and 0 <= pl <= 4),
             f"pin {p.get('name')} price_level {pl!r} is not an int 0-4 "
             "(a PRICE_LEVEL_* enum leaked through unmapped)")
        h = p.get("hours")
        want(h is None or (isinstance(h, list) and len(h) == 7),
             f"pin {p.get('name')} hours is not null or 7 entries")

    if failures:
        print(f"FAIL - {len(failures)} problem(s):")
        for f in failures[:25]:
            print("  -", f)
        if len(failures) > 25:
            print(f"  ... and {len(failures) - 25} more")
        sys.exit(1)

    print(f"OK  {len(pins)} pins · {len(seen)} reels on the map · "
          f"{len(extracted)} extracted candidates · {len(no_venue)} with no venue")
    print(f"OK  all {len(raw)} raw reels accounted for, 0 caption mismatches")


if __name__ == "__main__":
    check()
