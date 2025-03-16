from . import views
from django.urls import path

app_name = "user_profiles"

urlpatterns = [
    path('', views.base, name='base'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
]
