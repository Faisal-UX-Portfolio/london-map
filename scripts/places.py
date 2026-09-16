#!/usr/bin/env python3
"""Places provider + match scoring.

Kept separate from enrich.py so swapping provider is one file, and so the scoring rules
can be tested without a network call or an API key (see selftest at the bottom).

Google Places API (New). The fields we want - rating, opening hours, phone, website - are
billed on the Enterprise SKU, which carries ~1,000 free calls/month. One searchText call
per venue returns everything, so never follow up with a separate Place Details call.
"""
import json, os, re, math, difflib, unicodedata, urllib.request, urllib.error

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
FIELDS = ",".join("places." + f for f in [
    "id", "displayName", "formattedAddress", "location", "rating", "userRatingCount",
    "priceLevel", "regularOpeningHours", "businessStatus", "websiteUri",
    "nationalPhoneNumber", "primaryType",
])

# Auto-accept at or above this. Below ACCEPT but at or above REVIEW -> needs-review.
ACCEPT, REVIEW = 0.80, 0.55
# A near-perfect name this far from the known coordinates is almost certainly the wrong
# branch of a chain, not our venue. Send it to review however good the name looks.
CHAIN_TRAP_KM = 2.0

PRICE = {"PRICE_LEVEL_FREE": 0, "PRICE_LEVEL_INEXPENSIVE": 1, "PRICE_LEVEL_MODERATE": 2,
         "PRICE_LEVEL_EXPENSIVE": 3, "PRICE_LEVEL_VERY_EXPENSIVE": 4}

ADDRESS_NAME = re.compile(r"^\d+[A-Za-z]?([-–]\d+[A-Za-z]?)?\s+\S")


def looks_like_address(name):
    """True for pins the original build named after a street rather than a business,
    e.g. "10 Wakley St". Those should adopt whatever Google calls the place."""
    if not ADDRESS_NAME.match(name or ""):
        return False
    # "1947 London" and "113 KTV" are real trading names, not addresses.
    return bool(re.search(r"\b(st|street|rd|road|ave|avenue|ln|lane|ct|court|"
                          r"place|pl|sq|square|way|hill|row|gardens?)\b", name, re.I))


def normalize(name):
    # Fold accents first: "Gokyuzu" vs "Gokyuzu" with diacritics scored 0.58 and was
    # rejected as a different venue, because stripping non-ascii mangled the word.
    n = unicodedata.normalize("NFKD", name or "")
    n = "".join(c for c in n if not unicodedata.combining(c)).lower()
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    n = re.sub(r"\b(the|london|ltd|limited|uk|official)\b", " ", n)
    return " ".join(n.split())


def name_similarity(a, b):
    """Similarity that understands "JOIA" and "JOIA Restaurant, Bar & Rooftop" are one
    venue. Raw ratio scores that pair 0.33 purely because of the length difference, which
    rejected a pile of correct matches. Whole-word containment is the signal that matters
    for venue names that carry a descriptive tail."""
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    wa, wb = na.split(), nb.split()
    if wa[:len(wb)] == wb or wb[:len(wa)] == wa:
        return 0.92          # one is a prefix of the other, word-for-word
    if set(wa) <= set(wb) or set(wb) <= set(wa):
        return 0.86          # every word of the shorter appears in the longer
    return difflib.SequenceMatcher(None, na, nb).ratio()


def haversine_km(a, b):
    R, rad = 6371.0, math.pi / 180
    dlat, dlng = (b[0] - a[0]) * rad, (b[1] - a[1]) * rad
    s = (math.sin(dlat / 2) ** 2 +
         math.cos(a[0] * rad) * math.cos(b[0] * rad) * math.sin(dlng / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(s))


def score(our_name, our_ll, cand_name, cand_ll):
    """0.7 name + 0.3 distance. Returns (combined, name_sim, dist_km|None)."""
    name_sim = name_similarity(our_name, cand_name)
    if our_ll is None:
        # No coordinates to compare, so distance carries no information. Blending in a
        # neutral 0.5 just dilutes a good name match below the bar - a word-for-word
        # containment match scored 0.794 against a 0.80 threshold and was rejected.
        return name_sim, name_sim, None
    dist = haversine_km(our_ll, cand_ll)
    dist_score = max(0.0, 1.0 - dist / 1.0)                 # 1.0 at 0km, 0 at >=1km
    return 0.7 * name_sim + 0.3 * dist_score, name_sim, dist


def decide(our_name, our_ll, candidates):
    """Pick the best candidate and say what to do with it.
    Returns (verdict, best, scored) where verdict is accept | review | reject."""
    if not candidates:
        return "reject", None, []
    scored = []
    for c in candidates:
        loc = c.get("location") or {}
        cll = (loc.get("latitude"), loc.get("longitude"))
        combined, sim, dist = score(our_name, our_ll, disp(c), cll)
        scored.append({"cand": c, "combined": combined, "name_sim": sim, "dist_km": dist})
    scored.sort(key=lambda x: -x["combined"])
    best = scored[0]

    # Chain trap: the name matches beautifully but it is miles away.
    if best["dist_km"] is not None and best["dist_km"] > CHAIN_TRAP_KM and best["name_sim"] >= 0.85:
        return "review", best, scored
    # Two candidates too close to call - but only when they are genuinely different
    # places. Several branches of one chain all named "Kricket" is not ambiguity about
    # WHICH VENUE it is, and treating it as such rejected a pile of correct matches.
    if len(scored) > 1 and abs(scored[0]["combined"] - scored[1]["combined"]) < 0.05 \
            and best["combined"] < 0.92 \
            and name_similarity(disp(scored[0]["cand"]), disp(scored[1]["cand"])) < 0.85:
        return "review", best, scored
    if best["combined"] >= ACCEPT:
        return "accept", best, scored
    if best["combined"] >= REVIEW:
        return "review", best, scored
    return "reject", best, scored


def disp(place):
    return (place.get("displayName") or {}).get("text") or ""


def search(text_query, lat=None, lng=None, radius_m=500, api_key=None, timeout=20):
    """One searchText call. Raises on HTTP error so the caller can decide to stop."""
    api_key = api_key or os.environ.get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_PLACES_API_KEY is not set")
    body = {"textQuery": text_query, "maxResultCount": 5, "regionCode": "GB",
            "languageCode": "en"}
    if lat is not None and lng is not None:
        body["locationBias"] = {"circle": {"center": {"latitude": lat, "longitude": lng},
                                           "radius": float(radius_m)}}
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Goog-Api-Key": api_key,
                 "X-Goog-FieldMask": FIELDS})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read()).get("places", [])


def to_pin_fields(place):
    """Map a Google place onto our schema. Hours come back Monday-first already."""
    loc = place.get("location") or {}
    hours = (place.get("regularOpeningHours") or {}).get("weekdayDescriptions")
    status_map = {"OPERATIONAL": "open", "CLOSED_TEMPORARILY": "open",
                  "CLOSED_PERMANENTLY": "closed"}
    return {
        "place_id": place.get("id"),
        "name": disp(place),
        "lat": loc.get("latitude"),
        "lng": loc.get("longitude"),
        "address": place.get("formattedAddress"),
        "status": status_map.get(place.get("businessStatus"), "unknown"),
        "rating": place.get("rating"),
        "rating_count": place.get("userRatingCount"),
        "price_level": PRICE.get(place.get("priceLevel")),
        "hours": hours if (isinstance(hours, list) and len(hours) == 7) else None,
        "website": place.get("websiteUri"),
        "phone": place.get("nationalPhoneNumber"),
    }


def _selftest():
    soho = (51.5136, -0.1365)

    # exact name at the exact spot -> accept
    v, best, _ = decide("Gordon's Wine Bar", soho, [
        {"displayName": {"text": "Gordon's Wine Bar"}, "location": {"latitude": 51.5136, "longitude": -0.1365}}])
    assert v == "accept", v

    # the chain trap: perfect name, 5km away -> must NOT auto-accept
    v, best, _ = decide("Franco Manca", soho, [
        {"displayName": {"text": "Franco Manca"}, "location": {"latitude": 51.4613, "longitude": -0.1156}}])
    assert v == "review", f"chain trap should go to review, got {v}"

    # nothing like it -> reject
    v, _, _ = decide("Sarnie Social", soho, [
        {"displayName": {"text": "Barclays Bank"}, "location": {"latitude": 51.5137, "longitude": -0.1366}}])
    assert v == "reject", v

    # no candidates at all -> reject, no crash
    assert decide("Anything", soho, [])[0] == "reject"

    # two near-identical scores -> ambiguous, review
    v, _, _ = decide("Panadera", soho, [
        {"displayName": {"text": "Panadera"}, "location": {"latitude": 51.5200, "longitude": -0.1400}},
        {"displayName": {"text": "Panadera"}, "location": {"latitude": 51.5201, "longitude": -0.1401}}])
    assert v == "review", f"ambiguous pair should go to review, got {v}"

    # address-shaped names are detected, real trading names are not
    assert looks_like_address("10 Wakley St")
    assert looks_like_address("85 Old Brompton Road")
    assert not looks_like_address("1947 London")
    assert not looks_like_address("113 KTV")
    assert not looks_like_address("Gordon's Wine Bar")

    # price enum mapping, and hours only accepted at exactly 7 entries
    f = to_pin_fields({"displayName": {"text": "X"}, "priceLevel": "PRICE_LEVEL_MODERATE",
                       "businessStatus": "CLOSED_PERMANENTLY",
                       "regularOpeningHours": {"weekdayDescriptions": ["Mon: 9"] * 7},
                       "location": {"latitude": 1, "longitude": 2}})
    assert f["price_level"] == 2 and f["status"] == "closed" and len(f["hours"]) == 7
    bad = to_pin_fields({"displayName": {"text": "X"},
                         "regularOpeningHours": {"weekdayDescriptions": ["Mon: 9"] * 3},
                         "location": {}})
    assert bad["hours"] is None and bad["price_level"] is None
    print("places.py selftest OK")


if __name__ == "__main__":
    _selftest()
