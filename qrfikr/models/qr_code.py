import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.urls import reverse
from django.core.files.base import ContentFile
import io
import logging

logger = logging.getLogger(__name__)

# Ensure checklists.Location can be imported
try:
    from checklists.models import Location
except ImportError:
    logger.warning("qrfikr.models.qr_code: checklists.models.Location could not be imported. Using a dummy model.")
    class Location(models.Model):
        name = models.CharField(max_length=100)
        # Add other essential fields if your dummy needs them for related operations
        # For example, if properties like default_project_for_issues are accessed
        project = None # Placeholder for default_project_for_issues
        supervisor = None # Placeholder for responsible_user

        class Meta:
            abstract = True
            managed = False # Important for dummy models
        def __str__(self): return self.name

        @property
        def default_project_for_issues(self):
            # Dummy implementation
            if hasattr(self, 'project') and self.project:
                return self.project
            return None

        @property
        def responsible_user(self):
            # Dummy implementation
            if hasattr(self, 'supervisor') and self.supervisor:
                return self.supervisor
            return None


class QRCodeLink(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.OneToOneField(
        Location,
        on_delete=models.CASCADE,
        verbose_name=_("Location"),
        related_name="qr_feedback_link"
    )
    qr_image = models.ImageField(
        upload_to='qr_codes/%Y/%m/%d/', # Added year/month/day subdirectories
        blank=True, null=True,
        verbose_name=_("QR Code Image")
    )
    short_description = models.CharField(
        max_length=100, blank=True,
        verbose_name=_("Short Description for QR page"),
        help_text=_("E.g., 'Feedback for Main Entrance' or 'Restroom A1'")
    )
    is_active = models.BooleanField(default=True, verbose_name=_("Active"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated At"))

    class Meta:
        verbose_name = _("QR Code Link")
        verbose_name_plural = _("QR Code Links")
        ordering = ['location__name']

    def __str__(self):
        if hasattr(self, 'location') and self.location: # Check if location is loaded
            return f"QR for {self.location.name}"
        return f"QR Link {self.id.hex[:8]}"


    def get_feedback_url(self):
        # Ensure this route name matches the one in qrfikr/urls.py
        return reverse('qrfikr:submit_review_page', kwargs={'qr_uuid': str(self.id)})


    def get_admin_url(self):
        return reverse('admin:qrfikr_qrcodelink_change', args=[self.id])


    def generate_and_save_qr_image(self, force_regeneration=False):
        from qrfikr.utils import generate_qr_code_image # Local import
        
        if not self.is_active and not force_regeneration:
            logger.info(f"QR Link {self.id} is not active and regeneration not forced. Skipping QR generation.")
            if self.qr_image: # Delete image if link becomes inactive
                self.qr_image.delete(save=False) # save=False, will be saved by caller or signal
            return None

        # Construct full URL for the QR code
        # Ensure SITE_URL is set in settings.py (e.g., 'http://localhost:8000')
        base_url = getattr(settings, 'SITE_URL', 'http://localhost:8000').strip('/')
        feedback_url = base_url + self.get_feedback_url()
        
        buffer = io.BytesIO()
        try:
            img = generate_qr_code_image(feedback_url)
            img.save(buffer, format='PNG')
        except Exception as e:
            logger.error(f"Error generating QR image PIL object for {self.id}: {e}")
            return None
        
        file_name = f'qr_{self.id.hex}.png' # Use hex for a cleaner filename
        
        # Save the image. Django's ImageField will handle overwriting or unique naming if needed.
        # If a file with the same name exists, Django typically appends a suffix.
        self.qr_image.save(file_name, ContentFile(buffer.getvalue()), save=False) # save=False, will be saved by caller
        logger.info(f"QR image generated for QRCodeLink {self.id}, path: {self.qr_image.name if self.qr_image else 'N/A'}")
        return self.qr_image.url if self.qr_image else None