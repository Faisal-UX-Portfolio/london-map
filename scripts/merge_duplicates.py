#!/usr/bin/env python3
"""Merge pins that are the same venue under two records.

Dedupe elsewhere keys on place_id (DECISIONS.md D-008), which cannot match a pin that has
no place_id against one that does - exactly what happens when a pin from the original
export and a pin from geocoding describe the same restaurant.

Safe because it requires BOTH a matching name AND near-identical coordinates. "Three
Uncles" on Devonshire Row and "Three Uncles" on Old Bailey are different branches and stay
separate.
"""
import json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import places

ROOT = pathlib.Path(__file__).resolve().parent.parent
PINS = ROOT / "pins.json"
SAME_VENUE_M = 200


def main():
    dry = "--dry-run" in sys.argv
    pins = json.loads(PINS.read_text())
    merged, out = 0, []

    for pin in pins:
        hit = None
        for kept in out:
            if places.name_similarity(kept["name"], pin["name"]) < 0.90:
                continue
            d = places.haversine_km((kept["lat"], kept["lng"]), (pin["lat"], pin["lng"])) * 1000
            if d <= SAME_VENUE_M:
                hit = (kept, d)
                break
        if hit is None:
            out.append(pin)
            continue

        kept, d = hit
        # Keep the record that carries a place_id - it came from a real venue lookup
        # rather than a bare address geocode.
        if not kept.get("place_id") and pin.get("place_id"):
            pin["reels"] = pin["reels"] + [r for r in kept["reels"]
                                           if r["url"] not in {x["url"] for x in pin["reels"]}]
            out[out.index(kept)] = pin
            winner = pin
        else:
            kept["reels"].extend(r for r in pin["reels"]
                                 if r["url"] not in {x["url"] for x in kept["reels"]})
            winner = kept
        print(f"  merged {pin['name']!r} ({d:.0f}m apart) -> {len(winner['reels'])} reel(s)")
        merged += 1

    out.sort(key=lambda p: p["name"].lower())
    print(f"\n{len(pins)} -> {len(out)} pins ({merged} merged)")
    if dry:
        print("dry run - nothing written")
        return
    PINS.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
