# WOWSA Swimmable Distance Calculator

Standardizes official route distances for WOWSA-ratified open water swims. Calculates the shortest all-water path between two coordinates and stores the result as the canonical distance for that route.

Live preview: [web-production-e08e3.up.railway.app](https://web-production-e08e3.up.railway.app)

---

## How it works

### Shore-to-shore

Enter a start and end coordinate. The tool runs A* pathfinding through a water grid built from the [GLOBE](https://www.ngdc.noaa.gov/mgg/topo/globe.html) 925m land mask, finds the shortest all-water path, and returns the distance with a route line on the map.

On first calculation the result is displayed for review. A WOWSA team member enters a route name and clicks **Add to database** to lock it as the official distance. All future queries for those coordinates return the saved result instantly.

### Circumnavigation

Enter a landmass name. The tool fetches the island boundary from OpenStreetMap, buffers 900m offshore, and generates evenly-spaced waypoints around the perimeter. If OpenStreetMap doesn't have the boundary, Claude AI generates the waypoints and self-checks them against a land polygon dataset. A human reviews and adjusts waypoints on the map before the calculation runs.

---

## Routing methodology

Shore-to-shore uses **GLOBE A* pathfinding**:

1. Build a water/land grid over the bounding box of the two coordinates using the `global-land-mask` Python package (GLOBE dataset, 925m resolution)
2. Snap start/end points to the nearest water cell
3. Run A* with haversine heuristic and pre-computed directional step costs
4. Apply string-pull (line-of-sight) smoothing to remove grid staircase artifacts
5. Return the smoothed path and its haversine-summed distance

Adaptive resolution: 0.01 deg (~1.1 km) for crossings under 100 km, coarser for longer routes.

Circumnavigation legs use searoute-py (maritime routing network) between consecutive waypoints.

---

## Project structure

```
server.py              Flask API - all endpoints, GLOBE routing, DB logic
index.html             Web interface with Google Maps
circumnavigation.py    Waypoint-to-waypoint loop distance calculator
calculate.py           Searoute-py wrapper (used for circumnavigation legs)
propose-waypoints.py   CLI tool for generating circumnavigation waypoints
route_ireland.json     Pre-computed GLOBE route for Ireland circumnavigation
requirements.txt       Python dependencies
Procfile               Railway deployment command
```

---

## Local setup

```bash
git clone https://github.com/rose2023va/wowsa-distance-calculator
cd wowsa-distance-calculator
pip install -r requirements.txt
```

Create `config.py` (git-ignored):

```python
GOOGLE_MAPS_API_KEY = "your-key"
ANTHROPIC_API_KEY   = "your-key"
```

Run:

```bash
python3 server.py
# Open http://localhost:5050
```

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_MAPS_API_KEY` | Yes | Google Maps JavaScript API key for the interactive map |
| `ANTHROPIC_API_KEY` | Yes | Claude API key for AI waypoint generation (circumnavigation fallback) |
| `DATABASE_URL` | No | PostgreSQL connection string. If not set, DB features are silently disabled. |
| `PORT` | No | Server port. Defaults to 5050. Set automatically by Railway. |

---

## API endpoints

### `POST /api/calculate`
Calculates shore-to-shore swimmable distance.

```json
{ "startLat": 51.1295, "startLon": 1.3212, "endLat": 50.8715, "endLon": 1.5773 }
```

Response includes `distance_km`, `distance_miles`, `coordinates` (route path), `globe_routed`, `from_db`, `swim_name`.

### `POST /api/save-route`
Saves a calculated result to the database with a name.

```json
{
  "name": "English Channel",
  "distance_km": 33.826, "distance_miles": 21.018,
  "coordinates": [[1.3212, 51.1295], ...],
  "globe_routed": true,
  "start_lat": 51.1295, "start_lon": 1.3212,
  "end_lat": 50.8715, "end_lon": 1.5773
}
```

### `POST /api/propose-waypoints`
Generates circumnavigation waypoints for a named landmass.

```json
{ "landmass": "Catalina Island", "direction": "clockwise", "count": 24 }
```

### `POST /api/circumnavigate`
Calculates total circumnavigation distance from a waypoint list.

```json
{ "waypoints": [{"lat": 33.3, "lon": -118.3}, ...] }
```

---

## Database

PostgreSQL table `shore_routes`:

| Column | Type | Description |
|---|---|---|
| `start_lat/lon` | double | Route start coordinates |
| `end_lat/lon` | double | Route end coordinates |
| `distance_km/miles` | double | Official distance |
| `path` | jsonb | Route geometry as [[lon, lat], ...] |
| `route_type` | varchar | `globe`, `sea`, or `straight` |
| `name` | varchar | Human-assigned route name |
| `created_at` | timestamp | When it was saved |

Coordinate matching uses 0.5 km tolerance and handles both directions of a crossing.

---

## Deployment

Deployed on Railway. Connect the GitHub repo, set the three environment variables, add a PostgreSQL service (Railway auto-injects `DATABASE_URL`). The `Procfile` runs `python3 server.py`.

---

## Pre-computed routes

For complex courses, a GLOBE Dijkstra route can be pre-computed and stored as a JSON file in the repository (`route_{name}.json`, `shore_{name}.json`). These take priority over the database and on-demand computation. Currently included: Ireland circumnavigation (`route_ireland.json`).
