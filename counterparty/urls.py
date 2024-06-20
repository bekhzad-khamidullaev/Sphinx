from . import views
from django.urls import path

urlpatterns = [
    path('', views.counterparty_list_view, name='counterpartys'),
    path('counterparty_details/<int:pk>', views.counterparty_detail_view, name='counterparty_details'),
]
