from django.contrib import admin
from django.urls import path
from . import views
from .views import  SensorDataView, CustomTokenObtainPairView
from rest_framework_simplejwt.views import TokenRefreshView




urlpatterns = [
    path('', views.sensors, name='sensors'),
    path('api/sensor-data/', SensorDataView.as_view(), name='sensor-data'),
    path('api/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),


]
