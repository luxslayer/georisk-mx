# 🛣 CarreterasMX — Mapa de Incidentes

Mapa interactivo de incidentes en carreteras mexicanas, alimentado por los tweets de
[@GN_carreteras](https://twitter.com/GN_carreteras) y [@capufe](https://twitter.com/capufe)
obtenidos a través de Nitter RSS, actualizado automáticamente vía GitHub Actions.

![demo screenshot](docs/screenshot.png)

## ✨ Características

- Consume RSS feeds de Nitter (sin API key de Twitter)
- Extrae: número de carretera, kilómetro, tipo de incidente
- Muestra los incidentes en un mapa oscuro (Leaflet + CartoDB Dark)
- Filtra por tipo: accidente, cierre, tráfico, obras, etc.
- Se actualiza automáticamente cada 30 minutos
- Se despliega como sitio estático en **GitHub Pages**

---

## 🚀 Configuración rápida

### 1. Fork / clone este repositorio

```bash
git clone https://github.com/TU_USUARIO/carreteras-mx.git
cd carreteras-mx
```

### 2. Habilitar GitHub Pages

En tu repositorio → **Settings → Pages**:
- Source: `Deploy from a branch`
- Branch: `gh-pages` (se crea automáticamente) / carpeta `/root`

> Alternativamente, usa la acción `peaceiris/actions-gh-pages` (ya incluida) que hace el deploy automático.

### 3. Habilitar GitHub Actions

En **Settings → Actions → General** → asegúrate de que las Actions estén permitidas y que el workflow tenga permiso de escritura al repositorio:

**Settings → Actions → General → Workflow permissions → Read and write permissions** ✓

### 4. Ejecutar manualmente la primera vez

Ve a **Actions → Fetch Incidents & Deploy → Run workflow**.

---

## 🗂 Estructura del proyecto

```
carreteras-mx/
├── fetch_incidents.py          # Script principal (Python stdlib puro)
├── docs/
│   ├── index.html              # Mapa interactivo
│   └── incidents.json          # Generado automáticamente por el script
└── .github/
    └── workflows/
        └── fetch.yml           # GitHub Actions — cron cada 30 min
```

---

## ⚙️ Cómo funciona

```
GitHub Actions (cron cada 30 min)
        │
        ▼
fetch_incidents.py
  1. Intenta cada instancia de Nitter hasta obtener el RSS
  2. Parsea tweets de @GN_carreteras y @capufe
  3. Extrae con regex: número de carretera + kilómetro
  4. Clasifica el tipo de incidente por palabras clave
  5. Convierte carretera+km a coordenadas lat/lon aproximadas
  6. Escribe docs/incidents.json
        │
        ▼
GitHub Pages sirve docs/
  index.html carga incidents.json y renderiza el mapa
```

### Coordenadas aproximadas

Las coordenadas se calculan interpolando desde el **km 0** de cada carretera
usando vectores de dirección calibrados manualmente. La precisión es suficiente
para ubicar el incidente en el tramo correcto (±2–5 km).

Las carreteras actualmente mapeadas son:

| Clave | Carretera |
|-------|-----------|
| 95D   | México–Acapulco (Autopista del Sol) |
| 57D   | México–Querétaro |
| 150D  | México–Puebla–Veracruz |
| 15D   | Guadalajara–Tepic |
| 15    | México–Toluca |
| 85D   | Monterrey–Laredo |
| 40D   | Saltillo–Monterrey |
| 136   | Arco Norte |
| 180D  | Xalapa–Veracruz |
| 1D    | Tijuana–Ensenada |
| 2D    | Sonora |
| 150   | Puebla–Veracruz (libre) |

---

## 🔧 Desarrollo local

```bash
# Ejecutar el fetcher
python fetch_incidents.py

# Servir el mapa localmente
cd docs
python -m http.server 8000
# Abrir: http://localhost:8000
```

---

## 📝 Agregar más carreteras

Edita el diccionario `HIGHWAY_ANCHORS` en `fetch_incidents.py`:

```python
HIGHWAY_ANCHORS = {
    # "CLAVE": (lat_km0, lon_km0, delta_lat_por_km, delta_lon_por_km)
    "200": (15.8750, -97.0700, 0.000100, 0.011800),  # Costera del Pacífico
    ...
}
```

Para calibrar los deltas, toma las coordenadas de km 0 y km 100 de la carretera
y calcula `(lat_km100 - lat_km0) / 100` y `(lon_km100 - lon_km0) / 100`.

---

## 📄 Licencia

MIT — libre uso, sin garantías. Los datos de incidentes son propiedad de sus fuentes originales.
