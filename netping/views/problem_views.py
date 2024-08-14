from django.shortcuts import render, get_object_or_404
from ..models import NetPingDevice, Problems, Comments

def comments_list(request, pk):
    problem = get_object_or_404(Problems, pk=pk)
    comment = Comments.objects.filter(problem=problem)
    return render(request, 'comments.html', {'problem': problem, 'comment': comment})

def problems_list(request, pk):
    device = get_object_or_404(NetPingDevice, pk=pk)
    problems = Problems.objects.filter(sensor__device=device)
    return render(request, 'problems.html', {'problems': problems})

def problem_detail(request, pk):
    problem = get_object_or_404(Problems, pk=pk)
    return render(request, 'problem_detail.html', {'problem': problem})
