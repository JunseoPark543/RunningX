# 한 번만 실행하는 변환 스크립트 (로컬)
import geopandas as gpd
import json
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 같은 폴더에 있는 geojson 파일 경로 지정
file_path = os.path.join(BASE_DIR, "facility_buffers.geojson")
file_path2 = os.path.join(BASE_DIR, "facility_points.json")
gdf = gpd.read_file(file_path)

# name/type/lat/lon 필드를 유지하고, 중심점으로 포인트화 (또는 원래 보유한 좌표가 있으면 그걸 사용)
items = []
for _, r in gdf.iterrows():
    if "lat" in r and "lon" in r:
        lat, lon = float(r["lat"]), float(r["lon"])
    else:
        # geometry의 중심을 lat/lon으로 역투영해야 하지만, 보통 파일에 lat/lon이 있으니 그걸 권장
        lon, lat = r.geometry.centroid.x, r.geometry.centroid.y
    items.append({
        "name": r.get("name", ""),
        "type": r.get("type", ""),
        "lat": lat,
        "lon": lon,
    })

with open(file_path2, "w", encoding="utf-8") as f:
    json.dump(items, f, ensure_ascii=False)
