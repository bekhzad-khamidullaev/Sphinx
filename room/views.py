# room/views.py
import logging
import uuid
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden, JsonResponse, Http404
from django.views.decorators.http import require_POST, require_GET
from django.db.models import Q, Max, OuterRef, Subquery, Exists, Value, BooleanField
from django.db.models.functions import Coalesce
from django.utils.text import slugify
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib import messages as django_messages
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.urls import reverse
from django.db import transaction

from .models import Room, Message, MessageReadStatus
from .forms import RoomForm
from .serializers import MessageSerializer # Может понадобиться для начальной загрузки сообщений

User = get_user_model()
logger = logging.getLogger(__name__)


@login_required
def room_list_view(request):
    """
    Отображает список доступных чат-комнат для пользователя.
    Комнаты отсортированы по последней активности.
    Добавляется информация о непрочитанных сообщениях.
    """
    user = request.user

    # Подзапрос для получения ID последнего сообщения в комнате
    last_message_in_room_subquery = Message.objects.filter(
        room=OuterRef('pk'),
        is_deleted=False
    ).order_by('-date_added').values('id')[:1]

    # Подзапрос для получения ID последнего прочитанного сообщения пользователем в комнате
    user_last_read_message_subquery = MessageReadStatus.objects.filter(
        user=user,
        room=OuterRef('pk')
    ).values('last_read_message_id')[:1]

    # Основной запрос комнат
    rooms_qs = Room.objects.filter(
        Q(is_archived=False) &
        (Q(private=False) | Q(participants=user)) # Публичные или приватные, где пользователь участник
    ).select_related('creator').prefetch_related('participants').annotate(
        # Аннотируем ID последнего сообщения в комнате
        latest_message_id_in_room=Subquery(last_message_in_room_subquery),
        # Аннотируем ID последнего прочитанного сообщения пользователем
        user_latest_read_message_id=Subquery(user_last_read_message_subquery),
    ).distinct().order_by('-last_activity_at') # Сортировка по полю last_activity_at модели Room

    # Определяем наличие непрочитанных сообщений на основе аннотаций
    # has_unread = True если:
    # 1. В комнате есть сообщения (latest_message_id_in_room не NULL)
    # 2. ИЛИ пользователь никогда не читал сообщения в этой комнате (user_latest_read_message_id IS NULL)
    #    ИЛИ ID последнего сообщения в комнате не совпадает с ID последнего прочитанного пользователем
    #    (с учетом того, что ID сообщений UUID и могут не быть строго последовательными по значению,
    #     но date_added должно быть). Более надежно было бы сравнивать timestamp'ы, но это сложнее в одном запросе.
    #     Текущая логика с ID должна работать, если UUIDv1 или если мы предполагаем, что более новый ID > старый ID.
    #     Альтернативно, можно сделать это в цикле в Python, но это больше запросов.
    #
    #     Упрощенный вариант (если ID не всегда упорядочены, но мы хотим избежать цикла):
    #     has_unread = Exists(Message.objects.filter(room=OuterRef('pk'), is_deleted=False, date_added__gt=Coalesce(Subquery(MessageReadStatus.objects.filter(user=user, room=OuterRef('pk')).values('last_read_message__date_added')[:1]), timezone.datetime.min.replace(tzinfo=timezone.utc))))
    #     rooms_qs = rooms_qs.annotate(has_unread=has_unread)
    #
    # Пока оставим вариант с сравнением ID, так как он проще и часто используется
    processed_rooms = []
    for room in rooms_qs:
        has_unread_flag = False
        if room.latest_message_id_in_room: # Если в комнате есть сообщения
            if not room.user_latest_read_message_id: # Пользователь ничего не читал
                has_unread_flag = True
            # Сравниваем ID. UUID могут не быть упорядочены лексикографически так же, как по времени.
            # Для UUIDv1 это обычно так, для UUIDv4 - нет.
            # Более надежно было бы иметь timestamp последнего прочитанного сообщения.
            # Предположим, что last_read_message_id всегда "меньше или равно" latest_message_id_in_room, если прочитано.
            elif room.latest_message_id_in_room != room.user_latest_read_message_id:
                 has_unread_flag = True
        room.has_unread = has_unread_flag
        processed_rooms.append(room)


    context = {
        'rooms': processed_rooms,
        'page_title': _("Чат-комнаты")
    }
    return render(request, 'room/room_list.html', context)


@login_required
def room_detail_view(request, slug):
    """ Отображает конкретную чат-комнату и ее сообщения. """
    user = request.user
    try:
        # Загружаем комнату, включая участников для проверки прав
        room_obj = Room.objects.prefetch_related('participants').get(slug=slug, is_archived=False)
    except Room.DoesNotExist:
        raise Http404(_("Чат-комната не найдена или заархивирована."))

    # Проверка прав доступа
    if room_obj.private and not room_obj.participants.filter(pk=user.pk).exists():
        django_messages.error(request, _("У вас нет доступа к этой приватной комнате."))
        return redirect('room:rooms') # Имя URL для списка комнат

    # Загрузка начального набора сообщений (например, последние N)
    # Используем MessageSerializer для консистентности с WebSocket, если это удобно
    # Или собираем данные вручную для шаблона.
    # Пагинация на стороне клиента (бесконечная прокрутка) будет загружать старые сообщения через WebSocket.
    initial_messages_qs = Message.objects.filter(room=room_obj, is_deleted=False)\
                                       .select_related('user', 'reply_to__user')\
                                       .prefetch_related('reactions__user')\
                                       .order_by('-date_added')[:settings.CHAT_MESSAGES_PAGE_SIZE]
    
    initial_messages = list(initial_messages_qs)[::-1] # Переворачиваем для хронологического порядка

    # Сериализация сообщений (если нужна сложная структура для JS)
    # serialized_initial_messages = []
    # for msg in initial_messages:
    #     # Здесь нужен контекст с request для MessageSerializer, если он используется
    #     serializer_context = {'request': request, 'consumer_user': user} # consumer_user - тот, кто смотрит
    #     serialized_initial_messages.append(MessageSerializer(msg, context=serializer_context).data)

    # Отмечаем сообщения как прочитанные
    # Обновляем MessageReadStatus до последнего видимого сообщения
    if initial_messages:
        last_message_in_initial_set = initial_messages[-1]
        MessageReadStatus.objects.update_or_create(
            user=user, room=room_obj,
            defaults={'last_read_message': last_message_in_initial_set, 'last_read_timestamp': timezone.now()}
        )
    else: # Если сообщений нет, но пользователь зашел в комнату
        MessageReadStatus.objects.update_or_create(
            user=user, room=room_obj,
            defaults={'last_read_message': None, 'last_read_timestamp': timezone.now()}
        )

    # Список других комнат для боковой панели (аналогично room_list_view)
    # ... (можно скопировать и адаптировать логику из room_list_view для rooms_for_sidebar) ...
    # Для краткости здесь пропущено, но вы можете добавить похожую логику
    rooms_for_sidebar = Room.objects.filter(
        Q(is_archived=False) & (Q(private=False) | Q(participants=user))
    ).exclude(pk=room_obj.pk).order_by('-last_activity_at')[:10] # Пример

    context = {
        'room': room_obj,
        'messages_list': initial_messages, # Передаем объекты модели, шаблон сам их отобразит
        # 'serialized_messages_json': json.dumps(serialized_initial_messages), # Если JS ожидает JSON
        'rooms_for_sidebar': rooms_for_sidebar,
        'page_title': room_obj.name,
        'chat_messages_page_size': settings.CHAT_MESSAGES_PAGE_SIZE,
    }
    return render(request, 'room/room_detail.html', context)


@login_required
def room_create_view(request):
    """ Создание новой чат-комнаты. """
    if request.method == 'POST':
        form = RoomForm(request.POST, user=request.user) # Передаем пользователя для логики формы
        if form.is_valid():
            try:
                with transaction.atomic(): # Используем транзакцию для атомарности операций
                    new_room = form.save(commit=False)
                    new_room.creator = request.user

                    # Генерация уникального slug
                    base_slug = slugify(new_room.name) or f"room-{uuid.uuid4().hex[:6]}"
                    slug = base_slug
                    counter = 1
                    while Room.objects.filter(slug=slug).exists():
                        slug = f"{base_slug}-{counter}"
                        counter += 1
                    new_room.slug = slug
                    new_room.save() # Сначала сохраняем комнату, чтобы получить ID

                    # Сохраняем M2M участников, выбранных в форме
                    form.save_m2m()
                    # Добавляем создателя в участники, если он еще не там
                    if request.user not in new_room.participants.all():
                        new_room.participants.add(request.user)

                django_messages.success(request, _("Комната '%(name)s' успешно создана.") % {'name': new_room.name})
                return redirect(new_room.get_absolute_url())
            except Exception as e:
                logger.exception(f"Error creating room by {request.user.username}: {e}")
                django_messages.error(request, _("Произошла ошибка при создании комнаты. Попробуйте еще раз."))
    else:
        form = RoomForm(user=request.user)

    context = {
        'form': form,
        'page_title': _("Создать новую комнату")
    }
    return render(request, 'room/room_form.html', context)


@require_POST
@login_required
def room_archive_view(request, slug):
    """ Архивирование комнаты (AJAX). """
    room = get_object_or_404(Room, slug=slug)
    # Проверка прав: архивировать может создатель или staff
    if room.creator != request.user and not request.user.is_staff:
        logger.warning(f"User {request.user.username} (not creator/staff) tried to archive room '{slug}'.")
        return JsonResponse({'success': False, 'error': _('У вас нет прав для архивирования этой комнаты.')}, status=403)

    if room.is_archived:
        return JsonResponse({'success': True, 'message': _('Комната уже в архиве.')})

    room.is_archived = True
    room.save(update_fields=['is_archived'])
    logger.info(f"Room '{slug}' archived by user {request.user.username}.")
    return JsonResponse({'success': True, 'message': _('Комната успешно заархивирована.')})

# Поиск сообщений (если нужен HTTP эндпоинт, а не только через WebSocket)
@require_GET
@login_required
def message_search_view(request, slug):
    room = get_object_or_404(Room, slug=slug)
    if room.private and not room.participants.filter(pk=request.user.pk).exists():
        return JsonResponse({'success': False, 'error': _('Доступ запрещен.')}, status=403)

    query = request.GET.get('q', '').strip()
    if len(query) < 2: # Минимальная длина запроса
        return JsonResponse({'success': False, 'error': _('Запрос должен содержать минимум 2 символа.')}, status=400)

    # PostgreSQL FTS (если настроено)
    # from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
    # vector = SearchVector('content', weight='A') + SearchVector('user__username', weight='B') # Пример
    # search_query = SearchQuery(query, search_type='websearch')
    # results = Message.objects.annotate(
    #     rank=SearchRank(vector, search_query)
    # ).filter(search_vector=search_query, room=room, is_deleted=False).order_by('-rank')[:20]

    # Простой поиск
    results = Message.objects.filter(
        room=room,
        content__icontains=query,
        is_deleted=False
    ).select_related('user').order_by('-date_added')[:20]

    # Используем MessageSerializer для форматирования данных
    # Нужен request в контексте, если сериализатор его использует
    serializer_context = {'request': request, 'consumer_user': request.user}
    messages_data = MessageSerializer(results, many=True, context=serializer_context).data
    return JsonResponse({'success': True, 'messages': messages_data})