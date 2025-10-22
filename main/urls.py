from django.urls import path
from . import views

app_name = 'main'

urlpatterns = [
    path('', views.index, name='index'),               # 로고 애니메이션 + 로그인 버튼
    path('login/', views.login_view, name='login'),    # 로그인 페이지
    path('signup/', views.signup_view, name='signup'), # 회원가입 페이지
    path('profile/', views.profile_view, name='profile'), # 회원정보 수정 페이지
    path('logout/', views.logout_view, name='logout'), # 로그아웃
    path('home/', views.home_view, name='home'),
    path('developers/', views.developers_view, name='developers'),
]