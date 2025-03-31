# user_profiles/views.py
import sys
import logging
from django.conf import settings
from django.db.models import Q
from django.urls import reverse, reverse_lazy # Добавлен reverse_lazy
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect # Добавлен HttpResponseRedirect
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin # Для CBV
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.vary import vary_on_cookie
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
# Импорты для CBV
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from django.contrib.messages.views import SuccessMessageMixin

from rest_framework import viewsets, permissions, status
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import TaskUserRole, Team, User, Department
from .serializers import TeamSerializer, UserSerializer

from django.contrib.auth.views import PasswordChangeView, PasswordChangeDoneView
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.contrib.messages.views import SuccessMessageMixin
from tasks.models import Task
# user_profiles/views.py
from .forms import TeamForm, UserCreateForm, UserUpdateForm, UserProfileEditForm, LoginForm

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()


class UserProfileView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    """Отображение и редактирование профиля текущего пользователя."""
    model = User
    form_class = UserProfileEditForm # Используем нашу форму
    template_name = 'users/user_profile.html'
    success_url = reverse_lazy('user_profiles:profile_view')
    success_message = _("Профиль успешно обновлен.")

    def get_object(self, queryset=None):
        # Объектом всегда является текущий пользователь
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context['page_title'] = _("Мой профиль")
        context['profile_user'] = user # Передаем пользователя для отображения

        # --- Получаем историю задач ---
        user_tasks_qs = Task.objects.filter(
            Q(created_by=user) | Q(user_roles__user=user)
        ).select_related(
            'project', 'created_by'
        ).prefetch_related(
            'user_roles__user'
        ).distinct().order_by('-updated_at')

        # Пагинация для истории задач
        paginator = Paginator(user_tasks_qs, 10) # 10 задач на страницу
        page_number = self.request.GET.get('task_page')
        try:
             task_page_obj = paginator.page(page_number)
        except PageNotAnInteger:
             task_page_obj = paginator.page(1)
        except EmptyPage:
             task_page_obj = paginator.page(paginator.num_pages)

        context['task_history_page'] = task_page_obj
        # -----------------------------

        return context

    def form_valid(self, form):
         # SuccessMessageMixin покажет сообщение автоматически
         # Форма сохраняет и основные поля, и настройки в своем методе save()
         return super().form_valid(form)

# --- Представления для смены пароля (если нужны кастомные шаблоны) ---
# Используем встроенные LoginRequiredMixin для них
class UserPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
     template_name = 'users/password_change_form.html' # Ваш кастомный шаблон
     success_url = reverse_lazy('user_profiles:password_change_done')
     success_message = _("Ваш пароль был успешно изменен.")

     def form_valid(self, form):
         messages.success(self.request, self.success_message)
         return super().form_valid(form)

     def get_context_data(self, **kwargs):
         context = super().get_context_data(**kwargs)
         context['page_title'] = _("Смена пароля")
         return context

class UserPasswordChangeDoneView(LoginRequiredMixin, PasswordChangeDoneView):
      template_name = 'users/password_change_done.html' # Ваш кастомный шаблон

      def get_context_data(self, **kwargs):
         context = super().get_context_data(**kwargs)
         context['page_title'] = _("Пароль изменен")
         return context

# ==============================================================================
# API ViewSets (без изменений)
# ==============================================================================
class TeamViewSet(viewsets.ModelViewSet):
    queryset = Team.objects.all()
    serializer_class = TeamSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().select_related('department').prefetch_related('teams', 'groups')
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAdminUser]

# ==============================================================================
# Authentication (без изменений)
# ==============================================================================
@csrf_protect
@vary_on_cookie
@never_cache
def base(request):
    if request.user.is_authenticated:
        redirect_url = request.GET.get('next', settings.LOGIN_REDIRECT_URL)
        return redirect(redirect_url)

    next_page = request.GET.get('next', '/')
    error_message_for_template = "" # Инициализируем пустой строкой
    success_message_for_template = "" # Инициализируем пустой строкой

    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            # ... (логика успешного входа и редиректа) ...
            user = form.get_user(); auth_login(request, user)
            redirect_url = request.POST.get('next', settings.LOGIN_REDIRECT_URL)
            return redirect(redirect_url)
        else:
            error_message_for_template = _('Неверное имя пользователя или пароль.')
            # Передаем пустую строку для success_message
            context = {'form': form, 'next': request.POST.get('next', next_page), 'error_message': error_message_for_template, 'success_message': success_message_for_template}
            return render(request, 'users/login.html', context)
    else: # GET Request
        form = LoginForm(request)
        # Проверяем параметр успешного выхода
        if request.GET.get('logged_out') == '1':
            success_message_for_template = _('Вы успешно вышли из системы.')

    # Передаем error_message и success_message в контекст
    context = {'form': form, 'next': next_page, 'error_message': error_message_for_template, 'success_message': success_message_for_template}
    return render(request, 'users/login.html', context)

# Обновляем logout, чтобы он передавал параметр для Toastify
@csrf_protect
@vary_on_cookie
@never_cache
def user_logout(request):
    auth_logout(request)
    # messages.success(request, _('Вы успешно вышли из системы.')) # Убираем Django message
    # Редирект на страницу входа с параметром для Toastify
    logout_url = reverse('user_profiles:base')
    return redirect(f"{logout_url}?logged_out=1")

@csrf_protect
@vary_on_cookie
@never_cache
def user_login(request):
    return redirect('user_profiles:base')

# ==============================================================================
# Users (Используем CBV - Class-Based Views)
# ==============================================================================

class UserListView(LoginRequiredMixin, ListView):
    """Отображает список активных пользователей."""
    model = User
    template_name = "users/user_list.html" # Укажите правильный путь
    context_object_name = "users"
    paginate_by = 20 # Добавляем пагинацию

    def get_queryset(self):
        # Показываем только активных, оптимизируем запрос
        return User.objects.filter(is_active=True).select_related('department').prefetch_related('groups', 'teams').order_by('last_name', 'first_name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Пользователи")
        return context

class UserCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    """Страница создания нового пользователя."""
    model = User
    form_class = UserCreateForm # Используем нашу форму создания
    template_name = "users/user_form.html" # Шаблон формы
    success_url = reverse_lazy("user_profiles:user_list") # Куда перейти после успеха
    success_message = _("Пользователь '%(username)s' успешно создан!")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Создать пользователя")
        context['form_action_text'] = _("Создать")
        return context

    def form_valid(self, form):
        # WebSocket уведомление перед вызовом super().form_valid(), т.к. он делает редирект
        user = form.save(commit=False) # Пока не сохраняем, чтобы получить объект
        response = super().form_valid(form) # Теперь сохраняем и получаем редирект
        logger.info(f"User '{self.object.username}' created by '{self.request.user.username}'.")
        try:
            async_to_sync(channel_layer.group_send)(
                "users_list",
                {"type": "user_update", "message": {"action": "create", "id": self.object.id, "username": self.object.username}}
            )
        except Exception as e:
            logger.error(f"Failed to send user creation WebSocket notification: {e}")
        # Сообщение об успехе добавится через SuccessMessageMixin
        return response

class UserUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    """Страница редактирования пользователя."""
    model = User
    form_class = UserUpdateForm # Используем форму обновления
    template_name = "users/user_form.html"
    success_url = reverse_lazy("user_profiles:user_list")
    success_message = _("Данные пользователя '%(username)s' обновлены.")
    # context_object_name = "user_to_edit" # Можно задать имя объекта в контексте

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Редактировать пользователя: %s") % self.object.display_name
        context['form_action_text'] = _("Сохранить")
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        logger.info(f"User '{self.object.username}' updated by '{self.request.user.username}'.")
        # Добавить WebSocket уведомление, если нужно
        return response

class UserDeleteView(LoginRequiredMixin, SuccessMessageMixin, DeleteView):
    """Страница подтверждения удаления пользователя."""
    model = User
    template_name = "users/user_confirm_delete.html" # Шаблон подтверждения
    success_url = reverse_lazy("user_profiles:user_list")
    success_message = _("Пользователь удален!")
    # context_object_name = "user_to_delete"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Удалить пользователя: %s") % self.object.display_name
        return context

    def form_valid(self, form):
        # Проверка на самоудаление
        if self.request.user == self.object:
             messages.error(self.request, _("Вы не можете удалить свой собственный аккаунт."))
             return redirect(self.success_url)

        user_display_name = self.object.display_name
        user_id = self.object.id
        logger.info(f"User '{user_display_name}' (ID: {user_id}) deleted by '{self.request.user.username}'.")

        # SuccessMessageMixin покажет сообщение перед редиректом
        response = super().form_valid(form)

        # WebSocket уведомление
        try:
            async_to_sync(channel_layer.group_send)(
                "users_list",
                {"type": "user_update", "message": {"action": "delete", "id": user_id}}
            )
        except Exception as e:
            logger.error(f"Failed to send user deletion WebSocket notification: {e}")

        return response

# --- УДАЛЯЕМ ПРЕДСТАВЛЕНИЯ ДЛЯ МОДАЛЬНЫХ ОКОН ---
# modal_create_user, modal_update_user, modal_delete_user

# --- УДАЛЯЕМ ФУНКЦИОНАЛЬНЫЕ ПРЕДСТАВЛЕНИЯ, т.к. используем CBV ---
# create_user, update_user, delete_user


# ==============================================================================
# Teams (Используем CBV - Class-Based Views)
# ==============================================================================

class TeamListView(LoginRequiredMixin, ListView):
    """Отображает список команд."""
    model = Team
    template_name = "users/team_list.html" # Укажите правильный путь
    context_object_name = "teams"
    paginate_by = 20

    def get_queryset(self):
        return Team.objects.select_related('team_leader', 'department').prefetch_related('members').order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Команды")
        return context

class TeamCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    """Страница создания новой команды."""
    model = Team
    form_class = TeamForm
    template_name = "users/team_form.html" # Шаблон формы
    success_url = reverse_lazy("user_profiles:team_list")
    success_message = _("Команда '%(name)s' успешно создана!")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Создать команду")
        context['form_action_text'] = _("Создать")
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        logger.info(f"Team '{self.object.name}' created by '{self.request.user.username}'.")
        try:
            async_to_sync(channel_layer.group_send)(
                "teams_list",
                {"type": "team_update", "message": {"action": "create", "id": self.object.id, "name": self.object.name}}
            )
        except Exception as e:
            logger.error(f"Failed to send team creation WebSocket notification: {e}")
        return response

class TeamUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    """Страница редактирования команды."""
    model = Team
    form_class = TeamForm
    template_name = "users/team_form.html"
    success_url = reverse_lazy("user_profiles:team_list")
    success_message = _("Данные команды '%(name)s' обновлены.")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Редактировать команду: %s") % self.object.name
        context['form_action_text'] = _("Сохранить")
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        logger.info(f"Team '{self.object.name}' updated by '{self.request.user.username}'.")
        # Добавить WebSocket уведомление об обновлении, если нужно
        return response

class TeamDeleteView(LoginRequiredMixin, SuccessMessageMixin, DeleteView):
    """Страница подтверждения удаления команды."""
    model = Team
    template_name = "users/team_confirm_delete.html" # Шаблон подтверждения
    success_url = reverse_lazy("user_profiles:team_list")
    success_message = _("Команда удалена!")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Удалить команду: %s") % self.object.name
        return context

    def form_valid(self, form):
        team_name = self.object.name
        team_id = self.object.id
        logger.info(f"Team '{team_name}' (ID: {team_id}) deleted by '{self.request.user.username}'.")
        response = super().form_valid(form)
        try:
            async_to_sync(channel_layer.group_send)(
                "teams_list",
                {"type": "team_update", "message": {"action": "delete", "id": team_id}}
            )
        except Exception as e:
            logger.error(f"Failed to send team deletion WebSocket notification: {e}")
        return response