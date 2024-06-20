from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('', include('user_profiles.urls')),
    path('admin/', admin.site.urls),
    path('contacts/', include('contacts.urls')),
    path('counterpartys/', include('counterparty.urls')),
]
