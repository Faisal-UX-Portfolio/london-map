#!/usr/bin/env python3
"""Extract venue-name candidates from unmapped Instagram reel captions.

Two phases, deliberately split so the id-integrity assert lives in Python and never
depends on a model behaving:

    prepare  -> writes data/batches/batch-NN.in.json for subagents to read
    collect  -> validates subagent output and merges to data/extracted-venues.json

The join key is a short hash of the reel URL, present in both directions. List position
is never used to match anything (see DECISIONS.md D-006).
"""
import json, re, sys, hashlib, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
BATCH_DIR = ROOT / "data" / "batches"
BATCH_SIZE = 20

# Captions that are cooking recipes, not venue recommendations. Cheap to catch here;
# no reason to spend a subagent call on them.
# Split deliberately. "ingredients" alone is NOT enough - venue reviews say things like
# "high volume, great ingredients", and an early version of this filter binned three real
# venues (Pasta Station, Kebhouze, a Soho pasta spot) on that word alone. A weak signal
# needs a second one to count.
STRONG_RECIPE_RE = re.compile(
    r"\b(serves \d|method:|tbsp|tsp|marinate|preheat|bake for|kcal|"
    r"g protein|recipe below|full recipe)\b", re.I)
WEAK_RECIPE_RE = re.compile(r"\b(ingredients?|oven|whisk|saucepan|simmer)\b", re.I)


def is_recipe(caption: str) -> bool:
    if STRONG_RECIPE_RE.search(caption):
        return True
    return len({m.lower() for m in WEAK_RECIPE_RE.findall(caption)}) >= 2


def reel_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:12]


def load_unmapped():
    return json.loads((ROOT / "data" / "unmapped-reels.json").read_text())


def prepare():
    reels = load_unmapped()
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    for stale in BATCH_DIR.glob("*.json"):
        stale.unlink()

    skipped, todo = [], []
    for r in reels:
        row = {"id": reel_id(r["url"]), "caption": r["caption"] or "", "owner": r.get("owner") or ""}
        if is_recipe(row["caption"]):
            skipped.append({**row, "no_venue": True, "reason": "recipe", "venues": []})
        else:
            todo.append(row)

    # ids must be unique or the whole scheme is worthless - fail loudly, now.
    all_ids = [r["id"] for r in skipped + todo]
    assert len(all_ids) == len(set(all_ids)), "duplicate reel id - hash collision or duplicate url"

    (BATCH_DIR / "prefiltered.json").write_text(json.dumps(skipped, indent=1, ensure_ascii=False))

    batches = [todo[i:i + BATCH_SIZE] for i in range(0, len(todo), BATCH_SIZE)]
    for n, batch in enumerate(batches, 1):
        (BATCH_DIR / f"batch-{n:02d}.in.json").write_text(
            json.dumps(batch, indent=1, ensure_ascii=False))

    print(f"{len(reels)} unmapped reels")
    print(f"  {len(skipped)} prefiltered as recipes (no subagent call)")
    print(f"  {len(todo)} to extract across {len(batches)} batches of <= {BATCH_SIZE}")
    return len(batches)


def collect():
    reels = load_unmapped()
    by_id = {reel_id(r["url"]): r for r in reels}

    rows = json.loads((BATCH_DIR / "prefiltered.json").read_text())

    for infile in sorted(BATCH_DIR.glob("batch-*.in.json")):
        outfile = infile.with_name(infile.name.replace(".in.json", ".out.json"))
        if not outfile.exists():
            sys.exit(f"missing subagent output: {outfile.name}")
        sent = json.loads(infile.read_text())
        got = json.loads(outfile.read_text())

        in_ids = {r["id"] for r in sent}
        out_ids = [r["id"] for r in got]
        # The three checks that make misalignment impossible rather than unlikely.
        assert len(out_ids) == len(set(out_ids)), f"{outfile.name}: duplicate id in output"
        assert set(out_ids) == in_ids, (
            f"{outfile.name}: id set mismatch - "
            f"missing {sorted(in_ids - set(out_ids))}, unexpected {sorted(set(out_ids) - in_ids)}")
        rows.extend(got)

    seen = [r["id"] for r in rows]
    assert len(seen) == len(set(seen)), "an id was processed by more than one batch"
    assert set(seen) == set(by_id), "collected ids do not match the unmapped reel set"

    # Attach the real reel url from OUR map. The model never saw a url, so it cannot
    # have mangled one.
    venues, no_venue = [], []
    for row in rows:
        src = by_id[row["id"]]
        if row.get("no_venue") or not row.get("venues"):
            no_venue.append({"reel_url": src["url"], "reason": row.get("reason") or "no_venue_found"})
            continue
        for v in row["venues"]:
            venues.append({
                "candidate_name": v["name"],
                "area_hint": v.get("area_hint"),
                "source_signal": v.get("source_signal"),
                "reel_url": src["url"],
                "caption": src["caption"],
                "owner": src.get("owner"),
            })

    out = ROOT / "data" / "extracted-venues.json"
    out.write_text(json.dumps(venues, indent=1, ensure_ascii=False))
    (ROOT / "data" / "no-venue-reels.json").write_text(json.dumps(no_venue, indent=1, ensure_ascii=False))

    multi = len(venues) - len({v["reel_url"] for v in venues})
    print(f"{len(venues)} venue candidates from {len({v['reel_url'] for v in venues})} reels")
    print(f"  {multi} came from listicle expansion (extra venues beyond one per reel)")
    print(f"  {len(no_venue)} reels have no usable venue")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "prepare"
    {"prepare": prepare, "collect": collect}[cmd]()
