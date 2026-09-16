#!/usr/bin/env python3
"""Generate PLACES.md - a readable list of every place on the map.

Grouped by category, alphabetical, with address and a link to the reel(s).
Regenerate any time with: python3 scripts/build_list.py
"""
import json, pathlib, re
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
PINS = ROOT / "pins.json"
OUT = ROOT / "PLACES.md"

SECTIONS = [
    ("restaurant/food", "Eat & drink"),
    ("activity", "Things to do"),
    ("other", "Other"),
]
POSTCODE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b")


def area(address):
    """The outward postcode ('SW7', 'E8') is the most useful one-glance locator."""
    if not address:
        return ""
    m = POSTCODE.search(address)
    return m.group(1) if m else ""


def tidy(address):
    """Nominatim addresses repeat themselves - a venue named after its address comes back
    as "64 Old Compton Street, 64, Old Compton Street, London W1D 4UQ". Drop any segment
    already contained in one we've kept."""
    if not address:
        return "—"
    a = re.sub(r",?\s*(United Kingdom|England|Greater London)\b", "", address)
    kept = []
    for part in (x.strip() for x in a.split(",")):
        if not part:
            continue
        low = part.lower()
        if any(low == k.lower() or low in k.lower() for k in kept):
            continue
        kept = [k for k in kept if k.lower() not in low] + [part]
    out = re.sub(r"\s{2,}", " ", ", ".join(kept)).strip().strip(",")
    return out or "—"


def main():
    pins = json.loads(PINS.read_text())
    total_reels = len({r["url"] for p in pins for r in p["reels"]})

    out = [
        "# Places",
        "",
        f"Every place on [the map](https://faisal-ux-portfolio.github.io/london-map/), "
        f"grouped by category and listed A–Z.",
        "",
        f"**{len(pins)} places · {total_reels} reels** · generated {date.today().isoformat()}",
        "",
        "Regenerate with `python3 scripts/build_list.py`.",
        "",
    ]

    for key, heading in SECTIONS:
        group = sorted((p for p in pins if p.get("category") == key),
                       key=lambda p: p["name"].lower())
        if not group:
            continue
        out += [f"## {heading} ({len(group)})", "",
                "| Place | Address | Area | Reel |", "|---|---|---|---|"]
        for p in group:
            links = " ".join(f"[{i + 1}]({r['url']})" if len(p["reels"]) > 1
                             else f"[watch]({r['url']})"
                             for i, r in enumerate(p["reels"]))
            name = p["name"].replace("|", "\\|")
            closed = " *(closed)*" if p.get("status") == "closed" else ""
            out.append(f"| **{name}**{closed} | {tidy(p.get('address')).replace('|', '')} "
                       f"| {area(p.get('address'))} | {links} |")
        out.append("")

    OUT.write_text("\n".join(out))
    print(f"wrote {OUT.name}: {len(pins)} places, {total_reels} reels")
    for key, heading in SECTIONS:
        n = sum(1 for p in pins if p.get("category") == key)
        if n:
            print(f"  {heading}: {n}")


if __name__ == "__main__":
    main()
