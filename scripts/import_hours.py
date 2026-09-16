#!/usr/bin/env python3
"""Import opening hours from a PLACES.md that has an Hours column.

  python3 scripts/import_hours.py ~/Downloads/PLACES.md
  python3 scripts/import_hours.py ~/Downloads/PLACES.md --dry-run
  python3 scripts/import_hours.py --selftest

Writes three things per pin:
  hours        7 display strings, Monday first  ("Mon: 12pm-11pm")   - null if unparsed
  hours_text   the original human string, always kept
  open_ranges  7 lists of [startMin, endMin] for an accurate "Open now"

The source strings are free text written by a human/LLM, so the parser is deliberately
strict: anything it cannot read confidently yields hours=null and keeps hours_text, which
the app still displays. A venue with no hours shown is a minor annoyance; a venue shown as
open when it is shut sends someone across London for nothing.
"""
import argparse, json, pathlib, re, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import places

ROOT = pathlib.Path(__file__).resolve().parent.parent
PINS = ROOT / "pins.json"

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_IX = {d.lower(): i for i, d in enumerate(DAYS)}
DAY_IX.update({"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
               "friday": 4, "saturday": 5, "sunday": 6, "tues": 1, "thurs": 3, "weds": 2})

NOT_FOUND = {"not found", "n/a", "na", "unknown", ""}
CLOSED_PERMANENTLY = {"permanently closed", "closed permanently"}

TIME = r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?"
RANGE_RE = re.compile(rf"{TIME}\s*(?:-|–|—|to)\s*{TIME}", re.I)
PAREN_RE = re.compile(r"\([^)]*\)")


def _minutes(h, m, mer):
    h = int(h)
    m = int(m or 0)
    if mer:
        mer = mer.lower()
        if mer == "pm" and h != 12:
            h += 12
        elif mer == "am" and h == 12:
            h = 0
    return h * 60 + m


def parse_range(text):
    """'9:30am-6pm' -> (570, 1080). '6pm-1am' -> (1080, 1500) i.e. past midnight."""
    m = RANGE_RE.search(text)
    if not m:
        return None
    h1, m1, mer1, h2, m2, mer2 = m.groups()
    end = _minutes(h2, m2, mer2)
    # "12-11pm" omits the meridiem on the start; inherit from the end.
    start = _minutes(h1, m1, mer1 or mer2)
    if end <= start:
        if mer1 and mer2 and mer1.lower() == "pm" and mer2.lower() == "am":
            end += 24 * 60                 # genuinely crosses midnight: 6pm-1am
        elif not mer1:
            alt = _minutes(h1, m1, "am" if (mer2 or "pm").lower() == "pm" else "pm")
            if alt < end:
                start = alt                # inherited the wrong half of the day
            else:
                end += 24 * 60
        else:
            end += 24 * 60
    if end <= start or end - start > 24 * 60:
        return None
    return start, end


def parse_days(text):
    """'Mon-Fri' -> [0..4]; 'Tue/Thu' -> [1,3]; 'Daily' -> all; 'Sun-Wed' wraps."""
    t = text.strip().lower().rstrip(":")
    if t in ("daily", "every day", "everyday", "all week", "7 days"):
        return list(range(7))
    out = []
    for part in re.split(r"[/&+]|\band\b|,", t):
        part = part.strip()
        if not part:
            continue
        rng = re.match(r"^([a-z]+)\s*(?:-|–|to)\s*([a-z]+)$", part)
        if rng:
            a, b = DAY_IX.get(rng.group(1)), DAY_IX.get(rng.group(2))
            if a is None or b is None:
                return None
            i = a
            while True:
                out.append(i)
                if i == b:
                    break
                i = (i + 1) % 7
                if len(out) > 7:
                    return None
            continue
        d = DAY_IX.get(part)
        if d is None:
            return None
        out.append(d)
    return sorted(set(out)) or None


def fmt(start, end):
    def one(mins):
        mins %= 24 * 60
        h, m = divmod(mins, 60)
        mer = "am" if h < 12 else "pm"
        h12 = h % 12 or 12
        return f"{h12}:{m:02d}{mer}" if m else f"{h12}{mer}"
    return f"{one(start)}-{one(end)}"


def parse_hours(text):
    """-> (display[7], ranges[7]) or (None, None) if not confidently parseable."""
    if not text:
        return None, None
    raw = PAREN_RE.sub(" ", text).strip()
    raw = raw.replace("~", "").replace("approx.", "").replace("approx", "")
    if raw.lower().strip(" .") in NOT_FOUND | CLOSED_PERMANENTLY:
        return None, None

    per_day = {i: [] for i in range(7)}
    touched = set()
    # Split on commas, but keep "Mon closed, Tue 12-3pm & 6-11pm" clauses intact: '&'
    # joins multiple ranges WITHIN one clause, so only commas separate clauses.
    for clause in re.split(r",(?![^()]*\))", raw):
        clause = clause.strip()
        if not clause:
            continue
        lead = re.match(r"^(?:closed|shut)\s+(?:on\s+)?([A-Za-z/&,\- ]+)$", clause, re.I)
        if lead:
            days = parse_days(lead.group(1))
            if days is None:
                return None, None
            touched.update(days)
            continue

        m = re.match(r"^([A-Za-z/&,\- ]+?)\s+(.*)$", clause)
        if not m:
            # A bare range with no days, e.g. "12-11pm" - assume all week.
            r = parse_range(clause)
            if not r:
                return None, None
            for i in range(7):
                per_day[i].append(r)
                touched.add(i)
            continue
        days = parse_days(m.group(1))
        rest = m.group(2).strip()
        if days is None:
            return None, None
        if re.match(r"^(closed|shut)\b", rest, re.I):
            touched.update(days)
            continue
        ranges = []
        for piece in re.split(r"&|\band\b", rest):
            r = parse_range(piece)
            if r:
                ranges.append(r)
        if not ranges:
            return None, None
        for d in days:
            per_day[d].extend(ranges)
            touched.update(days)

    if not touched:
        return None, None
    display = [f"{DAYS[i]}: " + (", ".join(fmt(*r) for r in per_day[i]) if per_day[i] else "Closed")
               for i in range(7)]
    ranges = [[list(r) for r in per_day[i]] for i in range(7)]
    return display, ranges


def read_places_md(path):
    rows = {}
    for line in pathlib.Path(path).read_text().split("\n"):
        if not line.startswith("| **"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        name = cells[0].replace("**", "").replace("\\|", "|").strip()
        name = re.sub(r"\s*\*\(closed\)\*\s*$", "", name).strip()
        rows[name] = cells[3]
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", nargs="?", default=str(pathlib.Path.home() / "Downloads" / "PLACES.md"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows = read_places_md(args.source)
    pins = json.loads(PINS.read_text())
    by_name = {p["name"]: p for p in pins}

    stats = dict(parsed=0, text_only=0, not_found=0, closed=0, unmatched=0)
    unparsed = []
    for name, text in rows.items():
        pin = by_name.get(name)
        if pin is None:
            # Merging duplicates renames a pin to the surviving record's name, so a source
            # row can be left orphaned ("Uchi Bake, Hackney" vs "Uchi Bake"). Fall back to
            # a near-identical name, but never overwrite hours already set from an exact
            # match.
            cand = max(pins, key=lambda q: places.name_similarity(q["name"], name))
            if places.name_similarity(cand["name"], name) >= 0.90 and not cand.get("hours_text"):
                pin = cand
            else:
                stats["unmatched"] += 1
                continue
        low = PAREN_RE.sub("", text).lower().strip(" .")
        if low in CLOSED_PERMANENTLY:
            pin["status"] = "closed"
            pin["hours"], pin["hours_text"], pin["open_ranges"] = None, None, None
            stats["closed"] += 1
            continue
        if low in NOT_FOUND:
            stats["not_found"] += 1
            continue
        display, ranges = parse_hours(text)
        pin["hours_text"] = text
        if display:
            pin["hours"], pin["open_ranges"] = display, ranges
            stats["parsed"] += 1
        else:
            pin["hours"], pin["open_ranges"] = None, None
            stats["text_only"] += 1
            unparsed.append((name, text))

    # A handful of pins still carry hours from the original Google export
    # ("Mon: 7:30 AM-6:00 PM") with no machine-readable ranges, so they would never match
    # "Open now". Same times, just an older format - backfill rather than discard.
    backfilled = 0
    for pin in pins:
        if not isinstance(pin.get("hours"), list) or pin.get("open_ranges"):
            continue
        ranges, ok = [], True
        for line in pin["hours"]:
            rest = line.split(":", 1)[1].strip() if ":" in line else line
            if re.match(r"^(closed|shut)$", rest, re.I):
                ranges.append([])
                continue
            day = [parse_range(part) for part in rest.split(",")]
            if any(d is None for d in day):
                ok = False
                break
            ranges.append([list(d) for d in day])
        if ok and len(ranges) == 7:
            pin["open_ranges"] = ranges
            backfilled += 1

    print(f"source rows: {len(rows)}")
    if backfilled:
        print(f"  {backfilled} pin(s) backfilled from legacy Google-format hours")
    print(f"  {stats['parsed']} parsed into a 7-day schedule")
    print(f"  {stats['text_only']} kept as display text only (could not parse confidently)")
    print(f"  {stats['closed']} marked permanently closed")
    print(f"  {stats['not_found']} had no hours in the source")
    print(f"  {stats['unmatched']} rows matched no pin")
    if unparsed:
        print("\nnot parsed (still shown as text):")
        for n, t in unparsed[:12]:
            print(f"  {n[:32]:<32} {t[:60]}")
    if args.dry_run:
        print("\ndry run - nothing written")
        return
    PINS.write_text(json.dumps(pins, ensure_ascii=False, separators=(",", ":")))
    print(f"\nwrote pins.json")


def _selftest():
    d, r = parse_hours("Mon-Sat 11am-9pm, Sun 11am-7pm")
    assert d[0] == "Mon: 11am-9pm" and d[6] == "Sun: 11am-7pm", d
    assert r[0] == [[660, 1260]], r[0]

    # meridiem inherited from the end of the range
    d, r = parse_hours("Mon-Thu 12-11pm, Fri-Sat 12-11:30pm, Sun 12-10:30pm")
    assert r[0] == [[720, 1380]], r[0]
    assert d[4] == "Fri: 12pm-11:30pm", d[4]

    # explicit closed day, slash day list, two ranges in one day
    d, r = parse_hours("Mon closed, Tue/Thu 12-3pm & 6-11pm, Wed 11am-11pm, "
                       "Fri 12-3pm & 6-11:30pm, Sat 11am-3pm & 6-11:30pm, Sun 11am-4pm")
    assert d[0] == "Mon: Closed" and r[0] == []
    assert r[1] == [[720, 900], [1080, 1380]], r[1]
    assert r[3] == r[1], "Thu should match Tue"

    # days not mentioned at all default to closed
    d, r = parse_hours("Thu-Sat 6pm-1am (Downstairs at Sucre)")
    assert d[0] == "Mon: Closed" and r[3] == [[1080, 1500]], (d[0], r[3])

    # wrapping day range, and "Daily"
    d, _ = parse_hours("Sun-Wed 12-10:30pm, Thu-Sat 12-11pm (bar open later)")
    assert d[6].startswith("Sun: 12pm") and d[0].startswith("Mon: 12pm"), d
    d, r = parse_hours("Daily 12pm-11pm")
    assert all(x.endswith("12pm-11pm") for x in d), d

    # parenthetical noise is stripped, not choked on
    d, _ = parse_hours("Mon-Sun 9:30am-6pm (last entry 5:30pm)")
    assert d[0] == "Mon: 9:30am-6pm", d[0]

    # things that must NOT produce a schedule
    for bad in ["Not found", "N/A", "Permanently closed", "", "Open late most nights",
                "Check website", "Mon-Frunk 9am-5pm"]:
        assert parse_hours(bad) == (None, None), bad

    assert parse_days("Mon-Fri") == [0, 1, 2, 3, 4]
    assert parse_days("Tue/Thu") == [1, 3]
    assert parse_days("Sat-Sun") == [5, 6]
    assert parse_days("Nonsense") is None
    assert parse_range("6pm-1am") == (1080, 1500)
    assert parse_range("9:30am-6pm") == (570, 1080)
    print("import_hours.py selftest OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        main()
