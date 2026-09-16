#!/usr/bin/env python3
"""Build the served pins.json from mapped-pins.json.

Merges reels that describe the same venue into one pin carrying a reels[] array.

Merge rule (DECISIONS.md D-008): coordinates alone are NEVER enough - Nan Hotpot and
RedBox Karaoke share an exact building centroid and are different businesses. Two rows
merge only if they are co-located AND their names are similar. Co-located rows whose
names disagree are kept apart and flagged.
"""
import json, re, sys, difflib, hashlib, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
NAME_SIM_MERGE = 0.60
COORD_DP = 4  # ~11m


def normalize(name: str) -> str:
    n = name.lower()
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    n = re.sub(r"\b(the|london|ltd|limited|restaurant|cafe|bar)\b", " ", n)
    return " ".join(n.split())


def same_venue(a: str, b: str) -> bool:
    """Same venue if names are similar, or one name contains the other.

    Containment matters because the data holds "Forno" and "Forno, Hackney" as separate
    rows - the ratio scores that pair 0.55, just under the bar, while it is plainly one
    restaurant. Containment is only ever consulted for rows that already share a building
    centroid, so it cannot merge two unrelated venues that happen to share a word.
    """
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return False
    if na == nb or na.startswith(nb + " ") or nb.startswith(na + " "):
        return True
    return difflib.SequenceMatcher(None, na, nb).ratio() >= NAME_SIM_MERGE


def price_to_int(v):
    """Google's new API returns a PRICE_LEVEL_* enum; legacy rows hold 0-4 ints."""
    if v is None or isinstance(v, int):
        return v
    return {"PRICE_LEVEL_FREE": 0, "PRICE_LEVEL_INEXPENSIVE": 1, "PRICE_LEVEL_MODERATE": 2,
            "PRICE_LEVEL_EXPENSIVE": 3, "PRICE_LEVEL_VERY_EXPENSIVE": 4}.get(v)


def build():
    rows = json.loads((DATA / "mapped-pins.json").read_text())

    groups, flagged = [], []
    for r in rows:
        key = (round(r["lat"], COORD_DP), round(r["lng"], COORD_DP))
        for g in groups:
            if g["key"] != key:
                continue
            if same_venue(g["rows"][0]["place_name"], r["place_name"]):
                g["rows"].append(r)
                break
            # Co-located but a different name: do NOT merge. Flag both for a human.
            flagged.append({
                "reason": "same_coords_different_name",
                "names": [g["rows"][0]["place_name"], r["place_name"]],
                "lat": r["lat"], "lng": r["lng"],
                "reel_urls": [g["rows"][0]["reel_url"], r["reel_url"]],
            })
        else:
            groups.append({"key": key, "rows": [r]})

    pins = []
    for g in groups:
        rs = g["rows"]
        head = rs[0]
        enriched = next((x for x in rs if x.get("rating") is not None), head)
        pins.append({
            "id": "seed:" + hashlib.sha1(
                f"{normalize(head['place_name'])}|{g['key']}".encode()).hexdigest()[:12],
            "name": head["place_name"],
            "lat": head["lat"],
            "lng": head["lng"],
            "address": head.get("address"),
            "category": head.get("category") or "other",
            "status": "unknown",
            "rating": enriched.get("rating"),
            "rating_count": enriched.get("rating_count"),
            "price_level": price_to_int(enriched.get("price_level")),
            "hours": enriched.get("hours"),
            "website": None,
            "phone": None,
            "place_id": None,
            "reels": [{"url": x["reel_url"], "caption": x["caption"], "owner": x.get("owner")}
                      for x in rs],
        })

    pins.sort(key=lambda p: p["name"].lower())
    (ROOT / "pins.json").write_text(json.dumps(pins, ensure_ascii=False, separators=(",", ":")))

    existing = json.loads((DATA / "needs-review.json").read_text()) if (DATA / "needs-review.json").exists() else []
    existing = [x for x in existing if x.get("reason") != "same_coords_different_name"] + flagged
    (DATA / "needs-review.json").write_text(json.dumps(existing, indent=1, ensure_ascii=False))

    merged = sum(len(p["reels"]) - 1 for p in pins)
    print(f"{len(rows)} mapped rows -> {len(pins)} pins ({merged} reels merged into existing venues)")
    print(f"  {sum(1 for p in pins if p['rating'] is not None)} pins carry a rating")
    print(f"  {len(flagged)} co-located name mismatches flagged for review (not merged)")
    for f in flagged:
        print(f"    ! {f['names'][0]}  <->  {f['names'][1]}")
    size = (ROOT / "pins.json").stat().st_size
    print(f"wrote pins.json ({size/1024:.0f} KB)")


if __name__ == "__main__":
    build()
