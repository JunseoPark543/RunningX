import os
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

# 현재 파일(data.py)의 위치 기준 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
toilet_path = os.path.join(BASE_DIR, "raw_data", "seoul_toilet.xlsx")
water_path = os.path.join(BASE_DIR, "raw_data", "seoul_water.xlsx")
merge_path = os.path.join(BASE_DIR,"data","facility_buffers.geojson")
# 파일 읽기
toilet = pd.read_excel(toilet_path)
water = pd.read_excel(water_path)

# type 칼럼 추가
toilet['type'] = "toilet"
water['type'] = "water"

# 칼럼 통일: name, address, lon, lat
toilet = toilet.rename(columns={
    "이름":"name",
    "도로명주소":'address',
    "X좌표":"lon",
    "Y좌표":'lat',
})
water = water.rename(columns={
    "이름":"name",
    "도로명주소":'address',
    "X좌표":"lon",
    "Y좌표":'lat',
})

# 하나로 합치기
facility = pd.concat([toilet,water], ignore_index=True)

# 결측치 제거
facility = facility.dropna(subset=["lon","lat"])

# GeoDataFrame으로 변환 (좌표계: EPSG:4326 = WG584)
facility["geometry"] = facility.apply(lambda row: Point(row["lon"], row["lat"]), axis=1)
facility_gdf = gpd.GeoDataFrame(facility, geometry="geometry", crs="EPSG:4326")

# 투영 변환 -> buffer(100m)
gdf_proj = facility_gdf.to_crs(epsg=5179)
gdf_proj["geometry"] = gdf_proj.geometry.buffer(100)

# 저장
gdf_proj = gdf_proj.to_file(merge_path, driver="GeoJSON")