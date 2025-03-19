from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_protect
from .models import TaskUserRole, Team, User, Role
from rest_framework import viewsets, permissions, parsers, status
from .serializers import TeamSerializer, RoleSerializer, UserSerializer
from django.contrib.auth.decorators import login_required
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from tasks.forms import RoleForm, UserCreateForm, TeamForm


channel_layer = get_channel_layer()

# ------------------------ API ViewSets ------------------------

class TeamViewSet(viewsets.ModelViewSet):
    queryset = Team.objects.all()
    serializer_class = TeamSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

class RoleViewSet(viewsets.ModelViewSet):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    permission_classes = [permissions.IsAdminUser]

class UserViewSet(viewsets.ModelViewSet):
    """Manage users."""
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAdminUser]

# ------------------------ Authentication ------------------------

@csrf_protect
def base(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            auth_login(request, user)
            messages.success(request, _('Successfully logged in!'))
            return redirect('user_profiles:base')
        else:
            messages.error(request, _('Invalid credentials. Please try again!'))

    return render(request, 'base.html')


def user_login(request):
    return redirect('user_profiles:base')


def user_logout(request):
    auth_logout(request)
    messages.success(request, _('Successfully logged out!'))
    return redirect('user_profiles:base')


# ------------------------ Roles ------------------------

@login_required
def role_list(request):
    roles = Role.objects.all()
    return render(request, "users/role_list.html", {"roles": roles})

@login_required
def role_create(request):
    if request.method == "POST":
        form = RoleForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Роль успешно создана!")
            return redirect("role_list")
    else:
        form = RoleForm()
    return render(request, "modals/role_form.html", {"form": form})

@login_required
def role_delete(request, pk):
    role = get_object_or_404(Role, pk=pk)
    role.delete()
    messages.success(request, "Роль удалена!")
    return redirect("role_list")


# ------------------------ Users ------------------------

@login_required
def user_list(request):
    users = User.objects.all()
    return render(request, "users/user_list.html", {"users": users})

def modal_create_user(request):
    form = UserCreateForm()
    return render(request, "modals/user_form.html", {"form": form})

def modal_update_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    form = UserCreateForm(instance=user)
    return render(request, "modals/user_form.html", {"form": form})

def modal_delete_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    return render(request, "modals/user_delete.html", {"user": user})

def create_user(request):
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            async_to_sync(channel_layer.group_send)(
                "users",
                {"type": "updateUsers", "message": {"action": "create", "id": user.id, "username": user.username}}
            )
            messages.success(request, "Пользователь успешно создан!")
            return HttpResponse('<script>location.reload()</script>')
    return HttpResponse(status=400)

def delete_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    user.delete()
    async_to_sync(channel_layer.group_send)(
        "users",
        {"type": "updateUsers", "message": {"action": "delete", "id": pk}}
    )
    messages.success(request, "Пользователь удален!")
    return HttpResponse('<script>location.reload()</script>')


# ------------------------ Teams ------------------------

@login_required
def team_list(request):
    teams = Team.objects.all()
    return render(request, "users/team_list.html", {"teams": teams})

@login_required
def modal_create_team(request):
    form = TeamForm()
    return render(request, "modals/team_form.html", {"form": form})

@login_required
def modal_update_team(request, pk):
    team = get_object_or_404(Team, pk=pk)
    form = TeamForm(instance=team)
    return render(request, "modals/team_form.html", {"form": form})

@login_required
def modal_delete_team(request, pk):
    team = get_object_or_404(Team, pk=pk)
    return render(request, "modals/team_delete.html", {"team": team})

@login_required
def create_team(request):
    if request.method == "POST":
        form = TeamForm(request.POST)
        if form.is_valid():
            team = form.save()
            async_to_sync(channel_layer.group_send)(
                "teams",
                {"type": "updateTeams", "message": {"action": "create", "id": team.id, "name": team.name}}
            )
            messages.success(request, "Команда успешно создана!")
            return HttpResponse('<script>location.reload()</script>')
    return HttpResponse(status=400)

@login_required
def delete_team(request, pk):
    team = get_object_or_404(Team, pk=pk)
    team.delete()
    async_to_sync(channel_layer.group_send)(
        "teams",
        {"type": "updateTeams", "message": {"action": "delete", "id": pk}}
    )
    messages.success(request, "Команда удалена!")
    return HttpResponse('<script>location.reload()</script>')
