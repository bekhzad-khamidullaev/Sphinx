from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import QRCodeLink, Review


@admin.register(QRCodeLink)
class QRCodeLinkAdmin(admin.ModelAdmin):

    list_display = ('location_link', 'point', 'is_active', 'qr_preview', 'form_link', 'created_at')
    search_fields = ('location__name', 'point__name', 'description')
    list_filter = ('is_active',)
    readonly_fields = ('qr_preview', 'form_link', 'created_at', 'updated_at')
    fields = (
        'point', 'location', 'description', 'is_active', 'qr_image', 'qr_preview', 'form_link',

        'created_at', 'updated_at'
    )

    @admin.display(description=_('Location'), ordering='location__name')
    def location_link(self, obj):
        url = reverse('admin:checklists_location_change', args=[obj.location_id])
        return format_html('<a href="{}">{}</a>', url, obj.location.name)

    @admin.display(description=_('QR Code'))
    def qr_preview(self, obj):
        if obj.qr_image and hasattr(obj.qr_image, 'url'):
            return format_html('<img src="{}" style="height:60px;" />', obj.qr_image.url)
        return '-'

    @admin.display(description=_('Form link'))
    def form_link(self, obj):
        url = obj.get_feedback_url()
        return format_html('<a href="{}" target="_blank">{}</a>', url, _('Open form'))


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('qr_code_link_link', 'location_link', 'point_name', 'rating_display', 'submitted_at')
    list_filter = ('rating', 'submitted_at')
    search_fields = ('qr_code_link__location__name', 'qr_code_link__point__name', 'text', 'contact_info')
    readonly_fields = ('submitted_at', 'ip_address', 'user_agent')
    list_select_related = ('qr_code_link', 'qr_code_link__location', 'qr_code_link__point')
    fields = (
        'qr_code_link', 'category', 'rating', 'text', 'contact_info', 'photo',
        'submitted_at', 'ip_address', 'user_agent'
    )

    @admin.display(description=_('QR Link'), ordering='qr_code_link__location__name')
    def qr_code_link_link(self, obj):
        url = reverse('admin:qrfikr_qrcodelink_change', args=[obj.qr_code_link_id])
        return format_html('<a href="{}">{}</a>', url, obj.qr_code_link.location.name)

    @admin.display(description=_('Location'), ordering='qr_code_link__location__name')
    def location_link(self, obj):
        url = reverse('admin:checklists_location_change', args=[obj.qr_code_link.location_id])
        return format_html('<a href="{}">{}</a>', url, obj.qr_code_link.location.name)

    @admin.display(description=_('Point'), ordering='qr_code_link__point__name')
    def point_name(self, obj):
        return obj.qr_code_link.point.name

    @admin.display(description=_('Rating'))
    def rating_display(self, obj):
        return format_html('{}', '★' * obj.rating + '☆' * (5 - obj.rating))
