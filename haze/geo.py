"""Assign each hotspot to a province with a point-in-polygon test (no GIS libraries)."""


def _rings(geometry: dict) -> list[list[list[list[float]]]]:
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"]]
    if geometry["type"] == "MultiPolygon":
        return geometry["coordinates"]
    return []


def _in_ring(x: float, y: float, ring: list[list[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


class ProvinceIndex:
    """Province lookup. Each polygon (island) keeps its own bounding box, so a point is
    only tested against the few polygons whose box contains it."""

    def __init__(self, geojson: dict, name_field: str = "shapeName"):
        self.polys = []
        for f in geojson.get("features", []):
            name = (f.get("properties") or {}).get(name_field, "Unknown")
            for poly in _rings(f.get("geometry") or {}):
                if not poly or len(poly[0]) < 4:
                    continue
                xs = [p[0] for p in poly[0]]
                ys = [p[1] for p in poly[0]]
                self.polys.append((name, min(xs), min(ys), max(xs), max(ys), poly))
        self._cache: dict = {}

    def lookup(self, lon: float, lat: float) -> str:
        key = (round(lon, 4), round(lat, 4))
        if key in self._cache:
            return self._cache[key]
        result = "Outside Indonesia"
        for name, x0, y0, x1, y1, poly in self.polys:
            if x0 <= lon <= x1 and y0 <= lat <= y1 and _in_ring(lon, lat, poly[0]) \
                    and not any(_in_ring(lon, lat, hole) for hole in poly[1:]):
                result = name
                break
        self._cache[key] = result
        return result
