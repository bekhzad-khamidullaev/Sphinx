# room/views_api.py
from rest_framework import viewsets, permissions, status, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.db.models import Q
# from django.shortcuts import get_object_or_404 # Не используется напрямую, DRF это делает
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
import uuid

from .models import Room, Message, Reaction
from .serializers import RoomSerializer, MessageSerializer, BasicUserSerializer # ReactionSerializer не используется напрямую здесь
from .permissions import IsRoomParticipantOrCreatorOrReadOnly, IsMessageSenderOrRoomCreatorOrReadOnly

User = get_user_model()
class RoomViewSet(viewsets.ModelViewSet):
    serializer_class = RoomSerializer
    permission_classes = [permissions.IsAuthenticated, IsRoomParticipantOrCreatorOrReadOnly]
    lookup_field = 'slug'

    def get_queryset(self):
        user = self.request.user
        return Room.objects.filter(
            Q(is_archived=False) &
            (Q(private=False) | Q(participants=user) | Q(creator=user))
        ).select_related('creator').prefetch_related('participants').distinct().order_by('-last_activity_at') # Добавил сортировку

    def get_serializer_context(self):
        # Передаем request для генерации абсолютных URL в сериализаторах
        return {'request': self.request}

    def perform_create(self, serializer):
        user = self.request.user
        name = serializer.validated_data.get('name')
        base_slug = slugify(name, allow_unicode=True) or f"room-{uuid.uuid4().hex[:6]}"
        slug = base_slug
        counter = 1
        while Room.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        # Участники (participants) должны быть обработаны, если они передаются в request.data
        # В RoomSerializer поле participants сейчас read_only, что означает, что их нужно добавлять после создания комнаты.
        # Если вы хотите передавать participants при создании через API, нужно сделать поле writeable
        # или добавить кастомную логику в create/perform_create.
        room = serializer.save(creator=user, slug=slug)
        
        # Пример добавления участников, если они переданы в request.data['participants'] (список ID)
        participants_ids = self.request.data.get('participants', [])
        if isinstance(participants_ids, list):
            valid_participant_ids = []
            for pid in participants_ids:
                try:
                    valid_participant_ids.append(int(pid))
                except (ValueError, TypeError):
                    pass # Игнорируем невалидные ID
            if valid_participant_ids:
                room.participants.set(User.objects.filter(id__in=valid_participant_ids))
        
        # Всегда добавляем создателя, если его еще нет
        if user not in room.participants.all():
            room.participants.add(user)

    @action(detail=True, methods=['get'], permission_classes=[permissions.IsAuthenticated, IsRoomParticipantOrCreatorOrReadOnly])
    def messages(self, request, slug=None):
        room = self.get_object()
        messages_qs = Message.objects.filter(room=room, is_deleted=False)\
                                   .select_related('user', 'reply_to__user')\
                                   .prefetch_related('reactions__user')\
                                   .order_by('-date_added')

        page = self.paginate_queryset(messages_qs)
        # Передаем request и 'consumer_user' (текущий пользователь) в контекст MessageSerializer
        serializer_context = {'request': request, 'consumer_user': request.user}
        if page is not None:
            serializer = MessageSerializer(page, many=True, context=serializer_context)
            return self.get_paginated_response(serializer.data)

        serializer = MessageSerializer(messages_qs, many=True, context=serializer_context)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='archive', permission_classes=[permissions.IsAuthenticated, IsRoomParticipantOrCreatorOrReadOnly])
    def archive_room_action(self, request, slug=None):
        room = self.get_object()
        if room.creator != request.user and not request.user.is_staff:
            return Response({'error': _('Только создатель или администратор может архивировать комнату.')}, status=status.HTTP_403_FORBIDDEN)
        
        if room.is_archived:
            return Response({'status': _('Комната уже в архиве.')}, status=status.HTTP_400_BAD_REQUEST)

        room.is_archived = True
        room.save(update_fields=['is_archived', 'updated_at'])
        return Response({'status': _('Комната архивирована')})

    @action(detail=True, methods=['post'], url_path='unarchive', permission_classes=[permissions.IsAuthenticated, IsRoomParticipantOrCreatorOrReadOnly])
    def unarchive_room_action(self, request, slug=None):
        room = self.get_object()
        if room.creator != request.user and not request.user.is_staff:
             return Response({'error': _('Только создатель или администратор может разархивировать комнату.')}, status=status.HTTP_403_FORBIDDEN)
        
        if not room.is_archived:
            return Response({'status': _('Комната не была в архиве.')}, status=status.HTTP_400_BAD_REQUEST)

        room.is_archived = False
        room.save(update_fields=['is_archived', 'updated_at'])
        return Response({'status': _('Комната восстановлена из архива')})

    @action(detail=True, methods=['post', 'delete'], url_path='participants', permission_classes=[permissions.IsAuthenticated, IsRoomParticipantOrCreatorOrReadOnly])
    def manage_participants(self, request, slug=None):
        room = self.get_object()
        if not room.private:
            return Response({'error': _('Управление участниками доступно только для приватных комнат.')}, status=status.HTTP_400_BAD_REQUEST)
        if room.creator != request.user and not request.user.is_staff:
            return Response({'error': _('Только создатель или администратор может управлять участниками.')}, status=status.HTTP_403_FORBIDDEN)

        user_id_param = request.data.get('user_id')
        if not user_id_param:
            return Response({'error': _('Не указан ID пользователя.')}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user_to_manage = User.objects.get(pk=int(user_id_param)) # Убедимся, что это int
        except User.DoesNotExist:
            return Response({'error': _('Пользователь не найден.')}, status=status.HTTP_404_NOT_FOUND)
        except (ValueError, TypeError):
            return Response({'error': _('Некорректный ID пользователя.')}, status=status.HTTP_400_BAD_REQUEST)

        if request.method == 'POST':
            if user_to_manage not in room.participants.all():
                room.participants.add(user_to_manage)
                return Response({'status': _('Участник %(username)s добавлен.') % {'username': user_to_manage.username }})
            else:
                return Response({'status': _('Пользователь %(username)s уже является участником.')  % {'username': user_to_manage.username }}, status=status.HTTP_400_BAD_REQUEST)
        
        elif request.method == 'DELETE':
            if user_to_manage == room.creator:
                return Response({'error': _('Нельзя удалить создателя комнаты из участников.')}, status=status.HTTP_400_BAD_REQUEST)
            if user_to_manage in room.participants.all():
                room.participants.remove(user_to_manage)
                return Response({'status': _('Участник %(username)s удален.') % {'username': user_to_manage.username }})
            else:
                return Response({'error': _('Пользователь %(username)s не является участником этой комнаты.') % {'username': user_to_manage.username }}, status=status.HTTP_404_NOT_FOUND)
        
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


class MessageViewSet(mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated, IsMessageSenderOrRoomCreatorOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        accessible_room_pks = Room.objects.filter(
            Q(is_archived=False) &
            (Q(private=False) | Q(participants=user) | Q(creator=user))
        ).values_list('pk', flat=True)

        return Message.objects.filter(room_id__in=list(accessible_room_pks), is_deleted=False)\
                              .select_related('user', 'room', 'reply_to__user')\
                              .prefetch_related('reactions__user') # Префетчим user для реакций

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({'request': self.request, 'consumer_user': self.request.user})
        return context

    @action(detail=True, methods=['post'], url_path='react')
    def toggle_reaction(self, request, pk=None): # pk is message_id
        message = self.get_object()
        emoji = request.data.get('emoji')
        if not emoji:
            return Response({'error': _('Не указан эмодзи для реакции.')}, status=status.HTTP_400_BAD_REQUEST)

        reaction, created = Reaction.objects.get_or_create(
            message=message, user=request.user, emoji=emoji
        )
        action_taken_msg = _("добавлена") if created else _("удалена")
        if not created:
            reaction.delete()

        message.refresh_from_db() # Обновляем инстанс сообщения для актуальных реакций
        updated_reactions_summary = self.get_serializer(message).data.get('reactions') # Используем get_serializer для MessageSerializer

        return Response({
            'status': _('Реакция %(action)s.') % {'action': action_taken_msg}, # Исправлено сообщение
            'reactions': updated_reactions_summary
        })


class UserSearchViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = BasicUserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_context(self): # Передаем request для BasicUserSerializer
        return {'request': self.request}

    def get_queryset(self):
        queryset = User.objects.filter(is_active=True)
        search_query = self.request.query_params.get('q', None)
        exclude_ids_str = self.request.query_params.get('exclude_ids', '')
        exclude_ids = [int(uid) for uid in exclude_ids_str.split(',') if uid.isdigit()]

        if search_query and len(search_query) >= 2:
            queryset = queryset.filter(
                Q(username__icontains=search_query) |
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(email__icontains=search_query)
            ).distinct()
            if exclude_ids:
                queryset = queryset.exclude(id__in=exclude_ids)
            return queryset.order_by('username')[:15] # Ограничиваем количество результатов и сортируем
        else:
            return User.objects.none()
