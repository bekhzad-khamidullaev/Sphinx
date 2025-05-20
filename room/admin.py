# room/admin.py
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import Count
from django.contrib import messages as django_messages
from .models import Room, Message, MessageReadStatus, Reaction

# Предполагаем, что User модель из user_profiles
USER_ADMIN_CHANGE_URL_NAME = "admin:user_profiles_user_change" # ИЗМЕНИТЕ, ЕСЛИ USER В ДРУГОМ ПРИЛОЖЕНИИ (например, "admin:auth_user_change")

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'private', 'creator_link_display', 'participant_count_display', 'created_at', 'last_activity_at', 'is_archived')
    list_filter = ('private', 'is_archived', 'created_at', 'last_activity_at')
    search_fields = ('name', 'slug', 'participants__username', 'creator__username')
    prepopulated_fields = {'slug': ('name',)}
    filter_horizontal = ('participants',)
    readonly_fields = ('id', 'created_at', 'updated_at', 'last_activity_at', 'creator_link_display') # Добавил 'id'
    actions = ['archive_rooms', 'unarchive_rooms']
    fieldsets = (
        (None, {'fields': ('id', 'name', 'slug', 'creator_link_display', 'private', 'is_archived')}),
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

    # Убрал creator_username, так как creator_link_display показывает имя и является ссылкой
    def creator_link_display(self, obj):
        if obj.creator:
            link = reverse(USER_ADMIN_CHANGE_URL_NAME, args=[obj.creator.id])
            return format_html('<a href="{}">{}</a>', link, obj.creator.username) # или obj.creator.display_name
        return "-"
    creator_link_display.short_description = _("Создатель")
    creator_link_display.admin_order_field = 'creator__username'


    @admin.action(description=_("Архивировать выбранные комнаты"))
    def archive_rooms(self, request, queryset):
        updated_count = 0
        for room in queryset:
            if not room.is_archived:
                room.is_archived = True
                room.save(update_fields=['is_archived'])
                updated_count += 1
        if updated_count > 0:
            self.message_user(request, _("%(count)d комнат было архивировано.") % {'count': updated_count}, django_messages.SUCCESS)
        else:
            self.message_user(request, _("Выбранные комнаты уже были архивированы или не выбрано ни одной."), django_messages.WARNING)


    @admin.action(description=_("Восстановить выбранные комнаты из архива"))
    def unarchive_rooms(self, request, queryset):
        updated_count = 0
        for room in queryset:
            if room.is_archived:
                room.is_archived = False
                room.save(update_fields=['is_archived'])
                updated_count +=1
        if updated_count > 0:
            self.message_user(request, _("%(count)d комнат было восстановлено.") % {'count': updated_count}, django_messages.SUCCESS)
        else:
            self.message_user(request, _("Выбранные комнаты не были в архиве или не выбрано ни одной."), django_messages.WARNING)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id_short', 'room_link_display', 'user_link_display', 'content_preview', 'file_info_display', 'reply_to_short_display', 'is_deleted', 'date_added', 'edited_at')
    list_filter = ('is_deleted', 'date_added', 'room__name', 'user__username') # Фильтр по именам, а не ID
    search_fields = ('content', 'user__username', 'room__name', 'id__iexact')
    date_hierarchy = 'date_added'
    list_select_related = ('room', 'user', 'reply_to', 'reply_to__user')
    readonly_fields = ('id', 'date_added', 'edited_at', 'user_link_display_readonly', 'room_link_display_readonly', 'reply_to_link_readonly', 'file_link_readonly')
    fields = (
        'id', 'room_link_display_readonly', 'user_link_display_readonly', 'content', 'file', 'file_link_readonly',
        'reply_to_link_readonly', 'is_deleted', 'date_added', 'edited_at'
    )

    def id_short(self, obj):
        return str(obj.id).split('-')[0] + "..."
    id_short.short_description = _("ID")

    def _get_user_admin_url(self, user_id):
        return reverse(USER_ADMIN_CHANGE_URL_NAME, args=[user_id])

    def user_link_display(self, obj):
        if obj.user:
            link = self._get_user_admin_url(obj.user.id)
            return format_html('<a href="{}">{}</a>', link, obj.user.username) # или obj.user.display_name
        return "-"
    user_link_display.short_description = _("Пользователь")
    user_link_display.admin_order_field = 'user__username'

    def user_link_display_readonly(self, obj): return self.user_link_display(obj)
    user_link_display_readonly.short_description = _("Пользователь")


    def room_link_display(self, obj):
        link = reverse("admin:room_room_change", args=[obj.room.id])
        return format_html('<a href="{}">{}</a>', link, obj.room.name)
    room_link_display.short_description = _("Комната")
    room_link_display.admin_order_field = 'room__name'

    def room_link_display_readonly(self, obj): return self.room_link_display(obj)
    room_link_display_readonly.short_description = _("Комната")


    def reply_to_link_readonly(self, obj):
        if obj.reply_to:
            link = reverse("admin:room_message_change", args=[obj.reply_to.id])
            reply_user = obj.reply_to.user.username if obj.reply_to.user else _("неизвестный")
            return format_html('<a href="{}">Msg ID: {}... (by {})</a>', link, str(obj.reply_to.id)[:8], reply_user)
        return "-"
    reply_to_link_readonly.short_description = _("В ответ на")

    def reply_to_short_display(self, obj):
        if obj.reply_to:
            reply_user = obj.reply_to.user.username if obj.reply_to.user else _("неизв.")
            return format_html('Msg <a href="{}">{}...</a> ({})',
                               reverse("admin:room_message_change", args=[obj.reply_to.id]),
                               str(obj.reply_to.id)[:8],
                               reply_user)
        return "-"
    reply_to_short_display.short_description = _("Ответ на")


    def file_link_readonly(self, obj):
        if obj.file and hasattr(obj.file, 'url'): # Проверка hasattr
            return format_html('<a href="{}" target="_blank">{}</a>', obj.file.url, obj.get_filename() or _("файл"))
        return "-"
    file_link_readonly.short_description = _("Файл")

    def file_info_display(self, obj):
        if obj.file and hasattr(obj.file, 'url'):
            return format_html('<a href="{}" title="{}" target="_blank"><i class="fas fa-paperclip"></i></a>',
                               obj.file.url, obj.get_filename() or _("файл"))
        return "-"
    file_info_display.short_description = _("Ф") # Коротко для колонки
    file_info_display.allow_tags = True # Для FontAwesome


    def content_preview(self, obj):
        if obj.is_deleted: return f"[{_('Удалено')}]"
        text = obj.content or ""
        return text[:40] + '...' if len(text) > 40 else text # Уменьшил длину превью
    content_preview.short_description = _("Содержание")

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return request.user.is_superuser
    def has_delete_permission(self, request, obj=None): return request.user.is_superuser


@admin.register(MessageReadStatus)
class MessageReadStatusAdmin(admin.ModelAdmin):
    list_display = ('user_link_display', 'room_link_display', 'last_read_message_short_display', 'last_read_timestamp')
    list_filter = ('room__name', 'user__username', 'last_read_timestamp')
    search_fields = ('user__username', 'room__name', 'last_read_message__id__iexact')
    list_select_related = ('user', 'room', 'last_read_message', 'last_read_message__user')
    readonly_fields = ('user_link_display_readonly', 'room_link_display_readonly', 'last_read_message_link_readonly', 'last_read_timestamp')
    date_hierarchy = 'last_read_timestamp'
    fields = ('user_link_display_readonly', 'room_link_display_readonly', 'last_read_message_link_readonly', 'last_read_timestamp')


    def _get_user_admin_url(self, user_id):
        return reverse(USER_ADMIN_CHANGE_URL_NAME, args=[user_id])

    def user_link_display(self, obj):
        if obj.user:
            link = self._get_user_admin_url(obj.user.id)
            return format_html('<a href="{}">{}</a>', link, obj.user.username)
        return "-"
    user_link_display.short_description = _("Пользователь")

    def user_link_display_readonly(self, obj): return self.user_link_display(obj)
    user_link_display_readonly.short_description = _("Пользователь")


    def room_link_display(self, obj):
        link = reverse("admin:room_room_change", args=[obj.room.id])
        return format_html('<a href="{}">{}</a>', link, obj.room.name)
    room_link_display.short_description = _("Комната")

    def room_link_display_readonly(self, obj): return self.room_link_display(obj)
    room_link_display_readonly.short_description = _("Комната")

    def last_read_message_link_readonly(self, obj):
        if obj.last_read_message:
            link = reverse("admin:room_message_change", args=[obj.last_read_message.id])
            msg_user = obj.last_read_message.user.username if obj.last_read_message.user else _("неизв.")
            return format_html('<a href="{}">Msg ID: {}... (by {})</a>', link, str(obj.last_read_message.id)[:8], msg_user)
        return "-"
    last_read_message_link_readonly.short_description = _("Последнее прочитанное сообщение")

    def last_read_message_short_display(self, obj):
        if obj.last_read_message:
            msg_user = obj.last_read_message.user.username if obj.last_read_message.user else _("неизв.")
            return format_html('Msg <a href="{}">{}...</a> ({})',
                               reverse("admin:room_message_change", args=[obj.last_read_message.id]),
                               str(obj.last_read_message.id)[:8],
                               msg_user)
        return "-"
    last_read_message_short_display.short_description = _("Прочитано до")

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return request.user.is_superuser
    def has_delete_permission(self, request, obj=None): return request.user.is_superuser


@admin.register(Reaction)
class ReactionAdmin(admin.ModelAdmin):
    list_display = ('message_link_short_display', 'user_link_display', 'emoji', 'created_at')
    list_filter = ('emoji', 'message__room__name', 'created_at') # Фильтр по имени комнаты
    search_fields = ('emoji', 'user__username', 'message__content', 'message__id__iexact')
    list_select_related = ('message', 'user', 'message__room', 'message__user')
    readonly_fields = ('message_link_readonly', 'user_link_display_readonly', 'emoji', 'created_at')
    fields = ('message_link_readonly', 'user_link_display_readonly', 'emoji', 'created_at')

    def _get_user_admin_url(self, user_id):
        return reverse(USER_ADMIN_CHANGE_URL_NAME, args=[user_id])

    def message_link_readonly(self, obj):
        link = reverse("admin:room_message_change", args=[obj.message.id])
        msg_user = obj.message.user.username if obj.message.user else _("неизв.")
        return format_html('<a href="{}">Сообщение от {} (ID: {}...)</a>', link, msg_user, str(obj.message.id)[:8])
    message_link_readonly.short_description = _("Сообщение")

    def message_link_short_display(self, obj):
        msg_user = obj.message.user.username if obj.message.user else _("неизв.")
        return format_html('Msg <a href="{}">{}...</a> ({})',
                           reverse("admin:room_message_change", args=[obj.message.id]),
                           str(obj.message.id)[:8],
                           msg_user)
    message_link_short_display.short_description = _("Сообщение")


    def user_link_display(self, obj):
        if obj.user:
            link = self._get_user_admin_url(obj.user.id)
            return format_html('<a href="{}">{}</a>', link, obj.user.username)
        return "-"
    user_link_display.short_description = _("Пользователь")

    def user_link_display_readonly(self, obj): return self.user_link_display(obj)
    user_link_display_readonly.short_description = _("Пользователь")

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return request.user.is_superuser