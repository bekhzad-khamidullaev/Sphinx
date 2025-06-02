# qrfikr/models/review.py
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from phonenumber_field.modelfields import PhoneNumberField # Optional

from .qr_code import QRCodeLink
import logging

logger = logging.getLogger(__name__)

# Ensure tasks.Task can be imported
try:
    from tasks.models import Task
except ImportError:
    logger.warning("qrfikr.models.review: tasks.models.Task could not be imported. Using a dummy model.")
    class Task(models.Model):
        title = models.CharField(max_length=100)
        task_number = models.CharField(max_length=20, blank=True)
        class Meta:
            abstract = True
            managed = False
        def __str__(self): return self.title


class Review(models.Model):
    RATING_CHOICES = [
        (1, _('1 - Very Bad')),
        (2, _('2 - Bad')),
        (3, _('3 - Neutral')),
        (4, _('4 - Good')),
        (5, _('5 - Excellent')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code_link = models.ForeignKey(
        QRCodeLink,
        on_delete=models.CASCADE,
        related_name='reviews',
        verbose_name=_("QR Code Link")
    )
    rating = models.PositiveSmallIntegerField(
        choices=RATING_CHOICES,
        verbose_name=_("Rating"),
        db_index=True
    )
    text = models.TextField(
        blank=True,
        verbose_name=_("Review Text")
    )
    photo = models.ImageField(
        upload_to='review_photos/%Y/%m/%d/', # Added year/month/day subdirectories
        blank=True, null=True,
        verbose_name=_("Photo")
    )
    contact_info = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Contact Information (Phone/Email)"),
        help_text=_("Optional, if you want us to contact you.")
    )
    # Example using django-phonenumber-field
    # contact_phone = PhoneNumberField(blank=True, null=True, verbose_name=_("Contact Phone"))
    
    submitted_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Submitted At"), db_index=True)
    related_task = models.ForeignKey(
        Task,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='feedback_reviews',
        verbose_name=_("Related Task")
    )
    user_agent = models.TextField(blank=True, verbose_name=_("User Agent"))
    ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name=_("IP Address"))

    class Meta:
        verbose_name = _("Review")
        verbose_name_plural = _("Reviews")
        ordering = ['-submitted_at']

    def __str__(self):
        location_name_str = _("Unknown Location")
        if hasattr(self.qr_code_link, 'location') and self.qr_code_link.location:
            location_name_str = self.qr_code_link.location.name
        return f"Review for {location_name_str} - Rating: {self.get_rating_display()}"

    @property
    def location(self):
        return self.qr_code_link.location if self.qr_code_link else None