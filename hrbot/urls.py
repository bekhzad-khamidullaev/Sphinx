from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView
from . import views
from .analytics import export_excel

app_name = 'hrbot'

urlpatterns = [
    path('export_excel/', views.export_excel, name='export_excel'),
    path('success/', TemplateView.as_view(template_name='hrbot/success.html'), name='success'),
]