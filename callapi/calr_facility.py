# calr_facility.py
import os, json, logging
from functools import lru_cache
from shapely.geometry import Point, LineString
from shapely.strtree import STRtree
from shapely import prepared
from pyproj import Transformer

logger = logging.getLogger("callapi")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "data", "facility_points.json")

_transformer = Transformer.from_crs("EPSG:4326", "EPSG:5179", always_xy=True)

def _to5179_xy(lon, lat):
    return _transformer.transform(lon, lat)

@lru_cache(maxsize=1)
def load_facility_points():
    if not os.path.exists(DATA_PATH):
        logger.error("facility_points.json not found at %s", DATA_PATH)
        # 빈 데이터로 진행(서버가 안 죽게)
        return [], [], STRtree([]), {}

    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            items = json.load(f)
    except Exception as e:
        logger.exception("Failed to load JSON at %s: %s", DATA_PATH, e)
        return [], [], STRtree([]), {}

    geoms, meta = [], []
    for it in items:
        try:
            lon, lat = float(it["lon"]), float(it["lat"])
            x, y = _to5179_xy(lon, lat)
            geoms.append(Point(x, y))
            meta.append((it.get("name",""), it.get("type",""), lat, lon))
        except Exception as e:
            logger.warning("Skip bad row %s (%s)", it, e)

    tree = STRtree(geoms) if geoms else STRtree([])
    idx_map = {id(g): i for i, g in enumerate(geoms)}
    logger.info("[facility] loaded points=%d from %s", len(geoms), DATA_PATH)
    return geoms, meta, tree, idx_map

def check_facility(route_coords, buf_m=200, max_return=300):
    # 입력 검증
    if not route_coords or not isinstance(route_coords, (list, tuple)):
        raise ValueError("route_coords must be a non-empty list of (lat, lon)")

    # 좌표 형태 점검(처음 몇 개만)
    sample = route_coords[0]
    if not (isinstance(sample, (list, tuple)) and len(sample) == 2):
        raise ValueError("Each coord must be (lat, lon) tuple")

    geoms, meta, tree, idx_map = load_facility_points()

    # 변환: (lat, lon) -> (lon, lat)로 뒤집어 변환기에 전달
    try:
        proj_coords = [_to5179_xy(lon, lat) for (lat, lon) in route_coords]
    except Exception as e:
        raise ValueError(f"Invalid route_coords values: {e}")

    from shapely.geometry import LineString
    line = LineString(proj_coords).simplify(5, preserve_topology=True)
    buf = line.buffer(buf_m, join_style=2)

    candidates = tree.query(buf) if tree else []
    prep_line = prepared.prep(line)
    out = []
    for c in candidates:
        i = idx_map.get(id(c))
        if i is None:
            continue
        if buf.contains(c) or prep_line.intersects(c):
            name, typ, lat, lon = meta[i]
            out.append({"name": name, "type": typ, "lat": lat, "lon": lon})
            if len(out) >= max_return:
                break
    logger.debug("[facility] hit=%d (buf=%dm, max=%d)", len(out), buf_m, max_return)
    return out
