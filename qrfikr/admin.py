from django.contrib import admin
from .models import QRCodeLink, Review


@admin.register(QRCodeLink)
class QRCodeLinkAdmin(admin.ModelAdmin):
    list_display = ('location', 'is_active', 'created_at')
    search_fields = ('location__name',)
    list_filter = ('is_active',)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('qr_code_link', 'rating', 'submitted_at')
    list_filter = ('rating', 'submitted_at')
    search_fields = ('qr_code_link__location__name', 'text')
