# user_profiles/views.py
import logging
from django.conf import settings
from django.urls import reverse_lazy
from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.cache import never_cache
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib.auth.views import PasswordChangeView as AuthPasswordChangeView, PasswordChangeDoneView as AuthPasswordChangeDoneView
from django.core.paginator import Paginator
from django.db.models import Q, Count, Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions as drf_permissions
from django_filters import rest_framework as filters

from rest_framework import viewsets, permissions, filters as drf_filters
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth.forms import AuthenticationForm
from django.utils.http import url_has_allowed_host_and_scheme
from django.core.exceptions import PermissionDenied


from .models import User, Team, Department, JobTitle
from .serializers import TeamSerializer, UserSerializer, DepartmentSerializer, JobTitleSerializer
from .forms import (
    TeamForm, UserCreateForm, UserUpdateForm, UserProfileEditForm, LoginForm,
    UserPasswordChangeForm, DepartmentForm, JobTitleForm
)
from tasks.models import Task, TaskAssignment

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()

class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    raise_exception = True
    permission_denied_message = _("У вас нет прав для доступа к этой странице.")

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser

@csrf_protect
@never_cache
def base_login_view(request):
    next_url = request.GET.get('next', settings.LOGIN_REDIRECT_URL or '/')
    if not url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        logger.warning(f"Blocked unsafe redirect attempt to '{next_url}' during login.")
        next_url = settings.LOGIN_REDIRECT_URL or '/'

    if request.user.is_authenticated:
        return redirect(next_url)

    login_form_class = LoginForm

    if request.method == 'POST':
        form = login_form_class(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            messages.success(request, _("Вы успешно вошли в систему."))

            post_next_url = request.POST.get('next', settings.LOGIN_REDIRECT_URL or '/')
            if not url_has_allowed_host_and_scheme(
                url=post_next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                logger.warning(f"Blocked unsafe redirect attempt from POST 'next' field: '{post_next_url}'")
                post_next_url = settings.LOGIN_REDIRECT_URL or '/'
            return redirect(post_next_url)
        else:
            messages.error(request, _('Пожалуйста, исправьте ошибки ниже.'))
    else:
        form = login_form_class(request)
        if request.GET.get('logged_out') == '1':
            messages.info(request, _('Вы успешно вышли из системы.'))

    context = {
        'form': form,
        'next': next_url,
        'page_title': _("Вход")
    }
    return render(request, 'users/login.html', context)


@never_cache
def user_logout_view(request):
    auth_logout(request)
    logout_url = reverse_lazy('user_profiles:base_login')
    return redirect(f"{logout_url}?logged_out=1")

def user_login_redirect(request):
    return redirect('user_profiles:base_login')


class UserProfileView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    form_class = UserProfileEditForm
    template_name = 'users/user_profile.html'
    success_url = reverse_lazy('user_profiles:profile_view')
    success_message = _("Профиль успешно обновлен.")

    def get_object(self, queryset=None):
        return self.request.user

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context['page_title'] = _("Мой профиль")
        context['profile_user'] = user
        try:
            user_tasks_qs = Task.objects.filter(
                Q(created_by=user) | Q(assignments__user=user)
            ).select_related('project', 'created_by').prefetch_related(
                Prefetch('assignments', queryset=TaskAssignment.objects.select_related('user'))
            ).distinct().order_by('-updated_at')

            paginator = Paginator(user_tasks_qs, 10)
            page_number = self.request.GET.get('task_page')
            context['task_history_page'] = paginator.get_page(page_number)
        except Exception as e:
            logger.warning(f"Could not fetch task history for user {user.id}: {e}")
            context['task_history_page'] = None
        return context

class UserPasswordChangeView(LoginRequiredMixin, SuccessMessageMixin, AuthPasswordChangeView):
     template_name = 'users/password_change_form.html'
     form_class = UserPasswordChangeForm
     success_url = reverse_lazy('user_profiles:password_change_done')
     success_message = _("Ваш пароль был успешно изменен.")

     def form_valid(self, form):
        response = super().form_valid(form)
        from .signals import user_password_changed_signal
        request_info = {
            'ip_address': self.request.META.get('REMOTE_ADDR'),
            'user_agent': self.request.META.get('HTTP_USER_AGENT')
        }
        user_password_changed_signal.send(sender=self.request.user.__class__, user=self.request.user, request_info=request_info, request=self.request, actor=self.request.user)
        return response

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

class UserListView(StaffRequiredMixin, ListView):
    model = User
    template_name = "users/user_list.html"
    context_object_name = "object_list"
    paginate_by = 15

    def get_queryset(self):
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
        logger.info(f"User '{form.cleaned_data.get('username')}' being created by '{self.request.user.username}'.")
        response = super().form_valid(form)
        return response


class UserUpdateView(StaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    form_class = UserUpdateForm
    template_name = "users/user_form.html"
    success_url = reverse_lazy("user_profiles:user_list")
    success_message = _("Данные пользователя '%(username)s' обновлены.")
    context_object_name = "object"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request_user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Редактировать пользователя: %s") % self.object.display_name
        context['form_action_text'] = _("Сохранить")
        return context

    def form_valid(self, form):
        logger.info(f"User '{self.object.username}' being updated by '{self.request.user.username}'.")
        return super().form_valid(form)


class UserDeleteView(StaffRequiredMixin, DeleteView):
    model = User
    template_name = "users/user_confirm_delete.html"
    success_url = reverse_lazy("user_profiles:user_list")
    context_object_name = "object"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Удалить пользователя: %s") % self.object.display_name
        return context

    def form_valid(self, form):
        target_user = self.get_object()
        if self.request.user == target_user:
             messages.error(self.request, _("Вы не можете удалить свой собственный аккаунт."))
             return HttpResponseRedirect(self.success_url)
        
        user_display_name = target_user.display_name
        logger.info(f"User '{user_display_name}' (ID: {target_user.id}) attempt to delete by '{self.request.user.username}'.")
        
        try:
            response = super().form_valid(form)
            messages.success(self.request, _("Пользователь '%(name)s' успешно удален.") % {'name': user_display_name})
            return response
        except PermissionDenied as e:
            messages.error(self.request, str(e))
            return HttpResponseRedirect(reverse_lazy("user_profiles:user_update", kwargs={'pk': target_user.pk}))
        except Exception as e:
            logger.exception(f"Error deleting user '{user_display_name}': {e}")
            messages.error(self.request, _("Произошла ошибка при удалении пользователя."))
            return HttpResponseRedirect(self.success_url)


class TeamListView(StaffRequiredMixin, ListView):
    model = Team
    template_name = "users/team_list.html"
    context_object_name = "object_list"
    paginate_by = 15

    def get_queryset(self):
        return Team.objects.select_related('team_leader', 'department').prefetch_related(
            Prefetch('members', queryset=User.objects.order_by('username'))
        ).annotate(num_members=Count('members')).order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Команды")
        return context

class TeamDetailView(StaffRequiredMixin, DetailView):
    model = Team
    template_name = "users/team_detail.html"
    context_object_name = "team"

    def get_queryset(self):
        return super().get_queryset().select_related('team_leader', 'department').prefetch_related(
            Prefetch('members', queryset=User.objects.order_by('username'))
        )
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Команда: %s") % self.object.name
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
    
    def form_valid(self, form):
        logger.info(f"Team '{form.cleaned_data.get('name')}' created by '{self.request.user.username}'.")
        return super().form_valid(form)


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

    def form_valid(self, form):
        logger.info(f"Team '{self.object.name}' updated by '{self.request.user.username}'.")
        return super().form_valid(form)


class TeamDeleteView(StaffRequiredMixin, DeleteView):
    model = Team
    template_name = "users/team_confirm_delete.html"
    success_url = reverse_lazy("user_profiles:team_list")
    context_object_name = "object"

    def form_valid(self, form):
        team_name = self.object.name
        logger.info(f"Team '{team_name}' deleted by '{self.request.user.username}'.")
        messages.success(self.request, _("Команда '%(name)s' успешно удалена.") % {'name': team_name})
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Удалить команду: %s") % self.object.name
        return context


class DepartmentListView(StaffRequiredMixin, ListView):
    model = Department
    template_name = "users/department_list.html"
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
    template_name = "users/department_detail.html"
    context_object_name = "department"

    def get_queryset(self):
        return super().get_queryset().select_related('parent', 'head').prefetch_related(
            Prefetch('employees', queryset=User.objects.order_by('username')),
            Prefetch('teams', queryset=Team.objects.order_by('name')),
            Prefetch('children', queryset=Department.objects.order_by('name'))
        )
        
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
    template_name = "users/department_form.html"
    success_url = reverse_lazy("user_profiles:department_list")
    success_message = _("Отдел '%(name)s' успешно создан.")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Создать отдел")
        context['form_action_text'] = _("Создать")
        return context

    def form_valid(self, form):
        logger.info(f"Department '{form.cleaned_data.get('name')}' created by '{self.request.user.username}'.")
        return super().form_valid(form)

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

    def form_valid(self, form):
        logger.info(f"Department '{self.object.name}' updated by '{self.request.user.username}'.")
        return super().form_valid(form)

class DepartmentDeleteView(StaffRequiredMixin, DeleteView):
    model = Department
    template_name = "users/department_confirm_delete.html"
    success_url = reverse_lazy("user_profiles:department_list")
    context_object_name = "object"

    def form_valid(self, form):
        department_name = self.object.name
        logger.info(f"Department '{department_name}' deleted by '{self.request.user.username}'.")
        messages.success(self.request, _("Отдел '%(name)s' успешно удален.") % {'name': department_name})
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Удалить отдел: %s") % self.object.name
        return context

class JobTitleViewSet(viewsets.ModelViewSet):
    queryset = JobTitle.objects.annotate(user_count=Count('users')).order_by('name')
    serializer_class = JobTitleSerializer
    filter_backends = [DjangoFilterBackend, drf_filters.SearchFilter, drf_filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'user_count']
    ordering = ['name']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [drf_permissions.IsAdminUser()]
        return [drf_permissions.IsAuthenticated()]

class JobTitleListView(StaffRequiredMixin, ListView):
    model = JobTitle
    template_name = "users/jobtitle_list.html"
    context_object_name = "object_list"
    paginate_by = 20
    def get_queryset(self): return JobTitle.objects.annotate(num_users=Count('users')).order_by('name')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); context['page_title'] = _("Должности"); return context

class JobTitleCreateView(StaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = JobTitle; form_class = JobTitleForm; template_name = "users/jobtitle_form.html"
    success_url = reverse_lazy("user_profiles:jobtitle_list"); success_message = _("Должность '%(name)s' создана.")
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); context['page_title'] = _("Создать должность"); context['form_action_text'] = _("Создать"); return context
    def form_valid(self, form):
        logger.info(f"JobTitle '{form.cleaned_data.get('name')}' created by '{self.request.user.username}'.")
        return super().form_valid(form)

class JobTitleUpdateView(StaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = JobTitle; form_class = JobTitleForm; template_name = "users/jobtitle_form.html"
    success_url = reverse_lazy("user_profiles:jobtitle_list"); success_message = _("Должность '%(name)s' обновлена."); context_object_name = "object"
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); context['page_title'] = _("Редактировать должность: %s") % self.object.name; context['form_action_text'] = _("Сохранить"); return context
    def form_valid(self, form):
        logger.info(f"JobTitle '{self.object.name}' updated by '{self.request.user.username}'.")
        return super().form_valid(form)

class JobTitleDeleteView(StaffRequiredMixin, DeleteView):
    model = JobTitle; template_name = "users/jobtitle_confirm_delete.html"; success_url = reverse_lazy("user_profiles:jobtitle_list"); context_object_name = "object"
    def form_valid(self, form):
        name = self.object.name
        logger.info(f"JobTitle '{name}' deleted by '{self.request.user.username}'.")
        messages.success(self.request, _("Должность '%(name)s' удалена.") % {'name': name})
        return super().form_valid(form)
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); context['page_title'] = _("Удалить должность: %s") % self.object.name; return context

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().select_related('department', 'job_title').prefetch_related('teams', 'groups')
    serializer_class = UserSerializer
    filter_backends = [DjangoFilterBackend, drf_filters.SearchFilter, drf_filters.OrderingFilter]
    filterset_fields = ['department', 'job_title', 'groups', 'teams', 'is_active', 'is_staff']
    search_fields = ['username', 'first_name', 'last_name', 'email', 'department__name', 'job_title__name']
    ordering_fields = ['username', 'last_name', 'email', 'department__name', 'job_title__name']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [drf_permissions.IsAdminUser()]
        elif self.action == 'list':
             return [drf_permissions.IsAuthenticated()]
        elif self.action == 'retrieve':
            return [drf_permissions.IsAuthenticated()]
        return [drf_permissions.IsAdminUser()]

    def get_object(self):
        obj = super().get_object()
        if self.action == 'retrieve' and not self.request.user.is_staff and obj != self.request.user:
            raise PermissionDenied(_("У вас нет прав на просмотр этого профиля пользователя."))
        return obj
    
    def perform_create(self, serializer):
        user = serializer.save()

    def perform_update(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        if instance == self.request.user:
            raise PermissionDenied(_("Вы не можете удалить свой собственный аккаунт через API."))
        instance.delete()


class TeamViewSet(viewsets.ModelViewSet):
    queryset = Team.objects.select_related('team_leader', 'department').prefetch_related(
        Prefetch('members', queryset=User.objects.order_by('username'))
    )
    serializer_class = TeamSerializer
    filter_backends = [DjangoFilterBackend, drf_filters.SearchFilter, drf_filters.OrderingFilter]
    filterset_fields = ['department', 'team_leader']
    search_fields = ['name', 'description', 'team_leader__username', 'department__name', 'members__username']
    ordering_fields = ['name', 'department__name']
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            if self.request.user.is_staff:
                return [drf_permissions.IsAdminUser()]
            if self.action != 'create' and self.get_object().team_leader == self.request.user:
                 return [drf_permissions.IsAuthenticated()]
            return [drf_permissions.IsAdminUser()]
        return [drf_permissions.IsAuthenticated()]

class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.select_related('parent', 'head').prefetch_related('children', 'employees', 'teams')
    serializer_class = DepartmentSerializer
    filter_backends = [DjangoFilterBackend, drf_filters.SearchFilter, drf_filters.OrderingFilter]
    filterset_fields = ['parent', 'head']
    search_fields = ['name', 'description', 'head__username', 'parent__name']
    ordering_fields = ['name', 'parent__name']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            if self.request.user.is_staff:
                return [drf_permissions.IsAdminUser()]
            if self.action != 'create' and self.get_object().head == self.request.user:
                 return [drf_permissions.IsAuthenticated()]
            return [drf_permissions.IsAdminUser()]
        return [drf_permissions.IsAuthenticated()]