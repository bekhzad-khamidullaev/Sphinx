from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views, api

router = DefaultRouter()
router.register('qr-links', api.QRCodeLinkViewSet, basename='qr-link')
router.register('reviews', api.ReviewViewSet, basename='review')

app_name = 'qrfikr'

urlpatterns = [
    path('f/<uuid:qr_uuid>/', views.SubmitReviewView.as_view(), name='submit'),
    path('f/<uuid:qr_uuid>/thank-you/', views.ThankYouView.as_view(), name='thank_you'),
    path('location/<uuid:qr_uuid>/', views.LocationDetailView.as_view(), name='location_detail'),
    path('api/', include(router.urls)),
]
