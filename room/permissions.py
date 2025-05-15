# room/permissions.py
from rest_framework import permissions

class IsRoomParticipantOrCreatorOrReadOnly(permissions.BasePermission):
    """
    Разрешает доступ, если пользователь - участник или создатель комнаты.
    Для методов GET, HEAD, OPTIONS разрешает всем аутентифицированным.
    """
    def has_object_permission(self, request, view, obj): # obj это Room
        if request.method in permissions.SAFE_METHODS:
            # Для публичных комнат разрешаем просмотр всем
            if not obj.private:
                return True
            # Для приватных - только участникам или создателю
            return request.user == obj.creator or obj.participants.filter(pk=request.user.pk).exists()

        # Для небезопасных методов (POST, PUT, DELETE) - только создателю
        # (или можно расширить до участников, если им нужны права на изменение комнаты)
        return request.user == obj.creator or request.user.is_staff


class IsMessageSenderOrRoomCreatorOrReadOnly(permissions.BasePermission):
    """
    Разрешает доступ к сообщению, если пользователь - отправитель сообщения,
    или создатель комнаты, к которой принадлежит сообщение.
    Для SAFE_METHODS - если пользователь имеет доступ к комнате.
    """
    def has_object_permission(self, request, view, obj): # obj это Message
        room = obj.room
        # Проверка доступа к комнате
        can_access_room = False
        if not room.private:
            can_access_room = True
        elif request.user == room.creator or room.participants.filter(pk=request.user.pk).exists():
            can_access_room = True

        if not can_access_room:
            return False # Нет доступа даже на чтение, если нет доступа к комнате

        if request.method in permissions.SAFE_METHODS:
            return True # Если есть доступ к комнате, можно читать сообщения

        # Для небезопасных методов - только отправитель сообщения или создатель комнаты (или staff)
        return obj.user == request.user or room.creator == request.user or request.user.is_staff