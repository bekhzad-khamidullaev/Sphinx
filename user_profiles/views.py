from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_protect


@csrf_protect
def base(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            auth_login(request, user)
            messages.success(request, _('Successfully logged in!'))
            return redirect('base')
        else:
            messages.error(request, _('Invalid credentials. Please try again!'))

    return render(request, 'base.html')


def user_login(request):
    return redirect('base')


def user_logout(request):
    auth_logout(request)
    messages.success(request, _('Successfully logged out!'))
    return redirect('base')
