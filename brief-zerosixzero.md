# WOWSA Route Distance Calculator: Technical Brief

---

## What this tool does

It calculates the official swimmable distance for any open water route. The output is a standardized measurement, not derived from any individual swimmer's GPS track, but from the route itself. That figure becomes the number every future swimmer on that route is measured against.

It covers two swim types: shore-to-shore crossings and circumnavigations (loops around an island or landmass).

An initial build has been completed and is available to preview at [web-production-e08e3.up.railway.app](https://web-production-e08e3.up.railway.app). The core challenge encountered is routing accuracy - standard routing tools are built for shipping, not swimming, and struggle to stay in swimmable water, particularly in narrow channels, inland bodies, and anywhere close to shore.

---

## Shore-to-shore

Input is a start coordinate and an end coordinate. The tool finds the shortest path through water between those two points, avoiding land, and returns the distance in km and miles plus a route line for the map.

The swimmer's GPS track is separate from this. Their GPX shows where they actually swam; the official route shows the standardized path. Both go on the map, overlaid.

---

## Circumnavigation

Input is an ordered set of waypoints placed in open water around the landmass. The tool routes between consecutive waypoints and sums the legs into a total distance for the loop.

The waypoints are set by WOWSA, not derived from the swimmer. Once a circumnavigation is officially measured, those exact waypoints are locked. They become the permanent definition of that route, the same way start and finish coordinates define a crossing.

Generating the initial waypoints: the tool fetches the island's boundary from OpenStreetMap, buffers 900 meters offshore, and samples evenly-spaced points around the perimeter. When that fails (the island isn't in OSM, or the generated points land on terrain), Claude AI proposes the waypoints instead, then runs a self-check against a land polygon dataset and corrects any points that are on land or produce segments that cross it. A human reviews and confirms each waypoint before anything gets calculated.

---

## Routing

The primary routing library is [searoute-py](https://github.com/rose2023va/searoute-py), which finds the shortest maritime path between two coordinates using a shipping lane network. It handles ocean crossings well.

It fails in two situations: narrow water bodies (gulfs, inland seas, lakes) where the shipping network has no coverage, and cases where it snaps to the nearest commercial port rather than the actual swim coordinates, sometimes hundreds of kilometers away. Both produce wrong results.

When searoute fails those validation checks, the tool falls back to Claude AI, which generates a route through open water. This handles lakes, bays, lagoons, and inland passages. If the AI isn't available, the last fallback is a straight-line haversine, which is defensible for open water with no obstacles.

Each route segment is checked against a land polygon dataset before the result is accepted. If a segment crosses land, the AI gets a correction pass with the specific problem segments flagged.

---

## What we need from ZeroSixZero

**Hosted API.** The calculation logic needs to run as a real endpoint, not locally. It accepts route parameters (coordinates for a crossing, or waypoints for a circumnavigation) and returns distance plus route geometry.

**Map integration.** ZeroSixZero's existing map already displays the swimmer's GPS track. The second layer, WOWSA's calculated official route, needs to be added to that same map. Both paths on one view: what the swimmer actually swam, and what the standardized route is. The integration point is the existing map, not a new one.

**Route pages.** Each established route needs a permanent page: official distance, the map, the list of people who've swum it (some ratified, some unverified). This is the product - the route as a living record.

---

## What WOWSA contributes

Route definitions - start and finish coordinates for crossings, locked waypoint files for circumnavigations. The distance calculator and all underlying code. Distance certificates generated from the official calculation for ratification purposes.

---

## The hard part

Circumnavigation in tight spaces is still the trickiest problem. When the water between the island and the mainland is narrow, routing between waypoints without clipping land requires either a lot of intermediate points or accepting straight-line segments for those legs. We flag which legs used straight-line distance so it's transparent in the output.

---

## What we have so far

All files are in the [wowsa-distance-calculator](https://github.com/rose2023va/wowsa-distance-calculator) repository.

| File | What it does |
|---|---|
| [calculate.py](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/calculate.py) | Core shore-to-shore distance engine. Runs searoute, validates the result, falls back to AI or haversine if needed. |
| [circumnavigation.py](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/circumnavigation.py) | Takes an ordered list of waypoints and calculates total loop distance, leg by leg. |
| [propose-waypoints.py](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/propose-waypoints.py) | Generates initial offshore waypoints for a circumnavigation using OSMnx island boundary + 900m buffer. |
| [map_output.py](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/map_output.py) | Outputs the calculated route as a Google Maps link for visual verification. |
| [server.py](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/server.py) | Flask server that exposes the calculation and waypoint logic as API endpoints for the web interface. |
| [index.html](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/index.html) | Web interface with an interactive map. |
| [METHODOLOGY.md](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/METHODOLOGY.md) | Documents the routing methodology and validation logic. |
| [requirements.txt](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/requirements.txt) | Python dependencies. |
