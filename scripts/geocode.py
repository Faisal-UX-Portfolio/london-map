#!/usr/bin/env python3
"""Geocode venues onto the map using Nominatim (OpenStreetMap's search service).

This is MAPPING, not enrichment - it puts places on the map. It does not fetch ratings
or opening hours (see DECISIONS.md D-014/D-015 for why those were dropped).

Two jobs:
  1. Place the venues extracted from listicle captions that have no coordinates yet.
  2. Re-resolve pins the original build named after a street ("10 Wakley St"), which
     Nominatim usually identifies correctly ("Tanakatsu").

  python3 scripts/geocode.py --dry-run
  python3 scripts/geocode.py --limit 20
  python3 scripts/geocode.py

Nominatim is a free shared service with a strict 1 request/second limit and a mandatory
User-Agent. Respect both or it will (rightly) block us.
"""
import argparse, json, pathlib, re, sys, time, urllib.parse, urllib.request, urllib.error

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import places

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PINS = ROOT / "pins.json"
CACHE = DATA / "geocode-cache.json"
REVIEW = DATA / "needs-review.json"

URL = "https://nominatim.openstreetmap.org/search"
UA = "LondonReelsMap/1.0 (+https://github.com/Faisal-UX-Portfolio/london-map)"
MIN_INTERVAL_S = 1.1              # Nominatim's published limit is 1/sec. Do not lower.
LONDON_VIEWBOX = "-0.55,51.75,0.35,51.25"   # W,N,E,S - Greater London

# Nominatim happily returns streets and suburbs. We want somewhere you can walk into.
PLACE_TYPES = {
    "restaurant", "cafe", "bar", "pub", "fast_food", "food_court", "ice_cream",
    "bakery", "pastry", "confectionery", "deli", "nightclub", "biergarten",
    "museum", "gallery", "attraction", "theatre", "cinema", "arts_centre", "zoo",
    "hotel", "marketplace", "department_store", "shop", "leisure", "park",
    "bowling_alley", "escape_game", "amusement_arcade", "spa", "garden",
}
REJECT_CLASSES = {"highway", "boundary", "place", "landuse", "railway", "waterway"}

_last = 0.0


def nominatim(query, bounded=True, timeout=20):
    global _last
    wait = MIN_INTERVAL_S - (time.time() - _last)
    if wait > 0:
        time.sleep(wait)
    _last = time.time()
    qs = urllib.parse.urlencode({
        "q": query, "format": "jsonv2", "limit": 5, "countrycodes": "gb",
        "addressdetails": 1, "viewbox": LONDON_VIEWBOX, "bounded": 1 if bounded else 0,
    })
    req = urllib.request.Request(f"{URL}?{qs}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def to_google_shape(rows):
    """Adapt Nominatim rows to the shape places.decide() already understands, so the
    scoring rules (and their tests) are shared rather than reimplemented."""
    out = []
    for r in rows:
        if r.get("class") in REJECT_CLASSES:
            continue
        if r.get("type") not in PLACE_TYPES and r.get("class") not in (
                "amenity", "shop", "tourism", "leisure"):
            continue
        out.append({
            "id": f"osm:{r.get('osm_type')}/{r.get('osm_id')}",
            "displayName": {"text": r.get("name") or ""},
            "formattedAddress": r.get("display_name"),
            "location": {"latitude": float(r["lat"]), "longitude": float(r["lon"])},
            "_type": r.get("type"),
            "_class": r.get("class"),
        })
    return [o for o in out if o["displayName"]["text"]]


FOOD = {"restaurant", "cafe", "bar", "pub", "fast_food", "ice_cream", "bakery",
        "pastry", "confectionery", "deli", "food_court", "biergarten"}


def category_for(cand, fallback_text=""):
    t = cand.get("_type")
    if t in FOOD:
        return "restaurant/food"
    if cand.get("_class") in ("tourism", "leisure") or t in (
            "museum", "gallery", "attraction", "theatre", "cinema", "park"):
        return "activity"
    text = fallback_text.lower()
    return "restaurant/food" if any(k in text for k in (
        "eat", "food", "restaurant", "brunch", "dinner", "lunch", "coffee", "bar",
        "cocktail", "dessert", "bakery", "menu")) else "activity"


def short_address(display_name):
    """Nominatim display_name is a long comma chain; keep the useful head plus postcode."""
    if not display_name:
        return None
    parts = [p.strip() for p in display_name.split(",")]
    pc = next((p for p in reversed(parts) if re.match(r"^[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}$", p)), None)
    head = ", ".join(parts[:3])
    return f"{head}, London {pc}" if pc else f"{head}, London"


# An address pin's coordinate came from geocoding that same address, so anything this
# close is on the right doorstep. Beyond it we are guessing at a neighbour.
SAME_DOORSTEP_M = 130


def nearest_venue(ll, cands):
    scored = []
    for c in cands:
        loc = c["location"]
        d = places.haversine_km(ll, (loc["latitude"], loc["longitude"])) * 1000
        scored.append({"cand": c, "combined": round(max(0.0, 1 - d / 500), 3),
                       "name_sim": None, "dist_km": d / 1000})
    scored.sort(key=lambda x: x["dist_km"])
    if not scored:
        return "reject", None, []
    return ("accept" if scored[0]["dist_km"] * 1000 <= SAME_DOORSTEP_M else "review"), \
        scored[0], scored


def build_worklist(pins, extracted):
    work = []
    for p in pins:
        if places.looks_like_address(p["name"]) and not p.get("place_id"):
            work.append({"kind": "pin", "pin_id": p["id"], "name": p["name"],
                         "query": f"{p['name']}, London", "ll": (p["lat"], p["lng"])})
    seen = set()
    for v in extracted:
        key = v["candidate_name"].strip().lower()
        q = f"{v['candidate_name']}, {v['area_hint']}, London" if v.get("area_hint") \
            else f"{v['candidate_name']}, London"
        work.append({"kind": "candidate", "name": v["candidate_name"], "query": q, "ll": None,
                     "reel": {"url": v["reel_url"], "caption": v["caption"], "owner": v.get("owner")},
                     "dup": key in seen})
        seen.add(key)
    return work


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    pins = json.loads(PINS.read_text())
    extracted = json.loads((DATA / "extracted-venues.json").read_text())
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    work = build_worklist(pins, extracted)
    todo = [w for w in work if w["query"] not in cache]

    print(f"worklist: {len(work)} ({sum(1 for w in work if w['kind']=='pin')} address-named pins, "
          f"{sum(1 for w in work if w['kind']=='candidate')} extracted candidates)")
    print(f"  {len(work)-len(todo)} cached · {len(todo)} to look up "
          f"(~{len(todo)*MIN_INTERVAL_S/60:.1f} min at 1 req/sec)")
    if args.dry_run:
        for w in todo[:12]:
            print(f"    [{w['kind']:<9}] {w['query']}")
        print(f"    ... and {max(0,len(todo)-12)} more\n\ndry run - nothing fetched, nothing written")
        return

    n = 0
    for w in work:
        if w["query"] in cache:
            continue
        if args.limit and n >= args.limit:
            break
        try:
            cache[w["query"]] = nominatim(w["query"])
        except urllib.error.HTTPError as e:
            print(f"  Nominatim HTTP {e.code} on {w['query']!r} - stopping, {n} fetched")
            break
        except Exception as e:
            print(f"  {type(e).__name__} on {w['query']!r}: {e}")
            cache[w["query"]] = []
        n += 1
        if n % 20 == 0:
            print(f"  ... {n}/{len(todo)}")
            CACHE.write_text(json.dumps(cache))
    CACHE.write_text(json.dumps(cache))
    print(f"\n{n} lookups made; cache holds {len(cache)}")
    apply_results(pins, work, cache)


def apply_results(pins, work, cache):
    by_id = {p["id"]: p for p in pins}
    by_place = {p["place_id"]: p for p in pins if p.get("place_id")}
    review = [r for r in json.loads(REVIEW.read_text())] if REVIEW.exists() else []
    review = [r for r in review if r.get("reason") == "same_coords_different_name"]
    added = renamed = merged = skipped = 0

    for w in work:
        rows = cache.get(w["query"])
        if rows is None:
            skipped += 1
            continue
        cands = to_google_shape(rows)
        if w["kind"] == "pin":
            # These pins are named after a street, so comparing that name to a venue name
            # is meaningless - "10 Wakley St" vs "Tanakatsu" scores near zero. What we
            # actually trust here is the coordinate. Take the nearest real venue to it.
            verdict, best, scored = nearest_venue(w["ll"], cands)
        else:
            verdict, best, scored = places.decide(w["name"], w["ll"], cands)

        if verdict != "accept":
            review.append({
                "reason": "geocode_" + ("no_match" if not cands else "low_confidence"),
                "candidate_name": w["name"], "query": w["query"], "kind": w["kind"],
                "reel": w.get("reel"),
                "options": [{"name": places.disp(s["cand"]),
                             "address": s["cand"].get("formattedAddress"),
                             "combined": round(s["combined"], 3)} for s in scored[:3]],
            })
            continue

        c = best["cand"]
        loc = c["location"]
        if w["kind"] == "pin":
            pin = by_id.get(w["pin_id"])
            if pin is None:
                continue
            pin["name"] = places.disp(c)
            pin["address"] = short_address(c.get("formattedAddress")) or pin["address"]
            pin["place_id"] = c["id"]
            pin["lat"], pin["lng"] = loc["latitude"], loc["longitude"]
            by_place[c["id"]] = pin
            renamed += 1
            continue

        target = by_place.get(c["id"])
        if target is not None:
            if w["reel"]["url"] not in {x["url"] for x in target["reels"]}:
                target["reels"].append(w["reel"])
                merged += 1
            continue
        new = {
            "id": "osm:" + c["id"].split(":", 1)[1], "name": places.disp(c),
            "lat": loc["latitude"], "lng": loc["longitude"],
            "address": short_address(c.get("formattedAddress")),
            "category": category_for(c, (w["reel"].get("caption") or "")),
            "status": "unknown", "rating": None, "rating_count": None, "price_level": None,
            "hours": None, "website": None, "phone": None, "place_id": c["id"],
            "reels": [w["reel"]],
        }
        pins.append(new)
        by_place[c["id"]] = new
        added += 1

    pins.sort(key=lambda p: p["name"].lower())
    PINS.write_text(json.dumps(pins, ensure_ascii=False, separators=(",", ":")))
    REVIEW.write_text(json.dumps(review, indent=1, ensure_ascii=False))
    print(f"{added} new pins · {renamed} address-named pins resolved · "
          f"{merged} reels merged into existing venues · {len(review)} to review")
    print(f"pins.json now holds {len(pins)} places")


def _selftest():
    rows = [
        {"class": "highway", "type": "residential", "name": "Old Brompton Road",
         "lat": "51.49", "lon": "-0.18", "osm_type": "way", "osm_id": 1},
        {"class": "amenity", "type": "restaurant", "name": "Tanakatsu", "lat": "51.53",
         "lon": "-0.10", "osm_type": "node", "osm_id": 2, "display_name": "Tanakatsu, 10, Wakley Street, Islington, London, EC1V 7LT"},
    ]
    out = to_google_shape(rows)
    # A street must never survive - adopting one is exactly how the Overpass attempt
    # turned "85 Old Brompton Road" into "Old Brompton Road".
    assert len(out) == 1 and out[0]["displayName"]["text"] == "Tanakatsu", out
    assert category_for(out[0]) == "restaurant/food"
    assert "EC1V 7LT" in short_address(rows[1]["display_name"])
    assert to_google_shape([{"class": "place", "type": "suburb", "name": "Soho",
                             "lat": "51.5", "lon": "-0.1", "osm_type": "node", "osm_id": 3}]) == []
    print("geocode.py selftest OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        main()
