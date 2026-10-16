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
    def __init__(self, geojson: dict, name_field: str = "shapeName"):
        self.items = []
        for f in geojson.get("features", []):
            polys = _rings(f["geometry"])
            xs = [p[0] for poly in polys for p in poly[0]]
            ys = [p[1] for poly in polys for p in poly[0]]
            if xs:
                self.items.append((f["properties"].get(name_field, "Unknown"), (min(xs), min(ys), max(xs), max(ys)), polys))

    def lookup(self, lon: float, lat: float) -> str:
        for name, (x0, y0, x1, y1), polys in self.items:
            if not (x0 <= lon <= x1 and y0 <= lat <= y1):
                continue
            for poly in polys:
                if _in_ring(lon, lat, poly[0]) and not any(_in_ring(lon, lat, hole) for hole in poly[1:]):
                    return name
        return "Outside Indonesia"
