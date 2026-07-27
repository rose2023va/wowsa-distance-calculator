#!/usr/bin/env python3
"""
WOWSA Swimmable Distance Calculator

Computes the shortest swimmable route between two points using searoute-py,
which routes through a maritime network avoiding land rather than drawing
a straight line. Optionally generates a Google Static Maps visualization URL.

Usage:
  python calculate.py --origin 35.6762,139.6503 --destination 51.5074,-0.1278
  python calculate.py --gpx myswim.gpx
  python calculate.py --origin 35.6762,139.6503 --destination 51.5074,-0.1278 --maps-key YOUR_KEY --output result.json

Methodology: https://github.com/rose2023va/wowsa-builds
"""

import argparse
import json
import sys
from pathlib import Path


def encode_polyline(coordinates):
    """Encode [lon, lat] pairs as a Google Encoded Polyline string."""
    def encode_value(value):
        value = int(round(value * 1e5))
        value = value << 1
        if value < 0:
            value = ~value
        chunks = []
        while value >= 0x20:
            chunks.append(chr((0x20 | (value & 0x1f)) + 63))
            value >>= 5
        chunks.append(chr(value + 63))
        return ''.join(chunks)

    result = []
    prev_lat = 0
    prev_lon = 0
    for lon, lat in coordinates:
        result.append(encode_value(lat - prev_lat))
        result.append(encode_value(lon - prev_lon))
        prev_lat = lat
        prev_lon = lon
    return ''.join(result)


def km_to_miles(km):
    return round(km * 0.621371, 3)


def parse_coord(s):
    """Parse 'lat,lon' string into [lon, lat] for searoute (GeoJSON order)."""
    parts = s.strip().split(',')
    if len(parts) != 2:
        raise ValueError(f"Expected 'lat,lon', got: {s}")
    lat, lon = float(parts[0]), float(parts[1])
    return [lon, lat]


def parse_gpx(gpx_path):
    """Return first and last point from a GPX file as [lon, lat] pairs."""
    try:
        import gpxpy
    except ImportError:
        print("Error: gpxpy is required for GPX input. Run: pip install gpxpy", file=sys.stderr)
        sys.exit(1)

    with open(gpx_path, 'r') as f:
        gpx = gpxpy.parse(f)

    points = []
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                points.append([point.longitude, point.latitude])
    for route in gpx.routes:
        for point in route.points:
            points.append([point.longitude, point.latitude])
    for waypoint in gpx.waypoints:
        points.append([waypoint.longitude, waypoint.latitude])

    if len(points) < 2:
        print("Error: GPX file must contain at least two points.", file=sys.stderr)
        sys.exit(1)

    return points[0], points[-1]


def build_maps_url(coordinates, api_key, width=800, height=400):
    """Build a Google Static Maps URL with the route drawn as an encoded polyline."""
    encoded = encode_polyline(coordinates)
    base = "https://maps.googleapis.com/maps/api/staticmap"
    params = (
        f"size={width}x{height}"
        f"&maptype=satellite"
        f"&path=color:0x4488ffff|weight:3|enc:{encoded}"
        f"&key={api_key}"
    )
    return f"{base}?{params}"


def calculate(origin_lonlat, destination_lonlat, maps_key=None):
    """
    Compute the shortest sea route between two [lon, lat] points.
    Returns a dict with distance_km, distance_miles, geojson, and optionally maps_url.
    """
    try:
        import searoute as sr
    except ImportError:
        print("Error: searoute is required. Run: pip install searoute", file=sys.stderr)
        sys.exit(1)

    route = sr.searoute(origin_lonlat, destination_lonlat, units="km")
    distance_km = round(route['properties']['length'], 3)
    coordinates = route['geometry']['coordinates']

    result = {
        "distance_km": distance_km,
        "distance_miles": km_to_miles(distance_km),
        "origin": {"lat": origin_lonlat[1], "lon": origin_lonlat[0]},
        "destination": {"lat": destination_lonlat[1], "lon": destination_lonlat[0]},
        "geojson": route,
    }

    if maps_key:
        result["maps_url"] = build_maps_url(coordinates, maps_key)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="WOWSA Swimmable Distance Calculator — computes shortest sea route via searoute-py."
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('--origin', metavar='LAT,LON',
                             help='Origin coordinate, e.g. 35.6762,139.6503')
    input_group.add_argument('--gpx', metavar='FILE',
                             help='GPX file — uses first and last point as origin and destination')

    parser.add_argument('--destination', metavar='LAT,LON',
                        help='Destination coordinate (required with --origin)')
    parser.add_argument('--maps-key', metavar='KEY',
                        help='Google Maps JavaScript API key (optional — opens interactive map in browser)')
    parser.add_argument('--output', metavar='FILE',
                        help='Save full results to a JSON file')

    args = parser.parse_args()

    if args.origin and not args.destination:
        parser.error("--destination is required when using --origin")

    if args.gpx:
        origin, destination = parse_gpx(args.gpx)
    else:
        origin = parse_coord(args.origin)
        destination = parse_coord(args.destination)

    result = calculate(origin, destination)

    from datetime import datetime, timezone
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    print(f"\n{'=' * 50}")
    print(f"  WOWSA SWIMMABLE DISTANCE — RATIFICATION RECORD")
    print(f"{'=' * 50}")
    print(f"  Date computed:  {timestamp}")
    print(f"  Origin:         {result['origin']['lat']}, {result['origin']['lon']}")
    print(f"  Destination:    {result['destination']['lat']}, {result['destination']['lon']}")
    print(f"  Method:         searoute-py (maritime routing, avoids land)")
    print(f"{'=' * 50}")
    print(f"  DISTANCE:  {result['distance_km']} km  /  {result['distance_miles']} miles")
    print(f"{'=' * 50}\n")

    if args.maps_key:
        from map_output import route_html
        route_html(result, args.maps_key)

    if args.output:
        out_path = Path(args.output)
        record = {
            "computed_at": timestamp,
            "method": "searoute-py",
            "origin": result["origin"],
            "destination": result["destination"],
            "distance_km": result["distance_km"],
            "distance_miles": result["distance_miles"],
            "geojson": result["geojson"],
        }
        with open(out_path, 'w') as f:
            json.dump(record, f, indent=2)
        print(f"Record saved to: {out_path}")


if __name__ == '__main__':
    main()
