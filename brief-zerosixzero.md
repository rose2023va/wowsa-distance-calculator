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

This is the more mature of the two. The routing uses the GLOBE dataset (a 925-meter resolution global land mask) combined with A* pathfinding. It builds a water grid over the bounding box of the two coordinates, finds the shortest all-water path, and applies line-of-sight smoothing to produce a clean route line. Result is accurate to within the grid resolution, typically under 100 meters on a 30-40 km crossing.

The swimmer's GPS track is separate. Their GPX shows where they actually swam. The official route shows the standardized path. Both go on the map, overlaid - what was swum versus what is defined.

Saving is manual and intentional: a WOWSA team member reviews the calculated route, enters a name, and clicks "Add to database." From that point the distance is locked. Any future query for those coordinates returns the saved result with no recalculation.

### Circumnavigation

This is harder, and the input is fundamentally different from a crossing - which is why it works differently in the tool.

A shore-to-shore crossing takes two coordinates. The route is defined entirely by the geography between them: give the tool a start and an end, and there is one correct shortest-water-path answer.

A circumnavigation cannot work this way. The start and end are the same point - it is a loop. Two coordinates tell you nothing about the route. "Around Ireland" could mean 500 meters offshore or 5 kilometers offshore, clockwise or counterclockwise, and the resulting distance changes significantly depending on those choices. The route cannot be derived from coordinates alone; it has to be defined.

So the input is different: a landmass name, a direction (clockwise or counterclockwise), and a waypoint count. The tool constructs the route from there - it fetches the island boundary from OpenStreetMap, buffers 900 meters offshore, and samples evenly-spaced waypoints around the perimeter. Those waypoints define the course. The official distance is the sum of the legs connecting them.

When OpenStreetMap does not have the boundary, Claude AI proposes the waypoints and self-checks them against land polygon data. Either way, a human reviews every waypoint on the map before any distance is calculated.

Routing between waypoints uses a maritime routing library. This is where accuracy degrades: in narrow passages between an island and the mainland, the routing either fails or clips land. In open water it works; close to shore it struggles.

**Circumnavigation is started but not yet accurate.** Ireland is the only completed course - pre-computed using a more careful method and stored as a verified file. For other islands, the waypoint generation works but the leg routing is not reliable enough to produce a ratifiable distance.

---

## What we need from ZeroSixZero

**Hosted API.** The calculation logic needs to run as a real endpoint, not locally. It accepts coordinates for a crossing, or waypoints for a circumnavigation, and returns distance plus route geometry.

**Map integration.** ZeroSixZero's existing map already shows the swimmer's GPS track. The second layer - WOWSA's official route - goes on the same map. Both paths on one view: what the swimmer actually swam versus what the standardized route is.

**Input on circumnavigation.** This is the part we most want to discuss. Circumnavigation accuracy depends on how precisely the route can be kept in water around complex coastlines. ZeroSixZero's experience with maritime routing and coastal data may point to a better approach than what we have now - whether that is a different routing method, a dataset we are not using, or a methodology for defining offshore waypoints that produces consistent results across different islands. Any input on what has worked for similar problems would help us get this right.

---

## The standardization logic

The database is the source of truth. A distance becomes official when a WOWSA team member saves it with a route name. Before it is saved, it is just a calculation. After it is saved, it is the number.

This matters because the same coordinates queried twice should always return the same result. Without the database, two people calculating the same crossing on different days could get slightly different distances depending on the routing at that moment. With it, the first verified result is the permanent one.

---

## What we have so far

All files are in the [wowsa-distance-calculator](https://github.com/rose2023va/wowsa-distance-calculator) repository.

| File | What it does |
|---|---|
| [server.py](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/server.py) | Flask API. All endpoints: calculate, save-route, propose-waypoints, circumnavigate. GLOBE A* routing engine and PostgreSQL logic. |
| [index.html](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/index.html) | Web interface with Google Maps. Shore-to-shore and circumnavigation modes, map review, "Add to database" flow. |
| [circumnavigation.py](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/circumnavigation.py) | Takes an ordered list of waypoints and calculates total loop distance leg by leg. |
| [calculate.py](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/calculate.py) | Maritime routing wrapper, used for circumnavigation leg routing. |
| [propose-waypoints.py](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/propose-waypoints.py) | CLI tool for generating initial offshore waypoints from an island boundary. |
| [route_ireland.json](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/route_ireland.json) | Pre-computed verified route for Ireland circumnavigation. |
| [requirements.txt](https://github.com/rose2023va/wowsa-distance-calculator/blob/main/requirements.txt) | Python dependencies including global-land-mask for GLOBE routing. |
