# user_profiles/views.py
import logging
from django.conf import settings
from django.urls import reverse_lazy
from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin # Added UserPassesTestMixin
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.cache import never_cache
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView # Added DetailView
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib.auth.views import PasswordChangeView as AuthPasswordChangeView, PasswordChangeDoneView as AuthPasswordChangeDoneView
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Count, Prefetch
from django_filters.rest_framework import DjangoFilterBackend

from rest_framework import viewsets, permissions, filters
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth.forms import AuthenticationForm
# from .forms import LoginForm # ИЛИ, если у вас своя форма LoginForm
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.cache import never_cache
# --- Необходим для безопасной проверки URL перенаправления ---
from django.utils.http import url_has_allowed_host_and_scheme

from .models import User, Team, Department, JobTitle # TaskUserRole removed
from .serializers import TeamSerializer, UserSerializer, DepartmentSerializer, JobTitleSerializer
from .forms import (
    TeamForm, UserCreateForm, UserUpdateForm, UserProfileEditForm, LoginForm,
    UserPasswordChangeForm, DepartmentForm, JobTitleForm # Added DepartmentForm, JobTitleForm
)
from tasks.models import Task, TaskAssignment # For task history and permissions

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer() # Initialize once

# --- Mixins ---
class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Mixin to ensure user is staff or superuser."""
    raise_exception = True # Raise PermissionDenied if test fails
    permission_denied_message = _("У вас нет прав для доступа к этой странице.")

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser

# --- Authentication Views ---
@csrf_protect
@never_cache
def base_login_view(request):
    # --- Шаг 1: Получаем и ВАЛИДИРУЕМ URL для перенаправления ('next') ---
    # Получаем 'next' из GET параметра. Если его нет, используем LOGIN_REDIRECT_URL из настроек,
    # или '/' как абсолютный минимум по умолчанию.
    next_url = request.GET.get('next', settings.LOGIN_REDIRECT_URL or '/')

    # ПРОВЕРКА БЕЗОПАСНОСТИ: Убеждаемся, что URL безопасен для перенаправления.
    # Это предотвращает "Open Redirect" уязвимости.
    # Разрешаем перенаправление только на текущий хост (домен).
    if not url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()}, # Множество разрешенных хостов (только текущий)
        require_https=request.is_secure(), # Требовать HTTPS, если текущий запрос был по HTTPS
    ):
        # Если URL небезопасен (например, ведет на другой сайт), сбрасываем его
        # на безопасное значение по умолчанию.
        logger.warning(f"Blocked unsafe redirect attempt to '{next_url}' during login.")
        next_url = settings.LOGIN_REDIRECT_URL or '/'
    # --- Конец обработки 'next' ---

    # Если пользователь УЖЕ аутентифицирован, перенаправляем его сразу
    # используя безопасный, валидированный next_url
    if request.user.is_authenticated:
        return redirect(next_url)

    # Используем стандартную форму входа Django или вашу кастомную (LoginForm)
    # Замените AuthenticationForm на LoginForm, если используете свою
    login_form_class = AuthenticationForm
    # login_form_class = LoginForm

    if request.method == 'POST':
        form = login_form_class(request, data=request.POST)
        if form.is_valid():
            # Получаем пользователя из валидной формы
            user = form.get_user()
            # Аутентифицируем пользователя в сессии
            auth_login(request, user)
            messages.success(request, _("Вы успешно вошли в систему."))

            # --- Перенаправление после успешного входа ---
            # Получаем 'next' ИЗ ТЕЛА POST запроса (из hidden input)
            # и СНОВА ВАЛИДИРУЕМ его на безопасность, т.к. значение могло быть изменено
            post_next_url = request.POST.get('next', settings.LOGIN_REDIRECT_URL or '/')
            if not url_has_allowed_host_and_scheme(
                url=post_next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                logger.warning(f"Blocked unsafe redirect attempt from POST 'next' field: '{post_next_url}'")
                post_next_url = settings.LOGIN_REDIRECT_URL or '/' # Сброс на безопасный URL

            return redirect(post_next_url) # Перенаправляем на безопасный URL
        else:
            # Форма невалидна, показываем ошибки
            # Сообщения об ошибках полей обычно отображаются рядом с полями в шаблоне.
            # Можно добавить общее сообщение об ошибке.
            messages.error(request, _('Пожалуйста, исправьте ошибки ниже.'))
            # Можно также перебирать form.non_field_errors() если нужно
            # for error in form.non_field_errors():
            #     messages.error(request, error)

    else: # GET запрос
        form = login_form_class(request)
        # Показываем сообщение о выходе только при GET запросе и если не было ошибок POST
        if request.GET.get('logged_out') == '1':
            messages.info(request, _('Вы успешно вышли из системы.'))

    # Передаем форму и БЕЗОПАСНЫЙ next_url (из GET-валидации) в контекст шаблона
    context = {
        'form': form,
        'next': next_url, # Используем валидированный URL из GET-запроса
        'page_title': _("Вход")
    }
    return render(request, 'users/login.html', context)


@never_cache
def user_logout_view(request): # Renamed
    auth_logout(request)
    # messages.info(request, _('Вы успешно вышли из системы.')) # Message now shown on login page
    logout_url = reverse_lazy('user_profiles:base_login') # Use the renamed view
    return redirect(f"{logout_url}?logged_out=1")

def user_login_redirect(request): # Simple redirect if /login/ is accessed directly
    return redirect('user_profiles:base_login')


# --- User Profile & Password Change ---
class UserProfileView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    form_class = UserProfileEditForm
    template_name = 'users/user_profile.html'
    success_url = reverse_lazy('user_profiles:profile_view')
    success_message = _("Профиль успешно обновлен.")

    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context['page_title'] = _("Мой профиль")
        context['profile_user'] = user
        # Task history using TaskAssignment
        user_tasks_qs = Task.objects.filter(
            Q(created_by=user) | Q(assignments__user=user)
        ).select_related('project', 'created_by').prefetch_related(
            Prefetch('assignments', queryset=TaskAssignment.objects.select_related('user'))
        ).distinct().order_by('-updated_at')

        paginator = Paginator(user_tasks_qs, 10)
        page_number = self.request.GET.get('task_page')
        context['task_history_page'] = paginator.get_page(page_number)
        return context

class UserPasswordChangeView(LoginRequiredMixin, SuccessMessageMixin, AuthPasswordChangeView):
     template_name = 'users/password_change_form.html'
     form_class = UserPasswordChangeForm # Use custom form if defined, else Django's
     success_url = reverse_lazy('user_profiles:password_change_done')
     success_message = _("Ваш пароль был успешно изменен.")

     def get_context_data(self, **kwargs):
         context = super().get_context_data(**kwargs)
         context['page_title'] = _("Смена пароля")
         return context

class UserPasswordChangeDoneView(LoginRequiredMixin, AuthPasswordChangeDoneView):
      template_name = 'users/password_change_done.html'
      def get_context_data(self, **kwargs):
         context = super().get_context_data(**kwargs)
         context['page_title'] = _("Пароль изменен")
         return context

# --- User Management (Staff Required) ---
class UserListView(StaffRequiredMixin, ListView):
    model = User
    template_name = "users/user_list.html"
    context_object_name = "object_list" # Consistent with other ListViews
    paginate_by = 15

    def get_queryset(self):
        # Show all users for staff, could filter by is_active if needed
        return User.objects.select_related('department', 'job_title').prefetch_related('groups', 'teams').order_by('last_name', 'first_name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Пользователи")
        return context

class UserCreateView(StaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = User
    form_class = UserCreateForm
    template_name = "users/user_form.html"
    success_url = reverse_lazy("user_profiles:user_list")
    success_message = _("Пользователь '%(username)s' успешно создан.")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Создать пользователя")
        context['form_action_text'] = _("Создать")
        return context

    def form_valid(self, form):
        # User is saved by super().form_valid()
        response = super().form_valid(form)
        logger.info(f"User '{self.object.username}' created by '{self.request.user.username}'.")
        # WebSocket notification for user_list (already in model.save)
        return response

class UserUpdateView(StaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    form_class = UserUpdateForm
    template_name = "users/user_form.html"
    success_url = reverse_lazy("user_profiles:user_list")
    success_message = _("Данные пользователя '%(username)s' обновлены.")
    context_object_name = "object" # Use 'object' for consistency

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Редактировать пользователя: %s") % self.object.display_name
        context['form_action_text'] = _("Сохранить")
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        logger.info(f"User '{self.object.username}' updated by '{self.request.user.username}'.")
        # WebSocket notification for user_list and user_profile (already in model.save)
        return response

class UserDeleteView(StaffRequiredMixin, DeleteView): # No SuccessMessageMixin, handled manually
    model = User
    template_name = "users/user_confirm_delete.html"
    success_url = reverse_lazy("user_profiles:user_list")
    context_object_name = "object"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Удалить пользователя: %s") % self.object.display_name
        return context

    def form_valid(self, form):
        if self.request.user == self.object:
             messages.error(self.request, _("Вы не можете удалить свой собственный аккаунт."))
             return HttpResponseRedirect(self.success_url)

        user_display_name = self.object.display_name # Capture before delete
        logger.info(f"User '{user_display_name}' (ID: {self.object.id}) will be deleted by '{self.request.user.username}'.")
        response = super().form_valid(form) # Calls delete() on object
        messages.success(self.request, _("Пользователь '%(name)s' успешно удален.") % {'name': user_display_name})
        # WebSocket notification for user_list (already in model.delete)
        return response

# --- Team Management (Staff Required) ---
class TeamListView(StaffRequiredMixin, ListView):
    model = Team
    template_name = "users/team_list.html"
    context_object_name = "object_list"
    paginate_by = 15

    def get_queryset(self):
        return Team.objects.select_related('team_leader', 'department').prefetch_related('members').annotate(num_members=Count('members')).order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Команды")
        return context

class TeamDetailView(StaffRequiredMixin, DetailView): # Optional Detail View
    model = Team
    template_name = "users/team_detail.html" # Create this template
    context_object_name = "team"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Команда: %s") % self.object.name
        # Add related data like team tasks if Team model gets a relation to Task or Project
        return context

class TeamCreateView(StaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = Team
    form_class = TeamForm
    template_name = "users/team_form.html"
    success_url = reverse_lazy("user_profiles:team_list")
    success_message = _("Команда '%(name)s' успешно создана.")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Создать команду")
        context['form_action_text'] = _("Создать")
        return context

class TeamUpdateView(StaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Team
    form_class = TeamForm
    template_name = "users/team_form.html"
    success_url = reverse_lazy("user_profiles:team_list")
    success_message = _("Данные команды '%(name)s' обновлены.")
    context_object_name = "object"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Редактировать команду: %s") % self.object.name
        context['form_action_text'] = _("Сохранить")
        return context

class TeamDeleteView(StaffRequiredMixin, DeleteView):
    model = Team
    template_name = "users/team_confirm_delete.html"
    success_url = reverse_lazy("user_profiles:team_list")
    context_object_name = "object"

    def form_valid(self, form):
        team_name = self.object.name
        messages.success(self.request, _("Команда '%(name)s' успешно удалена.") % {'name': team_name})
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Удалить команду: %s") % self.object.name
        return context


# --- Department Management (Staff Required) ---
class DepartmentListView(StaffRequiredMixin, ListView):
    model = Department
    template_name = "users/department_list.html" # Create this template
    context_object_name = "object_list"
    paginate_by = 15

    def get_queryset(self):
        return Department.objects.select_related('parent', 'head').annotate(num_employees=Count('employees'), num_teams=Count('teams')).order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Отделы")
        return context

class DepartmentDetailView(StaffRequiredMixin, DetailView):
    model = Department
    template_name = "users/department_detail.html" # Create this template
    context_object_name = "department"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Отдел: %s") % self.object.name
        context['employees'] = self.object.employees.all()
        context['teams_in_department'] = self.object.teams.all()
        context['child_departments'] = self.object.children.all()
        return context

class DepartmentCreateView(StaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = Department
    form_class = DepartmentForm
    template_name = "users/department_form.html" # Create this template
    success_url = reverse_lazy("user_profiles:department_list")
    success_message = _("Отдел '%(name)s' успешно создан.")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Создать отдел")
        context['form_action_text'] = _("Создать")
        return context

class DepartmentUpdateView(StaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Department
    form_class = DepartmentForm
    template_name = "users/department_form.html"
    success_url = reverse_lazy("user_profiles:department_list")
    success_message = _("Данные отдела '%(name)s' обновлены.")
    context_object_name = "object"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Редактировать отдел: %s") % self.object.name
        context['form_action_text'] = _("Сохранить")
        return context

class DepartmentDeleteView(StaffRequiredMixin, DeleteView):
    model = Department
    template_name = "users/department_confirm_delete.html" # Create this template
    success_url = reverse_lazy("user_profiles:department_list")
    context_object_name = "object"

    def form_valid(self, form):
        department_name = self.object.name
        messages.success(self.request, _("Отдел '%(name)s' успешно удален.") % {'name': department_name})
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Удалить отдел: %s") % self.object.name
        return context

class JobTitleViewSet(viewsets.ModelViewSet): # ModelViewSet для CRUD
    queryset = JobTitle.objects.annotate(user_count=Count('users')).order_by('name')
    serializer_class = JobTitleSerializer
    permission_classes = [permissions.IsAuthenticated] # Или IsAdminUser для CUD операций
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'user_count']
    ordering = ['name']

    # Если нужны более строгие права доступа для создания/изменения/удаления:
    # def get_permissions(self):
    #     if self.action in ['create', 'update', 'partial_update', 'destroy']:
    #         return [permissions.IsAdminUser()]
    #     return [permissions.IsAuthenticated()]

# --- JobTitle Management (Staff Required) ---
class JobTitleListView(StaffRequiredMixin, ListView):
    model = JobTitle
    template_name = "users/jobtitle_list.html" # Create this template
    context_object_name = "object_list"
    paginate_by = 20
    def get_queryset(self): return JobTitle.objects.annotate(num_users=Count('users')).order_by('name')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); context['page_title'] = _("Должности"); return context

class JobTitleCreateView(StaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = JobTitle; form_class = JobTitleForm; template_name = "users/jobtitle_form.html" # Create
    success_url = reverse_lazy("user_profiles:jobtitle_list"); success_message = _("Должность '%(name)s' создана.")
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); context['page_title'] = _("Создать должность"); context['form_action_text'] = _("Создать"); return context

class JobTitleUpdateView(StaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = JobTitle; form_class = JobTitleForm; template_name = "users/jobtitle_form.html"
    success_url = reverse_lazy("user_profiles:jobtitle_list"); success_message = _("Должность '%(name)s' обновлена."); context_object_name = "object"
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); context['page_title'] = _("Редактировать должность: %s") % self.object.name; context['form_action_text'] = _("Сохранить"); return context

class JobTitleDeleteView(StaffRequiredMixin, DeleteView):
    model = JobTitle; template_name = "users/jobtitle_confirm_delete.html"; success_url = reverse_lazy("user_profiles:jobtitle_list"); context_object_name = "object" # Create
    def form_valid(self, form): name = self.object.name; messages.success(self.request, _("Должность '%(name)s' удалена.") % {'name': name}); return super().form_valid(form)
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); context['page_title'] = _("Удалить должность: %s") % self.object.name; return context

# --- API ViewSets ---
class UserViewSet(viewsets.ReadOnlyModelViewSet): # ReadOnly for now, expand if needed
    queryset = User.objects.filter(is_active=True).select_related('department', 'job_title').prefetch_related('teams', 'groups')
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated] # Or more granular permissions
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['department', 'job_title', 'groups', 'teams']
    search_fields = ['username', 'first_name', 'last_name', 'email', 'department__name', 'job_title__name']
    ordering_fields = ['username', 'last_name', 'email', 'department__name', 'job_title__name']

class TeamViewSet(viewsets.ModelViewSet):
    queryset = Team.objects.select_related('team_leader', 'department').prefetch_related('members')
    serializer_class = TeamSerializer
    permission_classes = [permissions.IsAuthenticated] # Staff or specific group for CUD

class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.select_related('parent', 'head')
    serializer_class = DepartmentSerializer
    permission_classes = [permissions.IsAuthenticated] # Staff or specific group for CUD