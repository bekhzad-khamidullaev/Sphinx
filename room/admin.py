# room/admin.py
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import Count
from django.contrib import messages as django_messages # Избегаем конфликта с моделью Message
from .models import Room, Message, MessageReadStatus, Reaction

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'private', 'creator_username', 'participant_count_display', 'created_at', 'last_activity_at', 'is_archived')
    list_filter = ('private', 'is_archived', 'created_at', 'last_activity_at')
    search_fields = ('name', 'slug', 'participants__username', 'creator__username')
    prepopulated_fields = {'slug': ('name',)}
    filter_horizontal = ('participants',)
    readonly_fields = ('created_at', 'updated_at', 'last_activity_at', 'creator_link')
    actions = ['archive_rooms', 'unarchive_rooms']
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'creator_link', 'private', 'is_archived')}),
        (_('Участники'), {'fields': ('participants',)}),
        (_('Даты'), {'fields': ('created_at', 'updated_at', 'last_activity_at')}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            participant_count_agg=Count('participants', distinct=True)
        ).select_related('creator')

    def participant_count_display(self, obj):
        return obj.participant_count_agg
    participant_count_display.short_description = _("Участников")
    participant_count_display.admin_order_field = 'participant_count_agg'

    def creator_username(self, obj):
        return obj.creator.username if obj.creator else '-'
    creator_username.short_description = _("Создатель")
    creator_username.admin_order_field = 'creator__username'

    def creator_link(self, obj):
        if obj.creator:
            # Предполагаем, что используется стандартная модель User из django.contrib.auth
            link = reverse("admin:auth_user_change", args=[obj.creator.id])
            return format_html('<a href="{}">{}</a>', link, obj.creator.username)
        return "-"
    creator_link.short_description = _("Создатель (ссылка)")


    @admin.action(description=_("Архивировать выбранные комнаты"))
    def archive_rooms(self, request, queryset):
        updated = queryset.update(is_archived=True)
        self.message_user(request, _("%(count)d комнат было архивировано.") % {'count': updated}, django_messages.SUCCESS)

    @admin.action(description=_("Восстановить выбранные комнаты из архива"))
    def unarchive_rooms(self, request, queryset):
        updated = queryset.update(is_archived=False)
        self.message_user(request, _("%(count)d комнат было восстановлено.") % {'count': updated}, django_messages.SUCCESS)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id_short', 'room_link', 'user_link', 'content_preview', 'file_info', 'reply_to_short', 'is_deleted', 'date_added', 'edited_at')
    list_filter = ('is_deleted', 'date_added', 'room', 'user')
    search_fields = ('content', 'user__username', 'room__name', 'id__iexact') # Поиск по полному UUID
    date_hierarchy = 'date_added'
    list_select_related = ('room', 'user', 'reply_to', 'reply_to__user')
    readonly_fields = ('id', 'date_added', 'edited_at', 'user_link_readonly', 'room_link_readonly', 'reply_to_link_readonly', 'file_link_readonly')
    fields = (
        'id', 'room_link_readonly', 'user_link_readonly', 'content', 'file', 'file_link_readonly',
        'reply_to_link_readonly', 'is_deleted', 'date_added', 'edited_at'
    )

    def id_short(self, obj):
        return str(obj.id).split('-')[0] + "..."
    id_short.short_description = _("ID")

    def _get_user_admin_url(self, user):
        # Предполагаем, что используется стандартная модель User из django.contrib.auth
        # Если у вас кастомная модель пользователя, app_label может быть другим (например, 'user_profiles')
        return reverse("admin:auth_user_change", args=[user.id])

    def user_link(self, obj): # Для list_display
        if obj.user:
            link = self._get_user_admin_url(obj.user)
            return format_html('<a href="{}">{}</a>', link, obj.user.username)
        return "-"
    user_link.short_description = _("Пользователь")
    user_link.admin_order_field = 'user__username'

    def user_link_readonly(self, obj): return self.user_link(obj) # Для fields/readonly_fields
    user_link_readonly.short_description = _("Пользователь")


    def room_link(self, obj): # Для list_display
        link = reverse("admin:room_room_change", args=[obj.room.id])
        return format_html('<a href="{}">{}</a>', link, obj.room.name)
    room_link.short_description = _("Комната")
    room_link.admin_order_field = 'room__name'

    def room_link_readonly(self, obj): return self.room_link(obj) # Для fields/readonly_fields
    room_link_readonly.short_description = _("Комната")


    def reply_to_link_readonly(self, obj):
        if obj.reply_to:
            link = reverse("admin:room_message_change", args=[obj.reply_to.id])
            reply_user = obj.reply_to.user.username if obj.reply_to.user else _("неизвестный")
            return format_html('<a href="{}">{} ({})</a>', link, str(obj.reply_to.id)[:8]+"...", reply_user)
        return "-"
    reply_to_link_readonly.short_description = _("В ответ на")

    def reply_to_short(self, obj): # Для list_display
        if obj.reply_to:
            reply_user = obj.reply_to.user.username if obj.reply_to.user else _("неизв.")
            return format_html('Msg <a href="{}">{}...</a> ({})',
                               reverse("admin:room_message_change", args=[obj.reply_to.id]),
                               str(obj.reply_to.id)[:8],
                               reply_user)
        return "-"
    reply_to_short.short_description = _("Ответ на")


    def file_link_readonly(self, obj):
        if obj.file and obj.file.url:
            return format_html('<a href="{}" target="_blank">{}</a>', obj.file.url, obj.get_filename())
        return "-"
    file_link_readonly.short_description = _("Файл")

    def file_info(self, obj): # Для list_display
        if obj.file and obj.file.url:
            return format_html('<a href="{}" title="{}" target="_blank"><i class="fas fa-paperclip"></i></a>',
                               obj.file.url, obj.get_filename())
        return "-"
    file_info.short_description = _("Файл")


    def content_preview(self, obj):
        if obj.is_deleted: return f"[{_('Удалено')}]"
        text = obj.content or ""
        return text[:50] + '...' if len(text) > 50 else text
    content_preview.short_description = _("Содержание")

    # Сообщения не должны создаваться через админку
    def has_add_permission(self, request): return False
    # Разрешить суперпользователям изменять/удалять для отладки
    def has_change_permission(self, request, obj=None): return request.user.is_superuser
    def has_delete_permission(self, request, obj=None): return request.user.is_superuser


@admin.register(MessageReadStatus)
class MessageReadStatusAdmin(admin.ModelAdmin):
    list_display = ('user_link', 'room_link', 'last_read_message_short', 'last_read_timestamp')
    list_filter = ('room', 'user', 'last_read_timestamp')
    search_fields = ('user__username', 'room__name', 'last_read_message__id__iexact')
    list_select_related = ('user', 'room', 'last_read_message', 'last_read_message__user')
    readonly_fields = ('user_link_readonly', 'room_link_readonly', 'last_read_message_link_readonly', 'last_read_timestamp')
    date_hierarchy = 'last_read_timestamp'

    def _get_user_admin_url(self, user):
        return reverse("admin:auth_user_change", args=[user.id])

    def user_link(self, obj): # Для list_display
        if obj.user:
            link = self._get_user_admin_url(obj.user)
            return format_html('<a href="{}">{}</a>', link, obj.user.username)
        return "-"
    user_link.short_description = _("Пользователь")

    def user_link_readonly(self, obj): return self.user_link(obj)
    user_link_readonly.short_description = _("Пользователь")


    def room_link(self, obj): # Для list_display
        link = reverse("admin:room_room_change", args=[obj.room.id])
        return format_html('<a href="{}">{}</a>', link, obj.room.name)
    room_link.short_description = _("Комната")

    def room_link_readonly(self, obj): return self.room_link(obj)
    room_link_readonly.short_description = _("Комната")

    def last_read_message_link_readonly(self, obj):
        if obj.last_read_message:
            link = reverse("admin:room_message_change", args=[obj.last_read_message.id])
            msg_user = obj.last_read_message.user.username if obj.last_read_message.user else _("неизв.")
            return format_html('<a href="{}">ID: {}... ({})</a>', link, str(obj.last_read_message.id)[:8], msg_user)
        return "-"
    last_read_message_link_readonly.short_description = _("Последнее прочитанное сообщение")

    def last_read_message_short(self, obj): # Для list_display
        if obj.last_read_message:
            msg_user = obj.last_read_message.user.username if obj.last_read_message.user else _("неизв.")
            return format_html('Msg <a href="{}">{}...</a> ({})',
                               reverse("admin:room_message_change", args=[obj.last_read_message.id]),
                               str(obj.last_read_message.id)[:8],
                               msg_user)
        return "-"
    last_read_message_short.short_description = _("Прочитано до")

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return request.user.is_superuser # Можно разрешить для админа
    def has_delete_permission(self, request, obj=None): return request.user.is_superuser


@admin.register(Reaction)
class ReactionAdmin(admin.ModelAdmin):
    list_display = ('message_link_short', 'user_link', 'emoji', 'created_at')
    list_filter = ('emoji', 'message__room', 'created_at')
    search_fields = ('emoji', 'user__username', 'message__content', 'message__id__iexact')
    list_select_related = ('message', 'user', 'message__room', 'message__user')
    readonly_fields = ('message_link_readonly', 'user_link_readonly', 'emoji', 'created_at')
    fields = ('message_link_readonly', 'user_link_readonly', 'emoji', 'created_at')

    def _get_user_admin_url(self, user):
        return reverse("admin:auth_user_change", args=[user.id])

    def message_link_readonly(self, obj):
        link = reverse("admin:room_message_change", args=[obj.message.id])
        msg_user = obj.message.user.username if obj.message.user else _("неизв.")
        return format_html('<a href="{}">Сообщение от {} (ID: {}...)</a>', link, msg_user, str(obj.message.id)[:8])
    message_link_readonly.short_description = _("Сообщение")

    def message_link_short(self, obj): # Для list_display
        msg_user = obj.message.user.username if obj.message.user else _("неизв.")
        return format_html('Msg <a href="{}">{}...</a> ({})',
                           reverse("admin:room_message_change", args=[obj.message.id]),
                           str(obj.message.id)[:8],
                           msg_user)
    message_link_short.short_description = _("Сообщение")


    def user_link(self, obj): # Для list_display
        if obj.user:
            link = self._get_user_admin_url(obj.user)
            return format_html('<a href="{}">{}</a>', link, obj.user.username)
        return "-"
    user_link.short_description = _("Пользователь")

    def user_link_readonly(self, obj): return self.user_link(obj)
    user_link_readonly.short_description = _("Пользователь")

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False # Реакции не должны меняться через админку
    def has_delete_permission(self, request, obj=None): return request.user.is_superuser