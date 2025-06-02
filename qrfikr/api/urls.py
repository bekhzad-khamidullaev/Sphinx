from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import QRCodeLinkViewSet, ReviewViewSet

app_name = 'qrfikr-api' # This is good for namespacing within the app's API

router = DefaultRouter()
# The lookup for qrcodes is 'id' (which is a UUIDField in the model)
router.register(r'qrcodes', QRCodeLinkViewSet, basename='qrcode')
router.register(r'reviews', ReviewViewSet, basename='review')

urlpatterns = [
    path('', include(router.urls)),
]