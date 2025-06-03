import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.urls import reverse
from django.core.files.base import ContentFile
import io
import logging

logger = logging.getLogger(__name__)

try:
    from checklists.models import Location
except ImportError:
    logger.warning("qrfikr.models.qr_code: checklists.models.Location could not be imported. Using a dummy model.")
    class Location(models.Model):
        name = models.CharField(max_length=100)
        project = None
        supervisor = None
        class Meta:
            abstract = True
            managed = False
        def __str__(self): return self.name
        @property
        def default_project_for_issues(self):
            if hasattr(self, 'project') and self.project:
                return self.project
            return None
        @property
        def responsible_user(self):
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
        upload_to='qr_codes/%Y/%m/%d/',
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
        if hasattr(self, 'location') and self.location:
            return f"QR for {self.location.name}"
        return f"QR Link {self.id.hex[:8]}"


    def get_feedback_url(self):
        return reverse('qrfikr:submit_review_page', kwargs={'qr_uuid': str(self.id)})


    def get_admin_url(self):
        return reverse('admin:qrfikr_qrcodelink_change', args=[self.id])


    def generate_and_save_qr_image(self, force_regeneration=False):
        from qrfikr.utils import generate_qr_code_image
        
        if not self.is_active and not force_regeneration:
            logger.info(f"QR Link {self.id} is not active and regeneration not forced. Skipping QR generation.")
            if self.qr_image:
                self.qr_image.delete(save=False)
            return None

        base_url = getattr(settings, 'SITE_URL', 'http://localhost:8000').strip('/')
        feedback_url = base_url + self.get_feedback_url()
        
        buffer = io.BytesIO()
        try:
            img = generate_qr_code_image(feedback_url)
            img.save(buffer, format='PNG')
        except Exception as e:
            logger.error(f"Error generating QR image PIL object for {self.id}: {e}")
            return None
        
        file_name = f'qr_{self.id.hex}.png'

        self.qr_image.save(file_name, ContentFile(buffer.getvalue()), save=False)
        logger.info(f"QR image generated for QRCodeLink {self.id}, path: {self.qr_image.name if self.qr_image else 'N/A'}")
        return self.qr_image.url if self.qr_image else None