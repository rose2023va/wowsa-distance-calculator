#!/usr/bin/env python3
"""
WOWSA Local API Server

Enables sea-routing and AI waypoints in the web interface.

Setup:
  pip install flask flask-cors anthropic

  Then set your API keys in config.py (preferred) or as environment variables:
    GOOGLE_MAPS_API_KEY
    ANTHROPIC_API_KEY

  python3 server.py
  Open: http://localhost:5050
"""

import json
import os
import io
import urllib.request
import zipfile

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Keys: config.py (git-ignored) takes priority, env vars as fallback
try:
    import config as _cfg
    MAPS_KEY      = getattr(_cfg, 'GOOGLE_MAPS_API_KEY', '') or os.environ.get('GOOGLE_MAPS_API_KEY', '')
    ANTHROPIC_KEY = getattr(_cfg, 'ANTHROPIC_API_KEY', '')   or os.environ.get('ANTHROPIC_API_KEY', '')
except ImportError:
    MAPS_KEY      = os.environ.get('GOOGLE_MAPS_API_KEY', '')
    ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

PORT        = int(os.environ.get('PORT', 5050))
DATABASE_URL = os.environ.get('DATABASE_URL')


# ── Database ───────────────────────────────────────────────────────────────────

def _db_conn():
    if not DATABASE_URL:
        return None
    try:
        import psycopg2
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f'DB connect error: {e}')
        return None

def _db_init():
    conn = _db_conn()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS shore_routes (
                    id             SERIAL PRIMARY KEY,
                    start_lat      DOUBLE PRECISION NOT NULL,
                    start_lon      DOUBLE PRECISION NOT NULL,
                    end_lat        DOUBLE PRECISION NOT NULL,
                    end_lon        DOUBLE PRECISION NOT NULL,
                    distance_km    DOUBLE PRECISION NOT NULL,
                    distance_miles DOUBLE PRECISION NOT NULL,
                    path           JSONB,
                    route_type     VARCHAR(20),
                    warning        TEXT,
                    name           VARCHAR(200),
                    created_at     TIMESTAMP DEFAULT NOW()
                )
            """)
            # Migration: add name column to existing tables
            cur.execute("ALTER TABLE shore_routes ADD COLUMN IF NOT EXISTS name VARCHAR(200)")
            conn.commit()
        print('DB ready.')
    except Exception as e:
        print(f'DB init error: {e}')
    finally:
        conn.close()

def _db_lookup(start_lat, start_lon, end_lat, end_lon, tolerance_km=0.5):
    conn = _db_conn()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT start_lat, start_lon, end_lat, end_lon,
                       distance_km, distance_miles, path, route_type, warning, name
                FROM shore_routes
                WHERE ABS(start_lat - %s) < 0.01 AND ABS(start_lon - %s) < 0.01
                  AND ABS(end_lat   - %s) < 0.01 AND ABS(end_lon   - %s) < 0.01
            """, (start_lat, start_lon, end_lat, end_lon))
            rows = cur.fetchall()
        for row in rows:
            slat, slon, elat, elon, km, mi, path, rtype, warn, name = row
            forward = (_haversine_km(start_lat, start_lon, slat, slon) < tolerance_km and
                       _haversine_km(end_lat,   end_lon,   elat, elon) < tolerance_km)
            reverse = (_haversine_km(start_lat, start_lon, elat, elon) < tolerance_km and
                       _haversine_km(end_lat,   end_lon,   slat, slon) < tolerance_km)
            if forward or reverse:
                coords = path if path else None
                if reverse and coords:
                    coords = list(reversed(coords))
                return {
                    'distance_km':    km,
                    'distance_miles': mi,
                    'coordinates':    coords,
                    'sea_routed':     rtype == 'sea',
                    'ai_routed':      False,
                    'globe_routed':   rtype == 'globe',
                    'warning':        warn,
                    'swim_name':      name,
                    'from_db':        True,
                }
        return None
    except Exception as e:
        print(f'DB lookup error: {e}')
        return None
    finally:
        conn.close()

def _db_save(start_lat, start_lon, end_lat, end_lon, result, route_type, name=''):
    conn = _db_conn()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO shore_routes
                    (start_lat, start_lon, end_lat, end_lon,
                     distance_km, distance_miles, path, route_type, warning, name)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                start_lat, start_lon, end_lat, end_lon,
                result['distance_km'], result['distance_miles'],
                json.dumps(result.get('coordinates')),
                route_type,
                result.get('warning'),
                name or None,
            ))
            conn.commit()
    except Exception as e:
        print(f'DB save error: {e}')
    finally:
        conn.close()


# ── Static ─────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_file('index.html')


# ── Config ─────────────────────────────────────────────────────────────────────

@app.route('/api/config')
def api_config():
    return jsonify({
        'hasMapsKey':      bool(MAPS_KEY),
        'hasAnthropicKey': bool(ANTHROPIC_KEY),
    })


@app.route('/api/maps-key')
def api_maps_key():
    return jsonify({'key': MAPS_KEY})


# ── Calculation ────────────────────────────────────────────────────────────────

def _precomputed_shore_route(start_lat, start_lon, end_lat, end_lon):
    """Check all shore_*.json files for a pre-computed route matching these coordinates (±500 m)."""
    import glob
    from calculate import km_to_miles
    for fpath in glob.glob(os.path.join(_SERVER_DIR, 'shore_*.json')):
        try:
            with open(fpath) as f:
                r = json.load(f)
            slat, slon = r['start_lat'], r['start_lon']
            elat, elon = r['end_lat'],   r['end_lon']
            forward  = (_haversine_km(start_lat, start_lon, slat, slon) < 0.5 and
                        _haversine_km(end_lat,   end_lon,   elat, elon) < 0.5)
            backward = (_haversine_km(start_lat, start_lon, elat, elon) < 0.5 and
                        _haversine_km(end_lat,   end_lon,   slat, slon) < 0.5)
            if not (forward or backward):
                continue
            raw_path = r.get('path', [])  # stored as [lat, lon] - convert to [lon, lat]
            path_lonlat = [[p[1], p[0]] for p in raw_path]
            if backward:
                path_lonlat = list(reversed(path_lonlat))
            km = r['km']
            return {
                'distance_km':    round(km, 3),
                'distance_miles': round(km_to_miles(km), 3),
                'coordinates':    path_lonlat,
                'sea_routed':     False,
                'ai_routed':      False,
                'globe_routed':   True,
                'swim_name':      r.get('name', ''),
                'warning':        None,
            }
        except Exception:
            continue
    return None


def _string_pull(cells, water, nrows, ncols):
    """Greedy line-of-sight smoothing: replaces A* staircase with direct segments
    wherever the straight line stays in water. Recalculates distance along the
    smoothed path."""
    if len(cells) <= 2:
        return cells

    def has_los(r1, c1, r2, c2):
        steps = max(abs(r2 - r1), abs(c2 - c1))
        if steps == 0:
            return True
        for k in range(1, steps):
            r = int(round(r1 + k * (r2 - r1) / steps))
            c = int(round(c1 + k * (c2 - c1) / steps))
            if not (0 <= r < nrows and 0 <= c < ncols and water[r, c]):
                return False
        return True

    result = [cells[0]]
    i = 0
    while i < len(cells) - 1:
        j = len(cells) - 1
        while j > i + 1:
            if has_los(cells[i][0], cells[i][1], cells[j][0], cells[j][1]):
                break
            j -= 1
        result.append(cells[j])
        i = j
    return result


def _globe_route_on_demand(start_lat, start_lon, end_lat, end_lon):
    """A* pathfinding through a GLOBE land-mask water grid for any coordinate pair."""
    try:
        from global_land_mask import globe
        import numpy as np
        import heapq
        from calculate import km_to_miles

        straight_km = _haversine_km(start_lat, start_lon, end_lat, end_lon)

        # Adaptive resolution and padding based on crossing distance
        if straight_km < 100:
            res, pad = 0.010, 1.0
        elif straight_km < 400:
            res, pad = 0.020, 1.5
        else:
            res, pad = 0.050, 2.0

        lat_min = min(start_lat, end_lat) - pad
        lat_max = max(start_lat, end_lat) + pad
        lon_min = min(start_lon, end_lon) - pad
        lon_max = max(start_lon, end_lon) + pad

        lats = np.arange(lat_min, lat_max + res / 2, res)
        lons = np.arange(lon_min, lon_max + res / 2, res)
        nrows, ncols = len(lats), len(lons)

        # Guard against huge grids
        if nrows * ncols > 600_000:
            factor = int(np.ceil(np.sqrt(nrows * ncols / 600_000)))
            res *= factor
            lats = np.arange(lat_min, lat_max + res / 2, res)
            lons = np.arange(lon_min, lon_max + res / 2, res)
            nrows, ncols = len(lats), len(lons)

        # Vectorised water mask
        lat_grid, lon_grid = np.meshgrid(lats, lons, indexing='ij')
        water = globe.is_ocean(lat_grid, lon_grid)

        def coord_to_cell(lat, lon):
            i = int(round((lat - lat_min) / res))
            j = int(round((lon - lon_min) / res))
            return max(0, min(i, nrows - 1)), max(0, min(j, ncols - 1))

        def snap_to_water(i, j):
            if water[i, j]:
                return i, j
            for r in range(1, 60):
                for di in range(-r, r + 1):
                    for dj in range(-r, r + 1):
                        if abs(di) != r and abs(dj) != r:
                            continue
                        ni, nj = i + di, j + dj
                        if 0 <= ni < nrows and 0 <= nj < ncols and water[ni, nj]:
                            return ni, nj
            return None, None

        si, sj = snap_to_water(*coord_to_cell(start_lat, start_lon))
        ei, ej = snap_to_water(*coord_to_cell(end_lat, end_lon))
        if si is None or ei is None:
            return None

        # Pre-compute step costs at centre latitude (avoids haversine in inner loop)
        clat = (start_lat + end_lat) / 2
        step_ns   = _haversine_km(clat, 0, clat + res, 0)
        step_ew   = _haversine_km(clat, 0, clat, res)
        step_diag = (step_ns ** 2 + step_ew ** 2) ** 0.5
        DIRS = {
            (-1, 0): step_ns, (1, 0): step_ns,
            (0, -1): step_ew, (0, 1): step_ew,
            (-1,-1): step_diag, (-1, 1): step_diag,
            ( 1,-1): step_diag, ( 1, 1): step_diag,
        }

        # A* search
        INF = float('inf')
        g = np.full((nrows, ncols), INF)
        g[si, sj] = 0.0
        prev = {}

        def h(i, j):
            return _haversine_km(float(lats[i]), float(lons[j]), end_lat, end_lon)

        pq = [(h(si, sj), 0.0, si, sj)]

        while pq:
            f, gval, i, j = heapq.heappop(pq)
            if gval > g[i, j]:
                continue
            if i == ei and j == ej:
                break
            for (di, dj), cost in DIRS.items():
                ni, nj = i + di, j + dj
                if not (0 <= ni < nrows and 0 <= nj < ncols) or not water[ni, nj]:
                    continue
                ng = gval + cost
                if ng < g[ni, nj]:
                    g[ni, nj] = ng
                    prev[(ni, nj)] = (i, j)
                    heapq.heappush(pq, (ng + h(ni, nj), ng, ni, nj))

        if g[ei, ej] == INF:
            return None

        # Reconstruct path
        path_cells = []
        cur = (ei, ej)
        while cur in prev:
            path_cells.append(cur)
            cur = prev[cur]
        path_cells.append((si, sj))
        path_cells.reverse()

        # String-pull: remove staircase grid artifacts with line-of-sight smoothing
        path_cells = _string_pull(path_cells, water, nrows, ncols)

        # Recalculate distance along the smoothed path
        km = 0.0
        for k in range(len(path_cells) - 1):
            ri, ci = path_cells[k]
            rj, cj = path_cells[k + 1]
            km += _haversine_km(float(lats[ri]), float(lons[ci]),
                                float(lats[rj]), float(lons[cj]))

        coords = [[round(float(lons[j]), 6), round(float(lats[i]), 6)]
                  for i, j in path_cells]

        return {
            'distance_km':    round(km, 3),
            'distance_miles': round(km_to_miles(km), 3),
            'coordinates':    coords,
            'sea_routed':     False,
            'ai_routed':      False,
            'globe_routed':   True,
            'warning':        None,
            'from_db':        False,
        }
    except Exception as e:
        print(f'Globe on-demand error: {e}')
        return None


@app.route('/api/save-route', methods=['POST'])
def api_save_route():
    d = request.get_json()
    name = (d.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Route name is required'}), 400
    result = {
        'distance_km':    float(d['distance_km']),
        'distance_miles': float(d['distance_miles']),
        'coordinates':    d.get('coordinates'),
        'warning':        None,
    }
    route_type = 'globe' if d.get('globe_routed') else ('sea' if d.get('sea_routed') else 'straight')
    _db_save(
        float(d['start_lat']), float(d['start_lon']),
        float(d['end_lat']),   float(d['end_lon']),
        result, route_type, name,
    )
    return jsonify({'ok': True, 'name': name})


@app.route('/api/calculate', methods=['POST'])
def api_calculate():
    d = request.get_json()
    from calculate import km_to_miles

    origin = [float(d['startLon']), float(d['startLat'])]
    dest   = [float(d['endLon']),   float(d['endLat'])]

    # 1. Pre-computed JSON files (git-committed, locked routes)
    precomp = _precomputed_shore_route(origin[1], origin[0], dest[1], dest[0])
    if precomp:
        return jsonify(precomp)

    # 2. Database - manually saved and named routes
    db_result = _db_lookup(origin[1], origin[0], dest[1], dest[0])
    if db_result:
        return jsonify(db_result)

    # 3. On-demand GLOBE A* routing
    globe = _globe_route_on_demand(origin[1], origin[0], dest[1], dest[0])
    if globe:
        return jsonify(globe)

    # 4. Haversine fallback (only if global-land-mask is not installed)
    km = _haversine_km(origin[1], origin[0], dest[1], dest[0])
    return jsonify({
        'distance_km':    round(km, 3),
        'distance_miles': round(km_to_miles(km), 3),
        'coordinates':    [origin, dest],
        'sea_routed':     False,
        'ai_routed':      False,
        'globe_routed':   False,
        'warning':        'Routing engine unavailable - straight-line shown.',
        'from_db':        False,
    })


def _ai_route_shore(origin, dest):
    """Use Claude to generate a water-following path for non-ocean water bodies."""
    if not ANTHROPIC_KEY:
        return None
    try:
        import anthropic, re, json as _json
        from calculate import km_to_miles

        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        start_lon, start_lat = origin
        end_lon, end_lat = dest

        prompt = (
            f"An open water swimmer needs to swim from shore point A to shore point B.\n\n"
            f"Start (A): longitude {start_lon}, latitude {start_lat}\n"
            f"End (B):   longitude {end_lon}, latitude {end_lat}\n\n"
            "This is NOT an ocean or sea - it is a lake, river, lagoon, bay, or inland water body.\n\n"
            "══════════════════════════════════════════\n"
            "THE ONE RULE THAT OVERRIDES EVERYTHING:\n"
            "Draw a straight line between every consecutive pair of waypoints.\n"
            "That line must NEVER cross land, a shoreline, a peninsula, or an island.\n"
            "Not even for one metre.\n"
            "══════════════════════════════════════════\n\n"
            "HOW TO ACHIEVE THIS:\n"
            f"• First point must be exactly: [{start_lon}, {start_lat}]\n"
            f"• Last point must be exactly: [{end_lon}, {end_lat}]\n"
            "• Intermediate points must be in open water, staying well clear of shores and islands\n"
            "• If the water body is narrow, keep points in the deepest/widest part of the channel\n"
            "• If there are islands, route AROUND them - never across\n"
            "• If the water narrows at any point, add extra intermediate waypoints to stay in the channel\n"
            "• No intermediate point may be on land, in a river mouth, in a harbour, or in\n"
            "  water too shallow to swim\n"
            "• Generate between 2 and 20 total points (including start and end)\n\n"
            "MANDATORY SELF-CHECK before you return your answer:\n"
            "Go through every consecutive pair in your list. For each pair ask:\n"
            "'Can a swimmer travel in a STRAIGHT LINE between these two points\n"
            "without touching land or crossing a shoreline?' If the answer is NO\n"
            "for any pair, insert extra intermediate points until the answer is YES\n"
            "for every single pair.\n\n"
            "Return ONLY a JSON array of [longitude, latitude] pairs, start to end. No markdown, no text."
        )

        msg = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=4096,
            messages=[{'role': 'user', 'content': prompt}],
        )
        text = msg.content[0].text.strip()
        text = re.sub(r'```[a-zA-Z]*', '', text).strip()
        text = text.replace('−', '-')  # Unicode minus → ASCII

        match = re.search(r'\[\s*\[[\s\S]*\]\s*\]', text)
        if not match:
            match = re.search(r'\[[\s\S]*\]', text)
        if not match:
            return None

        waypoints = _json.loads(match.group(0))
        if len(waypoints) < 2:
            return None

        # Total distance = sum of haversine segments
        total_km = 0.0
        for i in range(len(waypoints) - 1):
            lon1, lat1 = float(waypoints[i][0]), float(waypoints[i][1])
            lon2, lat2 = float(waypoints[i+1][0]), float(waypoints[i+1][1])
            total_km += _haversine_km(lat1, lon1, lat2, lon2)

        return {
            'distance_km':    round(total_km, 3),
            'distance_miles': km_to_miles(total_km),
            'coordinates':    waypoints,
            'sea_routed':     False,
            'ai_routed':      True,
            'warning':        'Non-ocean water body - swim path generated by AI. Verify route on map and drag markers to adjust if needed.',
        }
    except Exception:
        return None


def _haversine_km(lat1, lon1, lat2, lon2):
    import math
    R = 6371
    d = lambda x: x * math.pi / 180
    dLat = d(lat2 - lat1); dLon = d(lon2 - lon1)
    a = math.sin(dLat/2)**2 + math.cos(d(lat1))*math.cos(d(lat2))*math.sin(dLon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


# ── Land-crossing validation ────────────────────────────────────────────────────

_LAND_TREE  = None   # shapely STRtree (lazy-loaded)
_LAND_GEOMS = None   # list of land polygons

def _ensure_land_data():
    """Download Natural Earth 10m land polygons once, build spatial index."""
    global _LAND_TREE, _LAND_GEOMS
    if _LAND_TREE is not None:
        return True
    try:
        import shapefile as sf
        from shapely.geometry import shape
        from shapely.strtree import STRtree

        cache_dir = os.path.join(_SERVER_DIR, '.cache')
        shp_path  = os.path.join(cache_dir, 'ne_10m_land.shp')

        if not os.path.exists(shp_path):
            os.makedirs(cache_dir, exist_ok=True)
            url  = 'https://naturalearth.s3.amazonaws.com/10m_physical/ne_10m_land.zip'
            resp = urllib.request.urlopen(url, timeout=30)
            zipfile.ZipFile(io.BytesIO(resp.read())).extractall(cache_dir)

        reader      = sf.Reader(shp_path)
        _LAND_GEOMS = [shape(s.__geo_interface__) for s in reader.shapes()]
        _LAND_TREE  = STRtree(_LAND_GEOMS)
        return True
    except Exception:
        return False


def _is_on_land(lon, lat):
    """True if the point (lon, lat) is on land."""
    if not _ensure_land_data():
        return False
    try:
        from shapely.geometry import Point
        pt   = Point(lon, lat)
        hits = _LAND_TREE.query(pt, predicate='intersects')
        return any(_LAND_GEOMS[k].contains(pt) for k in hits)
    except Exception:
        return False


def _check_segments_land(waypoints):
    """
    For each consecutive [lon, lat] pair:
      • check whether the waypoint itself is on land
      • check whether the straight-line segment crosses land
    Returns (segment_problems, on_land_indices).
    """
    if not _ensure_land_data():
        return [], []
    try:
        from shapely.geometry import LineString, Point
        seg_problems  = []
        on_land_wps   = []

        for i, wp in enumerate(waypoints):
            if _is_on_land(float(wp[0]), float(wp[1])):
                on_land_wps.append(i + 1)  # 1-indexed

        for i in range(len(waypoints) - 1):
            lon1, lat1 = float(waypoints[i][0]),   float(waypoints[i][1])
            lon2, lat2 = float(waypoints[i+1][0]), float(waypoints[i+1][1])
            seg  = LineString([(lon1, lat1), (lon2, lat2)])
            hits = _LAND_TREE.query(seg, predicate='intersects')
            if len(hits) == 0:
                continue
            crossing = None
            for j in range(1, 20):
                t   = j / 20
                lon = lon1 + t * (lon2 - lon1)
                lat = lat1 + t * (lat2 - lat1)
                pt  = Point(lon, lat)
                if any(_LAND_GEOMS[k].contains(pt) for k in hits):
                    crossing = [round(lon, 4), round(lat, 4)]
                    break
            seg_problems.append({
                'segment':    i + 1,
                'from':       [round(lon1, 4), round(lat1, 4)],
                'to':         [round(lon2, 4), round(lat2, 4)],
                'land_point': crossing,
            })
        return seg_problems, on_land_wps
    except Exception:
        return [], []


def _interior_crosses_land(wpt_a, wpt_b, n=20):
    """Check only the interior of the path between two [lon, lat] points for land.
    Skips the first and last 15% of samples so coastal start/end coordinates
    (on a beach or harbour) don't trigger a false positive."""
    if not _ensure_land_data():
        return False
    try:
        from shapely.geometry import Point
        lon1, lat1 = float(wpt_a[0]), float(wpt_a[1])
        lon2, lat2 = float(wpt_b[0]), float(wpt_b[1])
        skip = max(1, int(n * 0.15))
        for i in range(skip, n - skip + 1):
            t   = i / n
            lon = lon1 + t * (lon2 - lon1)
            lat = lat1 + t * (lat2 - lat1)
            if _is_on_land(lon, lat):
                return True
        return False
    except Exception:
        return False


@app.route('/api/circumnavigate', methods=['POST'])
def api_circumnavigate():
    d = request.get_json()
    try:
        from circumnavigation import circumnavigate
        wp = [[float(w['lon']), float(w['lat'])] for w in d['waypoints']]
        result = circumnavigate(wp)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── AI waypoints ───────────────────────────────────────────────────────────────

_SERVER_DIR = os.path.dirname(os.path.abspath(__file__))

def _precomputed_route_path(landmass_name):
    """Return absolute path to a pre-computed GLOBE route file, or None if not found."""
    import re
    slug = re.sub(r'[^a-z0-9]+', '_', landmass_name.lower().strip()).strip('_')
    candidate = os.path.join(_SERVER_DIR, f'route_{slug}.json')
    return candidate if os.path.exists(candidate) else None


# ── Geographic circumnavigation agent ──────────────────────────────────────────

def _osmnx_circumnavigation(island_name, n_waypoints=24, offset_m=900, direction='clockwise'):
    """
    Fetch the island's boundary from OpenStreetMap, union with any nearby land
    within the buffer distance, then sample N evenly-spaced offshore waypoints.
    Returns list of [lon, lat] pairs, or raises on failure.
    """
    import osmnx as ox
    import pyproj
    from shapely.ops import transform as shp_transform, unary_union
    from shapely.geometry import MultiPolygon

    # 1 - Fetch boundary polygon from OSM
    gdf  = ox.geocode_to_gdf(island_name)
    poly = gdf.geometry.iloc[0]

    # 2 - Collect all constituent polygons (handles archipelagos / satellite islets)
    if isinstance(poly, MultiPolygon):
        parts = list(poly.geoms)
    else:
        parts = [poly]

    # 3 - Project to UTM for accurate metre-based buffering
    cx, cy = poly.centroid.x, poly.centroid.y
    zone   = int((cx + 180) / 6) + 1
    south  = '+south' if cy < 0 else ''
    utm    = f'+proj=utm +zone={zone} +datum=WGS84 +units=m +no_defs {south}'.strip()
    to_utm   = pyproj.Transformer.from_crs('EPSG:4326', utm,        always_xy=True).transform
    to_wgs84 = pyproj.Transformer.from_crs(utm,        'EPSG:4326', always_xy=True).transform

    # 4 - Buffer the main parts and build an initial offshore ring
    main_utm       = unary_union([shp_transform(to_utm, p) for p in parts])
    main_area_utm  = main_utm.area  # used to filter out mainland polygons later
    offshore_utm   = main_utm.buffer(offset_m, resolution=64)
    offshore       = shp_transform(to_wgs84, offshore_utm)

    # 5 - Detect crossings and absorb nearby satellite features
    #     If the initial ring crosses any land (nearby islets, rocks), add those
    #     features to the union so the ring routes around them too.
    #     Guard: only absorb features whose area (in UTM m²) is < 20× the main island -
    #     this prevents accidentally absorbing mainland continents.
    if _ensure_land_data():
        from shapely.geometry import LineString
        ring_coords = list(offshore.exterior.coords)
        extra_utm   = []
        seen        = set()
        for i in range(len(ring_coords) - 1):
            seg  = LineString([ring_coords[i], ring_coords[i + 1]])
            hits = _LAND_TREE.query(seg, predicate='intersects')
            for k in hits:
                if k in seen:
                    continue
                seen.add(k)
                land = _LAND_GEOMS[k]
                sub_list = list(land.geoms) if hasattr(land, 'geoms') else [land]
                for sub in sub_list:
                    if sub.intersects(seg):
                        sub_utm = shp_transform(to_utm, sub)
                        if sub_utm.area < main_area_utm * 20:
                            extra_utm.append(sub_utm)
        if extra_utm:
            offshore_utm = unary_union([main_utm] + extra_utm).buffer(offset_m, resolution=64)
            offshore     = shp_transform(to_wgs84, offshore_utm)

    # 6 - Sample N evenly-spaced points along the outer perimeter
    ring = offshore.exterior
    waypoints = []
    for i in range(n_waypoints):
        pt = ring.interpolate(i / n_waypoints, normalized=True)
        waypoints.append([round(pt.x, 6), round(pt.y, 6)])

    # 7 - Correct winding order to match requested direction
    if direction == 'counterclockwise':
        waypoints = list(reversed(waypoints))

    return waypoints


@app.route('/api/propose-waypoints', methods=['POST'])
def api_propose_waypoints():
    d = request.get_json()
    landmass = d.get('landmass', '').strip()

    # ── Pre-computed GLOBE route (highest priority) ────────────────────────────
    route_file = _precomputed_route_path(landmass)
    if route_file:
        try:
            with open(route_file) as f:
                route = json.load(f)
            from calculate import km_to_miles

            # Named waypoints (exclude last if it duplicates first)
            wps = route.get('waypoints', [])
            if len(wps) >= 2:
                last, first = wps[-1], wps[0]
                if abs(last['lat'] - first['lat']) < 0.001 and abs(last['lon'] - first['lon']) < 0.001:
                    wps = wps[:-1]

            # Full dense path: route.json stores [lat, lon] - convert to [lon, lat] for the frontend
            raw_path = route.get('path', [])
            path_lonlat = [[p[1], p[0]] for p in raw_path]

            # Segments: convert km to miles
            segments = []
            for seg in route.get('segments', []):
                km = seg.get('km', 0)
                segments.append({
                    'from': seg.get('from', ''),
                    'to':   seg.get('to', ''),
                    'km':   round(km, 3),
                    'miles': round(km_to_miles(km), 3),
                })

            km_total = route.get('km', 0)
            return jsonify({
                'waypoints':      [[w['lon'], w['lat']] for w in wps],
                'waypoint_names': [w.get('name', '') for w in wps],
                'precomputed':    True,
                'source':         'GLOBE 925m Dijkstra routing - verified zero land crossings',
                'distance_km':    round(km_total, 3),
                'distance_miles': round(km_to_miles(km_total), 3),
                'path':           path_lonlat,
                'segments':       segments,
            })
        except Exception as e:
            return jsonify({'error': f'Failed to load pre-computed route: {e}'}), 500

    # ── Geographic agent: OSMnx boundary → 900 m buffer → evenly-spaced points ─
    direction = d.get('direction', 'clockwise')
    count     = int(d.get('count', 24))
    try:
        waypoints = _osmnx_circumnavigation(
            landmass, n_waypoints=count, offset_m=900, direction=direction,
        )
        seg_problems, on_land_wps = _check_segments_land(waypoints)
        remaining = len(seg_problems) + len(on_land_wps)
        return jsonify({
            'waypoints':      waypoints,
            'land_crossings': remaining,
            'source':         'osmnx',
            'warning':        (f'{remaining} potential issue(s) detected - drag markers to correct.'
                               if remaining else None),
        })
    except Exception:
        pass  # OSMnx failed (not in OSM, network error, etc.) - fall back to AI

    # ── AI fallback: Claude with land-crossing validation loop ─────────────────
    if not ANTHROPIC_KEY:
        return jsonify({'error': 'ANTHROPIC_API_KEY not configured on server'}), 503
    try:
        import anthropic, re
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        # count and direction already set above

        def _parse_waypoints(text):
            text = re.sub(r'```[a-zA-Z]*', '', text).strip()
            text = text.replace('−', '-')
            m = re.search(r'\[\s*\[[\s\S]*\]\s*\]', text)
            if not m:
                m = re.search(r'\[[\s\S]*\]', text)
            if not m:
                return None
            try:
                wps = json.loads(m.group(0))
                return wps if len(wps) >= 3 else None
            except Exception:
                return None

        def _base_prompt(n):
            return (
                f"Generate exactly {n} GPS waypoints for an open water circumnavigation "
                f"swim around {landmass}, going {direction}.\n\n"
                "CRITICAL RULES - every single one is mandatory:\n"
                f"1. Return exactly {n} waypoints, no more, no less\n"
                "2. Every point MUST be in OPEN WATER - NOT on land, NOT on a beach,\n"
                "   NOT in a river, harbour, or shallow bay. Each point must be\n"
                "   at least 800 m from the nearest shoreline.\n"
                "3. Verify each point individually: if placing a point, ask yourself\n"
                "   'Is this coordinate in the open sea/ocean right now?' - if there\n"
                "   is any doubt, move it further from shore.\n"
                "4. Trace the COMPLETE coastline - no section skipped\n"
                "5. Add extra waypoints around peninsulas, headlands, and capes to curve\n"
                "   around them rather than cutting across\n"
                "6. The straight line between every consecutive pair must stay in water\n\n"
                "Return ONLY a JSON array of [longitude, latitude] pairs. No markdown, no text."
            )

        # ── Attempt 1: initial generation ─────────────────────────────────
        msg  = client.messages.create(
            model='claude-sonnet-4-6', max_tokens=4096,
            messages=[{'role': 'user', 'content': _base_prompt(count)}],
        )
        best = _parse_waypoints(msg.content[0].text)
        if not best:
            return jsonify({'error': 'AI did not return a valid coordinate list'}), 500

        seg_problems, on_land_wps = _check_segments_land(best)
        total_problems = len(seg_problems) + len(on_land_wps)

        # ── Attempt 2 ─────────────────────────────────────────────────────
        if total_problems > 0:
            seg_ratio = len(seg_problems) / max(len(best) - 1, 1)

            if seg_ratio > 0.4 or len(on_land_wps) > 2:
                # Most waypoints are wrong - full regeneration with stronger instructions
                regen_prompt = (
                    f"PREVIOUS ATTEMPT FAILED for circumnavigation of {landmass}:\n"
                    f"  • {len(on_land_wps)} waypoint(s) were placed ON LAND (not in water)\n"
                    f"  • {len(seg_problems)} segment(s) crossed land\n\n"
                    "You MUST generate a completely new set of waypoints.\n\n"
                    + _base_prompt(count) + '\n\n'
                    "EXTRA GUIDANCE FOR THIS SPECIFIC LANDMASS:\n"
                    f"• {landmass} is surrounded by water on all sides\n"
                    "• Every waypoint must be placed in the OPEN SEA, not on the coast\n"
                    "• If you are unsure whether a coordinate is water or land, move it\n"
                    "  further away from shore until you are certain it is in open water\n"
                    "• Think: where would a ship anchor offshore? Place points there."
                )
                msg2 = client.messages.create(
                    model='claude-sonnet-4-6', max_tokens=4096,
                    messages=[{'role': 'user', 'content': regen_prompt}],
                )
            else:
                # Targeted fix for a small number of specific problems
                lines = []
                for i in on_land_wps:
                    lines.append(f"  • Waypoint {i} ({best[i-1]}) is ON LAND - move it to open water ≥800 m from shore")
                for p in seg_problems:
                    desc = f"  • Segment {p['segment']} ({p['from']} → {p['to']}) crosses land"
                    if p['land_point']:
                        desc += f" near {p['land_point']}"
                    lines.append(desc)

                fix_prompt = (
                    f"Circumnavigation of {landmass} - {len(lines)} problem(s) to fix:\n"
                    + '\n'.join(lines) + '\n\n'
                    f"Current waypoints:\n{json.dumps(best)}\n\n"
                    "Fix each problem:\n"
                    "• For ON LAND waypoints: move them into open water ≥800 m offshore\n"
                    "• For crossing segments: insert intermediate open-water waypoints to route around the obstacle\n"
                    "• Keep all other waypoints unchanged\n"
                    "• Return the COMPLETE updated list as a JSON array of [longitude, latitude] pairs. No markdown."
                )
                msg2 = client.messages.create(
                    model='claude-sonnet-4-6', max_tokens=4096,
                    messages=[{'role': 'user', 'content': fix_prompt}],
                )

            fixed = _parse_waypoints(msg2.content[0].text)
            if fixed:
                fixed_seg, fixed_on_land = _check_segments_land(fixed)
                if len(fixed_seg) + len(fixed_on_land) <= total_problems:
                    best         = fixed
                    seg_problems = fixed_seg
                    on_land_wps  = fixed_on_land

        remaining = len(seg_problems) + len(on_land_wps)
        warning = (f'{remaining} issue(s) remain (land crossings or on-land waypoints) - '
                   'drag markers to correct before running circumnavigation.'
                   if remaining else None)

        return jsonify({
            'waypoints':      best,
            'land_crossings': remaining,
            'warning':        warning,
        })

    except json.JSONDecodeError as e:
        return jsonify({'error': f'Could not parse AI response as JSON: {e}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    _db_init()
    print(f'\nWOWSA API Server  ->  http://localhost:{PORT}')
    print(f'  Google Maps key: {"✓ configured" if MAPS_KEY else "not set - interactive map disabled"}')
    print(f'  Anthropic key:   {"✓ configured" if ANTHROPIC_KEY else "not set - AI waypoints disabled"}')
    print()
    app.run(host='0.0.0.0', port=PORT, debug=False)
