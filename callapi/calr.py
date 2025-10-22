import requests, math, polyline, json


# 칼로리 함수
def kalories(coord_list, min_total, weight_kg=70.0):
    if weight_kg < 0:
        raise ValueError("weight_kg는 양수여야 합니다.")
    if  min_total <= 0:
        raise ValueError("min_total은 양수여야 합니다.")
    
    D_up = 0.0
    D_non = 0.0
    # 오르막 경사(무차원) * 거리 가중 합
    uphill_grade_weighted_sum = 0.0
    elevation_data = get_elevation(coord_list)

    for i in range(len(elevation_data) - 1):
        lat1, lon1, h1 = elevation_data[i]['lat'], elevation_data[i]['lon'], elevation_data[i]['elevation']
        lat2, lon2, h2 = elevation_data[i + 1]['lat'], elevation_data[i + 1]['lon'], elevation_data[i + 1]['elevation']

        R = 6371000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
        d = R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))
        if d <= 0:
            continue

        slope = (h2 - h1) / d  # 무차원(예: 0.05 = 5%)

        if slope > 0:
            D_up += d
            uphill_grade_weighted_sum += slope * d
        else:
            D_non += d
    
    D_data_total = D_up + D_non
    avg_uphill_grade = (uphill_grade_weighted_sum / D_up) if D_up > 0 else 0.0     # 무차원
    avg_uphill_slope_pct = avg_uphill_grade * 100.0



    # 2) Tobler 속도(상대 시간 비율 추정을 위한 "기준" 속도) - km/h
    #    오르막은 avg_uphill_grade, 비오르막은 grade=0으로 가정
    s_speed_kmh = 6.0 * math.exp(-3.5 * abs(avg_uphill_grade + 0.05))  # uphill
    n_speed_kmh = 6.0 * math.exp(-3.5 * abs(0.0 + 0.05))               # non-uphill (평지/내리막 → grade=0 간주)

    # m/min로 변환
    s_speed_mpm = s_speed_kmh * 1000.0 / 60.0 if s_speed_kmh > 0 else 0.0
    n_speed_mpm = n_speed_kmh * 1000.0 / 60.0 if n_speed_kmh > 0 else 0.0

    # 3) 기준 속도로 구한 "상대 시간 비율" (총 시간 분배를 위한 비율)
    t_up0  = (D_up  / s_speed_mpm) if s_speed_mpm > 0 and D_up  > 0 else 0.0  # 분
    t_non0 = (D_non / n_speed_mpm) if n_speed_mpm > 0 and D_non > 0 else 0.0  # 분
    denom_time0 = t_up0 + t_non0

    if denom_time0 > 0:
        share_time_uphill = t_up0 / denom_time0
    else:
        # 속도를 계산 못했을 때는 거리 비율로 대체
        # 근데 쓸 확률 없다고 봐도 무방함
        share_time_uphill = D_up / (D_up + D_non) if (D_up + D_non) > 0 else 0.0

    # 실제 총 시간(min_total)을 이 비율로 분배
    minutes_uphill = min_total * share_time_uphill
    minutes_nonup  = min_total - minutes_uphill

    # 4) 실제 오르막길/평지 속도(m/min): 거리 / 시간
    s_speed_act_mpm = (D_up / minutes_uphill) if minutes_uphill > 0 else 0.0
    n_speed_act_mpm = (D_non / minutes_nonup) if minutes_nonup  > 0 else 0.0

    # 5) ACSM 보행식(ml/kg/min): VO2 = (3.5+0.2*v+ 0.9*v*grade) * weight / 200
    #    비오르막은 grade=0으로 간주
    vo2_up   = 3.5 + 0.2 * s_speed_act_mpm + 0.9 * s_speed_act_mpm * max(avg_uphill_grade, 0.0)
    vo2_non  = 3.5 + 0.2 * n_speed_act_mpm  # grade=0

    kcal_per_min_up  = (vo2_up  * weight_kg) / 200.0
    kcal_per_min_non = (vo2_non * weight_kg) / 200.0

    kcal_uphill = kcal_per_min_up  * minutes_uphill
    kcal_nonup  = kcal_per_min_non * minutes_nonup
    kcal_total  = kcal_uphill + kcal_nonup
    avg_uphill_grade100 = avg_uphill_grade * 100.0

    return kcal_total


# 난이도_점수, 칼로리함수
def difficulty_kcal(coord_list, min_total, weight_kg, num_blinker, num_turns):


    kcal_total = kalories(coord_list, min_total, weight_kg)
    score = float(kcal_total) + num_blinker * 5.0 + num_turns * 2.0
    return score, kcal_total

# 난이도 확인
def classify_difficulty_and_add_label(payload):
    """
    payload 리스트의 'difficulty' 점수를 기준으로 상, 중, 하 난이도를 부여하고,
    'difficulty_label' 필드를 새로 추가합니다. (기존 'difficulty' 값은 유지)
    """
    
    # 1. 모든 경로의 난이도 점수와 해당 경로 인덱스를 추출 (튜플: (score, index))
    scored_paths = []
    for i, item in enumerate(payload):
        # difficulty_score가 있는지 확인하고, None이 아닌 경우에만 리스트에 추가
        if 'difficulty' in item and item['difficulty'] is not None:
            # 원본 payload에서의 인덱스를 저장하여 나중에 업데이트할 때 사용
            scored_paths.append((item['difficulty'], i))
    
    N = len(scored_paths)
    
    # 예외 처리: 유효한 데이터가 없으면 종료
    if N == 0:
        print("경로 데이터가 없어 난이도 분류를 할 수 없습니다.")
        return payload

    # 2. 점수를 오름차순으로 정렬
    # 가장 낮은 점수부터 가장 높은 점수 순으로 정렬됩니다.
    scored_paths.sort(key=lambda x: x[0])
    
    # 3. 상, 중, 하를 나누는 경계 인덱스 계산
    # 전체 N을 가능한 한 균등하게 세 그룹으로 나눕니다.
    
    # 하 (Low): 가장 낮은 점수 그룹
    low_count = N // 3
    # 중 (Medium)
    medium_count = N // 3
    # 상 (High): 가장 높은 점수 그룹 (나머지 모두 포함)
    high_count = N - low_count - medium_count
    
    # 4. 정렬된 순서대로 '하', '중', '상' 레이블 부여
    
    # 하(Low) 그룹 경계: 정렬된 리스트의 0부터 low_count-1까지
    low_boundary = low_count
    
    # 중(Medium) 그룹 경계: low_count부터 low_count + medium_count - 1까지
    medium_boundary = low_count + medium_count
    
    # 정렬된 리스트를 순회하며 레이블 할당
    for i, (score, original_index) in enumerate(scored_paths):
        # i는 정렬된 리스트에서의 순서 (0부터 N-1)
        
        if i < low_boundary:
            # 하위 그룹 (가장 낮은 난이도)
            difficulty_label = '하' 
        elif i < medium_boundary:
            # 중간 그룹
            difficulty_label = '중'
        else:
            # 상위 그룹 (가장 높은 난이도)
            difficulty_label = '상'

        # 원본 payload의 해당 딕셔너리에 'difficulty_label' 필드를 새로 추가
        payload[original_index]['difficulty_label'] = difficulty_label
        
    return payload


def get_elevation(coords):
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