# checklists/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
import logging

from .models import Checklist, ChecklistResult, ChecklistTemplateItem, ChecklistItemStatus, AnswerType

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Checklist)
def create_checklist_results(sender, instance, created, **kwargs):
    if created:
        logger.debug(f"Post-save signal: Creating initial results for checklist run {instance.id}")
        template_items_qs = ChecklistTemplateItem.objects.filter(template=instance.template).select_related('section').order_by('section__order', 'order')

        results_to_create = []
        for item in template_items_qs:
            result = ChecklistResult(
                checklist_run=instance,
                template_item=item,
                status=ChecklistItemStatus.PENDING,
            )
            
            # Pre-fill value from template_item.default_value if applicable
            # This logic is complex due to various AnswerTypes and should be tested carefully.
            # It's often better to handle default population in the form's initial data.
            # However, if runs can be created programmatically without forms, this might be useful.
            if item.default_value:
                try:
                    if item.answer_type == AnswerType.TEXT:
                        result.value = item.default_value
                    elif item.answer_type == AnswerType.NUMBER:
                        result.numeric_value = float(item.default_value)
                    elif item.answer_type in [AnswerType.SCALE_1_4, AnswerType.SCALE_1_5]:
                        result.numeric_value = float(item.default_value) # Assuming default is numeric
                    elif item.answer_type in [AnswerType.YES_NO, AnswerType.YES_NO_MEH]:
                        result.value = item.default_value # Expects 'yes', 'no', 'yes_no_meh'
                    elif item.answer_type == AnswerType.BOOLEAN:
                        if item.default_value.lower() in ['true', 'yes', '1', 'ok']:
                            result.boolean_value = True
                        elif item.default_value.lower() in ['false', 'no', '0']:
                            result.boolean_value = False
                    elif item.answer_type == AnswerType.DATE:
                        # Add date parsing if default_value is string
                        pass # Requires robust date parsing
                    elif item.answer_type == AnswerType.URL:
                        result.media_url = item.default_value
                    # Other types (DATETIME, TIME, FILE) are harder to default here
                except (ValueError, TypeError) as e:
                    logger.warning(f"Could not apply default value '{item.default_value}' for item '{item.id}' (type: {item.answer_type}): {e}")
            
            results_to_create.append(result)

        if results_to_create:
            ChecklistResult.objects.bulk_create(results_to_create)
            logger.info(f"Created {len(results_to_create)} initial results for checklist run {instance.id}")
        else:
             logger.warning(f"No template items found for checklist run {instance.id} based on template {instance.template.id}. No results created.")
