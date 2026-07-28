# WOWSA Route Distance Calculator: Technical Brief

---

## Why this exists

Open water swimming lacks a consistent way to define route distance. When a swimmer crosses the English Channel, the reported distance varies depending on who measured it and how - GPS tracks differ swimmer to swimmer, straight-line approximations ignore the actual water path, and there is no agreed methodology.

WOWSA ratifies swims. For a ratification to mean something, the distance has to mean something. The goal of this tool is to produce one authoritative distance per route that every future swimmer on that route is measured against - not derived from any individual's GPS track, but from the route itself.

A working build is available to preview at [web-production-e08e3.up.railway.app](https://web-production-e08e3.up.railway.app).

---

## The two calculation types

These are fundamentally different problems, which is why they are handled separately.

### Shore-to-shore

Two coordinates go in. The tool finds the shortest path through water between them - avoiding every coastline, headland, and island along the way - and returns that distance as the official measurement for that crossing.

This is the more complete of the two. The routing uses the GLOBE dataset (a 925-meter resolution global land mask) combined with A* pathfinding. It builds a water grid over the bounding box of the two coordinates, finds the shortest all-water path, and applies line-of-sight smoothing to produce a clean route line. Accurate to within the grid resolution, typically under 100 meters on a 30-40 km crossing.

The swimmer's GPS track is separate. Their GPX shows where they actually swam. The official route shows the standardized path. Both go on the map, overlaid.

Saving is manual: a WOWSA team member reviews the calculated route, enters a name, and clicks "Add to database." From that point the distance is locked. Any future query for those coordinates returns the saved result with no recalculation.

### Circumnavigation

This is harder, and the input is fundamentally different from a crossing.

A shore-to-shore crossing takes two coordinates. The route is defined entirely by the geography between them - give the tool a start and an end, and there is one correct answer.

A circumnavigation cannot work this way. The start and end are the same point - it is a loop. Two coordinates tell you nothing about the route. "Around Ireland" could mean 500 meters offshore or 5 kilometers offshore, clockwise or counterclockwise, and the resulting distance changes significantly depending on those choices. The route cannot be derived from coordinates alone; it has to be defined.

So the input is different: a landmass name, a direction (clockwise or counterclockwise), and a waypoint count. The tool constructs the route from there.

**What it does now:**

The tool fetches the island boundary from OpenStreetMap and projects it into UTM coordinates for accurate metre-based calculations. It buffers 900 meters offshore, samples evenly-spaced waypoints around that perimeter, then checks whether the buffer ring crosses any nearby satellite islands or rocks. If it does, it absorbs those features into the union before re-running the buffer, so the ring routes around them. The sampled waypoints define the course. The official distance is the sum of the legs connecting them.

When OpenStreetMap does not have the boundary - or when the generated waypoints still land on terrain - Claude AI proposes the waypoints instead. The AI proposal goes through a land-crossing validation pass using a Natural Earth polygon dataset. Any segment that crosses land, or any waypoint placed on land, is flagged and sent back to the AI for a correction pass before the user sees anything.

Each leg between consecutive waypoints is routed using the same GLOBE A* approach as shore-to-shore crossings - finding the shortest all-water path through the GLOBE land mask. The full route renders on the map, and the user can drag any waypoint to adjust its position and re-run the calculation.

**Where it still needs work:**

The 900-meter offshore buffer is consistent in concept but not always in practice. Headlands and peninsulas cause the evenly-spaced sampling to bunch up in tight areas. Satellite rocks not in OpenStreetMap are not detected. The AI fallback produces different waypoints each time for the same island and is unreliable for complex coastlines.

The remaining weakness is the waypoint placement itself. The generated waypoints define the course, and if they are not placed consistently at the right offshore distance, the total distance varies. A swimmer adjusting the waypoints manually gets a different number than the auto-generated default.

**Current status:** Ireland is the only completed and saved course. For other islands, the tool generates a usable starting point that can be adjusted and saved, but the auto-generated waypoint placement is not yet reliable enough to produce a ratifiable distance without review.

---

## What we need from ZeroSixZero

**Hosted API.** The calculation logic needs to run as a real endpoint, not locally. It accepts coordinates for a crossing, or waypoints for a circumnavigation, and returns distance plus route geometry.

**Map integration.** ZeroSixZero's existing map already shows the swimmer's GPS track. The second layer - WOWSA's official route - goes on the same map. Both paths on one view: what the swimmer actually swam versus what the standardized route is.

**Input on circumnavigation.** The waypoint placement close to shore is where accuracy still breaks down. Specifically: we need the waypoint placement itself to land consistently at a defined distance from shore regardless of how complex or irregular the coastline is. If you have worked on something similar or know of an approach that holds up for tight coastal geometry, we would like to hear how you have handled it.

**Multi-island circumnavigation.** Some WOWSA-ratified swims go around more than one island in a single route - not one island at a time, but a connected loop that takes in multiple landmasses. The current tool handles a single named landmass. We need a way to define a route that circumnavigates several islands as one course - a defined order, a consistent offshore distance around each, and connecting legs between them. We have not designed the input model for this yet and would value input on how to structure it before building.

---

## The standardization logic

The database is the source of truth. A distance becomes official when a WOWSA team member saves it with a route name. Before it is saved, it is just a calculation. After it is saved, it is the number.

This applies to both crossing and circumnavigation. The same coordinates or the same island queried twice should always return the same result.

---

## What we have so far

All files are in the [wowsa-distance-calculator](https://github.com/rose2023va/wowsa-distance-calculator) repository.

| File | What it does |
|---|---|
| [server.py](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/server.py) | Flask API. All endpoints: calculate, save-route, propose-waypoints, circumnavigate. GLOBE A* routing engine and PostgreSQL logic. |
| [index.html](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/index.html) | Web interface with Google Maps. Shore-to-shore and circumnavigation modes, draggable waypoints, "Add to database" flow. |
| [propose-waypoints.py](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/propose-waypoints.py) | CLI tool for generating initial offshore waypoints from an island boundary. |
| [route_ireland.json](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/route_ireland.json) | Pre-computed verified route for Ireland circumnavigation. |
| [requirements.txt](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/requirements.txt) | Python dependencies including global-land-mask for GLOBE routing. |
