#!/usr/bin/env python3
"""Enrich pins.json from Google Places, and geocode the venues extracted from listicles.

  python3 scripts/enrich.py --dry-run        # show the worklist and queries, spend nothing
  python3 scripts/enrich.py --limit 50       # the budget guard: stop and report after 50
  python3 scripts/enrich.py                  # everything not already cached

Idempotent: every API response is cached in data/cache.json keyed by the exact query, so
re-running only pays for venues it has not seen. Delete a cache entry to force a refresh.
"""
import argparse, hashlib, json, pathlib, sys, time, urllib.error

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import places

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PINS = ROOT / "pins.json"
CACHE = DATA / "cache.json"
REVIEW = DATA / "needs-review.json"

# Roughly-central points for area hints seen in the extracted captions, so a candidate
# with no coordinates at least gets biased to the right part of London.
AREAS = {
    "soho": (51.5137, -0.1341), "shoreditch": (51.5265, -0.0784), "hackney": (51.5450, -0.0553),
    "camden": (51.5390, -0.1426), "peckham": (51.4739, -0.0695), "brixton": (51.4613, -0.1156),
    "chinatown": (51.5116, -0.1310), "china town": (51.5116, -0.1310),
    "mayfair": (51.5096, -0.1475), "marylebone": (51.5186, -0.1500),
    "notting hill": (51.5090, -0.1960), "hammersmith": (51.4927, -0.2240),
    "islington": (51.5362, -0.1033), "clapham": (51.4618, -0.1384),
    "borough market": (51.5055, -0.0910), "covent garden": (51.5129, -0.1243),
    "kensington": (51.4991, -0.1938), "belgravia": (51.4977, -0.1533),
    "battersea": (51.4791, -0.1450), "whitechapel": (51.5195, -0.0600),
    "city of london": (51.5155, -0.0922), "leyton": (51.5686, -0.0155),
    "greenwich": (51.4810, -0.0050), "wembley": (51.5560, -0.2795),
    "green lanes": (51.5810, -0.0980), "east london": (51.5300, -0.0500),
    "west london": (51.5100, -0.2000), "north london": (51.5600, -0.1200),
    "south london": (51.4600, -0.1000), "harrods": (51.4994, -0.1632),
    "seven dials": (51.5145, -0.1265), "portobello road": (51.5175, -0.2050),
}
LONDON = (51.5074, -0.1278)


def load(p, default):
    return json.loads(p.read_text()) if p.exists() else default


def qkey(q, lat, lng):
    return hashlib.sha1(f"{q}|{round(lat,4) if lat else ''}|{round(lng,4) if lng else ''}"
                        .encode()).hexdigest()[:16]


def build_worklist(pins, extracted, refresh_all):
    """Existing pins that still lack data, plus every extracted candidate."""
    work = []
    for p in pins:
        needs = refresh_all or p.get("place_id") is None or p.get("rating") is None
        if not needs:
            continue
        addressy = places.looks_like_address(p["name"])
        # An address-named pin searches better by its address than by its "name".
        query = p.get("address") if addressy else f"{p['name']}, London"
        work.append({"kind": "pin", "pin_id": p["id"], "name": p["name"],
                     "query": query or p["name"], "lat": p["lat"], "lng": p["lng"],
                     "trusted_coords": True, "adopt_name": addressy})
    for v in extracted:
        hint = (v.get("area_hint") or "").strip().lower()
        ll = AREAS.get(hint, LONDON)
        q = f"{v['candidate_name']}, {v['area_hint']}, London" if v.get("area_hint") \
            else f"{v['candidate_name']}, London"
        work.append({"kind": "candidate", "name": v["candidate_name"], "query": q,
                     "lat": ll[0], "lng": ll[1], "trusted_coords": False, "adopt_name": True,
                     "reel": {"url": v["reel_url"], "caption": v["caption"], "owner": v.get("owner")}})
    return work


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="stop after N API calls (0 = no cap)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--refresh-all", action="store_true",
                    help="re-query pins that already have data")
    args = ap.parse_args()

    pins = load(PINS, [])
    extracted = load(DATA / "extracted-venues.json", [])
    cache = load(CACHE, {})
    work = build_worklist(pins, extracted, args.refresh_all)

    uncached = [w for w in work if qkey(w["query"], w["lat"], w["lng"]) not in cache]
    print(f"worklist: {len(work)} venues ({sum(1 for w in work if w['kind']=='pin')} existing pins, "
          f"{sum(1 for w in work if w['kind']=='candidate')} new candidates)")
    print(f"  {len(work)-len(uncached)} already cached · {len(uncached)} need an API call")
    if args.limit:
        print(f"  budget guard: stopping after {args.limit} call(s)")

    if args.dry_run:
        for w in uncached[:15]:
            print(f"    [{w['kind']:<9}] {w['query']}")
        if len(uncached) > 15:
            print(f"    ... and {len(uncached)-15} more")
        print("\ndry run - no API calls made, nothing written")
        return

    calls = 0
    for w in work:
        k = qkey(w["query"], w["lat"], w["lng"])
        if k in cache:
            continue
        if args.limit and calls >= args.limit:
            break
        try:
            res = places.search(w["query"], w["lat"], w["lng"],
                                radius_m=400 if w["trusted_coords"] else 6000)
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:300]
            print(f"\nAPI error {e.code} on {w['query']!r}:\n  {body}")
            print(f"stopped after {calls} call(s); {len(cache)} cached results kept")
            CACHE.write_text(json.dumps(cache))
            sys.exit(1)
        calls += 1
        cache[k] = {"query": w["query"], "results": res, "at": int(time.time())}
        time.sleep(0.05)

    CACHE.write_text(json.dumps(cache))
    print(f"\n{calls} API call(s) made; cache now holds {len(cache)} queries")

    applied = apply_results(pins, work, cache)
    print(f"\n{applied['accepted']} accepted · {applied['review']} to review · "
          f"{applied['rejected']} rejected · {applied['pending']} not looked up yet")
    print(f"pins.json: {applied['total']} pins ({applied['new']} new, "
          f"{applied['closed']} permanently closed, {applied['renamed']} renamed from an address)")
    print("\nrun `python3 scripts/selfcheck.py` to verify integrity")


def apply_results(pins, work, cache):
    by_id = {p["id"]: p for p in pins}
    by_place = {p["place_id"]: p for p in pins if p.get("place_id")}
    review = [r for r in load(REVIEW, []) if r.get("reason") == "same_coords_different_name"]
    stats = dict(accepted=0, review=0, rejected=0, pending=0, new=0, closed=0, renamed=0)

    for w in work:
        entry = cache.get(qkey(w["query"], w["lat"], w["lng"]))
        if entry is None:
            stats["pending"] += 1
            continue
        ll = (w["lat"], w["lng"]) if w["trusted_coords"] else None
        verdict, best, scored = places.decide(w["name"], ll, entry["results"])

        if verdict != "accept":
            stats["review" if verdict == "review" else "rejected"] += 1
            review.append({
                "reason": "low_confidence" if verdict == "review" else
                          ("zero_results" if not entry["results"] else "no_plausible_match"),
                "candidate_name": w["name"], "query": w["query"], "kind": w["kind"],
                "reel": w.get("reel"),
                "options": [{"name": places.disp(s["cand"]),
                             "address": s["cand"].get("formattedAddress"),
                             "combined": round(s["combined"], 3),
                             "name_sim": round(s["name_sim"], 3),
                             "dist_km": None if s["dist_km"] is None else round(s["dist_km"], 2)}
                            for s in scored[:3]],
            })
            continue

        stats["accepted"] += 1
        f = places.to_pin_fields(best["cand"])
        if f["status"] == "closed":
            stats["closed"] += 1

        target = by_place.get(f["place_id"])
        if w["kind"] == "pin":
            pin = by_id[w["pin_id"]]
            if target is not None and target is not pin:
                # This pin is the same venue as one already enriched - fold the reels in.
                target["reels"].extend(r for r in pin["reels"]
                                       if r["url"] not in {x["url"] for x in target["reels"]})
                pins.remove(pin)
                continue
            if w["adopt_name"] and f["name"]:
                stats["renamed"] += 1
                pin["name"] = f["name"]
            for key in ("place_id", "address", "status", "rating", "rating_count",
                        "price_level", "hours", "website", "phone"):
                if f.get(key) is not None:
                    pin[key] = f[key]
            if f["lat"] and f["lng"]:
                pin["lat"], pin["lng"] = f["lat"], f["lng"]
            by_place[f["place_id"]] = pin
        else:
            reel = w["reel"]
            if target is not None:
                if reel["url"] not in {x["url"] for x in target["reels"]}:
                    target["reels"].append(reel)
                continue
            new = {"id": "g:" + f["place_id"], "name": f["name"], "lat": f["lat"], "lng": f["lng"],
                   "address": f["address"], "category": guess_category(best["cand"], reel),
                   "status": f["status"], "rating": f["rating"], "rating_count": f["rating_count"],
                   "price_level": f["price_level"], "hours": f["hours"], "website": f["website"],
                   "phone": f["phone"], "place_id": f["place_id"], "reels": [reel]}
            pins.append(new)
            by_place[f["place_id"]] = new
            stats["new"] += 1

    pins.sort(key=lambda p: p["name"].lower())
    PINS.write_text(json.dumps(pins, ensure_ascii=False, separators=(",", ":")))
    REVIEW.write_text(json.dumps(review, indent=1, ensure_ascii=False))
    stats["total"] = len(pins)
    return stats


FOOD_TYPES = ("restaurant", "cafe", "bar", "bakery", "food", "meal", "coffee", "pub",
              "ice_cream", "dessert", "brunch", "breakfast", "pizza", "sandwich")


def guess_category(place, reel):
    t = (place.get("primaryType") or "").lower()
    if any(k in t for k in FOOD_TYPES):
        return "restaurant/food"
    if t:
        return "activity"
    text = ((reel.get("caption") or "") + " " + (reel.get("owner") or "")).lower()
    return "restaurant/food" if any(k in text for k in
                                    ("eat", "food", "restaurant", "brunch", "dinner", "lunch",
                                     "coffee", "bar", "cocktail", "dessert")) else "activity"


if __name__ == "__main__":
    main()
