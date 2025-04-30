# room/admin.py
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from .models import Room, Message, MessageReadStatus, Reaction
from django.db import models
from django.contrib import messages

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'private', 'participant_count', 'created_at', 'updated_at', 'is_archived')
    list_filter = ('private', 'is_archived', 'created_at')
    search_fields = ('name', 'slug', 'participants__username')
    prepopulated_fields = {'slug': ('name',)}
    filter_horizontal = ('participants',) # Easier M2M management
    actions = ['archive_rooms', 'unarchive_rooms']

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            participant_count_agg=models.Count('participants', distinct=True)
        )

    def participant_count(self, obj):
        return obj.participant_count_agg
    participant_count.short_description = _("Участников")
    participant_count.admin_order_field = 'participant_count_agg'

    @admin.action(description=_("Архивировать выбранные комнаты"))
    def archive_rooms(self, request, queryset):
        updated = queryset.update(is_archived=True)
        self.message_user(request, _("%(count)d комнат было архивировано.") % {'count': updated}, messages.SUCCESS)

    @admin.action(description=_("Восстановить выбранные комнаты из архива"))
    def unarchive_rooms(self, request, queryset):
        updated = queryset.update(is_archived=False)
        self.message_user(request, _("%(count)d комнат было восстановлено.") % {'count': updated}, messages.SUCCESS)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('room', 'user_link', 'content_preview', 'file_link', 'reply_to_link', 'is_deleted', 'date_added', 'edited_at')
    list_filter = ('room', 'is_deleted', 'date_added', 'user')
    search_fields = ('content', 'user__username', 'room__name', 'id')
    date_hierarchy = 'date_added'
    list_select_related = ('room', 'user', 'reply_to')
    readonly_fields = ('date_added', 'edited_at', 'user_link', 'room_link', 'reply_to_link', 'file_link')
    fields = (
        'room_link', 'user_link', 'date_added', 'edited_at', 'content', 'file_link',
        'reply_to_link', 'is_deleted'
    )

    def user_link(self, obj):
        if obj.user:
            link = reverse("admin:user_profiles_user_change", args=[obj.user.id]) # Adjust app_label if needed
            return format_html('<a href="{}">{}</a>', link, obj.user.username)
        return "-"
    user_link.short_description = _("Пользователь")

    def room_link(self, obj):
         link = reverse("admin:room_room_change", args=[obj.room.id])
         return format_html('<a href="{}">{}</a>', link, obj.room.name)
    room_link.short_description = _("Комната")

    def reply_to_link(self, obj):
        if obj.reply_to:
             link = reverse("admin:room_message_change", args=[obj.reply_to.id])
             return format_html('<a href="{}">{}</a>', link, str(obj.reply_to))
        return "-"
    reply_to_link.short_description = _("В ответ на")


    def file_link(self, obj):
         if obj.file:
             return format_html('<a href="{}" target="_blank">{}</a>', obj.file.url, obj.file.name.split('/')[-1])
         return "-"
    file_link.short_description = _("Файл")

    def content_preview(self, obj):
        if obj.is_deleted:
            return f"[{_('Удалено')}]"
        text = obj.content or ""
        return text[:50] + '...' if len(text) > 50 else text
    content_preview.short_description = _("Содержание")

    # Prevent adding/deleting messages directly via admin (should happen via chat)
    def has_add_permission(self, request): return False
    # Allow superusers to change/delete for debugging maybe
    def has_change_permission(self, request, obj=None): return request.user.is_superuser
    def has_delete_permission(self, request, obj=None): return request.user.is_superuser

@admin.register(MessageReadStatus)
class MessageReadStatusAdmin(admin.ModelAdmin):
    list_display = ('user_link', 'room_link', 'last_read_message_preview', 'last_read_timestamp')
    list_filter = ('room',)
    search_fields = ('user__username', 'room__name')
    list_select_related = ('user', 'room', 'last_read_message')
    readonly_fields = ('user_link', 'room_link', 'last_read_message_preview', 'last_read_timestamp')
    date_hierarchy = 'last_read_timestamp'

    def user_link(self, obj):
        if obj.user:
            link = reverse("admin:user_profiles_user_change", args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', link, obj.user.username)
        return "-"
    user_link.short_description = _("Пользователь")

    def room_link(self, obj):
         link = reverse("admin:room_room_change", args=[obj.room.id])
         return format_html('<a href="{}">{}</a>', link, obj.room.name)
    room_link.short_description = _("Комната")

    def last_read_message_preview(self, obj):
        if obj.last_read_message:
             link = reverse("admin:room_message_change", args=[obj.last_read_message.id])
             return format_html('<a href="{}">{}</a>', link, str(obj.last_read_message))
        return "-"
    last_read_message_preview.short_description = _("Последнее сообщение")

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return request.user.is_superuser


@admin.register(Reaction)
class ReactionAdmin(admin.ModelAdmin):
    list_display = ('message_link', 'user_link', 'emoji', 'created_at')
    list_filter = ('emoji', 'message__room')
    search_fields = ('emoji', 'user__username', 'message__content')
    list_select_related = ('message', 'user', 'message__room')
    readonly_fields = ('message_link', 'user_link', 'created_at')
    fields = ('message_link', 'user_link', 'emoji', 'created_at')

    def message_link(self, obj):
        link = reverse("admin:room_message_change", args=[obj.message.id])
        return format_html('<a href="{}">{}</a>', link, str(obj.message))
    message_link.short_description = _("Сообщение")

    def user_link(self, obj):
        if obj.user:
            link = reverse("admin:user_profiles_user_change", args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', link, obj.user.username)
        return "-"
    user_link.short_description = _("Пользователь")

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return request.user.is_superuser