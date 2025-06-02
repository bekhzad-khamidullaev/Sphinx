# qrfikr/tasks.py (Celery tasks)
from celery import shared_task
import logging
import os # For potential old file deletion
from django.conf import settings

from .models import QRCodeLink

logger = logging.getLogger(__name__)

@shared_task(name="qrfikr.generate_qr_image_for_link", bind=True, max_retries=3, default_retry_delay=60)
def generate_qr_image_task(self, qr_code_link_id):
    try:
        qr_link = QRCodeLink.objects.get(id=qr_code_link_id)
        
        old_image_path = None
        if qr_link.qr_image:
            try:
                old_image_path = qr_link.qr_image.path
            except ValueError: # Handles cases where file might not exist on disk
                logger.warning(f"Could not get path for existing QR image of {qr_link.id}, it might be missing from storage.")


        # generate_and_save_qr_image now takes force_regeneration
        # It handles saving internally but save=False to allow caller (signal) to save the model instance
        qr_link.generate_and_save_qr_image(force_regeneration=True)
        qr_link.save(update_fields=['qr_image', 'updated_at']) # Save the QRCodeLink model instance itself
        
        logger.info(f"Successfully generated and saved QR image for QRCodeLink ID: {qr_code_link_id}. New path: {qr_link.qr_image.path if qr_link.qr_image else 'N/A'}")
        
        # Delete old physical file if the path has changed AND the old file existed
        # Django's FileField.save() usually handles this by overwriting or creating a new unique name.
        # Explicit deletion is generally only needed if you are manually managing file paths
        # and want to ensure old, unreferenced files are cleaned up.
        # Given QRCodeLink.generate_and_save_qr_image() uses qr_link.id.hex in filename,
        # it should overwrite.
        # if old_image_path and qr_link.qr_image and old_image_path != qr_link.qr_image.path:
        #     if os.path.exists(old_image_path):
        #         try:
        #             os.remove(old_image_path)
        #             logger.info(f"Deleted old QR image at {old_image_path}")
        #         except OSError as e:
        #             logger.error(f"Error deleting old QR image {old_image_path}: {e}")

    except QRCodeLink.DoesNotExist:
        logger.error(f"QRCodeLink with ID {qr_code_link_id} not found for QR image generation.")
    except Exception as e:
        logger.exception(f"Error in generate_qr_image_task for QRCodeLink ID {qr_code_link_id}: {e}")
        try:
            self.retry(exc=e)
        except self.MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for generating QR for {qr_code_link_id}.")
