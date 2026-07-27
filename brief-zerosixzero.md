# WOWSA Route Distance Calculator: Technical Brief

---

## What this tool does

It calculates the official swimmable distance for any open water route. The output is a standardized measurement - not derived from any individual swimmer's GPS track, but from the route itself. That figure becomes the number every future swimmer on that route is measured against.

It covers two swim types: shore-to-shore crossings and circumnavigations (loops around an island or landmass).

A working build is available to preview at [web-production-e08e3.up.railway.app](https://web-production-e08e3.up.railway.app).

---

## Shore-to-shore

Input is a start coordinate and an end coordinate. The tool finds the shortest path through water between those two points, avoiding land entirely, and returns the distance in km and miles plus a route line on the map.

The swimmer's GPS track is separate from this. Their GPX shows where they actually swam; the official route shows the standardized path. Both go on the map, overlaid.

---

## Circumnavigation

Input is an ordered set of waypoints placed in open water around the landmass. The tool routes between consecutive waypoints and sums the legs into a total distance for the loop.

The waypoints are set by WOWSA, not derived from the swimmer. Once a circumnavigation is officially measured, those exact waypoints are locked. They become the permanent definition of that route, the same way start and finish coordinates define a crossing.

Generating the initial waypoints: the tool fetches the island's boundary from OpenStreetMap, buffers 900 meters offshore, and samples evenly-spaced points around the perimeter. When that fails, Claude AI proposes the waypoints instead, then self-checks against a land polygon dataset and corrects any points that cross land. A human reviews and confirms each waypoint before anything gets calculated.

---

## Routing

Shore-to-shore routing uses the GLOBE dataset - a 925-meter resolution global land mask - combined with A* pathfinding. The algorithm builds a water grid over the bounding box of the two coordinates and finds the shortest all-water path between them, routing around every coastline, headland, and island it encounters. It produces a smooth line after a path-smoothing pass, and the resulting distance is accurate to within the grid resolution (~50 meters on a 33 km crossing).

This runs on-demand for any coordinate pair. It takes 2-5 seconds on first calculation. After that, the result is stored in the database and returned instantly for any repeat query of the same coordinates.

---

## Database and standardization

Every route calculated by the tool can be saved to a PostgreSQL database with a name. Saving is a manual step - a member of the WOWSA team enters a route name and clicks "Add to database." From that point, any query for those coordinates returns the saved result with no recalculation. This is how a distance becomes official: one calculation, reviewed by WOWSA, saved once.

The database is the source of truth. Pre-computed routes for complex courses (Ireland circumnavigation, others) are stored as JSON files in the repository for instant retrieval without any computation.

---

## What we need from ZeroSixZero

**Hosted API.** The calculation logic needs to run as a real endpoint, not locally. It accepts route parameters (coordinates for a crossing, or waypoints for a circumnavigation) and returns distance plus route geometry.

**Map integration.** ZeroSixZero's existing map already displays the swimmer's GPS track. The second layer - WOWSA's official route - needs to be added to that same map. Both paths on one view: what the swimmer actually swam, and what the standardized route is.

---

## The hard part

Circumnavigation in tight spaces is still the trickiest part. When the water between an island and the mainland is narrow, routing between waypoints without clipping land requires either a lot of intermediate points or accepting straight-line segments for those legs. We flag which legs used straight-line distance so it's transparent in the output.

For shore-to-shore, this is now solved: the GLOBE A* handles any crossing, including narrow channels and inland water bodies that shipping-lane tools cannot route through.

---

## What we have so far

All files are in the [wowsa-distance-calculator](https://github.com/rose2023va/wowsa-distance-calculator) repository.

| File | What it does |
|---|---|
| [server.py](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/server.py) | Flask API server. All endpoints: calculate, save-route, propose-waypoints, circumnavigate. Includes GLOBE A* routing engine and PostgreSQL database logic. |
| [index.html](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/index.html) | Web interface with Google Maps. Shore-to-shore and circumnavigation modes. "Add to database" flow for saving verified routes. |
| [circumnavigation.py](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/circumnavigation.py) | Takes an ordered list of waypoints and calculates total loop distance leg by leg. |
| [calculate.py](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/calculate.py) | Searoute-py wrapper, used for circumnavigation leg routing. |
| [propose-waypoints.py](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/propose-waypoints.py) | CLI tool for generating initial offshore waypoints using OSMnx boundary + 900m buffer. |
| [route_ireland.json](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/route_ireland.json) | Pre-computed GLOBE route for Ireland circumnavigation. |
| [requirements.txt](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/requirements.txt) | Python dependencies including global-land-mask for GLOBE routing. |
