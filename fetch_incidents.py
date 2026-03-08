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

# Display labels for each route
ROUTE_LABELS: dict = {
    "mexico-acapulco":          "Méx–Acapulco",
    "mexico-cuernavaca":        "Méx–Cuernavaca",
    "cuernavaca-acapulco":      "Cuernavaca–Acapulco",
    "mexico-queretaro":         "Méx–Querétaro",
    "mexico-puebla":            "Méx–Puebla",
    "puebla-cordoba":           "Puebla–Córdoba",
    "puebla-veracruz":          "Puebla–Veracruz",
    "puebla-acatzingo":         "Puebla–Acatzingo",
    "mexico-toluca":            "Méx–Toluca",
    "toluca-palmillas":         "Toluca–Palmillas",
    "guadalajara-tepic":        "Gdl–Tepic",
    "guadalajara-morelia":      "Gdl–Morelia",
    "monterrey-laredo":         "Mty–Laredo",
    "saltillo-monterrey":       "Saltillo–Mty",
    "chihuahua-juarez":         "Chih–Cd Juárez",
    "durango-parral":           "Durango–Parral",
    "villahermosa-escarcega":   "Villahermosa–Escárcega",
    "acayucan-cosoleacaque":    "Acayucan–Cosoleacaque",
    "salamanca-leon":           "Salamanca–León",
    "isla-acayucan":            "Isla–Acayucan",
    "tijuana-ensenada":         "Tijuana–Ensenada",
    "zacatecas-durango":        "Zac–Durango",
    "cordoba-yanga":            "Córdoba–Yanga",
    "teziutlan-nautla":         "Teziutlán–Nautla",
    "libramiento-queretaro":    "Lib. Sur Qro.",
    "coatzacoalcos-salinaCruz": "Coatza–Salina Cruz",
    "carmen-campeche":          "Carmen–Campeche",
    "guadalupe-guanacevi":      "Guadalupe–Guanaceví",
    "tinaja-cosoleacaque":      "La Tinaja–Cosoleacaque",
}

# Waypoints: route_key → [(km, lat, lon), ...]  ordered by km ascending.
# Interpolation follows the road geometry instead of a straight line.
# Routes without waypoints fall back to the first waypoint of the nearest
# neighbour or return None (unresolved).
ROUTE_WAYPOINTS: dict = {
    "durango-parral": [
        (0,   24.0290, -104.6628),
        (30,  24.3180, -104.8200),
        (60,  24.5800, -104.9700),
        (90,  24.8400, -105.1200),
        (120, 25.1200, -105.2900),
        (150, 25.3800, -105.4200),
        (180, 25.6500, -105.5200),
        (210, 25.9200, -105.5900),
        (230, 26.9320, -105.6640),
    ],
    "mexico-acapulco": [
        (0,   19.2924, -99.1010),
        (40,  18.9130, -99.2340),
        (80,  18.6800, -99.1200),
        (130, 18.3600, -99.5000),
        (175, 17.5510, -99.5000),
        (220, 17.2000, -99.5500),
        (280, 16.9600, -99.7500),
        (390, 16.8531, -99.8237),
    ],
    "mexico-cuernavaca": [
        (0,   19.2924, -99.1010),
        (40,  18.9130, -99.2340),
        (85,  18.9186, -99.2340),
    ],
    "cuernavaca-acapulco": [
        (0,   18.9186, -99.2340),
        (45,  18.6800, -99.1200),
        (90,  18.3600, -99.5000),
        (175, 16.8531, -99.8237),
    ],
    "mexico-queretaro": [
        (0,   19.5200, -99.1600),
        (50,  20.0800, -99.3200),
        (100, 20.3600, -99.8600),
        (150, 20.5300, -100.1900),
        (200, 20.5880, -100.3900),
    ],
    "mexico-puebla": [
        (0,   19.3600, -98.9800),
        (30,  19.2500, -98.7200),
        (60,  19.1500, -98.4800),
        (100, 19.0530, -98.1830),
        (135, 19.0480, -97.8700),
    ],
    "puebla-cordoba": [
        (0,   19.0530, -98.1830),
        (40,  18.9800, -97.7500),
        (80,  18.9300, -97.3500),
        (120, 18.8900, -97.0000),
        (160, 18.8840, -96.9230),
    ],
    "puebla-veracruz": [
        (0,   19.0530, -98.1830),
        (50,  18.9300, -97.3000),
        (100, 18.9800, -96.7200),
        (145, 19.1730, -96.1340),
    ],
    "puebla-acatzingo": [
        (0,   19.0530, -98.1830),
        (50,  18.9800, -97.7500),
        (90,  18.9480, -97.4500),
    ],
    "mexico-toluca": [
        (0,   19.4326, -99.1332),
        (20,  19.3500, -99.3500),
        (40,  19.3200, -99.5500),
        (65,  19.2860, -99.6640),
    ],
    "toluca-palmillas": [
        (0,   19.2860, -99.6640),
        (50,  20.0000, -99.9500),
        (90,  20.2600, -100.2200),
    ],
    "guadalajara-tepic": [
        (0,   20.6597, -103.3496),
        (50,  20.8800, -103.8000),
        (100, 21.1200, -104.1500),
        (150, 21.3500, -104.6500),
        (220, 21.5080, -104.8950),
    ],
    "guadalajara-morelia": [
        (0,   20.6597, -103.3496),
        (50,  20.3600, -102.7500),
        (100, 20.1500, -102.0200),
        (160, 19.7050, -101.1940),
    ],
    "monterrey-laredo": [
        (0,   25.6866, -100.3161),
        (50,  26.1000, -100.2500),
        (100, 26.5200, -100.1800),
        (150, 27.0600, -100.0800),
        (210, 27.5060, -99.5070),
    ],
    "saltillo-monterrey": [
        (0,   25.4231, -100.9940),
        (40,  25.5800, -100.5900),
        (80,  25.6700, -100.2300),
        (100, 25.6866, -100.3161),
    ],
    "guadalajara-morelia": [
        (0,   20.6597, -103.3496),
        (50,  20.3600, -102.7500),
        (100, 20.1500, -102.0200),
        (160, 19.7050, -101.1940),
    ],
    "chihuahua-juarez": [
        (0,   28.6320, -106.0690),
        (50,  29.1200, -106.2500),
        (100, 29.6500, -106.3800),
        (150, 30.2500, -106.4200),
        (200, 31.7380, -106.4870),
    ],
    "tijuana-ensenada": [
        (0,   32.5149, -117.0382),
        (40,  32.1800, -116.9300),
        (80,  31.8680, -116.6900),
        (110, 31.8670, -116.5960),
    ],
    "isla-acayucan": [
        (0,   18.0560, -95.5300),
        (50,  18.0700, -95.1000),
        (100, 18.0200, -94.8500),
        (155, 17.9480, -94.9140),
    ],
    "villahermosa-escarcega": [
        (0,   17.9892, -92.9472),
        (60,  18.1000, -91.8000),
        (120, 18.6200, -91.0000),
        (200, 18.6490, -90.7300),
    ],
    "zacatecas-durango": [
        (0,   22.7709, -102.5832),
        (60,  23.1500, -103.0000),
        (120, 23.6000, -103.5000),
        (180, 24.0290, -104.6628),
    ],
    "salamanca-leon": [
        (0,   20.5700, -101.1950),
        (30,  20.7000, -101.3500),
        (60,  21.1220, -101.6820),
    ],
    "acayucan-cosoleacaque": [
        (0,   17.9480, -94.9140),
        (30,  18.1000, -94.8000),
        (55,  18.1490, -94.4480),
    ],
    "cordoba-yanga": [
        (0,   18.8840, -96.9230),
        (20,  18.8000, -96.7800),
        (40,  18.8100, -96.6500),
    ],
    "teziutlan-nautla": [
        (0,   19.8180, -97.3570),
        (40,  20.0500, -97.0500),
        (80,  20.2000, -96.8000),
    ],
    "libramiento-queretaro": [
        (0,   20.5450, -100.4500),
        (25,  20.4700, -100.2500),
        (50,  20.5880, -100.3900),
    ],
    "coatzacoalcos-salinaCruz": [
        (0,   18.1490, -94.4480),
        (80,  17.0000, -95.0000),
        (160, 16.1600, -95.2000),
    ],
    "carmen-campeche": [
        (0,   18.6490, -91.8220),
        (60,  19.0000, -90.8000),
        (160, 19.8450, -90.5230),
    ],
    "guadalupe-guanacevi": [
        (0,   26.1000, -105.9500),
        (50,  25.8000, -105.7000),
        (80,  25.5500, -105.4800),
    ],
    "tinaja-cosoleacaque": [
        (0,   18.3200, -95.0200),
        (40,  18.2000, -94.8500),
        (70,  18.1490, -94.4480),
    ],
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
    """Interpolate coordinates along waypoints for the given route and km."""
    waypoints = ROUTE_WAYPOINTS.get(route_key)
    if not waypoints:
        return None
    # Clamp to known range
    km = max(waypoints[0][0], min(waypoints[-1][0], km))
    for i in range(len(waypoints) - 1):
        km0, lat0, lon0 = waypoints[i]
        km1, lat1, lon1 = waypoints[i + 1]
        if km0 <= km <= km1:
            t = (km - km0) / (km1 - km0)
            return (round(lat0 + t * (lat1 - lat0), 6),
                    round(lon0 + t * (lon1 - lon0), 6))
    return None


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
        display_highway = ROUTE_LABELS.get(route_key, route_key)
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