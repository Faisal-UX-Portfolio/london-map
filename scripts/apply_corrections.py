#!/usr/bin/env python3
"""Apply hand-verified fixes from data/manual-corrections.json to pins.json.

Some venues cannot be resolved automatically - they are absent from OpenStreetMap, or the
original geocoding landed on a street instead of the business. Where a caption names the
place unambiguously, the fix is recorded here with its evidence rather than typed straight
into pins.json, so it is reviewable and survives a pipeline re-run.

Idempotent: a correction already applied is skipped.
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PINS = ROOT / "pins.json"
FIXES = ROOT / "data" / "manual-corrections.json"


def main():
    pins = json.loads(PINS.read_text())
    fixes = json.loads(FIXES.read_text())
    by_name = {p["name"]: p for p in pins}
    applied = skipped = missing = 0

    for fix in fixes:
        target = by_name.get(fix["match_name"])
        if target is None:
            if fix["name"] in by_name:
                skipped += 1            # already applied on an earlier run
            else:
                print(f"  ! no pin named {fix['match_name']!r} and none named "
                      f"{fix['name']!r} either - correction is stale")
                missing += 1
            continue
        target["name"] = fix["name"]
        for key in ("lat", "lng", "address"):
            if key in fix:
                target[key] = fix[key]
        moved = " (relocated)" if "lat" in fix else ""
        print(f"  {fix['match_name']} -> {fix['name']}{moved}")
        applied += 1

    pins.sort(key=lambda p: p["name"].lower())
    PINS.write_text(json.dumps(pins, ensure_ascii=False, separators=(",", ":")))
    print(f"\n{applied} applied · {skipped} already applied · {missing} stale")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
