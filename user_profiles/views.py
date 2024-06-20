from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib import messages


def base(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)

        if user is not None:
            auth_login(request, user)
            messages.success(request, 'Successfully logged in!')
            return redirect('base')
        else:
            messages.error(request, 'Invalid credentials. Please try again!')

    else:
        return render(request, 'base.html')



def user_login(request):
    return redirect('base')

def user_logout(request):
    auth_logout(request)
    messages.success(request, 'Successfully logged out!')
    return redirect('base')