#!/usr/bin/env python3
"""
Fetches tweets from Nitter RSS feeds for @GN_carreteras and @capufe,
extracts highway incident information, and generates incidents.json
for the map visualization.
"""

import json
import re
import hashlib
import unicodedata
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
# Named route table
#
# Real tweets use route NAMES, not numbers:
#   "km 009+300, de la carretera México - Toluca"
#   "km 106+000 Aut. (950) Guadalajara-Tepic"
#   "km 032+200 autopista (1710) México-Puebla"
#
# Each entry: route_key → (display_label, lat_km0, lon_km0, dlat/km, dlon/km)
# Anchors calibrated at km 0 with approximate direction vectors.
# ---------------------------------------------------------------------------

ROUTES: dict = {
    "mexico-acapulco":         ("Méx–Acapulco",         19.2924, -99.1010, -0.00882, -0.00120),
    "mexico-cuernavaca":       ("Méx–Cuernavaca",        19.2924, -99.1010, -0.00850, -0.00080),
    "cuernavaca-acapulco":     ("Cuernavaca–Acapulco",   18.9186, -99.2340, -0.00920, -0.00100),
    "mexico-queretaro":        ("Méx–Querétaro",         19.5200, -99.1600,  0.01150, -0.00680),
    "mexico-puebla":           ("Méx–Puebla",            19.3600, -98.9800, -0.00050,  0.01020),
    "puebla-cordoba":          ("Puebla–Córdoba",        19.0530, -98.1830, -0.00150,  0.01100),
    "puebla-veracruz":         ("Puebla–Veracruz",       19.0400, -98.1800, -0.00200,  0.01150),
    "puebla-acatzingo":        ("Puebla–Acatzingo",      19.0530, -98.1830, -0.00100,  0.00980),
    "mexico-toluca":           ("Méx–Toluca",            19.4326, -99.1332,  0.00100, -0.01200),
    "toluca-palmillas":        ("Toluca–Palmillas",      19.2860, -99.6640, -0.00030, -0.01150),
    "guadalajara-tepic":       ("Gdl–Tepic",             20.6597,-103.3496,  0.00420,  0.01080),
    "guadalajara-morelia":     ("Gdl–Morelia",           20.6597,-103.3496, -0.00350,  0.00920),
    "monterrey-laredo":        ("Mty–Laredo",            25.6866,-100.3161,  0.01100,  0.00030),
    "saltillo-monterrey":      ("Saltillo–Mty",          25.4231,-100.9940,  0.00080,  0.01350),
    "chihuahua-juarez":        ("Chih–Cd Juárez",        28.6320,-106.0690,  0.01080,  0.00120),
    "durango-parral":          ("Durango–Parral",        24.0240,-104.6570, -0.01050,  0.00080),
    "villahermosa-escarcega":  ("Villahermosa–Escárcega",17.9892, -92.9472, -0.00030,  0.01120),
    "acayucan-cosoleacaque":   ("Acayucan–Cosoleacaque", 17.9480, -94.9140,  0.00020,  0.00980),
    "salamanca-leon":          ("Salamanca–León",        20.5700,-101.1950,  0.00250,  0.01050),
    "isla-acayucan":           ("Isla–Acayucan",         18.0350, -95.5300,  0.00010,  0.01020),
    "tijuana-ensenada":        ("Tijuana–Ensenada",      32.5149,-117.0382, -0.01200,  0.00150),
    "zacatecas-durango":       ("Zac–Durango",           22.7709,-102.5832,  0.00880, -0.00350),
    "cordoba-yanga":           ("Córdoba–Yanga",         18.8840, -96.9230,  0.00150, -0.00920),
    "teziutlan-nautla":        ("Teziutlán–Nautla",      19.8180, -97.3570, -0.00650,  0.00980),
    "libramiento-queretaro":   ("Lib. Sur Qro.",         20.5450,-100.4500,  0.00050,  0.00900),
    "coatzacoalcos-salinaCruz":("Coatza–Salina Cruz",    18.1490, -94.4480, -0.00180,  0.01050),
    "carmen-campeche":         ("Carmen–Campeche",       18.6490, -91.8220,  0.00020,  0.01080),
    "guadalupe-guanacevi":     ("Guadalupe–Guanaceví",   26.1000,-105.9500,  0.00950, -0.00120),
    "tinaja-cosoleacaque":     ("La Tinaja–Cosoleacaque",18.3200, -95.0200,  0.00010,  0.01000),
}

# Alias table: normalised text fragment → route key
ROUTE_ALIASES: dict = {
    # Numeric GN codes found in tweets like "Aut. (950)"
    "950":  "guadalajara-tepic",
    "1710": "mexico-puebla",
    "2100": "puebla-cordoba",
    # Common numeric codes
    "95d":  "mexico-acapulco",
    "95":   "mexico-acapulco",
    "57d":  "mexico-queretaro",
    "57":   "mexico-queretaro",
    "150d": "mexico-puebla",
    "150":  "puebla-veracruz",
    "15d":  "guadalajara-tepic",
    "15":   "mexico-toluca",
    "85d":  "monterrey-laredo",
    "40d":  "saltillo-monterrey",
    # Named route fragments (accents stripped, lowercase)
    "mexico - toluca":          "mexico-toluca",
    "mexico-toluca":            "mexico-toluca",
    "mexico toluca":            "mexico-toluca",
    "mexico - queretaro":       "mexico-queretaro",
    "mexico-queretaro":         "mexico-queretaro",
    "mexico queretaro":         "mexico-queretaro",
    "mexico - puebla":          "mexico-puebla",
    "mexico-puebla":            "mexico-puebla",
    "mexico puebla":            "mexico-puebla",
    "mexico - cuernavaca":      "mexico-cuernavaca",
    "mexico-cuernavaca":        "mexico-cuernavaca",
    "mexico - acapulco":        "mexico-acapulco",
    "mexico-acapulco":          "mexico-acapulco",
    "cuernavaca - acapulco":    "cuernavaca-acapulco",
    "cuernavaca-acapulco":      "cuernavaca-acapulco",
    "puebla - cordoba":         "puebla-cordoba",
    "puebla-cordoba":           "puebla-cordoba",
    "puebla cordoba":           "puebla-cordoba",
    "puebla - acatzingo":       "puebla-acatzingo",
    "amozoc":                   "mexico-puebla",
    "guadalajara - tepic":      "guadalajara-tepic",
    "guadalajara-tepic":        "guadalajara-tepic",
    "guadalajara tepic":        "guadalajara-tepic",
    "guadalajara - morelia":    "guadalajara-morelia",
    "guadalajara-morelia":      "guadalajara-morelia",
    "monterrey - laredo":       "monterrey-laredo",
    "monterrey-laredo":         "monterrey-laredo",
    "saltillo - monterrey":     "saltillo-monterrey",
    "saltillo-monterrey":       "saltillo-monterrey",
    "chihuahua - cd. juarez":   "chihuahua-juarez",
    "chihuahua - juarez":       "chihuahua-juarez",
    "chihuahua-juarez":         "chihuahua-juarez",
    "durango - parral":         "durango-parral",
    "durango-parral":           "durango-parral",
    "villahermosa - escarcega": "villahermosa-escarcega",
    "villahermosa-escarcega":   "villahermosa-escarcega",
    "acayucan - cosoleacaque":  "acayucan-cosoleacaque",
    "acayucan-cosoleacaque":    "acayucan-cosoleacaque",
    "salamanca - leon":         "salamanca-leon",
    "salamanca-leon":           "salamanca-leon",
    "isla - acayucan":          "isla-acayucan",
    "isla-acayucan":            "isla-acayucan",
    "tijuana - ensenada":       "tijuana-ensenada",
    "tijuana-ensenada":         "tijuana-ensenada",
    "zacatecas - durango":      "zacatecas-durango",
    "zacatecas-durango":        "zacatecas-durango",
    "cordoba - yanga":          "cordoba-yanga",
    "cordoba-yanga":            "cordoba-yanga",
    "teziutlan - nautla":       "teziutlan-nautla",
    "teziutlan-nautla":         "teziutlan-nautla",
    "libramiento sur":          "libramiento-queretaro",
    "libramiento sur poniente": "libramiento-queretaro",
    "coatzacoalcos - salina":   "coatzacoalcos-salinaCruz",
    "tinaja - cosoleacaque":    "tinaja-cosoleacaque",
    "la tinaja":                "tinaja-cosoleacaque",
    "carmen - campeche":        "carmen-campeche",
    "carmen-campeche":          "carmen-campeche",
    "autopista de occidente":   "guadalajara-morelia",
    "autopista del sol":        "mexico-acapulco",
    "autopista siglo xxi":      "guadalajara-morelia",
    "toluca - palmillas":       "toluca-palmillas",
    "toluca-palmillas":         "toluca-palmillas",
    "guadalupe aguilera":       "guadalupe-guanacevi",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def strip_accents(s: str) -> str:
    """Remove diacritics: á→a, é→e, etc."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def normalise(s: str) -> str:
    return strip_accents(s).lower().strip()


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
        def text(tag, _item=item):
            el = _item.find(tag)
            return (el.text or "").strip() if el is not None else ""
        items.append({
            "title":       text("title"),
            "description": text("description"),
            "link":        text("link"),
            "pubDate":     text("pubDate"),
        })

    # Atom fallback
    if not items:
        for entry in root.findall("atom:entry", ns):
            def atext(tag, _e=entry):
                el = _e.find(f"atom:{tag}", ns)
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

# km patterns — handles:  "km 009+300"  "km 146+900"  "km 142"  "kilómetro 56"
RE_KM = re.compile(
    r"(?:km\.?|k\.?|kil[oó]metro\.?)\s*(\d{1,4})(?:[+.,]\d{0,3})?",
    re.IGNORECASE,
)

# Numeric GN route code in parentheses: "Aut. (950)" or "(1710)"
RE_CODE = re.compile(r"\((\d{3,4})\)")

# Named route after "de la carretera" / "autopista" / "aut."
# Captures everything up to a comma, period, or newline (max 60 chars)
RE_NAMED = re.compile(
    r"(?:de\s+la\s+carretera|autopista|aut\.|carretera)\s+([A-Za-záéíóúÁÉÍÓÚüÜñÑ\s\-–]+?)(?:\s*[,.\n]|$)",
    re.IGNORECASE,
)

# Incident type keywords (checked after accent stripping)
INCIDENT_KEYWORDS = {
    "accidente":    "accident",
    "choque":       "accident",
    "colision":     "accident",
    "percance":     "accident",
    "volcadura":    "rollover",
    "vuelco":       "rollover",
    "incendio":     "fire",
    "fuego":        "fire",
    "cierre":       "closure",
    "cerrada":      "closure",
    "cerrado":      "closure",
    "obras":        "roadwork",
    "mantenimiento":"roadwork",
    "derrumbe":     "landslide",
    "deslizamiento":"landslide",
    "inundaci":     "flood",
    "neblina":      "fog",
    "niebla":       "fog",
    "nieve":        "ice",
    "hielo":        "ice",
    "cristalizaci": "ice",
    "granizo":      "hail",
    "trafico":      "traffic",
    "congestion":   "traffic",
    "carga vehicular": "traffic",
    "lento":        "traffic",
    "manifestaci":  "protest",
    "bloqueo":      "blockade",
    "presencia de personas": "blockade",
}


def classify_incident(text: str) -> str:
    t = normalise(text)
    for keyword, itype in INCIDENT_KEYWORDS.items():
        if keyword in t:
            return itype
    return "alert"


def resolve_route(text_norm: str) -> str | None:
    """Return route key if we can identify the highway in the tweet text."""
    # 1. Numeric GN code in parens: (950), (1710), etc.
    for m in RE_CODE.finditer(text_norm):
        key = ROUTE_ALIASES.get(m.group(1))
        if key:
            return key

    # 2. Named route fragments — try longest match first
    candidates = sorted(ROUTE_ALIASES.keys(), key=len, reverse=True)
    for alias in candidates:
        if alias in text_norm:
            return ROUTE_ALIASES[alias]

    # 3. Named route after "carretera / autopista" keyword
    for m in RE_NAMED.finditer(text_norm):
        fragment = normalise(m.group(1)).strip(" -–")
        for alias in candidates:
            if alias in fragment or fragment in alias:
                return ROUTE_ALIASES[alias]

    return None


def km_to_coords(route_key: str, km: float) -> tuple[float, float] | None:
    entry = ROUTES.get(route_key)
    if entry is None:
        return None
    _, lat0, lon0, dlat, dlon = entry
    return (round(lat0 + dlat * km, 6), round(lon0 + dlon * km, 6))


def parse_date(date_str: str) -> str:
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
    raw = f"{item['title']} {item['description']}"
    # Strip HTML tags
    raw_clean = re.sub(r"<[^>]+>", " ", raw)
    raw_clean = re.sub(r"\s+", " ", raw_clean).strip()

    text_norm = normalise(raw_clean)

    # Must mention a km to be an incident
    km_match = RE_KM.search(raw_clean)
    if not km_match:
        return None

    km_value = float(km_match.group(1))

    # Resolve route
    route_key = resolve_route(text_norm)

    # Get display label and coords
    if route_key:
        display_highway = ROUTES[route_key][0]
        coords = km_to_coords(route_key, km_value)
    else:
        display_highway = "?"

    resolved = coords is not None if route_key else False
    if not resolved:
        coords = (23.6345, -102.5528)  # centre of Mexico fallback

    uid = hashlib.md5((item.get("link", "") + raw_clean[:80]).encode()).hexdigest()[:12]

    return {
        "id":        uid,
        "account":   f"@{account}",
        "type":      classify_incident(raw_clean),
        "highway":   display_highway,
        "route_key": route_key or "unknown",
        "km":        km_value,
        "lat":       coords[0],
        "lon":       coords[1],
        "resolved":  resolved,
        "text":      raw_clean[:280],
        "link":      item.get("link", ""),
        "date":      parse_date(item.get("pubDate", "")),
    }


# ---------------------------------------------------------------------------
# Debug helper – print a few samples when run locally
# ---------------------------------------------------------------------------

SAMPLE_TWEETS = [
    "#TomePrecauciones en #EdoMex se registra cierre parcial de circulación por #AccidenteVíal cerca del km 009+300, de la carretera México - Toluca. Atienda indicación vial.",
    "#Atención en #EdoMex se registra cierre de circulación en ambos sentidos por colisión múltiple, aproximadamente en el km 032+200 autopista (1710) México-Puebla.",
    "#Atención, en #Nayarit se registra cierre de circulación en ambos sentidos por accidente km 106+000 Aut. (950) Guadalajara-Tepic (Directo).",
    "CAPUFE informó sobre el cierre parcial de circulación en la autopista Isla-Acayucan, a la altura del kilómetro 159, por un accidente.",
    "#TomePrecauciones en #Durango se registra cierre parcial de circulación por #AccidenteVial cerca del km 128+400, de la carretera Durango - Parral.",
    "En Chihuahua se registra cierre parcial de circulación por accidente vial cerca del km 146+900, de la carretera Chihuahua - Cd. Juárez.",
    "Autopista México-Querétaro, km 171, dirección Ciudad de México: cierre de circulación tras un choque.",
    "#TomePrecauciones en #CDMX se registra cierre total de circulación por presencia de personas cerca del km 031+500, de la carretera México - Cuernavaca.",
]


def run_debug():
    print("=== DEBUG – sample tweet parsing ===\n")
    for tweet in SAMPLE_TWEETS:
        item = {"title": tweet, "description": "", "link": "", "pubDate": ""}
        inc = tweet_to_incident(item, "GN_carreteras")
        if inc:
            print(f"  ✓ {inc['highway']:25s}  km {inc['km']:>7.0f}  type={inc['type']:10s}  resolved={inc['resolved']}")
            print(f"    {tweet[:90]}")
        else:
            print(f"  ✗ NO MATCH: {tweet[:90]}")
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import sys
    if "--debug" in sys.argv:
        run_debug()
        return

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
    seen: set = set()
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