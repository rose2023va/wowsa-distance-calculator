# WOWSA Swimmable Distance Methodology

Version: 1.0  
Library: searoute-py (check installed version: `pip3 show searoute`)  
Units: kilometres (km) primary, miles secondary  
Coordinate convention: inputs use lat,lon; internally GeoJSON order (lon,lat) is used throughout

---

## Why this tool exists

An AI giving a swim distance is not a defensible source of truth. The same question
can return a different answer on a different run with no way to audit how it was derived.

A method is defensible when:
- The same inputs always produce the same output
- The method is documented and published
- Anyone can rerun it and verify the result

This tool meets all three criteria.

---

## Calculation layer: searoute-py

searoute-py computes the shortest sea route between two coordinate pairs by routing
through a maritime network that avoids land — not a straight line through it.
It returns a GeoJSON LineString tracing the path plus the total distance.

**Known limitation:** The network was built for commercial shipping between ports,
not for coastline-hugging swim routes. For point-to-point open water crossings the
result closely matches the real swimmable path. For tight coastline routes, verify
the output against the swimmer's actual route before treating it as the official figure.

---

## Visualization layer: Google Maps

Google Maps is used only for display. The coordinate list from searoute-py is passed
to the Google Maps JavaScript API and drawn as a polyline on a satellite view.
Google does not influence the distance figure in any way.

Pass `--maps-key YOUR_KEY` to any script to open the result as an interactive map
in your browser automatically.

---

## Point-to-point swims

```
python3 calculate.py --origin LAT,LON --destination LAT,LON
python3 calculate.py --origin LAT,LON --destination LAT,LON --maps-key YOUR_KEY
python3 calculate.py --gpx swimmer-file.gpx --maps-key YOUR_KEY
python3 calculate.py --origin LAT,LON --destination LAT,LON --output record.json
```

The terminal prints a timestamped ratification record. With `--maps-key` the route
opens in the browser on a satellite map with a green start marker and red finish marker.

---

## Circumnavigation swims

For swims that close back on themselves (swimming around an island or peninsula),
use this three-step workflow:

### Step 1 — AI proposes candidate waypoints

Ask Claude (or another AI):

> "Propose waypoints placed in open water around [island/landmass name] for a
> circumnavigation swim, going [clockwise/counterclockwise]. Return as a JSON array
> of [longitude, latitude] pairs only — no explanation."

Save the AI's output to a file named `candidate-[landmass].json`.

Example output format:
```json
[
  [-74.0060, 40.7128],
  [-73.9442, 40.7831],
  [-74.0200, 40.6892]
]
```

**Important:** AI is used only to propose a starting list. It cannot decide the
final waypoints — a different prompt or run could place them differently, which
breaks reproducibility.

### Step 2 — Human verifies each waypoint on Google Maps

```
python3 propose-waypoints.py \
  --waypoints candidate-[landmass].json \
  --name "[Landmass Name]" \
  --maps-key YOUR_KEY
```

This opens a satellite map in your browser with each candidate waypoint shown as a
numbered marker. Click each one to confirm:

- The point sits in open water (not on land, not in a harbour that would be avoided)
- The sequence traces the coastline sensibly in the intended direction
- No obvious gaps or waypoints that would route through land

Make any corrections to the JSON file manually — move, add, or remove points until
the sequence is correct. When satisfied, rename the file:

```
mv candidate-[landmass].json locked-[landmass]-waypoints.json
```

The `locked-` prefix is required by `circumnavigation.py` as a signal that human
verification has been completed.

### Step 3 — Run the circumnavigation calculator

```
python3 circumnavigation.py \
  --waypoints locked-[landmass]-waypoints.json \
  --maps-key YOUR_KEY \
  --output [landmass]-ratification-record.json
```

The terminal prints a ratification record with total distance and per-leg breakdown.
With `--maps-key` the full route opens in the browser with numbered waypoint markers
and the stitched route drawn in blue.

---

## Locked reference data

Once a circumnavigation has been officially measured, the following must be archived:

- The locked waypoints JSON file (exact file used, not regenerated)
- searoute-py version (`pip3 show searoute`)
- Date of measurement
- Total distance in km and miles
- Per-leg breakdown
- The JSON output record

This allows any swimmer, organizer, or ratification body to rerun the exact
calculation and reproduce the same result independently. The locked waypoints file
has the same standing as the swim's published start and finish coordinates —
it must not be modified after ratification.
