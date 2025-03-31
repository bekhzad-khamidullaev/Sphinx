# user_profiles/views.py
import sys
import logging # Добавлен импорт logging
from django.conf import settings # Добавлен импорт settings
from django.urls import reverse # Добавлен импорт reverse
from django.http import HttpResponse, JsonResponse # Добавлен импорт JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.decorators import login_required # permission_required убран, т.к. не используется явно здесь
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.vary import vary_on_cookie
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST # <--- ДОБАВЬТЕ ЭТОТ ИМПОРТ

from rest_framework import viewsets, permissions, status
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import TaskUserRole, Team, User, Department # Убедитесь, что Department импортирован, если используется
from .serializers import TeamSerializer, UserSerializer # Убран RoleSerializer
# Убран RoleForm, добавлены UserUpdateForm (если вы создали его)
from tasks.forms import UserCreateForm, TeamForm #, UserUpdateForm

logger = logging.getLogger(__name__) # Инициализация логгера

# sys.setrecursionlimit(2000) # Можно оставить, если нужно

channel_layer = get_channel_layer()

# ------------------------ API ViewSets ------------------------
# ... (ViewSet'ы как были) ...
class TeamViewSet(viewsets.ModelViewSet):
    queryset = Team.objects.all()
    serializer_class = TeamSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

class UserViewSet(viewsets.ModelViewSet):
    """Manage users."""
    queryset = User.objects.all().select_related('department').prefetch_related('teams', 'groups') # Оптимизация
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAdminUser] # Ограничить доступ администраторам

# ------------------------ Authentication ------------------------
@csrf_protect
@vary_on_cookie
@never_cache
def base(request):
    if request.user.is_authenticated:
        # Если пользователь уже аутентифицирован, перенаправляем на дашборд
        return redirect(settings.LOGIN_REDIRECT_URL)

    if request.method == 'POST':
        # Используем LoginForm для обработки POST
        form = LoginForm(request, data=request.POST) # Используем LoginForm из tasks.forms
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            messages.success(request, _('Вы успешно вошли в систему!'))
            # Перенаправляем на страницу, указанную в 'next', или на дашборд
            next_url = request.POST.get('next', settings.LOGIN_REDIRECT_URL)
            return redirect(next_url)
        else:
            # Если форма невалидна, показываем ошибки
            messages.error(request, _('Неверное имя пользователя или пароль.'))
            # Снова рендерим шаблон с формой и ошибками
            return render(request, 'registration/login.html', {'form': form}) # Используем стандартный шаблон или ваш 'base.html'
    else:
        # Для GET запроса просто показываем форму входа
        form = LoginForm() # Используем LoginForm из tasks.forms

    # Рендерим шаблон login.html (или ваш base.html, если он содержит форму)
    # Лучше использовать отдельный шаблон для входа: 'registration/login.html'
    return render(request, 'registration/login.html', {'form': form})

@csrf_protect
@vary_on_cookie
@never_cache
def user_login(request):
    # Эта view теперь может просто перенаправлять на 'base', если 'base' рендерит форму,
    # или быть основной точкой входа для логина, как показано в 'base' выше.
    # Для ясности, лучше переименовать 'base' в 'login_view' или использовать стандартный LoginView Django.
    # Пока оставим перенаправление на 'base'.
    return redirect('user_profiles:base')

@csrf_protect
@vary_on_cookie
@never_cache
def user_logout(request):
    auth_logout(request)
    messages.success(request, _('Вы успешно вышли из системы.'))
    return redirect(settings.LOGOUT_REDIRECT_URL) # Используем настройку

# ------------------------ Users ------------------------

@login_required
def user_list(request):
    users = User.objects.filter(is_active=True).prefetch_related('groups', 'teams') # Фильтруем активных
    return render(request, "users/user_list.html", {"users": users})

# --- Модальные окна (рендерят только шаблон) ---
@login_required
def modal_create_user(request):
    form = UserCreateForm()
    action_url = reverse('user_profiles:create_user')
    # Убедитесь, что шаблон 'modals/user_form.html' существует
    return render(request, "modals/user_form.html", {"form": form, "action_url": action_url, "form_title": _("Создать пользователя")})

@login_required
def modal_update_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    # Используйте UserUpdateForm, если он создан, иначе UserCreateForm может не подойти
    form = UserUpdateForm(instance=user) # Предполагаем, что UserUpdateForm существует
    action_url = reverse('user_profiles:update_user', kwargs={'pk': pk})
    return render(request, "modals/user_form.html", {"form": form, "instance": user, "action_url": action_url, "form_title": _("Редактировать пользователя")})

@login_required
def modal_delete_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    action_url = reverse('user_profiles:delete_user', kwargs={'pk': pk})
    # Убедитесь, что шаблон 'modals/user_delete_confirmation.html' существует
    return render(request, "modals/user_delete_confirmation.html", {"user_to_delete": user, "action_url": action_url})

# --- Обработчики действий (POST запросы) ---
@login_required
@require_POST # Теперь декоратор импортирован
def create_user(request):
    form = UserCreateForm(request.POST, request.FILES)
    if form.is_valid():
        user = form.save()
        logger.info(f"User '{user.username}' created by '{request.user.username}'.")
        try:
            async_to_sync(channel_layer.group_send)(
                "users_list",
                {"type": "user_update", "message": {"action": "create", "id": user.id, "username": user.username}}
            )
        except Exception as e:
            logger.error(f"Failed to send user creation WebSocket notification: {e}")
        messages.success(request, _("Пользователь '%s' успешно создан!") % user.display_name)
        return JsonResponse({'success': True, 'message': _("Пользователь создан.")})
    else:
        logger.warning(f"User creation failed for user '{request.user.username}'. Errors: {form.errors.get_json_data()}")
        return JsonResponse({'success': False, 'errors': form.errors.get_json_data()}, status=400)

# Добавлено представление для обновления пользователя
@login_required
@require_POST
def update_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    form = UserUpdateForm(request.POST, request.FILES, instance=user) # Используем UserUpdateForm
    if form.is_valid():
        updated_user = form.save()
        logger.info(f"User '{updated_user.username}' updated by '{request.user.username}'.")
        # Добавить WebSocket уведомление об обновлении, если нужно
        messages.success(request, _("Данные пользователя '%s' обновлены.") % updated_user.display_name)
        return JsonResponse({'success': True, 'message': _("Данные пользователя обновлены.")})
    else:
        logger.warning(f"User update failed for user '{user.username}' by '{request.user.username}'. Errors: {form.errors.get_json_data()}")
        return JsonResponse({'success': False, 'errors': form.errors.get_json_data()}, status=400)


@login_required
@require_POST # Теперь декоратор импортирован
def delete_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    if request.user == user:
         logger.warning(f"User '{request.user.username}' attempted to delete self.")
         return JsonResponse({'success': False, 'message': _("Самоудаление запрещено.")}, status=403)

    user_display_name = user.display_name
    user_id = user.id
    user.delete()
    logger.info(f"User '{user_display_name}' (ID: {user_id}) deleted by '{request.user.username}'.")
    try:
        async_to_sync(channel_layer.group_send)(
            "users_list",
            {"type": "user_update", "message": {"action": "delete", "id": user_id}}
        )
    except Exception as e:
        logger.error(f"Failed to send user deletion WebSocket notification: {e}")

    messages.success(request, _("Пользователь '%s' удален!") % user_display_name)
    return JsonResponse({'success': True, 'message': _("Пользователь удален.")})


# ------------------------ Teams ------------------------
@login_required
def team_list(request):
    teams = Team.objects.all().prefetch_related('members', 'team_leader', 'department')
    return render(request, "users/team_list.html", {"teams": teams})

# --- Модальные окна для Команд ---
@login_required
def modal_create_team(request):
    form = TeamForm()
    action_url = reverse('user_profiles:create_team')
    return render(request, "modals/team_form.html", {"form": form, "action_url": action_url, "form_title": _("Создать команду")})

@login_required
def modal_update_team(request, pk):
    team = get_object_or_404(Team, pk=pk)
    form = TeamForm(instance=team)
    action_url = reverse('user_profiles:update_team', kwargs={'pk': pk})
    return render(request, "modals/team_form.html", {"form": form, "instance": team, "action_url": action_url, "form_title": _("Редактировать команду")})

@login_required
def modal_delete_team(request, pk):
    team = get_object_or_404(Team, pk=pk)
    action_url = reverse('user_profiles:delete_team', kwargs={'pk': pk})
    # Убедитесь, что шаблон 'modals/team_delete_confirmation.html' существует
    return render(request, "modals/team_delete_confirmation.html", {"team_to_delete": team, "action_url": action_url})

# --- Обработчики действий для Команд ---
@login_required
@require_POST # Теперь декоратор импортирован
def create_team(request):
    form = TeamForm(request.POST)
    if form.is_valid():
        team = form.save()
        logger.info(f"Team '{team.name}' created by '{request.user.username}'.")
        try:
            async_to_sync(channel_layer.group_send)(
                "teams_list",
                {"type": "team_update", "message": {"action": "create", "id": team.id, "name": team.name}}
            )
        except Exception as e:
            logger.error(f"Failed to send team creation WebSocket notification: {e}")
        messages.success(request, _("Команда '%s' успешно создана!") % team.name)
        return JsonResponse({'success': True, 'message': _("Команда создана.")})
    else:
        logger.warning(f"Team creation failed by '{request.user.username}'. Errors: {form.errors.get_json_data()}")
        return JsonResponse({'success': False, 'errors': form.errors.get_json_data()}, status=400)

# Добавлено представление для обновления команды
@login_required
@require_POST
def update_team(request, pk):
    team = get_object_or_404(Team, pk=pk)
    form = TeamForm(request.POST, instance=team)
    if form.is_valid():
        updated_team = form.save()
        logger.info(f"Team '{updated_team.name}' updated by '{request.user.username}'.")
        # Добавить WebSocket уведомление об обновлении, если нужно
        messages.success(request, _("Данные команды '%s' обновлены.") % updated_team.name)
        return JsonResponse({'success': True, 'message': _("Данные команды обновлены.")})
    else:
        logger.warning(f"Team update failed for team '{team.name}' by '{request.user.username}'. Errors: {form.errors.get_json_data()}")
        return JsonResponse({'success': False, 'errors': form.errors.get_json_data()}, status=400)

@login_required
@require_POST # Теперь декоратор импортирован
def delete_team(request, pk):
    team = get_object_or_404(Team, pk=pk)
    team_name = team.name
    team_id = team.id
    team.delete()
    logger.info(f"Team '{team_name}' (ID: {team_id}) deleted by '{request.user.username}'.")
    try:
        async_to_sync(channel_layer.group_send)(
            "teams_list",
            {"type": "team_update", "message": {"action": "delete", "id": team_id}}
        )
    except Exception as e:
        logger.error(f"Failed to send team deletion WebSocket notification: {e}")
    messages.success(request, _("Команда '%s' удалена!") % team_name)
    return JsonResponse({'success': True, 'message': _("Команда удалена.")})

# Импортируем нужную форму Login
from tasks.forms import LoginForm