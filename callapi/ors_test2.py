from typing import List, Tuple, Literal, Optional, Sequence, Union, Dict
import math, requests, time

# 내부 계산 표준: (lon, lat) 튜플
Coord = Tuple[float, float]

# =========================
# 공개 API (최종 결과: 딕셔너리)
# =========================

def build_multiple_corrected_roundcourses(
    start_lon: float,
    start_lat: float,
    distance_m: int,
    ors_api_key: str,
    tmap_api_key: str,
    n_routes: int = 10,
    ors_profile: Literal["foot-walking","cycling-regular","driving-car"] = "foot-walking",
    tmap_profile: Literal["pedestrian","car","bicycle"] = "pedestrian",
    seed_base: int = 11,
    seed_step: int = 997,
    points_cycle: Sequence[int] = (3, 4,),
    # 새 옵션: Tmap 한 번 호출용 경유지 개수(권장 3~6)
    n_passes: int = 4,
) -> List[Dict]:
    """
    ORS → (raw 겹침 제거) → (등간격 경유지 추출) → Tmap '한 번' 스냅(passList)
    각 루트를 {"경로":[[lon,lat],...], "회전":{...}, "횡단보도 개수":n, "경로의 총 길이":m} 형태로 반환
    """
    routes: List[Dict] = []
    for i in range(n_routes):
        seed_i = seed_base + i * seed_step
        points_i = points_cycle[i % len(points_cycle)]

        result = build_corrected_roundcourse(
            start_lon=start_lon,
            start_lat=start_lat,
            distance_m=distance_m,
            ors_api_key=ors_api_key,
            tmap_api_key=tmap_api_key,
            ors_profile=ors_profile,
            tmap_profile=tmap_profile,
            points=points_i,
            seed=seed_i,
            n_passes=n_passes,      # <= 분할 대신 '다중 경유지' 사용
        )
        routes.append(result)  # 딕셔너리
    return routes


def build_corrected_roundcourse(
    start_lon: float,
    start_lat: float,
    distance_m: int,
    ors_api_key: str,
    tmap_api_key: str,
    ors_profile: Literal["foot-walking","cycling-regular","driving-car"] = "foot-walking",
    tmap_profile: Literal["pedestrian","car","bicycle"] = "pedestrian",
    points: int = 3,
    seed: int = 42,
    # 새 옵션: Tmap 한 번 호출용 경유지 개수
    n_passes: int = 4,
    # (선택) 최종 길이를 목표거리로 컷할지
    trim_to_target: bool = False,
) -> dict:
    """
    1) ORS 라운드코스
    2) (RAW) 겹침 구간 과감히 삭제(겹치기 시작점만 유지)
    3) 등거리 '경유지(passList)' 추출
    4) Tmap에 시작/경유지/종점 한 번에 전달하여 스냅 + guides 수집
    5) 후처리(+소중복 제거, (옵션)목표거리 컷)
    최종 리턴: {"경로":[[lon,lat],...], "회전":{"좌회전":n,"우회전":n}, "횡단보도 개수":n, "경로의 총 길이":m}
    """
    # 1) ORS round-trip
    raw_ors: List[Coord] = ors_roundtrip(
        start_lon, start_lat, distance_m, ors_api_key,
        profile=ors_profile, seed=seed, points=points
    )

    # 2) ORS 단계에서 겹침 삭제
    raw_ors_pruned: List[Coord] = prune_overlaps_keep_single_anchor(
        raw_ors, edge_tol_round=6, point_tol_m=0.5
    )

    # 3) 등거리 경유지 추출 (시작/끝 제외, n_passes개)
    pass_pts: List[Coord] = select_passpoints_equal_distance(
        raw_ors_pruned, n_passes=n_passes
    )

    # 4) Tmap 스냅(한 번 호출, passList 사용, guides 수집)
    snapped_path, guides = tmap_route_with_passlist(
        start=(start_lon, start_lat),
        passes=pass_pts,
        end=(raw_ors_pruned[-1][0], raw_ors_pruned[-1][1]),
        tmap_api_key=tmap_api_key,
        profile=tmap_profile
    )

    # 5) 후처리
    merged: List[Coord] = dedup_path_by_distance(snapped_path, tol_m=0.5)

    # (선택) 목표거리로 컷
    if trim_to_target and distance_m > 0:
        merged = trim_path_to_length(merged, float(distance_m))

    counts = analyze_turns_and_crosswalks(guides)
    total_len_m = linestring_length_m(merged)

    return {
        "경로": to_lists(merged),  # [[lon,lat], ...]
        "회전": {"좌회전": counts["left_turns"], "우회전": counts["right_turns"]},
        "횡단보도 개수": counts["crosswalks"],
        "경로의 총 길이": float(total_len_m),
    }

# =========================
# ORS / Tmap 호출부
# =========================

def ors_roundtrip(
    start_lon: float,
    start_lat: float,
    distance_m: int,
    ors_api_key: str,
    profile: Literal["foot-walking","cycling-regular","driving-car"] = "foot-walking",
    seed: int = 42,
    points: int = 3,
) -> List[Coord]:
    """ ORS Directions round_trip 라인 반환: [(lon,lat), ...] """
    url = f"https://api.openrouteservice.org/v2/directions/{profile}/geojson"
    headers = {"Authorization": ors_api_key, "Content-Type": "application/json"}
    body = {
        "coordinates": [[start_lon, start_lat]],
        "options": {"round_trip": {
            "length": max(1000, int(distance_m)),
            "points": points,
            "seed": seed
        }}
    }
    r = _request_with_retry("POST", url, headers=headers, json=body)
    gj = r.json()
    coords = gj["features"][0]["geometry"]["coordinates"]  # [[lon,lat], ...]
    # 종점이 시작점과 매우 가까우면 딱 시작점으로 정렬
    if haversine_m((coords[-1][0], coords[-1][1]), (start_lon, start_lat)) < 50:
        coords[-1] = [start_lon, start_lat]
    return [(float(c[0]), float(c[1])) for c in coords]


def tmap_route_with_passlist(
    start: Coord,
    passes: List[Coord],
    end: Coord,
    tmap_api_key: str,
    profile: Literal["car","pedestrian","bicycle"] = "pedestrian",
) -> Tuple[List[Coord], List[Dict]]:
    """
    Tmap REST Routes를 '한 번' 호출하여 (start → passList... → end) 경로를 스냅.
    반환: (coords[(lon,lat)...], guides[{"turnType":..., "pointType":..., "index":...}, ...])
    """
    base = "https://apis.openapi.sk.com/tmap"
    if profile == "car":
        endpoint = f"{base}/routes?version=1"
        payload = {
            "startX": f"{start[0]}", "startY": f"{start[1]}",
            "endX": f"{end[0]}",     "endY": f"{end[1]}",
            "passList": encode_passlist(passes),
            "reqCoordType": "WGS84GEO",
            "resCoordType": "WGS84GEO",
            "searchOption": "0"
        }
    elif profile == "pedestrian":
        endpoint = f"{base}/routes/pedestrian?version=1"
        payload = {
            "startX": f"{start[0]}", "startY": f"{start[1]}",
            "endX": f"{end[0]}",     "endY": f"{end[1]}",
            "passList": encode_passlist(passes),
            "reqCoordType": "WGS84GEO",
            "resCoordType": "WGS84GEO",
            "startName": "S", "endName": "E",
            "sort": "index"
        }
    else:
        endpoint = f"{base}/routes/bicycle?version=1"
        payload = {
            "startX": f"{start[0]}", "startY": f"{start[1]}",
            "endX": f"{end[0]}",     "endY": f"{end[1]}",
            "passList": encode_passlist(passes),
            "reqCoordType": "WGS84GEO",
            "resCoordType": "WGS84GEO",
        }

    headers = {"Content-Type": "application/json", "appKey": tmap_api_key}
    r = _request_with_retry("POST", endpoint, headers=headers, json=payload)
    data = r.json()

    coords: List[Coord] = []
    guides: List[Dict] = []

    if "features" in data:
        for feat in data["features"]:
            geom = feat.get("geometry", {})
            gtype = geom.get("type")
            props = feat.get("properties", {}) or {}

            if gtype == "LineString":
                for x, y in geom.get("coordinates", []):
                    coords.append((float(x), float(y)))
            elif gtype == "MultiLineString":
                for line in geom.get("coordinates", []):
                    for x, y in line:
                        coords.append((float(x), float(y)))
            elif gtype == "Point":
                tt = props.get("turnType")
                pt = props.get("pointType")
                idx = props.get("index")
                if tt is not None or pt is not None:
                    guides.append({"turnType": tt, "pointType": pt, "index": idx})
    else:
        raise ValueError("Unrecognized Tmap response format for route")

    coords = dedup_path_by_distance(coords, tol_m=0.5)
    return coords, guides

# =========================
# passList / 경유지 선택 유틸
# =========================

def encode_passlist(passes: List[Coord]) -> str:
    """
    Tmap passList 형식: "lon,lat_lon,lat_lon,lat"
    (빈 리스트면 빈 문자열)
    """
    if not passes:
        return ""
    parts = []
    for lon, lat in passes:
        parts.append(f"{lon},{lat}")
    return "_".join(parts)

def select_passpoints_equal_distance(poly: List[Coord], n_passes: int = 4) -> List[Coord]:
    """
    ORS(중복 삭제 후) 라인을 전체 길이 기준 등간격으로 n_passes개 추출.
    - 시작점/끝점은 제외하고 중간 점만 반환 (passList로 사용).
    """
    if n_passes <= 0 or len(poly) < 2:
        return []
    total = linestring_length_m(poly)
    if total <= 0:
        return []
    step = total / (n_passes + 1)
    pts: List[Coord] = []
    for k in range(1, n_passes + 1):
        target = step * k
        pts.append(point_at_distance(poly, target))
    return pts

# =========================
# 겹침 '삭제' 로직 (RAW에서 수행)
# =========================

def prune_overlaps_keep_single_anchor(
    poly: List[Coord],
    edge_tol_round: int = 6,
    point_tol_m: float = 0.5
) -> List[Coord]:
    """
    이미 지나간 엣지를 다시 밟으려 하면:
      - 겹치기 '시작점'(앵커)만 남기고
      - 겹치는 구간 전체를 건너뛴 뒤,
      - 겹침이 끝나는 첫 '새 엣지' 시작점으로 점프(연결선은 그리지 않음).
    """
    if len(poly) < 2:
        return poly[:]

    seen = set()  # 무방향 엣지 키
    out: List[Coord] = [poly[0]]

    i = 0
    while i < len(poly) - 1:
        a, b = poly[i], poly[i+1]
        k = _edge_key(a, b, nd=edge_tol_round)

        if k not in seen:
            seen.add(k)
            if haversine_m(out[-1], b) > point_tol_m:
                out.append(b)
            i += 1
        else:
            # 겹침 시작: i+1부터 계속 스킵하다가 '새 엣지'가 나오는 위치 j 찾기
            j = i + 1
            while j < len(poly) - 1:
                k2 = _edge_key(poly[j], poly[j+1], nd=edge_tol_round)
                if k2 not in seen:
                    break
                j += 1

            # 끝까지 겹친다면 종료
            if j >= len(poly) - 1:
                break

            # 앵커(out[-1]==a)는 유지, 겹침 종료 첫 점 poly[j]만 추가해서 점프
            if haversine_m(out[-1], poly[j]) > point_tol_m:
                out.append(poly[j])

            i = j  # j 지점부터 재개
    return out

# =========================
# 거리/보간 등 유틸
# =========================

def dedup_path_by_distance(path: List[Coord], tol_m: float = 0.5) -> List[Coord]:
    """ 연속 중복/초근접 점 제거 """
    out: List[Coord] = []
    for pt in path:
        if not out or haversine_m(out[-1], pt) > tol_m:
            out.append(pt)
    return out

def trim_path_to_length(path: List[Coord], target_m: float) -> List[Coord]:
    """경로를 시작점부터 target_m 지점까지만 남기고 잘라낸다."""
    if not path or target_m <= 0:
        return path[:1] if path else []
    cum = [0.0]
    for i in range(1, len(path)):
        cum.append(cum[-1] + haversine_m(path[i-1], path[i]))
    if cum[-1] <= target_m:
        return path[:]  # 이미 짧음
    i = next(k for k in range(1, len(cum)) if cum[k] >= target_m)
    seg_len = max(1e-9, cum[i] - cum[i-1])
    t = (target_m - cum[i-1]) / seg_len
    cut = interpolate_point(path[i-1], path[i], t)
    return path[:i] + [cut]

def haversine_m(p1: Coord, p2: Coord) -> float:
    R = 6371000.0
    lon1, lat1 = map(math.radians, p1)
    lon2, lat2 = map(math.radians, p2)
    dlon, dlat = lon2 - lon1, lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def linestring_length_m(coords: List[Coord]) -> float:
    return sum(haversine_m(coords[i], coords[i+1]) for i in range(len(coords)-1))

def cumulative_lengths(coords: List[Coord]) -> List[float]:
    acc = [0.0]
    for i in range(1, len(coords)):
        acc.append(acc[-1] + haversine_m(coords[i-1], coords[i]))
    return acc

def interpolate_point(p1: Coord, p2: Coord, t: float) -> Coord:
    lon = p1[0] + (p2[0]-p1[0]) * t
    lat = p1[1] + (p2[1]-p1[1]) * t
    return (lon, lat)

def point_at_distance(coords: List[Coord], target_m: float) -> Coord:
    """ polyline 시작점으로부터 target_m 지점의 좌표 """
    if target_m <= 0: return coords[0]
    cum = cumulative_lengths(coords)
    total = cum[-1]
    if target_m >= total: return coords[-1]
    i = next(k for k in range(1, len(cum)) if cum[k] >= target_m)
    seg_len = cum[i] - cum[i-1]
    t = (target_m - cum[i-1]) / seg_len if seg_len > 0 else 0.0
    return interpolate_point(coords[i-1], coords[i], t)

def to_tmap_v3_path(coords_list_format: List[List[float]]) -> List[dict]:
    """ Tmap JS v3용 [{"lat":lat, "lng":lon}, ...] (입력은 [[lon,lat], ...]) """
    return [{"lat": float(lat), "lng": float(lon)} for lon, lat in coords_list_format]

def _request_with_retry(method, url, **kwargs):
    for attempt in range(3):
        try:
            r = requests.request(method, url, timeout=20, **kwargs)
            if r.status_code == 429:
                time.sleep(1.0 + attempt)
                continue
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(0.8 * (attempt + 1))

# =========================
# 겹침 판정 유틸(무방향 엣지 키)
# =========================

def _round_coord(p: Coord, nd=6) -> Tuple[float, float]:
    return (round(p[0], nd), round(p[1], nd))

def _edge_key(a: Coord, b: Coord, nd=6) -> Tuple[Tuple[float,float], Tuple[float,float]]:
    a2, b2 = _round_coord(a, nd), _round_coord(b, nd)
    return (a2, b2) if a2 <= b2 else (b2, a2)

# =========================
# 최종 리스트 변환
# =========================

def to_lists(path: List[Union[Coord, List[float]]]) -> List[List[float]]:
    """[(lon,lat), ...] 또는 [[lon,lat], ...] → [[lon,lat], ...]"""
    return [[float(p[0]), float(p[1])] for p in path]

# =========================
# 회전/횡단보도 집계 유틸
# =========================

# 표 기준: 좌/우 회전 및 횡단보도 turnType 코드
LEFT_TURNS = {12, 16, 17}                              # 좌회전, 8시방향 좌회전, 10시방향 좌회전
RIGHT_TURNS = {13, 18, 19}                             # 우회전, 2시방향 우회전, 4시방향 우회전
CROSSWALKS = {211, 212, 213, 214, 215, 216, 217}       # 횡단보도 계열

def analyze_turns_and_crosswalks(guides: List[Dict]) -> Dict[str, int]:
    """
    Tmap 'Point' 피처의 properties.turnType을 이용해
    좌/우 회전 횟수와 횡단보도 통과 횟수를 집계
    """
    left_turns = right_turns = crosswalks = 0
    for g in guides:
        tt = g.get("turnType")
        if not isinstance(tt, int):
            continue
        if tt in LEFT_TURNS:
            left_turns += 1
        elif tt in RIGHT_TURNS:
            right_turns += 1
        elif tt in CROSSWALKS:
            crosswalks += 1
    return {
        "left_turns": left_turns,
        "right_turns": right_turns,
        "crosswalks": crosswalks,
    }
