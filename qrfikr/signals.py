# qrfikr/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
import logging

from .models import QRCodeLink, Review
from .tasks import generate_qr_image_task # Celery task
from .services.review_task_service import create_task_from_review_if_needed

logger = logging.getLogger(__name__)

@receiver(post_save, sender=QRCodeLink)
def handle_qr_code_link_save(sender, instance: QRCodeLink, created: bool, update_fields=None, **kwargs):
    should_generate = False
    reason = ""

    if instance.is_active:
        if created:
            should_generate = True
            reason = "created"
        elif not instance.qr_image:
            should_generate = True
            reason = "no_image_exists"
        elif update_fields and 'location' in update_fields: # If location FK changes
            should_generate = True
            reason = "location_changed"
        # Could also check if the feedback URL content has changed if more complex logic depends on location details
        # For now, generating on create, if no image, or if location changes seems reasonable.

    elif not instance.is_active and instance.qr_image:
        # If link becomes inactive, delete the QR image file
        try:
            instance.qr_image.delete(save=False) # Delete file, model save will happen if this signal is part of a larger save
            logger.info(f"Deleted QR image for inactive QRCodeLink {instance.id}.")
            # If this signal handler is the *only* thing saving after this, you might need:
            # instance.save(update_fields=['qr_image', 'updated_at'])
        except Exception as e:
            logger.error(f"Error deleting QR image for inactive link {instance.id}: {e}")


    if should_generate:
        logger.info(f"QRCodeLink {instance.id} ({reason}), scheduling QR image generation.")
        try:
            # Using .si() for immutable signature if arguments might change before task execution
            generate_qr_image_task.si(str(instance.id)).apply_async()
            # generate_qr_image_task.delay(str(instance.id)) # Alternative
        except Exception as e:
            logger.error(f"Failed to schedule Celery task for QRCodeLink {instance.id}. Error: {e}. "
                         "Attempting synchronous QR generation as fallback (NOT RECOMMENDED FOR PRODUCTION).")
            try:
                instance.generate_and_save_qr_image(force_regeneration=True)
                instance.save(update_fields=['qr_image', 'updated_at']) # Ensure the model is saved after sync generation
                logger.info(f"Synchronously generated and saved QR for QRCodeLink {instance.id} as fallback.")
            except Exception as sync_e:
                logger.error(f"Synchronous QR generation also failed for QRCodeLink {instance.id}: {sync_e}")

@receiver(post_save, sender=Review)
def handle_new_review(sender, instance: Review, created: bool, **kwargs):
    if created:
        logger.info(f"New review (ID: {instance.id}) received. Rating: {instance.rating}. Processing for task creation.")
        create_task_from_review_if_needed(instance)