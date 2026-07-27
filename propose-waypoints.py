#!/usr/bin/env python3
"""
WOWSA Waypoint Verification Tool

Step 1 of the circumnavigation workflow: takes AI-proposed candidate waypoints
and opens them on a Google Map so a human can verify each point is in water
before the list is locked for use in circumnavigation.py.

Workflow:
  1. Ask Claude: "Propose waypoints in water around [island] for a circumnavigation
     swim. Return as JSON array of [longitude, latitude] pairs."
  2. Save Claude's output to a file, e.g. candidate-waypoints.json
  3. Run this script to open the verification map
  4. Click each numbered marker — confirm it sits in open water
  5. Rename the confirmed file to locked-[island]-waypoints.json
  6. Run: python3 circumnavigation.py --waypoints locked-[island]-waypoints.json

Waypoint file format ([longitude, latitude] — GeoJSON order):
  [
    [-74.0060, 40.7128],
    [-73.9442, 40.7831],
    ...
  ]

Usage:
  python3 propose-waypoints.py --waypoints candidate.json --name "Manhattan Island" --maps-key YOUR_KEY
"""

import argparse
import json
import sys
from pathlib import Path

from map_output import waypoint_verification_html


def main():
    parser = argparse.ArgumentParser(
        description="Open AI-proposed waypoints on Google Maps for human verification."
    )
    parser.add_argument('--waypoints', metavar='FILE', required=True,
                        help='JSON file of candidate waypoints: [[lon, lat], ...]')
    parser.add_argument('--name', metavar='NAME', required=True,
                        help='Landmass name, e.g. "Manhattan Island"')
    parser.add_argument('--maps-key', metavar='KEY', required=True,
                        help='Google Maps JavaScript API key')
    parser.add_argument('--output', metavar='FILE', default='verify-waypoints.html',
                        help='HTML output file (default: verify-waypoints.html)')

    args = parser.parse_args()

    wp_path = Path(args.waypoints)
    if not wp_path.exists():
        print(f"Error: file not found: {wp_path}", file=sys.stderr)
        sys.exit(1)

    with open(wp_path) as f:
        waypoints = json.load(f)

    if not isinstance(waypoints, list) or len(waypoints) < 2:
        print("Error: waypoints file must be a JSON array of at least 2 [lon, lat] pairs.",
              file=sys.stderr)
        sys.exit(1)

    print(f"\nWaypoint Verification — {args.name}")
    print(f"{'=' * 50}")
    print(f"  {len(waypoints)} candidate waypoints loaded from {wp_path.name}")
    for i, wp in enumerate(waypoints):
        print(f"  {i+1:2}. lon {wp[0]}, lat {wp[1]}")
    print(f"\nOpening verification map in browser...")
    print(f"  → Click each numbered marker to confirm it is in water.")
    print(f"  → When satisfied, rename the confirmed file:")
    confirmed_name = wp_path.stem.replace("candidate", "locked") + ".json"
    print(f"     mv {wp_path} {confirmed_name}")
    print(f"  → Then run:")
    print(f"     python3 circumnavigation.py --waypoints {confirmed_name} --maps-key YOUR_KEY\n")

    waypoint_verification_html(waypoints, args.name, args.maps_key, args.output)


if __name__ == '__main__':
    main()
