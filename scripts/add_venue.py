#!/usr/bin/env python3
"""Add one venue to the map from a shared Instagram reel.

Run by .github/workflows/add-venue.yml when the iOS Shortcut fires a repository_dispatch.

  python3 scripts/add_venue.py --name "Tanakatsu" --url https://instagram.com/reel/xyz/

Never exits non-zero for a venue it cannot place - that would fail the workflow and block
everything else in the run. An unresolvable venue lands in data/needs-review.json instead,
and the map keeps working.
"""
import argparse, json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import places, geocode

ROOT = pathlib.Path(__file__).resolve().parent.parent
PINS = ROOT / "pins.json"
REVIEW = ROOT / "data" / "needs-review.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    name = args.name.strip()
    url = args.url.strip()
    if not name or not url:
        print("::warning::empty venue name or url, nothing to do")
        return

    pins = json.loads(PINS.read_text())
    if any(r["url"] == url for p in pins for r in p["reels"]):
        print(f"already on the map: {url}")
        return

    reel = {"url": url, "caption": args.note or f"Added from a shared reel: {name}",
            "owner": None}

    try:
        rows = geocode.nominatim(f"{name}, London")
    except Exception as e:
        print(f"::warning::lookup failed for {name!r}: {type(e).__name__}: {e}")
        rows = []

    cands = geocode.to_google_shape(rows)
    verdict, best, scored = places.decide(name, None, cands)

    if verdict != "accept":
        review = json.loads(REVIEW.read_text()) if REVIEW.exists() else []
        review.append({"reason": "shared_" + ("no_match" if not cands else "low_confidence"),
                       "candidate_name": name, "query": f"{name}, London", "kind": "shared",
                       "reel": reel,
                       "options": [{"name": places.disp(s["cand"]),
                                    "address": s["cand"].get("formattedAddress"),
                                    "combined": round(s["combined"], 3)} for s in scored[:3]]})
        REVIEW.write_text(json.dumps(review, indent=1, ensure_ascii=False))
        print(f"::warning::could not place {name!r} confidently - sent to needs-review")
        return

    c = best["cand"]
    loc = c["location"]
    existing = next((p for p in pins if p.get("place_id") == c["id"]), None)
    if existing:
        existing["reels"].append(reel)
        print(f"added reel to existing pin: {existing['name']}")
    else:
        pins.append({
            "id": "osm:" + c["id"].split(":", 1)[1], "name": places.disp(c),
            "lat": loc["latitude"], "lng": loc["longitude"],
            "address": geocode.short_address(c.get("formattedAddress")),
            "category": geocode.category_for(c, args.note), "status": "unknown",
            "rating": None, "rating_count": None, "price_level": None, "hours": None,
            "website": None, "phone": None, "place_id": c["id"], "reels": [reel],
        })
        print(f"added new pin: {places.disp(c)}")

    pins.sort(key=lambda p: p["name"].lower())
    PINS.write_text(json.dumps(pins, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
