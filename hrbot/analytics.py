import pandas as pd
from django.http import HttpResponse
from .models import Evaluation

def export_excel(request):
    evaluations = Evaluation.objects.select_related('evaluator', 'role')
    data = [{
        'Дата': ev.timestamp.strftime('%Y-%m-%d %H:%M'),
        'Сотрудник': ev.employee_name,
        'Роль': ev.role.name,
        'Оценщик': ev.evaluator.user.username,
        **ev.responses
    } for ev in evaluations]

    df = pd.DataFrame(data)
    response = HttpResponse(content_type='application/vnd.ms-excel')
    response['Content-Disposition'] = 'attachment; filename="evaluations.xlsx"'
    df.to_excel(response, index=False)
    return response
