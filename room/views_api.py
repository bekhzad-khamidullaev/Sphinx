# room/views_api.py
from rest_framework import viewsets, permissions, status, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
import uuid

from .models import Room, Message, Reaction
from .serializers import RoomSerializer, MessageSerializer, BasicUserSerializer, ReactionSerializer
from .permissions import IsRoomParticipantOrCreatorOrReadOnly, IsMessageSenderOrRoomCreatorOrReadOnly

User = get_user_model()

class RoomViewSet(viewsets.ModelViewSet):
    serializer_class = RoomSerializer
    permission_classes = [permissions.IsAuthenticated, IsRoomParticipantOrCreatorOrReadOnly]
    lookup_field = 'slug'

    def get_queryset(self):
        user = self.request.user
        # Пользователь видит публичные комнаты и приватные, где он участник или создатель
        # Также не показываем архивированные комнаты в основном списке
        return Room.objects.filter(
            Q(is_archived=False) &
            (Q(private=False) | Q(participants=user) | Q(creator=user))
        ).select_related('creator').prefetch_related('participants').distinct()

    def perform_create(self, serializer):
        # Создатель и slug устанавливаются в сериализаторе или здесь
        user = self.request.user
        name = serializer.validated_data.get('name')

        base_slug = slugify(name) or f"room-{uuid.uuid4().hex[:6]}"
        slug = base_slug
        counter = 1
        while Room.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

        room = serializer.save(creator=user, slug=slug)
        if user not in room.participants.all(): # Добавляем создателя в участники
            room.participants.add(user)

    @action(detail=True, methods=['get'], permission_classes=[permissions.IsAuthenticated, IsRoomParticipantOrCreatorOrReadOnly])
    def messages(self, request, slug=None):
        """ Получить сообщения для комнаты с пагинацией. """
        room = self.get_object() # Проверит права через IsRoomParticipantOrCreatorOrReadOnly
        
        messages_qs = Message.objects.filter(room=room, is_deleted=False)\
                                   .select_related('user', 'reply_to__user')\
                                   .prefetch_related('reactions__user')\
                                   .order_by('-date_added')
        
        # Пагинация DRF
        page = self.paginate_queryset(messages_qs)
        if page is not None:
            # Передаем request в контекст для сериализатора (например, для `reacted_by_current_user`)
            serializer = MessageSerializer(page, many=True, context={'request': request, 'consumer_user': request.user})
            return self.get_paginated_response(serializer.data)

        serializer = MessageSerializer(messages_qs, many=True, context={'request': request, 'consumer_user': request.user})
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='archive', permission_classes=[permissions.IsAuthenticated, IsRoomParticipantOrCreatorOrReadOnly])
    def archive_room(self, request, slug=None):
        room = self.get_object()
        if room.creator != request.user and not request.user.is_staff:
            return Response({'error': _('Только создатель или администратор может архивировать комнату.')}, status=status.HTTP_403_FORBIDDEN)
        
        room.is_archived = True
        room.save(update_fields=['is_archived'])
        return Response({'status': _('Комната архивирована')})

    @action(detail=True, methods=['post'], url_path='unarchive', permission_classes=[permissions.IsAuthenticated, IsRoomParticipantOrCreatorOrReadOnly])
    def unarchive_room(self, request, slug=None):
        room = self.get_object()
        # Аналогичная проверка прав, если нужно
        room.is_archived = False
        room.save(update_fields=['is_archived'])
        return Response({'status': _('Комната восстановлена из архива')})

    @action(detail=True, methods=['post'], url_path='add-participant', permission_classes=[permissions.IsAuthenticated, IsRoomParticipantOrCreatorOrReadOnly])
    def add_participant(self, request, slug=None):
        room = self.get_object()
        if not room.private:
            return Response({'error': _('Нельзя добавлять участников в публичную комнату.')}, status=status.HTTP_400_BAD_REQUEST)
        if room.creator != request.user and not request.user.is_staff: # Только создатель может добавлять
            return Response({'error': _('Только создатель может добавлять участников.')}, status=status.HTTP_403_FORBIDDEN)

        user_id_to_add = request.data.get('user_id')
        if not user_id_to_add:
            return Response({'error': _('Не указан ID пользователя для добавления.')}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user_to_add = User.objects.get(pk=user_id_to_add)
            if user_to_add not in room.participants.all():
                room.participants.add(user_to_add)
                return Response({'status': _('Участник добавлен.')})
            else:
                return Response({'status': _('Пользователь уже является участником.')})
        except User.DoesNotExist:
            return Response({'error': _('Пользователь не найден.')}, status=status.HTTP_404_NOT_FOUND)


class MessageViewSet(
    mixins.RetrieveModelMixin,
    # mixins.UpdateModelMixin, # Редактирование сообщений через WebSocket
    # mixins.DestroyModelMixin, # Удаление сообщений через WebSocket
    mixins.ListModelMixin, # Для возможности получения списка всех сообщений (если нужно, обычно через RoomViewSet.messages)
    viewsets.GenericViewSet
):
    """
    API для отдельных сообщений. В основном для Retrieve,
    так как создание/обновление/удаление происходит через WebSocket.
    """
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated, IsMessageSenderOrRoomCreatorOrReadOnly]

    def get_queryset(self):
        # Показываем только сообщения из комнат, к которым у пользователя есть доступ
        user = self.request.user
        accessible_room_pks = Room.objects.filter(
            Q(is_archived=False) &
            (Q(private=False) | Q(participants=user) | Q(creator=user))
        ).values_list('pk', flat=True)
        
        return Message.objects.filter(room_id__in=accessible_room_pks, is_deleted=False)\
                              .select_related('user', 'room', 'reply_to__user')\
                              .prefetch_related('reactions__user')

    def get_serializer_context(self):
        # Передаем request в контекст для MessageSerializer
        context = super().get_serializer_context()
        context.update({'request': self.request, 'consumer_user': self.request.user})
        return context

    # Действие для добавления/удаления реакции через API (альтернатива WebSocket)
    @action(detail=True, methods=['post'], url_path='react')
    def toggle_reaction(self, request, pk=None):
        message = self.get_object() # Проверит права на сообщение
        emoji = request.data.get('emoji')
        if not emoji:
            return Response({'error': _('Не указан эмодзи для реакции.')}, status=status.HTTP_400_BAD_REQUEST)

        reaction, created = Reaction.objects.get_or_create(
            message=message, user=request.user, emoji=emoji
        )
        action_taken = "added"
        if not created: # Если реакция уже была, удаляем ее (toggle)
            reaction.delete()
            action_taken = "removed"
        
        # Возвращаем обновленный список реакций для этого сообщения
        # Здесь можно использовать self._get_reactions_summary_for_message из консьюмера, если вынести его
        updated_reactions_summary = MessageSerializer(instance=message, context=self.get_serializer_context()).data.get('reactions')

        return Response({
            'status': _('Реакция %(action)s.') % {'action': action_taken},
            'reactions': updated_reactions_summary
        })


class UserSearchViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    API для поиска пользователей.
    Используется BasicUserSerializer.
    """
    serializer_class = BasicUserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = User.objects.filter(is_active=True)
        search_query = self.request.query_params.get('q', None)
        if search_query and len(search_query) >= 2: # Поиск от 2х символов
            queryset = queryset.filter(
                Q(username__icontains=search_query) |
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(email__icontains=search_query) # Осторожно с поиском по email, если он не публичный
            ).distinct()[:15] # Ограничиваем количество результатов
        else:
            return User.objects.none() # Не возвращаем ничего, если запрос короткий или пустой
        return queryset