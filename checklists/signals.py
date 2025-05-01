from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
import logging

from .models import Checklist, ChecklistResult, ChecklistTemplateItem, ChecklistRunStatus, ChecklistItemStatus
from .utils import calculate_checklist_score # Import the utility function

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Checklist)
def create_checklist_results(sender, instance, created, **kwargs):
    """
    Signal to create ChecklistResult objects when a new Checklist is created.
    """
    if created:
        logger.debug(f"Post-save signal: Creating initial results for checklist run {instance.id}")
        # Get template items, ordered by section and order
        template_items = ChecklistTemplateItem.objects.filter(template=instance.template).order_by('section__order', 'order')

        results_to_create = []
        for item in template_items:
            # Create result object but don't save yet
            result = ChecklistResult(
                checklist_run=instance,
                template_item=item,
                status=ChecklistItemStatus.PENDING, # Initial status is pending
                # Default values are handled during form/view processing, not here on creation
                # Setting default_value on the result model directly might overwrite user input
                # It's better to pre-populate the *form* with the default value when displaying.
                # For now, just create the result object linked to the item.
            )
            results_to_create.append(result)

        # Bulk create results for performance
        if results_to_create:
            ChecklistResult.objects.bulk_create(results_to_create)
            logger.info(f"Created {len(results_to_create)} initial results for checklist run {instance.id}")
        else:
             logger.warning(f"No template items found for checklist run {instance.id} based on template {instance.template.id}. No results created.")

# The score calculation signal needs refinement. Calculating on every save
# might be inefficient or lead to partial scores.
# A better approach is to calculate the score explicitly when the checklist
# status becomes SUBMITTED or APPROVED. This is handled in the `save` method
# of the `ChecklistStatusUpdateForm` or the view logic.

# Let's remove the auto score calculation signal here and rely on explicit calculation
# when the checklist is finalized (submitted/approved).


# Example of a signal that might update completion_time if status changes,
# but this is also handled in the form/model methods now.
# @receiver(post_save, sender=Checklist)
# def update_checklist_completion(sender, instance, created, **kwargs):
#     if not created and instance.status == ChecklistRunStatus.SUBMITTED and instance.completion_time is None:
#          instance.completion_time = timezone.now()
#          instance.save(update_fields=['completion_time'])
#          logger.info(f"Set completion_time for checklist run {instance.id} on status change to SUBMITTED")