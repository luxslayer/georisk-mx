#!/usr/bin/env python3
"""
Fetches tweets from Nitter RSS feeds for @GN_carreteras and @capufe,
extracts highway incident information, and generates incidents.json
for the map visualization.
"""

import json
import re
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError
import os

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.1d4.us",
]

ACCOUNTS = ["GN_carreteras", "capufe"]

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "docs", "incidents.json")
MAX_TWEETS = 50  # per account

# ---------------------------------------------------------------------------
# Known highway coordinates (km 0 anchor points + direction vectors)
# Tuple: (lat_km0, lon_km0, delta_lat_per_km, delta_lon_per_km)
# These are approximate; good enough for map plotting.
# ---------------------------------------------------------------------------

HIGHWAY_ANCHORS = {
    # Autopista del Sol  México–Acapulco (Mex-95D)
    "95D": (19.2924, -99.1010, -0.008820, -0.001200),
    # México–Querétaro (Mex-57D)
    "57D": (19.5200, -99.1600,  0.011500, -0.006800),
    # México–Puebla (Mex-150D)
    "150D": (19.3600, -98.9800, -0.000500,  0.010200),
    # Arco Norte (Mex-136/Periferico)
    "136":  (19.6800, -99.3000,  0.000200,  0.009500),
    # Guadalajara–Tepic (Mex-15D)
    "15D":  (20.6597, -103.3496,  0.004200,  0.010800),
    # México–Toluca (Mex-15)
    "15":   (19.4326, -99.1332,  0.001000, -0.012000),
    # Monterrey–Laredo (Mex-85D)
    "85D":  (25.6866, -100.3161,  0.011000,  0.000300),
    # Puebla–Veracruz (Mex-150)
    "150":  (19.0400, -98.1800, -0.002000,  0.011500),
    # Tijuana–Ensenada (Mex-1D)
    "1D":   (32.5149, -117.0382, -0.012000,  0.001500),
    # Mex-2D (Sonora)
    "2D":   (30.7000, -110.9500,  0.000200,  0.013000),
    # Saltillo–Monterrey (Mex-40D)
    "40D":  (25.4231, -100.9940,  0.000800,  0.013500),
    # Veracruz–Xalapa (Mex-180D)
    "180D": (19.1738, -96.1342,  0.008800, -0.003000),
}

# Extended alias map (common variations found in tweets → canonical key)
HIGHWAY_ALIASES: dict[str, str] = {}
for k in list(HIGHWAY_ANCHORS.keys()):
    HIGHWAY_ALIASES[k.upper()] = k
    HIGHWAY_ALIASES[f"MEX-{k}"] = k
    HIGHWAY_ALIASES[f"CARR-{k}"] = k
    HIGHWAY_ALIASES[f"AUTOPISTA {k}"] = k

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_rss_url(instance: str, account: str) -> str:
    return f"{instance}/{account}/rss"


def fetch_rss(account: str) -> str | None:
    """Try each Nitter instance until one works."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; CarreterasMX/1.0)"}
    for instance in NITTER_INSTANCES:
        url = get_rss_url(instance, account)
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=15) as resp:
                content = resp.read().decode("utf-8", errors="replace")
                if "<rss" in content or "<feed" in content:
                    print(f"  ✓ {instance} → @{account}")
                    return content
        except (URLError, Exception) as exc:
            print(f"  ✗ {instance}: {exc}")
    return None


def parse_rss_items(xml_text: str) -> list[dict]:
    """Parse RSS/Atom XML and return list of {title, description, link, pubDate}."""
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        print(f"  XML parse error: {exc}")
        return items

    ns = {"atom": "http://www.w3.org/2005/Atom"}

    # RSS 2.0
    for item in root.iter("item"):
        def text(tag: str) -> str:
            el = item.find(tag)
            return (el.text or "").strip() if el is not None else ""

        items.append({
            "title":       text("title"),
            "description": text("description"),
            "link":        text("link"),
            "pubDate":     text("pubDate"),
        })

    # Atom
    if not items:
        for entry in root.findall("atom:entry", ns):
            def atext(tag: str) -> str:
                el = entry.find(f"atom:{tag}", ns)
                return (el.text or "").strip() if el is not None else ""
            items.append({
                "title":       atext("title"),
                "description": atext("summary") or atext("content"),
                "link":        atext("id"),
                "pubDate":     atext("updated") or atext("published"),
            })

    return items[:MAX_TWEETS]


# ---------------------------------------------------------------------------
# Incident extraction
# ---------------------------------------------------------------------------

# Patterns to detect highway number (e.g. "autopista 95D", "tramo 57D", "Méx-150D")
RE_HIGHWAY = re.compile(
    r"(?:autopista|carretera|libre|cuota|federal|tramo|méx|mex|carr\.?)\s*[-–]?\s*(\d{1,3}[A-Z]{0,2})",
    re.IGNORECASE,
)

# Patterns to detect kilometer (e.g. "km 142", "kilómetro 23", "k.42")
RE_KM = re.compile(
    r"(?:km\.?|k\.?|kil[oó]metro\.?)\s*(\d{1,4}(?:[.,]\d{1,2})?)",
    re.IGNORECASE,
)

# Incident type keywords
INCIDENT_KEYWORDS = {
    "accidente":   "accident",
    "choque":      "accident",
    "volcadura":   "rollover",
    "vuelco":      "rollover",
    "incendio":    "fire",
    "fuego":       "fire",
    "cierre":      "closure",
    "cerrada":     "closure",
    "cerrado":     "closure",
    "obras":       "roadwork",
    "trabajo":     "roadwork",
    "derrumbe":    "landslide",
    "deslizamiento":"landslide",
    "inundaci":    "flood",
    "neblina":     "fog",
    "niebla":      "fog",
    "hielo":       "ice",
    "granizo":     "hail",
    "tráfico":     "traffic",
    "congestion":  "traffic",
    "lento":       "traffic",
    "manifestaci": "protest",
    "bloqueo":     "blockade",
}


def classify_incident(text: str) -> str:
    text_lower = text.lower()
    for keyword, itype in INCIDENT_KEYWORDS.items():
        if keyword in text_lower:
            return itype
    return "alert"


def km_to_coords(highway: str, km: float) -> tuple[float, float] | None:
    """Convert highway + km to approximate lat/lon."""
    key = HIGHWAY_ALIASES.get(highway.upper())
    if key is None:
        # Try partial match
        for alias, canonical in HIGHWAY_ALIASES.items():
            if highway.upper() in alias:
                key = canonical
                break
    if key is None:
        return None
    lat0, lon0, dlat, dlon = HIGHWAY_ANCHORS[key]
    return (round(lat0 + dlat * km, 6), round(lon0 + dlon * km, 6))


def parse_date(date_str: str) -> str:
    """Normalise various date formats to ISO 8601."""
    if not date_str:
        return datetime.now(timezone.utc).isoformat()
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
    ):
        try:
            return datetime.strptime(date_str, fmt).astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    return datetime.now(timezone.utc).isoformat()


def tweet_to_incident(item: dict, account: str) -> dict | None:
    """Try to extract an incident from a tweet item. Returns None if not applicable."""
    raw = f"{item['title']} {item['description']}"
    # Strip HTML tags
    raw_clean = re.sub(r"<[^>]+>", " ", raw)
    raw_clean = re.sub(r"\s+", " ", raw_clean).strip()

    hw_match = RE_HIGHWAY.search(raw_clean)
    km_match = RE_KM.search(raw_clean)

    if not hw_match:
        return None  # No highway mentioned → skip

    highway = hw_match.group(1).upper()
    km_value = float(km_match.group(1).replace(",", ".")) if km_match else None

    coords = None
    if km_value is not None:
        coords = km_to_coords(highway, km_value)

    # Fallback coords (centre of Mexico) if we can't resolve
    if coords is None:
        coords = (23.6345, -102.5528)
        resolved = False
    else:
        resolved = True

    uid = hashlib.md5((item.get("link", "") + raw_clean[:80]).encode()).hexdigest()[:12]

    return {
        "id":        uid,
        "account":   f"@{account}",
        "type":      classify_incident(raw_clean),
        "highway":   highway,
        "km":        km_value,
        "lat":       coords[0],
        "lon":       coords[1],
        "resolved":  resolved,
        "text":      raw_clean[:280],
        "link":      item.get("link", ""),
        "date":      parse_date(item.get("pubDate", "")),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=== CarreterasMX – Incident Fetcher ===")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n")

    all_incidents: list[dict] = []

    for account in ACCOUNTS:
        print(f"Fetching @{account} …")
        xml_text = fetch_rss(account)
        if not xml_text:
            print(f"  ⚠ Could not fetch feed for @{account}\n")
            continue

        items = parse_rss_items(xml_text)
        print(f"  Parsed {len(items)} tweets")

        count = 0
        for item in items:
            incident = tweet_to_incident(item, account)
            if incident:
                all_incidents.append(incident)
                count += 1
        print(f"  Extracted {count} incidents\n")

    # Deduplicate by id
    seen: set[str] = set()
    unique: list[dict] = []
    for inc in all_incidents:
        if inc["id"] not in seen:
            seen.add(inc["id"])
            unique.append(inc)

    # Sort newest first
    unique.sort(key=lambda x: x["date"], reverse=True)

    output = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "count":   len(unique),
        "incidents": unique,
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"✓ Saved {len(unique)} incidents → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
