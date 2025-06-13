from django.urls import path
from . import views

app_name = 'qrfikr'

urlpatterns = [
    path('f/<uuid:qr_uuid>/', views.SubmitReviewView.as_view(), name='submit'),
    path('f/<uuid:qr_uuid>/thank-you/', views.ThankYouView.as_view(), name='thank_you'),
    path('location/<uuid:qr_uuid>/', views.LocationDetailView.as_view(), name='location_detail'),
]
