from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from .models import Profile
from django.contrib.auth.decorators import login_required

# 메인 페이지 (로고 → 로그인 유도)
def index(request):
    if request.user.is_authenticated:
        return render(request, 'main/index.html', {'username': request.user.username})
    return render(request, 'main/index.html')

# 로그인
def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('main:home')
        else:
            return render(request, 'main/login.html', {'error': '아이디 또는 비밀번호가 잘못되었습니다.'})
    return render(request, 'main/login.html')

# 회원가입
def signup_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        password_confirm = request.POST['password_confirm']

        # 1️⃣ 아이디 중복 체크
        if User.objects.filter(username=username).exists():
            return render(request, 'main/signup.html', {'error': '이미 존재하는 아이디입니다.'})

        # 2️⃣ 아이디/비번 길이 체크
        if len(username) < 6 or len(password) < 6:
            return render(request, 'main/signup.html', {'error': '아이디와 비밀번호 모두 6글자 이상이어야 합니다.'})

        # 3️⃣ 비밀번호 일치 여부 체크
        if password != password_confirm:
            return render(request, 'main/signup.html', {'error': '비밀번호와 비밀번호 확인이 일치하지 않습니다.'})

        # 모든 조건 통과 시 회원 생성
        user = User.objects.create_user(username=username, password=password)
        Profile.objects.create(user=user)  # 기본 프로필 생성
        login(request, user)
        return redirect('main:login')

    return render(request, 'main/signup.html')

# 로그아웃
def logout_view(request):
    logout(request)
    return redirect('main:index')

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from .models import Profile

# 필수 프로필 정보가 모두 유효한지 확인하는 함수
def is_profile_complete(profile):
    try:
        return float(profile.weight) > 0 and float(profile.preferred_distance) > 0 and int(profile.preferred_cycle) > 0
    except (TypeError, ValueError):
        return False

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from .models import Profile

# 필수 프로필 정보가 모두 양의 실수인지 확인하는 함수
def is_profile_complete(profile):
    try:
        # None, 0, 음수, 타입 오류 모두 체크
        return float(profile.weight) > 0 and float(profile.preferred_distance) > 0 and float(profile.preferred_cycle) > 0
    except (TypeError, ValueError):
        return False

@login_required
def home_view(request):
    user = request.user
    profile, created = Profile.objects.get_or_create(user=user)

    if request.method == 'POST':
        if profile.edit_count == 0:
            return render(request, 'main/home.html', {
                'profile': profile,
                'error_message': '회원 정보를 먼저 입력해주세요!',
            })
        else:
            return redirect('index')  # callapi 앱으로 이동

    return render(request, 'main/home.html', {'profile': profile})


# 회원 정보 수정 페이지
@login_required
def profile_view(request):
    user = request.user
    profile, created = Profile.objects.get_or_create(user=user)
    error_message = None  # 에러 메시지 초기화

    if request.method == 'POST':
        try:
            # 입력값을 float으로 변환하고 양수인지 확인
            weight = float(request.POST.get('weight', ''))
            preferred_distance = float(request.POST.get('preferred_distance', ''))
            preferred_cycle = float(request.POST.get('preferred_cycle', ''))

            if weight <= 0 or preferred_distance <= 0 or preferred_cycle <= 0:
                raise ValueError("양수가 아닌 값")

            # 모두 정상이라면 프로필에 저장
            profile.weight = weight
            profile.preferred_distance = preferred_distance
            profile.preferred_cycle = preferred_cycle
            profile.prefers_facilities = request.POST.get('prefers_facilities') == 'on'

            # edit_count 증가
            profile.edit_count += 1
            profile.save()
            return redirect('main:home')

        except ValueError:
            error_message = "올바른 양의 숫자를 입력해주세요!"

    context = {
        'profile': profile,
        'error_message': error_message,
    }
    return render(request, 'main/profile.html', context)

# 개발자들 페이지
@login_required
def developers_view(request):
    # 만든 사람들 이름 리스트
    developers = ["장재혁", "홍길동", "김철수"]  # 필요하면 추가
    return render(request, 'main/developer.html', {'developers': developers})