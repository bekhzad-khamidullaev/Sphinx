from django.urls import path, include
from . import views

app_name = 'qrfikr'


urlpatterns = [
    path('f/<uuid:qr_uuid>/', views.SubmitReviewView.as_view(), name='submit_review_page'),
    path('f/<uuid:qr_uuid>/thank-you/', views.ThankYouView.as_view(), name='submit_review_thank_you'),
    path('location/<int:pk>/', views.LocationDetailView.as_view(), name='location_detail'),
    path('internal/qr-details/<uuid:pk>/', views.AdminQRCodeDetailView.as_view(), name='admin_qr_detail'),
]


api_urlpatterns = [
    path('', include('qrfikr.api.urls')),
]

if api_urlpatterns:
    urlpatterns += [
        path('api/v1/', include((api_urlpatterns, 'qrfikr'), namespace='api')),
    ]