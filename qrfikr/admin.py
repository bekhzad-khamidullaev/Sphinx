from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.urls import reverse
from django.conf import settings
import logging

from .models import QRCodeLink, Review
from .tasks import generate_qr_image_task # Celery task

logger = logging.getLogger(__name__)

@admin.register(QRCodeLink)
class QRCodeLinkAdmin(admin.ModelAdmin):
    list_display = ('location_name_display', 'short_description_display', 'is_active', 'qr_image_thumbnail', 'created_at', 'feedback_link_actions')
    list_filter = ('is_active', 'location__name', 'created_at') # Use location__name for filtering
    search_fields = ('location__name', 'short_description')
    autocomplete_fields = ['location']
    readonly_fields = ('id', 'created_at', 'updated_at', 'qr_image_display_admin')
    fields = (('id', 'is_active'), 'location', 'short_description', 'qr_image', 'qr_image_display_admin', ('created_at', 'updated_at'))
    actions = ['regenerate_qr_codes_action']
    list_select_related = ['location']

    def location_name_display(self, obj):
        if obj.location:
            return obj.location.name
        return _("N/A")
    location_name_display.short_description = _("Location")
    location_name_display.admin_order_field = 'location__name'

    def short_description_display(self, obj):
        return obj.short_description or "-"
    short_description_display.short_description = _("Short Description")

    def qr_image_thumbnail(self, obj):
        if obj.qr_image and hasattr(obj.qr_image, 'url'):
            return format_html('<img src="{}" style="max-height: 50px; max-width: 50px;" />', obj.qr_image.url)
        return _("No image")
    qr_image_thumbnail.short_description = _("QR")

    def qr_image_display_admin(self, obj): # Renamed to avoid conflict with model property
        if obj.qr_image and hasattr(obj.qr_image, 'url'):
            return format_html(
                '<div style="margin-bottom: 10px;"><img src="{0}" style="max-width: 200px; max-height: 200px; border:1px solid #ccc;" /></div>'
                '<a href="{0}" target="_blank" class="button">{}</a> '
                '<a href="{0}" download="qr_{1}.png" class="button">{}</a>',
                obj.qr_image.url, obj.id.hex, _("Open Image"), _("Download Image")
            )
        return _("QR code will be generated upon saving (if active and image missing) or via action.")
    qr_image_display_admin.short_description = _("QR Image Preview & Download")


    def feedback_link_actions(self, obj):
        # Ensure SITE_URL is configured in settings.py
        base_url = getattr(settings, 'SITE_URL', 'http://localhost:8000').strip('/')
        try:
            feedback_url_path = obj.get_feedback_url()
            full_feedback_url = base_url + feedback_url_path
        except Exception as e:
            logger.error(f"Could not generate feedback URL for QR Link {obj.id}: {e}")
            full_feedback_url = "#error-generating-url"
            
        # Link to the custom admin detail view (if you created one in qrfikr/views.py and qrfikr/urls.py)
        # Or link to the standard Django admin change view.
        admin_view_url = reverse('admin:qrfikr_qrcodelink_change', args=[obj.id]) # Standard change view
        # If you have a custom detail view registered in qrfikr.urls:
        # admin_view_url = reverse('qrfikr:admin_qr_detail', kwargs={'pk': obj.id})


        return format_html(
            '<a href="{}" target="_blank" class="button" title="{}">{}</a>&nbsp;'
            '<a href="{}" class="button" title="{}">{}</a>',
            full_feedback_url, _("Open public feedback form in new tab"), _("Open Form"),
            admin_view_url, _("View/Edit QR Link in Admin"), _("View/Edit")
        )
    feedback_link_actions.short_description = _("Actions")

    @admin.action(description=_("Regenerate selected QR codes"))
    def regenerate_qr_codes_action(self, request, queryset):
        count_scheduled = 0
        count_failed_schedule = 0
        for qr_link in queryset:
            if not qr_link.is_active:
                self.message_user(request, _("QR Link for %s is not active. QR not regenerated.") % qr_link.location.name, level='warning')
                continue
            try:
                # Using .si() for an immutable signature is good practice if args could change.
                generate_qr_image_task.si(str(qr_link.id)).apply_async()
                count_scheduled += 1
            except Exception as e:
                count_failed_schedule +=1
                logger.error(f"AdminAction: Failed to schedule QR regeneration for {qr_link.id}. Error: {e}")
                self.message_user(request, _("Failed to schedule QR regeneration for %s. Error: %s") % (qr_link.location.name, e), level='error')
        
        if count_scheduled > 0:
            self.message_user(request, _("Scheduled QR code regeneration for %(count)d links.") % {'count': count_scheduled})
        if count_failed_schedule > 0:
            self.message_user(request, _("Failed to schedule QR regeneration for %(count)d links. Check Celery/Broker status.") % {'count': count_failed_schedule}, level='error')

    def save_model(self, request, obj: QRCodeLink, form, change):
        super().save_model(request, obj, form, change)
        # The signal handle_qr_code_link_save will trigger QR generation if needed.
        # If Celery is not running, the signal has a synchronous fallback.
        # No need to call obj.generate_and_save_qr_image() here directly unless specific conditions.


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('submitted_at_formatted', 'location_name_admin', 'rating_display_admin', 'text_preview', 'photo_thumbnail', 'contact_info', 'related_task_link')
    list_filter = ('rating', 'qr_code_link__location__name', 'submitted_at', ('related_task', admin.EmptyFieldListFilter))
    search_fields = ('text', 'contact_info', 'qr_code_link__location__name', 'qr_code_link__short_description', 'related_task__title', 'related_task__task_number', 'ip_address')
    readonly_fields = ('id', 'qr_code_link_display', 'rating_display_admin_form', 'text', 'photo_display_admin', 'contact_info', 'submitted_at', 'user_agent', 'ip_address', 'related_task_link_readonly')
    fields = (('id', 'submitted_at'), 'qr_code_link_display', 'rating_display_admin_form', 'text', 'photo_display_admin', 'contact_info', ('ip_address', 'user_agent'), 'related_task_link_readonly')
    list_select_related = ('qr_code_link__location', 'related_task')
    date_hierarchy = 'submitted_at'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('qr_code_link__location', 'related_task')

    def location_name_admin(self, obj):
        return obj.qr_code_link.location.name if obj.qr_code_link and obj.qr_code_link.location else _("N/A")
    location_name_admin.short_description = _("Location")
    location_name_admin.admin_order_field = 'qr_code_link__location__name'

    def qr_code_link_display(self, obj):
        if obj.qr_code_link:
            link = reverse("admin:qrfikr_qrcodelink_change", args=[obj.qr_code_link.id])
            return format_html('<a href="{}">{}</a>', link, str(obj.qr_code_link))
        return "-"
    qr_code_link_display.short_description = _("QR Code Link")

    def rating_display_admin(self, obj): # For list_display
        return obj.get_rating_display()
    rating_display_admin.short_description = _("Rating")
    rating_display_admin.admin_order_field = 'rating'

    def rating_display_admin_form(self, obj): # For readonly_fields in form
        return obj.get_rating_display()
    rating_display_admin_form.short_description = _("Rating")


    def text_preview(self, obj):
        return (obj.text[:75] + '...' if obj.text and len(obj.text) > 75 else obj.text) or "-"
    text_preview.short_description = _("Feedback Text")

    def photo_thumbnail(self, obj):
        if obj.photo and hasattr(obj.photo, 'url'):
            return format_html('<a href="{0}" target="_blank"><img src="{0}" style="max-height:40px; max-width:70px; object-fit:cover;" /></a>', obj.photo.url)
        return _("No")
    photo_thumbnail.short_description = _("Photo")

    def photo_display_admin(self, obj): # Renamed for clarity
        if obj.photo and hasattr(obj.photo, 'url'):
            return format_html('<a href="{0}" target="_blank"><img src="{0}" style="max-width: 300px; max-height: 300px; border:1px solid #ccc;" /></a>', obj.photo.url)
        return _("No photo attached")
    photo_display_admin.short_description = _("Attached Photo")

    def submitted_at_formatted(self, obj):
        return obj.submitted_at.strftime("%d-%m-%Y %H:%M")
    submitted_at_formatted.short_description = _("Submitted At")
    submitted_at_formatted.admin_order_field = 'submitted_at'

    def related_task_link(self, obj): # For list_display
        if obj.related_task and hasattr(obj.related_task, '_meta'):
            task_admin_url_name = f"admin:{obj.related_task._meta.app_label}_{obj.related_task._meta.model_name}_change"
            try:
                link = reverse(task_admin_url_name, args=[obj.related_task.id])
                task_display = obj.related_task.task_number or obj.related_task.title[:30]
                return format_html('<a href="{}" target="_blank">{}</a>', link, task_display)
            except Exception as e:
                logger.warning(f"Could not reverse admin URL for task {obj.related_task.id}: {e}")
                return str(obj.related_task) # Fallback
        return "-"
    related_task_link.short_description = _("Related Task")
    related_task_link.admin_order_field = 'related_task__task_number'

    def related_task_link_readonly(self, obj): # For readonly_fields in form
        return self.related_task_link(obj)
    related_task_link_readonly.short_description = _("Related Task")


    def has_add_permission(self, request):
        return False 

    def has_change_permission(self, request, obj=None):
        return False # Generally reviews should be immutable from admin after creation by user

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser # Or more granular permission