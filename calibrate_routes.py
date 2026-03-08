#!/usr/bin/env python3
"""
Herramienta para calcular y verificar waypoints de carreteras.
Dado un conjunto de puntos (km, lat, lon), genera la tabla ROUTE_WAYPOINTS
y verifica la interpolación para cualquier kilómetro.

Uso:
  python calibrate_routes.py verify durango-parral 128
  python calibrate_routes.py list
"""

import math
import sys

# ---------------------------------------------------------------------------
# ROUTE_WAYPOINTS: puntos GPS reales a lo largo de cada carretera
# Formato: route_key → [(km, lat, lon), ...]  ordenados por km creciente
#
# Fuentes: Google Maps midiendo la distancia sobre la carretera desde km 0,
#          OpenStreetMap, y datos de SCT.
# ---------------------------------------------------------------------------

ROUTE_WAYPOINTS: dict[str, list[tuple]] = {

    # ── Durango → Hidalgo del Parral (Fed 45) ────────────────────────────
    # km 0 = Durango city (glorieta norte), km ~230 = Parral
    "durango-parral": [
        (0,   24.0290, -104.6628),   # Durango, entronque norte
        (30,  24.3180, -104.8200),   # Canatlán
        (60,  24.5800, -104.9700),   # El Salto aprox
        (90,  24.8400, -105.1200),   # Valle del Guadiana aprox
        (120, 25.1200, -105.2900),   # Llano Grande aprox
        (150, 25.3800, -105.4200),   # Rodeo / Guanaceví área
        (180, 25.6500, -105.5200),   # Área norte Durango
        (210, 25.9200, -105.5900),   # Límite Chihuahua
        (230, 26.9320, -105.6640),   # Hidalgo del Parral
    ],

    # ── México (CDMX) → Acapulco (Autopista del Sol / 95D) ───────────────
    # km 0 = Periférico Sur CDMX, km ~390 = Acapulco
    "mexico-acapulco": [
        (0,   19.2924, -99.1010),    # Periférico Sur / Tlalpan
        (40,  18.9130, -99.2340),    # Cuernavaca norte
        (80,  18.6800, -99.1200),    # Alpuyeca
        (130, 18.3600, -99.5000),    # Chilpancingo norte aprox
        (175, 17.5510, -99.5000),    # Chilpancingo
        (220, 17.2000, -99.5500),    # Omiltemi
        (280, 16.9600, -99.7500),    # Tierra Colorada
        (390, 16.8531, -99.8237),    # Acapulco
    ],

    # ── México → Querétaro (57D) ─────────────────────────────────────────
    "mexico-queretaro": [
        (0,   19.5200, -99.1600),    # Tepotzotlán / La Venta
        (50,  20.0800, -99.3200),    # Jilotepec
        (100, 20.3600, -99.8600),    # Palmillas
        (150, 20.5300, -100.1900),   # San Juan del Río
        (200, 20.5880, -100.3900),   # Querétaro
    ],

    # ── México → Puebla (150D) ───────────────────────────────────────────
    "mexico-puebla": [
        (0,   19.3600, -98.9800),    # Peñón / inicio
        (30,  19.2500, -98.7200),    # Chalco
        (60,  19.1500, -98.4800),    # Río Frío
        (100, 19.0530, -98.1830),    # Puebla poniente
        (135, 19.0480, -97.8700),    # Amozoc / entronque 150
    ],

    # ── Puebla → Córdoba (150D / 2100) ───────────────────────────────────
    "puebla-cordoba": [
        (0,   19.0530, -98.1830),    # Puebla oriente
        (40,  18.9800, -97.7500),    # Acatzingo
        (80,  18.9300, -97.3500),    # Tepeaca / Tehuacán área
        (120, 18.8900, -97.0000),    # Orizaba
        (160, 18.8840, -96.9230),    # Córdoba
    ],

    # ── México → Toluca (15 libre / cuota) ───────────────────────────────
    "mexico-toluca": [
        (0,   19.4326, -99.1332),    # Santa Fe / inicio CDMX
        (20,  19.3500, -99.3500),    # Las Cruces
        (40,  19.3200, -99.5500),    # Lerma
        (65,  19.2860, -99.6640),    # Toluca
    ],

    # ── Guadalajara → Tepic (15D / 950) ──────────────────────────────────
    "guadalajara-tepic": [
        (0,   20.6597, -103.3496),   # Guadalajara norte
        (50,  20.8800, -103.8000),   # Tequila
        (100, 21.1200, -104.1500),   # Magdalena / Etzatlán area
        (150, 21.3500, -104.6500),   # Ixtlán del Río
        (220, 21.5080, -104.8950),   # Tepic
    ],

    # ── Monterrey → Laredo (85D) ─────────────────────────────────────────
    "monterrey-laredo": [
        (0,   25.6866, -100.3161),   # Monterrey norte
        (50,  26.1000, -100.2500),   # Sabinas Hidalgo
        (100, 26.5200, -100.1800),   # Lampazos
        (150, 27.0600, -100.0800),   # Anahuac
        (210, 27.5060, -99.5070),    # Nuevo Laredo
    ],

    # ── Saltillo → Monterrey (40D) ────────────────────────────────────────
    "saltillo-monterrey": [
        (0,   25.4231, -100.9940),   # Saltillo poniente
        (40,  25.5800, -100.5900),   # La Cienega
        (80,  25.6700, -100.2300),   # Santa Catarina
        (100, 25.6866, -100.3161),   # Monterrey
    ],

    # ── Guadalajara → Morelia (15D Occidente) ────────────────────────────
    "guadalajara-morelia": [
        (0,   20.6597, -103.3496),   # Guadalajara
        (50,  20.3600, -102.7500),   # La Barca
        (100, 20.1500, -102.0200),   # Zamora
        (160, 19.7050, -101.1940),   # Morelia
    ],

    # ── Chihuahua → Ciudad Juárez (45) ───────────────────────────────────
    "chihuahua-juarez": [
        (0,   28.6320, -106.0690),   # Chihuahua norte
        (50,  29.1200, -106.2500),   # Sacramento
        (100, 29.6500, -106.3800),   # Villa Ahumada
        (150, 30.2500, -106.4200),   # Samalayuca
        (200, 31.7380, -106.4870),   # Ciudad Juárez
    ],

    # ── Puebla → Veracruz (150 libre) ────────────────────────────────────
    "puebla-veracruz": [
        (0,   19.0530, -98.1830),
        (50,  18.9300, -97.3000),
        (100, 18.9800, -96.7200),
        (145, 19.1730, -96.1340),    # Veracruz
    ],

    # ── Tijuana → Ensenada (1D) ───────────────────────────────────────────
    "tijuana-ensenada": [
        (0,   32.5149, -117.0382),   # Tijuana
        (40,  32.1800, -116.9300),   # Rosarito
        (80,  31.8680, -116.6900),   # Ensenada norte
        (110, 31.8670, -116.5960),   # Ensenada
    ],

    # ── Isla → Acayucan (180D) ───────────────────────────────────────────
    "isla-acayucan": [
        (0,   18.0560, -95.5300),    # Isla, Veracruz
        (50,  18.0700, -95.1000),    # Tierra Blanca aprox
        (100, 18.0200, -94.8500),    # Sayula de Alemán
        (155, 17.9480, -94.9140),    # Acayucan
    ],
}

# ---------------------------------------------------------------------------
# Interpolación a lo largo de waypoints
# ---------------------------------------------------------------------------

def interpolate(route_key: str, km: float) -> tuple[float, float] | None:
    waypoints = ROUTE_WAYPOINTS.get(route_key)
    if not waypoints:
        return None

    # Clamp to route bounds
    km = max(waypoints[0][0], min(waypoints[-1][0], km))

    for i in range(len(waypoints) - 1):
        km0, lat0, lon0 = waypoints[i]
        km1, lat1, lon1 = waypoints[i + 1]
        if km0 <= km <= km1:
            t = (km - km0) / (km1 - km0)
            return (round(lat0 + t * (lat1 - lat0), 6),
                    round(lon0 + t * (lon1 - lon0), 6))
    return None


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_verify(route_key: str, km_str: str):
    km = float(km_str)
    coords = interpolate(route_key, km)
    if coords is None:
        print(f"Route '{route_key}' not found or km out of range.")
        return
    lat, lon = coords
    wps = ROUTE_WAYPOINTS[route_key]
    print(f"\nRoute  : {route_key}")
    print(f"km     : {km}")
    print(f"Result : {lat}, {lon}")
    print(f"Google : https://maps.google.com/?q={lat},{lon}")
    print(f"\nWaypoints ({len(wps)}):")
    for k, la, lo in wps:
        dist = haversine_km(la, lo, lat, lon)
        print(f"  km {k:>4}  ({la:.4f}, {lo:.4f})  ~{dist:.1f} km from result")


def cmd_list():
    print("\nAvailable routes:")
    for key, wps in ROUTE_WAYPOINTS.items():
        km_start = wps[0][0]
        km_end   = wps[-1][0]
        print(f"  {key:<35}  km {km_start}–{km_end}  ({len(wps)} waypoints)")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "list":
        cmd_list()
    elif args[0] == "verify" and len(args) >= 3:
        cmd_verify(args[1], args[2])
    else:
        print("Usage:")
        print("  python calibrate_routes.py list")
        print("  python calibrate_routes.py verify <route-key> <km>")