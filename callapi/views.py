from django.shortcuts import render
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from main.models import Profile
import json
import requests
import time

from .ors_test2 import *
from .calr import *
from .calr_facility import check_facility

# API_KEY
ORS_API_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjYyM2M1NzI5MGRkYzRhYjdiODM2N2E4MjJiZjQ1MDg5IiwiaCI6Im11cm11cjY0In0="
KAKAO_REST_API_KEY = "8aceb6c0c05874546bcabb6ad9405cf0"
TMAP_APP_KEY = "OF93Av1S5v2pHZvLIqzpUaq7OYEpaKFKa9yKt0NF"


import json
from django.shortcuts import render

# from .services import build_multiple_corrected_roundcourses
# ORS_API_KEY, TMAP_APP_KEY 는 settings 등에서 읽어오세요.

@login_required
def index(request):
    user = request.user
    profile, created = Profile.objects.get_or_create(user=user)

    if request.method == "GET":
        context = {
            "default_weight": profile.weight or "",
            "default_distance": profile.preferred_distance or "",
            "default_cycle": profile.preferred_cycle or "",
            "default_facility": "checked" if profile.prefers_facilities else "",
        }
        return render(request, "callapi/index.html", context)
        
    if request.method == "POST":
        # -------- 입력 파싱 & 캐스팅 --------
        lat_str = request.POST.get("lat")
        lon_str = request.POST.get("lon")
        address = request.POST.get("address") or ""
        cycle = request.POST.get('cycle') or 1
        cycle = int(cycle)
        distance_str = request.POST.get("distance") or "5000"
        weight_kg = request.POST.get('weight_kg') or "70"
        weight_kg = float(weight_kg)
        facility_flag = (request.POST.get("facility") == "yes")

        try:
            lat = float(lat_str)
            lon = float(lon_str)
            distance = int(round(float(distance_str)))
        except (TypeError, ValueError):
            # 잘못된 입력일 때 기본값/에러 처리
            lat, lon, distance = 37.5665, 126.9780, 5000

        print("주소:", address)
        print("좌표:", lat, lon)
        print("거리:", distance)
        print('cycle',cycle)
        print('체중', weight_kg)
        print("편의시설 포함 여부:", facility_flag)
        print('-----------------------------')
        cycle_distance = int(round(distance/cycle))
        # -------- 경로 생성 --------
        routes = build_multiple_corrected_roundcourses(
            start_lon=lon,
            start_lat=lat,
            distance_m=cycle_distance,
            ors_api_key=ORS_API_KEY,
            tmap_api_key=TMAP_APP_KEY,
            n_routes=5,
            ors_profile="foot-walking",
            tmap_profile="pedestrian",
            seed_base=13,
            seed_step=991,
            points_cycle=(3, 4),
        )
        # routes: List[Dict]  예) {"경로":[[lon,lat]...], "회전":{"좌회전":n,"우회전":n}, "횡단보도 개수":n, "경로의 총 길이":m}

        # -------- 프론트에 주기 좋은 영문 키로 매핑 --------
        payload = []
        # print(len(routes))
        for r in routes:
            if int(r["경로의 총 길이"]) < cycle_distance-int(round(500/cycle)) or int(r["경로의 총 길이"]) > cycle_distance+int(round(500/cycle)):
                continue
            facility_list = check_facility(r["경로"]) if facility_flag else []
            if facility_flag and facility_list ==[]:
                continue
            # 6.37: 전세계 평균 페이스 
            min_total = 6.37*float(r["경로의 총 길이"])*0.001
            turn_left, turn_right = r["회전"]["좌회전"], r["회전"]["우회전"]
            turn_total = int(turn_left) + int(turn_right)
            crosswalks = r["횡단보도 개수"]
            difficulty_score, kcal = difficulty_kcal(r["경로"],min_total,weight_kg,crosswalks, turn_total)
            info = {
                "path": r["경로"],
                "turn": {
                    "left": turn_left,
                    "right": turn_right,
                },
                "crosswalks": crosswalks,
                "length_m": r["경로의 총 길이"],
                'calorie':int(kcal)*cycle,
                'difficulty':difficulty_score,
                'facilities':facility_list,
            }
            payload.append(info)
            # print(payload)
        payload = classify_difficulty_and_add_label(payload)
        # print(payload)
        return render(request, "callapi/result.html", {
            "address": address,
            "lat": lat,
            "lon": lon,
            "distance": distance,
            'cycle_distance':cycle_distance,
            "cycle":cycle,
            # 프론트에서: const routesPayload = {{ routes_payload|safe }};
            "routes_payload": json.dumps(payload, ensure_ascii=False),
        })

    # GET
    return render(request, "callapi/index.html")




# 모든 기능
def main(lat, lon, distance_m, difficulty, facility):
    # 입력받은 출발지로부터 후보지 찾기
    # 12개의 후보지가 생성됨
    lat_lon_list = move_from_latlon(lat,lon, distance_m)

    info_list = []
    i = -1
    for [a_lat, a_lon] in lat_lon_list:
        i += 1
        # 티맵 길찾기 API
        coords,total_distance = find_direction(lat,lon,a_lat,a_lon)
        print(f'{i}인덱스 총거리: {total_distance}')

        if float(distance_m) - 200 <= float(total_distance) <= float(distance_m) + 200:
            pass
        else:
            print(f'{i}인덱스 코스 거리 불만족')
            print('----------------------------')
            continue  # 조건 불만족


        # 편의시설 포함 여부
        facility_list = []
        if facility:
            facility_list = check_facility(coords)
            if facility_list == []:
                print('편의시설이 없음')
                print('----------------------------')
                continue
        else:
            pass
        
        # 고도데이터 불러오기
        elevation = get_elevation(coords)

        # 고도데이터 점수화
        score = calculate_score(elevation)[0]
        
        info_dict = {
            'index':i,
            'facility_list':facility_list,
            'coords':coords,
            'score':score,
        }
        # print(coords)
        info_list.append(info_dict)

        print(f'{i}인덱스 편의시설:{facility_list}')
        print(f'{i}인덱스 점수:{score}')
        print('----------------------------')

    # score 기준으로 정렬
    sorted_courses = sorted(info_list, key=lambda x: x["score"])
    easy = sorted_courses[0]
    medium = sorted_courses[len(sorted_courses)//2]
    hard = sorted_courses[-1]
    
    if difficulty == '하':
        return easy
    elif difficulty == '중':
        return medium
    else:
        return hard
        

# 5. 티맵 길찾기 API
def find_direction(start_lat, start_lon, end_lat, end_lon):
    url = "https://apis.openapi.sk.com/tmap/routes/pedestrian?version=1"
    headers = {
        "Content'Type":"application/json",
        "appkey":TMAP_APP_KEY,
    }
    data = {
        "startX":start_lon,
        "startY":start_lat,
        "endX":end_lon,
        "endY":end_lat,
        "reqCoordType":"WGS84GEO",
        "resCoodrdType":"WGS84GEO",
        "startName":"출발지",
        "endName":"도착지"
    }

    response = requests.post(url,headers=headers, data=json.dumps(data))
    result = response.json()
    # print(result)
    features = result["features"]
    # print(features)
    
    total_distance = result['features'][0]['properties']['totalDistance']

    coords = []
    for f in features:
        if f["geometry"]["type"] == "LineString":
            coordss = f["geometry"]["coordinates"]
            # print("경로 좌표 목록:")
            for coord in coordss:
                # print(f"경도: {coord[0]}, 위도: {coord[1]}")
                coords.append(coord)
    # print(coords)
    # print(len(coords))
    
    return coords, total_distance * 2


# 3. 경로 후보지 찾기
def move_from_latlon(lat, lon, distance_m):
    import random
    from geopy.point import Point
    from geopy.distance import distance as geopy_distance
    A_lat = float(lat)
    A_lon = float(lon)
    distance_km = float(distance_m) * 0.001

    min_radius = distance_km * 0.40
    max_radius = distance_km * 0.45
    distance_km = random.uniform(min_radius, max_radius)

    fixed_angles = [i * 30 for i in range(12)]

    
    lat_lon_list = []
    for angle in fixed_angles:
        li = []

        orgin = Point(A_lat, A_lon)

        # 각 방향에서 반환점 좌표 생성
        destination = geopy_distance(kilometers=distance_km).destination(orgin, angle)
        B_lat, B_lon = destination.latitude, destination.longitude
        li.append(B_lat)
        li.append(B_lon)
        
        lat_lon_list.append(li)
    return lat_lon_list




# 7. 경로의 고도데이터 불러오기
def get_elevation(coords):
    import polyline
    coord_list = json.loads(str(coords))

    # ORS는 [lon, lat] 형식 요구
    geometry = [[lon,lat] for [lat,lon] in coord_list]
    
    # polyline 인코딩
    encoded = polyline.encode(geometry)

    url = 'https://api.openrouteservice.org/elevation/line'
    headers = {
        'Authorization': "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjYyM2M1NzI5MGRkYzRhYjdiODM2N2E4MjJiZjQ1MDg5IiwiaCI6Im11cm11cjY0In0=",
        'Content-Type': 'application/json',
    }
    body = {
        'format_in': 'encodedpolyline',
        'format_out': 'point',  #JSON 형식에서!
        'geometry': encoded
    }
    response = requests.post(url, headers=headers, json=body)

    # print(f'응답 코드: {response.status_code}')
    # print(f'응답 내용: {response.text}')

    elevation_data = []
    if response.status_code == 200:
        res_json = response.json()
        result_coords = res_json['geometry'] # [lon, lat, elevation]
        # print(result_coords)
        elevation_data = [
            {
                'lat': c[1],
                'lon': c[0],
                'elevation': c[2],
            }
            for c in result_coords
        ]
    else:
        error_message = f"ORS API 오류: {response.status_code} - {response.text}"

    return elevation_data


# 고도데이터 다루기
# (1) 총 고도 부담 (2) 최대 고도차
def get_total_elevation_change_and_range(elevation_data):
    total_elevation_change = 0
    elevation = [pt['elevation'] for pt in elevation_data]
    for i in range(len(elevation) - 1):
        total_elevation_change += abs(elevation[i + 1] - elevation[i])
    elevation_range = max(elevation) - min(elevation)
    return total_elevation_change, elevation_range


# (3) 급경사 구간 수
import math
def get_steep_segments(elevation_data):

    # 거리 구하는 함수
    def get_distance(lat1, lon1, lat2, lon2):
        R = 6371000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))
    
    slope_list = []
    over8_count = 0

    for i in range(len(elevation_data) - 1):
        lat1 = elevation_data[i]['lat']
        lon1 = elevation_data[i]['lon']
        h1 = elevation_data[i]['elevation']
        
        lat2 = elevation_data[i + 1]['lat']
        lon2 = elevation_data[i + 1]['lon']
        h2 = elevation_data[i + 1]['elevation']

        distance = get_distance(lat1, lon1, lat2, lon2)
        elevation_ckdl = h2 - h1
        slope = (elevation_ckdl / distance) * 100 if distance != 0 else 0
        slope_info = {
            'index': i + 1,
            'slope': round(slope,2),
            'start_coord': [lat1,lon1],
            'end_coord':[lat2,lon2],
            'distance_m':round(distance,2),
            'elevation_diff': round(h2-h1,2)
        }
        if abs(slope) >= 8:
            over8_count += 1
            slope_list.append(slope_info)

    return over8_count, slope_info


# 고도데이터 점수 구하기
def calculate_score(elevation_data):
    total_elevation_change, elevation_range = get_total_elevation_change_and_range(elevation_data)
    steep_segments, slope_info = get_steep_segments(elevation_data)
    w1,w2,w3 = 1,1,1
    score = (
        w1 * (total_elevation_change / 100) +
        w2 * (elevation_range / 50) +
        w3 * (steep_segments * 0.3)
    )
    print(f'total_elevation_change: {total_elevation_change}')
    print(f'elevation_range: {elevation_range}')
    print(f'steep_segments: {steep_segments}')
    return [score, total_elevation_change, elevation_range, steep_segments, slope_info]
