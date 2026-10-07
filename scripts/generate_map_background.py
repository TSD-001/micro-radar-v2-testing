#!/usr/bin/env python3
"""Render OSM airport infrastructure and major roads to assets/background.png."""
import argparse, hashlib, json, math, os, sys
import urllib.error, urllib.parse, urllib.request
from pathlib import Path
from PIL import Image, ImageDraw

ENDPOINT = "https://overpass-api.de/api/interpreter"
EARTH_RADIUS_M = 6378137.0
BACKGROUND = (0, 0, 0)
RUNWAY = (192, 192, 192)  # light grey
AIRPORT = (96, 96, 96)    # dark grey for general aviation infrastructure
ROAD = (2, 48, 32)        # dark brown
AIRPORT_AREAS = {"aerodrome", "apron", "hangar", "terminal"}
AIRPORT_LINES = {"runway": 3.0, "taxiway": 0.0, "taxilane": 0.0, "parking_position": 0.0}
ROADS = {"motorway": 2.5, "motorway_link": 1.75, "trunk": 2.25,
         "trunk_link": 1.5, "primary": 1.75, "primary_link": 1.25}

def arguments():
    p = argparse.ArgumentParser(description="Generate the vector radar-map background")
    p.add_argument("--latitude", type=float, required=True)
    p.add_argument("--longitude", type=float, required=True)
    p.add_argument("--radius-km", type=float, required=True,
                   help="Ground distance from image centre to an edge")
    p.add_argument("--output", type=Path, default=Path("assets/background.png"))
    p.add_argument("--size", type=int, default=240)
    p.add_argument("--supersample", type=int, default=4)
    p.add_argument("--endpoint", default=ENDPOINT)
    p.add_argument("--cache-dir", type=Path, default=Path(".cache/osm-background"))
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--user-agent", default=os.getenv(
        "OSM_USER_AGENT", "AircraftRadarBackground/1.0 (set OSM_USER_AGENT with contact details)"))
    return p.parse_args()

def validate(a):
    if not -85 <= a.latitude <= 85: raise ValueError("latitude must be between -85 and 85")
    if not -180 <= a.longitude <= 180: raise ValueError("longitude must be between -180 and 180")
    if a.radius_km <= 0 or a.size <= 0 or a.supersample <= 0:
        raise ValueError("radius, size and supersample must be positive")

def bbox(lat, lon, radius_km):
    angular = radius_km * 1000 / EARTH_RADIUS_M
    dlat = math.degrees(angular)
    dlon = math.degrees(angular / math.cos(math.radians(lat)))
    return lat-dlat, lon-dlon, lat+dlat, lon+dlon

def query_for(box):
    b = ",".join(f"{v:.7f}" for v in box)
    return ("[out:json][timeout:90];\n(\n"
            f'way["aeroway"~"^(aerodrome|runway|taxiway|taxilane|apron|parking_position|hangar|terminal)$"]({b});\n'
            f'way["building"~"^(hangar|terminal)$"]({b});\n'
            f'way["highway"~"^(motorway|motorway_link|trunk|trunk_link|primary|primary_link)$"]({b});\n'
            ");\nout body;\n>;\nout skel qt;\n")

def download(query, a):
    a.cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256((a.endpoint + "\n" + query).encode()).hexdigest()
    cache = a.cache_dir / (key + ".json")
    if cache.exists() and not a.refresh:
        print(f"Using cached data: {cache}")
        return json.loads(cache.read_text(encoding="utf-8"))
    request = urllib.request.Request(a.endpoint,
        data=urllib.parse.urlencode({"data": query}).encode("ascii"), method="POST",
        headers={"User-Agent": a.user_agent, "Accept": "application/json",
                 "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        raise RuntimeError(f"Overpass HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not contact Overpass: {e.reason}") from e
    data = json.loads(raw.decode("utf-8"))
    cache.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    return data

def mercator(lat, lon):
    lat = min(85.05112878, max(-85.05112878, lat))
    return (EARTH_RADIUS_M * math.radians(lon),
            EARTH_RADIUS_M * math.log(math.tan(math.pi/4 + math.radians(lat)/2)))

def geometry(data):
    nodes, ways = {}, []
    for e in data.get("elements", []):
        if e.get("type") == "node" and "lat" in e:
            nodes[int(e["id"])] = (float(e["lat"]), float(e["lon"]))
        elif e.get("type") == "way": ways.append(e)
    return nodes, ways

def render(data, a):
    n = a.size * a.supersample
    image = Image.new("RGB", (n, n), BACKGROUND)
    draw = ImageDraw.Draw(image)
    nodes, ways = geometry(data)
    cx, cy = mercator(a.latitude, a.longitude)
    projected_radius = a.radius_km * 1000 / math.cos(math.radians(a.latitude))
    scale = (n / 2) / projected_radius
    def points(way):
        result = []
        for node_id in way.get("nodes", []):
            if int(node_id) in nodes:
                x, y = mercator(*nodes[int(node_id)])
                result.append((n/2 + (x-cx)*scale, n/2 - (y-cy)*scale))
        return result
    def closed(p): return len(p) >= 4 and p[0] == p[-1]
    for way in ways:
        tags = way.get("tags", {}); aw = tags.get("aeroway"); bld = tags.get("building")
        if aw not in AIRPORT_AREAS and bld not in {"hangar", "terminal"}: continue
        p = points(way)
        if closed(p): draw.polygon(p, fill=AIRPORT)
        elif len(p) >= 2: draw.line(p, fill=AIRPORT, width=a.supersample)
    for way in ways:
        aw = way.get("tags", {}).get("aeroway")
        if aw not in AIRPORT_LINES: continue
        p = points(way)
        if len(p) >= 2:
            colour = RUNWAY if aw == "runway" else AIRPORT
            if aw == "runway" and closed(p): draw.polygon(p, fill=colour)
            else: draw.line(p, fill=colour,
                            width=max(1, round(AIRPORT_LINES[aw]*a.supersample)), joint="curve")
    for way in ways:
        road = way.get("tags", {}).get("highway")
        if road not in ROADS: continue
        p = points(way)
        if len(p) >= 2: draw.line(p, fill=ROAD,
            width=max(1, round(ROADS[road]*a.supersample)), joint="curve")
    if a.supersample > 1:
        image = image.resize((a.size, a.size), Image.Resampling.LANCZOS)
    return image, len(ways)

def main():
    a = arguments()
    try:
        validate(a)
        data = download(query_for(bbox(a.latitude, a.longitude, a.radius_km)), a)
        image, count = render(data, a)
        a.output.parent.mkdir(parents=True, exist_ok=True)
        image.save(a.output, "PNG", optimize=True)
        print(f"Rendered {count} ways to {a.output} ({a.size}x{a.size}).")
        print("Next run: python scripts/convert_background.py")
        print("Map data: (c) OpenStreetMap contributors, ODbL 1.0")
        return 0
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as e:
        print(f"Error: {e}", file=sys.stderr); return 1
if __name__ == "__main__": raise SystemExit(main())
