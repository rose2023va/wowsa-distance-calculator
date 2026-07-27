"""
Shared Google Maps HTML output for WOWSA distance scripts.
Generates a self-contained HTML file and opens it in the default browser.
"""

import json
import webbrowser
from pathlib import Path
from datetime import datetime, timezone

_BASE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0d1117; }}
  #header {{ padding: 14px 24px; background: #0d1117; color: #fff;
             display: flex; align-items: center; gap: 40px;
             border-bottom: 1px solid #21262d; }}
  #header h1 {{ font-size: 12px; font-weight: 500; color: #8b949e;
                letter-spacing: 0.8px; text-transform: uppercase; }}
  .dist-primary {{ font-size: 30px; font-weight: 700; color: #58a6ff; line-height: 1; }}
  .dist-secondary {{ font-size: 13px; color: #8b949e; margin-top: 4px; }}
  .meta {{ font-size: 11px; color: #484f58; margin-top: 6px; line-height: 1.6; }}
  #map {{ height: calc(100vh - 86px); width: 100%; }}
</style>
</head>
<body>
<div id="header">
  <div>
    <h1>{label}</h1>
    <div class="meta">{meta}</div>
  </div>
  <div>
    <div class="dist-primary">{primary}</div>
    <div class="dist-secondary">{secondary}</div>
  </div>
</div>
<div id="map"></div>
<script>
function initMap() {{
  var map = new google.maps.Map(document.getElementById('map'), {{
    mapTypeId: 'satellite', zoom: 4
  }});
  {map_js}
}}
</script>
<script async defer
  src="https://maps.googleapis.com/maps/api/js?key={api_key}&callback=initMap">
</script>
</body>
</html>"""


def _save_and_open(html, path):
    p = Path(path)
    p.write_text(html, encoding="utf-8")
    webbrowser.open(p.resolve().as_uri())
    print(f"Map opened: {p.resolve()}")


def route_html(result, api_key, output_path="wowsa-distance-map.html"):
    """Point-to-point route map — green start, red finish, blue polyline."""
    coords = result["geojson"]["geometry"]["coordinates"]
    js_path = json.dumps([{"lat": c[1], "lng": c[0]} for c in coords])
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    js = f"""
  var path = {js_path};
  new google.maps.Polyline({{ path: path, map: map, geodesic: false,
    strokeColor: '#58a6ff', strokeOpacity: 0.9, strokeWeight: 3 }});

  new google.maps.Marker({{ position: path[0], map: map, title: 'Origin',
    icon: {{ path: google.maps.SymbolPath.CIRCLE, scale: 7,
      fillColor: '#3fb950', fillOpacity: 1, strokeColor: '#fff', strokeWeight: 2 }} }});
  new google.maps.Marker({{ position: path[path.length-1], map: map, title: 'Destination',
    icon: {{ path: google.maps.SymbolPath.CIRCLE, scale: 7,
      fillColor: '#f85149', fillOpacity: 1, strokeColor: '#fff', strokeWeight: 2 }} }});

  var b = new google.maps.LatLngBounds();
  path.forEach(function(p) {{ b.extend(p); }});
  map.fitBounds(b);
"""

    meta = (f"Origin: {result['origin']['lat']}, {result['origin']['lon']}  →  "
            f"Destination: {result['destination']['lat']}, {result['destination']['lon']}\n"
            f"{ts}  |  searoute-py (maritime routing, avoids land)")

    html = _BASE.format(
        title="WOWSA Swimmable Distance",
        label="WOWSA · Swimmable Distance",
        meta=meta,
        primary=f"{result['distance_km']} km",
        secondary=f"{result['distance_miles']} miles",
        map_js=js,
        api_key=api_key,
    )
    _save_and_open(html, output_path)


def circumnavigation_html(result, api_key, output_path="wowsa-circumnavigation-map.html"):
    """Circumnavigation map — full route in blue, numbered waypoint markers in gold."""
    coords = result["route_coordinates"]
    js_path = json.dumps([{"lat": c[1], "lng": c[0]} for c in coords])
    waypoints = result["waypoints_used"]
    js_wps = json.dumps([{"lat": w["lat"], "lng": w["lon"]} for w in waypoints])
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    js = f"""
  var path = {js_path};
  var wps  = {js_wps};

  new google.maps.Polyline({{ path: path, map: map, geodesic: false,
    strokeColor: '#58a6ff', strokeOpacity: 0.9, strokeWeight: 3 }});

  var info = new google.maps.InfoWindow();
  wps.forEach(function(wp, i) {{
    var m = new google.maps.Marker({{
      position: wp, map: map,
      label: {{ text: String(i+1), color: '#fff', fontSize: '11px', fontWeight: '700' }},
      icon: {{ path: google.maps.SymbolPath.CIRCLE, scale: 9,
        fillColor: '#d29922', fillOpacity: 1, strokeColor: '#fff', strokeWeight: 2 }}
    }});
    m.addListener('click', function() {{
      info.setContent('<b>Waypoint ' + (i+1) + '</b><br>' + wp.lat.toFixed(5) + ', ' + wp.lng.toFixed(5));
      info.open(map, m);
    }});
  }});

  var b = new google.maps.LatLngBounds();
  path.forEach(function(p) {{ b.extend(p); }});
  map.fitBounds(b);
"""

    leg_summary = "  |  ".join(
        f"Leg {l['leg']}: {l['distance_km']} km" for l in result["legs"]
    )
    meta = (f"{len(waypoints)} waypoints  |  {ts}  |  searoute-py (maritime routing)\n"
            f"{leg_summary}")

    html = _BASE.format(
        title="WOWSA Circumnavigation Distance",
        label="WOWSA · Circumnavigation Distance",
        meta=meta,
        primary=f"{result['total_distance_km']} km",
        secondary=f"{result['total_distance_miles']} miles",
        map_js=js,
        api_key=api_key,
    )
    _save_and_open(html, output_path)


def waypoint_verification_html(waypoints, landmass_name, api_key,
                               output_path="verify-waypoints.html"):
    """
    Verification map for AI-proposed candidate waypoints.
    Opens in browser so a human can confirm each numbered point is in water
    before the list is locked as reference data.
    """
    js_wps = json.dumps([{"lat": w[1], "lng": w[0]} for w in waypoints])

    js = f"""
  var wps = {js_wps};
  var info = new google.maps.InfoWindow();

  // Dashed proposed loop
  new google.maps.Polyline({{
    path: wps.concat([wps[0]]), map: map, geodesic: false,
    strokeColor: '#d29922', strokeOpacity: 0.5, strokeWeight: 2,
    icons: [{{ icon: {{ path: 'M 0,-1 0,1', strokeOpacity: 1, scale: 3 }},
              offset: '0', repeat: '18px' }}]
  }});

  wps.forEach(function(wp, i) {{
    var m = new google.maps.Marker({{
      position: wp, map: map,
      label: {{ text: String(i+1), color: '#fff', fontSize: '11px', fontWeight: '700' }},
      icon: {{ path: google.maps.SymbolPath.CIRCLE, scale: 10,
        fillColor: '#d29922', fillOpacity: 1, strokeColor: '#fff', strokeWeight: 2 }}
    }});
    m.addListener('click', function() {{
      info.setContent(
        '<b>Waypoint ' + (i+1) + '</b><br>' +
        'Lat: ' + wp.lat.toFixed(5) + '<br>' +
        'Lon: ' + wp.lng.toFixed(5) + '<br><br>' +
        '<span style="color:#cc8800">Confirm this point is in water<br>before locking the waypoint list.</span>'
      );
      info.open(map, m);
    }});
  }});

  var b = new google.maps.LatLngBounds();
  wps.forEach(function(p) {{ b.extend(p); }});
  map.fitBounds(b);
"""

    meta = (f"AI-proposed candidate waypoints for {landmass_name}\n"
            f"Click each marker to verify it sits in water and traces the coastline correctly.\n"
            f"Do not run circumnavigation.py until all waypoints are confirmed and the file is renamed to locked-*.json")

    html = _BASE.format(
        title=f"Verify Waypoints — {landmass_name}",
        label=f"WOWSA · Waypoint Verification — {landmass_name}",
        meta=meta,
        primary=f"{len(waypoints)} candidate waypoints",
        secondary="Pending human verification",
        map_js=js,
        api_key=api_key,
    )
    _save_and_open(html, output_path)
