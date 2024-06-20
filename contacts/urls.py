from . import views
from django.urls import path

urlpatterns = [
    path('', views.contact_list_view, name='contacts'),
    path('contact_details/<int:pk>', views.contact_detail_view, name='contact_details'),
]
