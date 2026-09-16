#!/usr/bin/env python3
"""OSM/Overpass provider + opening_hours parser.

Same interface as places.py (search / to_pin_fields) so enrich.py only swaps the import.
decide(), normalize(), haversine_km(), looks_like_address() live in places.py and are
provider-agnostic - reused here unchanged, not reimplemented.

Overpass has no reliable text search (regex name matching is brittle on punctuation/case),
so search() pulls everything named within radius_m of the point and returns it in the
Google-shaped form places.decide()/places.disp() already expect ({"location": {...},
"displayName": {"text": ...}}); the caller (enrich.py) scores locally with places.decide().

Overpass is a free shared service - be a good citizen: throttle to >=1 call/sec, identify
with a User-Agent, and back off on 429/504 before giving up.
"""
import json, re, difflib, time, urllib.request, urllib.error, urllib.parse

import places  # reuse decide/normalize/haversine_km/looks_like_address/disp

# overpass-api.de is the canonical instance and stays first choice; the second is a public
# mirror to fall back on when the main one is rate-limiting or unreachable - still free,
# still no key, same query language. Either can be flaky since it's a shared free service.
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]
# Overpass asks clients to identify themselves. A repo URL does that without putting
# a personal email into every request to a third-party service.
USER_AGENT = "LondonReelsMap/1.0 (+https://github.com/Faisal-UX-Portfolio/london-map)"
MIN_INTERVAL_S = 1.0          # be a good citizen on a free shared service
MAX_CANDIDATES = 200          # cap how many decide() has to score per lookup

_last_call = 0.0


def _throttle():
    global _last_call
    wait = MIN_INTERVAL_S - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()


def _post(query, timeout, retries):
    """Try each mirror in turn; within a mirror, back off and retry on 429/504."""
    body = urllib.parse.urlencode({"data": query}).encode()
    last_err = RuntimeError("overpass: no mirrors configured")
    for url in OVERPASS_URLS:
        host = url.split("/")[2]
        req = urllib.request.Request(url, data=body, method="POST",
                                      headers={"User-Agent": USER_AGENT,
                                               "Content-Type": "application/x-www-form-urlencoded"})
        for attempt in range(retries):
            _throttle()
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code in (429, 504) and attempt < retries - 1:
                    backoff = 5 * (attempt + 1)
                    print(f"    {host} HTTP {e.code}, backing off {backoff}s...")
                    time.sleep(backoff)
                    continue
                break  # not retryable, or out of attempts - try the next mirror
            except urllib.error.URLError as e:
                last_err = e
                print(f"    {host} unreachable ({e.reason}), trying next mirror...")
                break
    raise last_err


def _to_candidate(el):
    tags = el.get("tags") or {}
    if el["type"] == "node":
        lat, lon = el.get("lat"), el.get("lon")
    else:
        center = el.get("center") or {}
        lat, lon = center.get("lat"), center.get("lon")
    return {
        "osm_type": el["type"], "osm_id": el["id"], "tags": tags,
        "location": {"latitude": lat, "longitude": lon},
        "displayName": {"text": tags.get("name", "")},
    }


def search(query_name, lat, lng, radius_m=500, timeout=30, retries=5):
    """Nodes/ways/relations named anything, within radius_m of (lat, lng).

    query_name isn't sent to Overpass (no trustworthy text search there) - it's used only
    to pre-rank a huge result set down to MAX_CANDIDATES before the caller runs the real
    (name + distance) scoring in places.decide().
    """
    q = f'[out:json][timeout:25];nwr(around:{int(radius_m)},{lat},{lng})["name"];out center tags;'
    data = _post(q, timeout=timeout, retries=retries)
    candidates = [_to_candidate(el) for el in data.get("elements", [])
                  if el.get("lat") is not None or (el.get("center") or {}).get("lat") is not None]
    if len(candidates) > MAX_CANDIDATES:
        candidates.sort(key=lambda c: difflib.SequenceMatcher(
            None, places.normalize(query_name), places.normalize(c["displayName"]["text"])
        ).ratio(), reverse=True)
        candidates = candidates[:MAX_CANDIDATES]
    return candidates


# --- opening_hours -----------------------------------------------------------------
# A wrong opening time sends someone to a closed restaurant, which is worse than no
# opening time at all. So this only handles the common, unambiguous subset of the OSM
# opening_hours spec and returns None (never a guess) for anything else: sunrise/sunset,
# month/week ranges, quoted comments, or a day-range spec it doesn't recognise.

_DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
_FULL = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_DAY_TOKEN = "|".join(_DAYS) + "|PH"       # PH (public holiday) is dropped, not rejected
_SEG_RE = re.compile(
    rf'^((?:(?:{_DAY_TOKEN})(?:-(?:{_DAY_TOKEN}))?)(?:,\s*(?:(?:{_DAY_TOKEN})(?:-(?:{_DAY_TOKEN}))?))*)'
    rf'\s+(.+)$')
_TIME_RE = re.compile(r'^([0-2]\d:[0-5]\d)-([0-2]\d:[0-5]\d)$')
_UNSUPPORTED_RE = re.compile(
    r'\b(sunrise|sunset|week|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|open)\b|"',
    re.I)


def _expand_days(days_part):
    """Mo..Su tokens/ranges, comma-separated (optional space after the comma). A day range
    wraps across the week boundary the way the OSM spec defines it - "Fr-Mo" is Fri,Sat,
    Sun,Mon, not an error. Bare "PH" (public holiday) entries are dropped, not rejected."""
    days = []
    for group in (g.strip() for g in days_part.split(",")):
        if group == "PH":
            continue
        if "-" in group:
            a, b = group.split("-")
            if a not in _DAYS or b not in _DAYS:
                return None
            ia, ib = _DAYS.index(a), _DAYS.index(b)
            days.extend(_DAYS[ia:ib + 1] if ia <= ib else _DAYS[ia:] + _DAYS[:ib + 1])
        elif group in _DAYS:
            days.append(group)
        else:
            return None
    return days


def parse_opening_hours(value):
    """OSM opening_hours -> 7 "Mon: 09:00-17:00" strings (Monday first), or None."""
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    if value == "24/7":
        return [f"{d}: 00:00-24:00" for d in _FULL]

    segments = [s.strip() for s in value.split(";")]
    segments = [s for s in segments if s and not s.lower().startswith("ph")]
    if not segments:
        return None
    if any(_UNSUPPORTED_RE.search(s) for s in segments):
        return None

    day_hours = {d: None for d in _DAYS}  # None = untouched, "off" = closed, else [ranges]
    for seg in segments:
        m = _SEG_RE.match(seg)
        if not m:
            return None
        days = _expand_days(m.group(1))
        if days is None:
            return None
        rest = m.group(2).strip()

        if rest.lower() in ("off", "closed"):
            for d in days:
                day_hours[d] = "off"
            continue

        times = []
        for part in rest.split(","):
            tm = _TIME_RE.match(part.strip())
            if not tm:
                return None
            times.append(f"{tm.group(1)}-{tm.group(2)}")
        for d in days:
            day_hours[d] = times

    return [f"{_FULL[i]}: " + (", ".join(day_hours[d]) if isinstance(day_hours[d], list) else "Closed")
            for i, d in enumerate(_DAYS)]


# --- pin schema mapping -------------------------------------------------------------

_FOOD_AMENITY = {"restaurant", "cafe", "bar", "pub", "fast_food", "ice_cream"}
_FOOD_SHOP = {"bakery", "pastry"}
_ACTIVITY_AMENITY = {"cinema", "theatre", "nightclub"}


def guess_category_from_tags(tags):
    """None if OSM tags don't say - caller falls back to caption keywords."""
    amenity = (tags.get("amenity") or "").lower()
    shop = (tags.get("shop") or "").lower()
    if amenity in _FOOD_AMENITY or shop in _FOOD_SHOP:
        return "restaurant/food"
    if tags.get("tourism") or tags.get("leisure") or amenity in _ACTIVITY_AMENITY:
        return "activity"
    return None


def to_pin_fields(cand):
    """Map a search() candidate onto our pin schema. rating/rating_count/price_level are
    always null - OSM has no ratings, and inventing one is worse than leaving it blank."""
    tags = cand.get("tags") or {}
    loc = cand.get("location") or {}

    parts = []
    if tags.get("addr:housenumber") and tags.get("addr:street"):
        parts.append(f"{tags['addr:housenumber']} {tags['addr:street']}")
    elif tags.get("addr:street"):
        parts.append(tags["addr:street"])
    if tags.get("addr:postcode"):
        parts.append(tags["addr:postcode"])

    disused = any(k.startswith("disused:amenity") or k.startswith("disused:shop") for k in tags)
    opening_hours = tags.get("opening_hours")

    return {
        "place_id": f"osm:{cand['osm_type']}/{cand['osm_id']}",
        "name": places.disp(cand),
        "lat": loc.get("latitude"),
        "lng": loc.get("longitude"),
        "address": ", ".join(parts) if parts else None,
        "status": "closed" if (disused or opening_hours == "closed") else "open",
        "rating": None,
        "rating_count": None,
        "price_level": None,
        "hours": parse_opening_hours(opening_hours),
        "website": tags.get("website") or tags.get("contact:website"),
        "phone": tags.get("phone") or tags.get("contact:phone"),
    }


def _selftest():
    poh = parse_opening_hours

    assert poh("Mo-Fr 09:00-17:00") == [
        "Mon: 09:00-17:00", "Tue: 09:00-17:00", "Wed: 09:00-17:00", "Thu: 09:00-17:00",
        "Fri: 09:00-17:00", "Sat: Closed", "Sun: Closed"]

    r = poh("Mo-Sa 11:00-23:00; Su 12:00-22:00")
    assert r[0] == "Mon: 11:00-23:00" and r[5] == "Sat: 11:00-23:00" and r[6] == "Sun: 12:00-22:00"

    assert poh("Mo-Su 08:00-20:00") == [f"{d}: 08:00-20:00" for d in
                                         ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]]

    r = poh("Tu-Su 12:00-15:00,18:00-23:00")
    assert r[0] == "Mon: Closed"
    assert r[1] == "Tue: 12:00-15:00, 18:00-23:00"
    assert r[6] == "Sun: 12:00-15:00, 18:00-23:00"

    r = poh("Tu-Su 09:00-17:00; Mo off")
    assert r[0] == "Mon: Closed" and r[1] == "Tue: 09:00-17:00"
    r = poh("Tu-Su 09:00-17:00; Mo closed")
    assert r[0] == "Mon: Closed"

    assert poh("24/7") == [f"{d}: 00:00-24:00" for d in
                            ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]]

    r = poh("Mo-Fr 09:00-17:00; PH off")
    assert r[0] == "Mon: 09:00-17:00" and r[5] == "Sat: Closed"

    # a day range wraps across the week boundary the way the OSM spec defines it
    r = poh("Fr-Mo 09:00-17:00")
    assert r[4] == "Fri: 09:00-17:00" and r[6] == "Sun: 09:00-17:00" and r[0] == "Mon: 09:00-17:00"
    assert r[1] == "Tue: Closed" and r[2] == "Wed: Closed" and r[3] == "Thu: Closed"

    # PH (public holiday) is dropped wherever it appears, never treated as an unknown day
    r = poh("Mo-Su,PH 10:00-22:00")
    assert all(":" in x and "Closed" not in x for x in r)

    # a space after the comma in a day list is common in the wild and must still parse
    r = poh("Mo 13:00-22:00; Tu-Th, Su 12:00-22:00; Fr, Sa 12:00-23:00")
    assert r[0] == "Mon: 13:00-22:00" and r[6] == "Sun: 12:00-22:00" and r[4] == "Fri: 12:00-23:00"

    # malformed / unsupported -> None, never a guess
    assert poh(None) is None
    assert poh("") is None
    assert poh("sunrise-sunset") is None
    assert poh("Mo-Fr 09:00-17:00; Jan-Mar off") is None
    assert poh("week 1-3 Mo-Fr 09:00-17:00") is None
    assert poh('Mo-Fr 09:00-17:00 "by appointment"') is None
    assert poh("banana") is None

    # pin schema mapping
    node = {"osm_type": "node", "osm_id": 123, "tags": {
        "name": "Tanakatsu", "addr:housenumber": "10", "addr:street": "Wakley St",
        "addr:postcode": "EC1V 7LT", "website": "https://tanakatsu.example",
        "phone": "+44 20 1234 5678", "opening_hours": "Mo-Su 12:00-22:00",
        "amenity": "restaurant"},
        "location": {"latitude": 51.53, "longitude": -0.10}, "displayName": {"text": "Tanakatsu"}}
    f = to_pin_fields(node)
    assert f["place_id"] == "osm:node/123"
    assert f["address"] == "10 Wakley St, EC1V 7LT"
    assert f["status"] == "open" and f["rating"] is None and f["price_level"] is None
    assert len(f["hours"]) == 7
    assert guess_category_from_tags(node["tags"]) == "restaurant/food"

    way = {"osm_type": "way", "osm_id": 456, "tags": {
        "name": "Old Cinema", "disused:amenity": "cinema"},
        "location": {"latitude": 51.5, "longitude": -0.1}, "displayName": {"text": "Old Cinema"}}
    f2 = to_pin_fields(way)
    assert f2["status"] == "closed" and f2["hours"] is None and f2["place_id"] == "osm:way/456"

    print("osm.py selftest OK")


if __name__ == "__main__":
    _selftest()
