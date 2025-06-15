from django.contrib import admin
from .models import Review

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('restaurant_name', 'user_name', 'rating', 'created_at')
    list_filter = ('restaurant_name', 'rating')
    search_fields = ('restaurant_name', 'user_name', 'comment')
