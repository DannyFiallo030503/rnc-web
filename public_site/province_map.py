"""Geographic rendering of published aggregates, with explicit name matching."""

import json
import math
from functools import lru_cache
from pathlib import Path

NAMES = {
    "Isle of Youth": "Isla de la Juventud", "Havana": "La Habana",
    "Matanzas": "Matanzas", "Pinar del Rio": "Pinar del Río",
    "Camagüey": "Camagüey", "Ciego de Avila": "Ciego de Ávila",
    "Cienfuegos": "Cienfuegos", "Granma": "Granma", "Guantánamo": "Guantánamo",
    "Holguín": "Holguín", "Las Tunas": "Las Tunas", "Santiago de Cuba": "Santiago de Cuba",
    "Sancti Spiritus": "Sancti Spíritus", "Villa Clara": "Villa Clara",
    "Artemisa": "Artemisa", "Mayabeque": "Mayabeque",
}
COLORS = ("#e1f0ec", "#abd7cc", "#69b8a6", "#258e7b", "#075e5b")


@lru_cache(maxsize=1)
def geometries():
    source = Path(__file__).resolve().parent.parent / "static/geo/cuba-provinces.geojson"
    data = json.loads(source.read_text(encoding="utf-8"))
    regions = []
    for feature in data["features"]:
        geometry = feature["geometry"]
        polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        regions.append({"name": NAMES[feature["properties"]["shapeName"]], "polygons": polygons})
    return regions


def map_context(table):
    by_name = {row.get("display_label", row["label"]): row["value"] for row in table}
    values = [value for value in by_name.values() if value is not None]
    minimum, maximum = (min(values), max(values)) if values else (0, 0)
    all_points = [point for region in geometries() for polygon in region["polygons"] for ring in polygon for point in ring]
    west = min(point[0] for point in all_points)
    east = max(point[0] for point in all_points)
    north = max(point[1] for point in all_points)
    south = min(point[1] for point in all_points)
    ratio = math.cos(math.radians(22.5))
    scale = 960 / ((east - west) * ratio)
    height = (north - south) * scale + 40
    regions = []
    for region in geometries():
        value = by_name.get(region["name"])
        index = min(4, int((value - minimum) / (maximum - minimum) * 5)) if value is not None and maximum > minimum else 0
        commands = []
        for polygon in region["polygons"]:
            for ring in polygon:
                coords = [(20 + (x - west) * ratio * scale, 20 + (north - y) * scale) for x, y, *_ in ring]
                commands.append("M" + "L".join(f"{x:.2f},{y:.2f}" for x, y in coords) + "Z")
        regions.append({"name": region["name"], "value": value, "path": "".join(commands), "color": COLORS[index] if value is not None else "#dedede"})
    return {"regions": regions, "viewbox": f"0 0 1000 {height:.2f}", "minimum": minimum, "maximum": maximum, "colors": COLORS}
