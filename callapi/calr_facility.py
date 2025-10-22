# calr_facility.py  (새 파일로 분리 추천)
from functools import lru_cache
from shapely.geometry import Point, LineString
from shapely.strtree import STRtree
from shapely import prepared, ops
from pyproj import Transformer
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 1) 좌표 변환기 (WGS84 -> EPSG:5179, 미터단위)
_transformer = Transformer.from_crs("EPSG:4326", "EPSG:5179", always_xy=True)

def _to5179_xy(lon, lat):
    x, y = _transformer.transform(lon, lat)
    return x, y

@lru_cache(maxsize=1)
def load_facility_points():
    """
    가벼운 포인트 데이터만 메모리에 1회 적재.
    - 파일 포맷은 JSON/CSV 아무거나 가능.
    - 필드: name, type, lat, lon
    (가능하면 'points.parquet' 등으로 더 가볍게 저장해서 읽는 걸 권장)
    """
    file_path = os.path.join(BASE_DIR, "data", "facility_points.json")
    with open(file_path, "r", encoding="utf-8") as f:
        items = json.load(f)  # [{name, type, lat, lon}, ...]

    # EPSG:5179으로 미리 변환
    geoms = []
    meta = []
    for it in items:
        x, y = _to5179_xy(it["lon"], it["lat"])
        geoms.append(Point(x, y))
        meta.append((it["name"], it["type"], it["lat"], it["lon"]))

    # STRtree 구축 (빠른 후보 질의용)
    tree = STRtree(geoms)
    # 인덱스 매핑
    idx_map = {id(g): i for i, g in enumerate(geoms)}
    return geoms, meta, tree, idx_map

def check_facility(route_coords, buf_m=200, max_return=300):
    """
    route_coords: [(lat, lon), ...] 또는 [(lon, lat), ...] 가 아니라면 꼭 아래에서 통일!
    buf_m: 라인 주변 탐색 반경(미터)
    """
    # 0) 데이터/인덱스 1회 로딩 (메모리 재사용)
    geoms, meta, tree, idx_map = load_facility_points()

    # 1) 경로 좌표 -> EPSG:5179
    #    네 코드가 (lat, lon) 이었으니 그대로 맞춰 변환
    proj_coords = [_to5179_xy(lon, lat) for (lat, lon) in route_coords]  # 주의: (lon, lat) 순서로 변환기 사용
    line = LineString(proj_coords)

    # 2) 라인을 적당히 단순화해서 버퍼 비용 절감
    #    (수치 5~10m 정도 권장; 너무 크면 형태 왜곡)
    line = line.simplify(5, preserve_topology=True)

    # 3) 버퍼 만들기 (사각 조인 방지 위해 평면상 버퍼)
    buf = line.buffer(buf_m, join_style=2)  # join_style=2: 깔끔한 miter

    # 4) 공간 인덱스 질의(후보군 뽑기) — 아주 빠름
    candidates = tree.query(buf)

    # 5) 최종 필터: 실제 거리가 buf_m 이내인지 체크
    #    (query는 바운딩 박스 기반이라 오탐 있을 수 있음)
    prep_line = prepared.prep(line)
    out = []
    for c in candidates:
        i = idx_map[id(c)]
        # 빠른 배제: 버퍼 내부(or 라인과 교차)면 OK
        if buf.contains(c) or prep_line.intersects(c):
            name, typ, lat, lon = meta[i]
            out.append({"name": name, "type": typ, "lat": lat, "lon": lon})
            if len(out) >= max_return:
                break

    return out
