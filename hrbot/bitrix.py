from fast_bitrix24 import Bitrix
from django.conf import settings

bx = Bitrix(settings.BITRIX24_WEBHOOK)

def send_evaluation_to_bitrix(evaluation):
    bx.call('crm.lead.add', {
        'fields': {
            'TITLE': f'Оценка сотрудника {evaluation.employee_name}',
            'NAME': evaluation.employee_name,
            'COMMENTS': f'Оценщик: {evaluation.evaluator.user.username}, Роль: {evaluation.role.name}\nОтветы: {evaluation.responses}',
            'SOURCE_ID': 'WEB',
        }
    })
    print(f"Evaluation sent to Bitrix: {evaluation.employee_name}, Evaluator: {evaluation.evaluator.user.username}")
