# room/views.py
import logging
import uuid
from datetime import datetime, timezone as dt_timezone
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden, JsonResponse, Http404
from django.views.decorators.http import require_POST, require_GET
from django.db.models import Q, Max, OuterRef, Subquery, Exists, Value, BooleanField, Min
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

User = get_user_model()
logger = logging.getLogger(__name__)


@login_required
def room_list_view(request):
    user = request.user

    last_message_time_subquery = Message.objects.filter(
        room=OuterRef('pk'),
        is_deleted=False
    ).order_by('-date_added').values('date_added')[:1]

    user_last_read_time_subquery = MessageReadStatus.objects.filter(
        user=user,
        room=OuterRef('pk')
    ).values('last_read_timestamp')[:1]
    
    rooms_qs = Room.objects.filter(
        Q(is_archived=False) &
        (Q(private=False) | Q(participants=user) | Q(creator=user))
    ).select_related('creator').prefetch_related('participants').annotate(
        latest_message_timestamp_in_room=Subquery(last_message_time_subquery),
        user_latest_read_timestamp=Subquery(user_last_read_time_subquery),
        has_unread=Exists(
            Message.objects.filter(
                room=OuterRef('pk'),
                is_deleted=False,
                date_added__gt=Coalesce(
                    OuterRef('user_latest_read_timestamp'),
                    datetime.min.replace(tzinfo=dt_timezone.utc)
                )
            )
        )
    ).distinct().order_by('-last_activity_at')

    context = {
        'rooms': rooms_qs,
        'page_title': _("Чат-комнаты")
    }
    return render(request, 'room/room_list.html', context)


@login_required
def room_detail_view(request, slug):
    user = request.user
    try:
        room_obj = Room.objects.prefetch_related(
            'participants',
        ).get(slug=slug, is_archived=False)
    except Room.DoesNotExist:
        raise Http404(_("Чат-комната не найдена или заархивирована."))

    if room_obj.private and not room_obj.participants.filter(pk=user.pk).exists() and room_obj.creator != user:
        django_messages.error(request, _("У вас нет доступа к этой приватной комнате."))
        return redirect('room:rooms')

    initial_messages_qs = Message.objects.filter(room=room_obj, is_deleted=False)\
                                       .select_related('user', 'reply_to__user')\
                                       .prefetch_related('reactions__user')\
                                       .order_by('-date_added')[:settings.CHAT_MESSAGES_PAGE_SIZE]
    initial_messages = list(initial_messages_qs)[::-1]

    last_message_to_mark_read = None
    if initial_messages:
        last_message_to_mark_read = initial_messages[-1]
    elif Message.objects.filter(room=room_obj, is_deleted=False).exists():
        last_message_to_mark_read = Message.objects.filter(room=room_obj, is_deleted=False).latest('date_added')

    MessageReadStatus.objects.update_or_create(
        user=user, room=room_obj,
        defaults={'last_read_message': last_message_to_mark_read, 'last_read_timestamp': timezone.now()}
    )

    last_message_time_subquery_sidebar = Message.objects.filter(
        room=OuterRef('pk'),
        is_deleted=False
    ).order_by('-date_added').values('date_added')[:1]

    user_last_read_time_subquery_sidebar = MessageReadStatus.objects.filter(
        user=user,
        room=OuterRef('pk')
    ).values('last_read_timestamp')[:1]

    rooms_for_sidebar_qs = Room.objects.filter(
        Q(is_archived=False) & (Q(private=False) | Q(participants=user) | Q(creator=user))
    ).exclude(pk=room_obj.pk).annotate(
        latest_message_timestamp_in_room=Subquery(last_message_time_subquery_sidebar),
        user_latest_read_timestamp=Subquery(user_last_read_time_subquery_sidebar),
        has_unread=Exists(
            Message.objects.filter(
                room=OuterRef('pk'),
                is_deleted=False,
                date_added__gt=Coalesce(
                    OuterRef('user_latest_read_timestamp'),
                    datetime.min.replace(tzinfo=dt_timezone.utc)
                )
            )
        )
    ).order_by('-last_activity_at')[:10]


    context = {
        'room': room_obj,
        'messages_list': initial_messages, # messages_list - это имя переменной, используемое в шаблоне
        'rooms_for_sidebar': rooms_for_sidebar_qs,
        'page_title': room_obj.name,
        'chat_messages_page_size': settings.CHAT_MESSAGES_PAGE_SIZE,
    }
    return render(request, 'room/room_detail.html', context)


@login_required
def room_create_view(request):
    if request.method == 'POST':
        form = RoomForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                with transaction.atomic():
                    new_room = form.save(commit=False)
                    new_room.creator = request.user

                    base_slug = slugify(new_room.name, allow_unicode=True) or f"room-{uuid.uuid4().hex[:6]}"
                    slug = base_slug
                    counter = 1
                    while Room.objects.filter(slug=slug).exists():
                        slug = f"{base_slug}-{counter}"
                        counter += 1
                    new_room.slug = slug
                    new_room.save()
                    
                    form.save_m2m() 
                    
                    if request.user not in new_room.participants.all():
                        new_room.participants.add(request.user)

                django_messages.success(request, _("Комната '%(name)s' успешно создана.") % {'name': new_room.name})
                return redirect(new_room.get_absolute_url())
            except Exception as e:
                logger.exception(f"Error creating room by {request.user.username}: {e}")
                django_messages.error(request, _("Произошла ошибка при создании комнаты. Попробуйте еще раз."))
                form.add_error(None, _("Внутренняя ошибка сервера при создании комнаты."))
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
    room = get_object_or_404(Room, slug=slug)
    if room.creator != request.user and not request.user.is_staff:
        logger.warning(f"User {request.user.username} (not creator/staff) tried to archive room '{slug}'.")
        return JsonResponse({'success': False, 'error': _('У вас нет прав для архивирования этой комнаты.')}, status=403)

    if room.is_archived:
        return JsonResponse({'success': True, 'message': _('Комната уже в архиве.')})

    room.is_archived = True
    room.save(update_fields=['is_archived', 'updated_at'])
    logger.info(f"Room '{slug}' archived by user {request.user.username}.")
    return JsonResponse({'success': True, 'message': _('Комната успешно заархивирована.')})


@require_GET
@login_required
def message_search_view(request, slug):
    room = get_object_or_404(Room, slug=slug)
    if room.private and not room.participants.filter(pk=request.user.pk).exists() and room.creator != request.user:
        return JsonResponse({'success': False, 'error': _('Доступ запрещен.')}, status=403)

    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'success': False, 'error': _('Запрос должен содержать минимум 2 символа.')}, status=400)

    results_qs = Message.objects.filter(
        room=room,
        content__icontains=query,
        is_deleted=False
    ).select_related('user', 'reply_to__user').prefetch_related('reactions__user').order_by('-date_added')[:20] # Убрал __userprofile
    
    messages_data = []
    for msg in results_qs:
        user_avatar_url = None
        if hasattr(msg.user, 'image') and msg.user.image and hasattr(msg.user.image, 'url'):
            user_avatar_url = request.build_absolute_uri(msg.user.image.url) if request else msg.user.image.url
        
        reply_user_avatar_url = None
        if msg.reply_to and msg.reply_to.user:
            if hasattr(msg.reply_to.user, 'image') and msg.reply_to.user.image and hasattr(msg.reply_to.user.image, 'url'):
                 reply_user_avatar_url = request.build_absolute_uri(msg.reply_to.user.image.url) if request else msg.reply_to.user.image.url

        user_data = {
            'id': msg.user.id,
            'username': msg.user.username,
            'display_name': msg.user.display_name if hasattr(msg.user, 'display_name') else msg.user.username,
            'avatar_url': user_avatar_url
        }
        reply_data = None
        if msg.reply_to:
            reply_user_data = {
                'id': msg.reply_to.user.id,
                'username': msg.reply_to.user.username,
                'display_name': msg.reply_to.user.display_name if hasattr(msg.reply_to.user, 'display_name') else msg.reply_to.user.username,
                'avatar_url': reply_user_avatar_url
            }
            reply_data = {
                'id': str(msg.reply_to.id),
                'user': reply_user_data,
                'content_preview': msg.reply_to.content[:70] + '...' if msg.reply_to.content and len(msg.reply_to.content) > 70 else (_("[Файл]") if msg.reply_to.file else ""),
                'has_file': bool(msg.reply_to.file),
                'is_deleted': msg.reply_to.is_deleted,
            }
        file_data = None
        if msg.file and hasattr(msg.file, 'url'):
            try:
                file_data = {'url': request.build_absolute_uri(msg.file.url) if request else msg.file.url, 'name': msg.get_filename(), 'size': msg.file.size}
            except ValueError:
                 file_data = {'url': msg.file.url, 'name': msg.get_filename(), 'size': msg.file.size}
            except Exception:
                 file_data = {'url': '#', 'name': _('Ошибка файла'), 'size': None}
        
        reactions_summary = {}
        for r_obj in msg.reactions.all():
            if r_obj.emoji not in reactions_summary:
                reactions_summary[r_obj.emoji] = {'count': 0, 'users': []}
            reactions_summary[r_obj.emoji]['count'] +=1
            reactions_summary[r_obj.emoji]['users'].append(r_obj.user.username)

        messages_data.append({
            'id': str(msg.id),
            'user': user_data,
            'room_slug': room.slug,
            'content': msg.content if not msg.is_deleted else (_("Сообщение удалено") if msg.is_deleted else ""),
            'file': file_data,
            'timestamp': msg.date_added.isoformat(),
            'edited_at': msg.edited_at.isoformat() if msg.edited_at else None,
            'is_deleted': msg.is_deleted,
            'reply_to': reply_data,
            'reactions': reactions_summary,
        })

    return JsonResponse({'success': True, 'messages': messages_data})