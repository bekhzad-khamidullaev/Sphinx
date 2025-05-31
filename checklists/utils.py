# checklists/utils.py
from .models import Checklist, ChecklistResult, AnswerType, ChecklistItemStatus
import logging

logger = logging.getLogger(__name__)

def calculate_checklist_score(checklist_run: Checklist) -> float | None:
    results = checklist_run.results.filter(
        status__in=[ChecklistItemStatus.OK, ChecklistItemStatus.NOT_OK, ChecklistItemStatus.NOT_APPLICABLE]
    ).select_related('template_item')

    valid_scores = []
    item_count_for_average = 0
    # not_ok_count = 0 # Можно раскомментировать, если понадобится

    for result in results:
        item = result.template_item
        score_value = None

        if result.status == ChecklistItemStatus.NOT_APPLICABLE or result.status == ChecklistItemStatus.PENDING:
            continue

        can_contribute_to_average = False

        if item.answer_type in [AnswerType.SCALE_1_4, AnswerType.SCALE_1_5, AnswerType.NUMBER]:
            if result.numeric_value is not None:
                score_value = result.numeric_value
                can_contribute_to_average = True
        elif item.answer_type == AnswerType.YES_NO:
             if result.value == 'yes': score_value = 1.0
             elif result.value == 'no': score_value = 0.0
             if result.value in ['yes', 'no']: can_contribute_to_average = True
        elif item.answer_type == AnswerType.YES_NO_MEH:
             if result.value == 'yes': score_value = 1.0
             elif result.value == 'yes_no_meh': score_value = 0.5
             elif result.value == 'no': score_value = 0.0
             if result.value in ['yes', 'no', 'yes_no_meh']: can_contribute_to_average = True
        elif item.answer_type == AnswerType.BOOLEAN:
            if result.boolean_value is True: score_value = 1.0
            elif result.boolean_value is False: score_value = 0.0
            if result.boolean_value is not None: can_contribute_to_average = True
        
        if result.status == ChecklistItemStatus.OK and can_contribute_to_average and score_value is not None:
            valid_scores.append(score_value)
            item_count_for_average +=1
        elif result.status == ChecklistItemStatus.NOT_OK and can_contribute_to_average:
            valid_scores.append(0.0)
            item_count_for_average +=1
            # not_ok_count +=1
        elif can_contribute_to_average:
            # Если пункт должен был дать оценку (can_contribute_to_average == True),
            # но не попал в предыдущие условия (например, статус ОК, но score_value is None, что маловероятно для этих типов,
            # или статус не ОК, но мы все равно хотим его учесть в знаменателе),
            # можно добавить его в item_count_for_average, чтобы понизить средний балл.
            # Однако, текущая логика уже покрывает основные случаи.
            # Если нужно строго учитывать все "оцениваемые" пункты в знаменателе,
            # независимо от их фактического вклада в valid_scores, то item_count_for_average
            # должен инкрементироваться просто по факту can_contribute_to_average == True.
            # Пока оставим как есть, т.к. для NOT_OK мы уже добавляем 0 и инкрементируем.
            pass # Добавлен pass для корректного отступа

    if not item_count_for_average:
        average_score = None
    else:
        average_score = sum(valid_scores) / item_count_for_average

    final_score = round(average_score * 100, 2) if average_score is not None else None

    return final_score